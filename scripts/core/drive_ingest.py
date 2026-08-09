#!/usr/bin/env python3
"""
Nạp tài liệu tự động từ thư mục Google Drive (YC-BU-21).

QUY TRÌNH THẬT ĐANG THAY THẾ: cán bộ quét tài liệu bằng máy scan → tệp rơi vào một thư mục Drive
dùng chung → hiện phải tải từng tệp về máy rồi tải lại lên hệ thống. Hai lần chuyển tệp thủ công
cho mỗi tài liệu, và không ai nhớ được tệp nào đã nạp.

QUY TRÌNH MỚI, GIỮ NGUYÊN CHỖ CHO CON NGƯỜI:
    quét thư mục → tải về → OCR → đoán loại → trích metadata → **CÁN BỘ DUYỆT + CHỌN BỘ SƯU TẬP**
    → đẩy DSpace

Bước áp chót viết hoa là có chủ đích. Máy làm hết phần cơ bắp, nhưng KHÔNG có tài liệu nào đi lên
DSpace mà không có cán bộ xác nhận — đúng nguyên tắc SRS "con người giữ quyền quyết định". Nguồn
Drive chỉ đặt sẵn GỢI Ý bộ sưu tập; chốt vẫn ở màn hình duyệt.

BA LỚP CHỐNG TRÙNG, vì quét định kỳ nghĩa là thấy lại cùng bộ tệp mãi mãi:
  1. `drive_files.drive_file_id`  — đã xử lý tệp Drive này rồi thì bỏ qua, không cần tải về.
  2. SHA-256 nội dung             — cùng nội dung dưới hai tên tệp khác nhau vẫn là một tài liệu.
  3. Khóa Redis khi quét          — hai worker cùng quét một nguồn sẽ tạo job trùng.
Lớp 1 rẻ nhất nên chặn trước; chỉ tệp qua được lớp 1 mới tốn băng thông tải về.

CHỈ ĐỌC TRÊN DRIVE: không đổi tên, không chuyển thư mục, không xóa. Tài liệu gốc là của Nhà trường.
"""

import logging
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import scripts.db as db
from scripts.core import batches, file_check, gdrive, uploads

logger = logging.getLogger("core.drive_ingest")

# Trần số tệp nạp trong MỘT lượt quét. Thư mục 5000 tệp không được đổ hết vào hàng đợi trong một
# nhịp — lượt quét sau sẽ lấy tiếp. Hàng đợi ngập là cách nhanh nhất làm cả hệ thống trông như chết.
MAX_PER_SCAN = int(os.getenv("DRIVE_MAX_PER_SCAN", "200"))

# Khóa Redis giữ trong bao lâu. Phải dài hơn một lượt quét thật (tải vài trăm tệp) nhưng không quá
# dài, kẻo worker chết giữa chừng thì nguồn bị treo tới hết hạn khóa.
SCAN_LOCK_TTL_SEC = int(os.getenv("DRIVE_SCAN_LOCK_TTL", "1800"))


@dataclass
class ScanResult:
    """Kết quả một lượt quét — số liệu đủ để cán bộ biết chuyện gì đã xảy ra, không chỉ 'xong'."""
    source_id: int
    found: int = 0                                  # số tệp PDF thấy trên Drive
    ingested: int = 0                               # số tệp đã tạo job
    skipped: int = 0                                # bỏ qua có chủ đích (trùng, quá cỡ)
    failed: int = 0                                 # lỗi tải/đưa hàng đợi
    batch_id: Optional[str] = None
    error: Optional[str] = None
    details: List[Dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> Dict:
        return {
            "source_id": self.source_id, "batch_id": self.batch_id,
            "so_thay": self.found, "so_da_nap": self.ingested,
            "so_bo_qua": self.skipped, "so_loi": self.failed,
            "loi": self.error, "chi_tiet": self.details,
        }


# =====================================================================
# KHÓA QUÉT
# =====================================================================

def acquire_scan_lock(redis_client, source_id: int, ttl: int = SCAN_LOCK_TTL_SEC) -> bool:
    """
    Giành quyền quét một nguồn. `False` = worker khác đang quét, lượt này bỏ qua.

    `SET NX EX` là một thao tác nguyên tử phía Redis: kiểm tra rồi mới đặt ở phía client sẽ có khe
    hở giữa hai lệnh, và với nhiều worker cùng đánh thức theo chu kỳ thì khe hở đó gặp thường xuyên
    chứ không hiếm.

    Không có Redis (chạy tay từ dòng lệnh) thì cho phép quét — người gõ lệnh đã biết mình làm gì.
    """
    if redis_client is None:
        return True
    try:
        return bool(redis_client.set(f"drive:scan:{source_id}", "1", nx=True, ex=ttl))
    except Exception as e:  # noqa: BLE001 — Redis hỏng không được làm sập việc quét
        logger.warning("Không đặt được khóa quét Drive (%s) — vẫn quét tiếp", e)
        return True


def release_scan_lock(redis_client, source_id: int) -> None:
    if redis_client is None:
        return
    try:
        redis_client.delete(f"drive:scan:{source_id}")
    except Exception:  # noqa: BLE001
        pass


# =====================================================================
# QUÉT MỘT NGUỒN
# =====================================================================

def scan_source(source: Dict, *, base_dir: Path, enqueue, redis_client=None,
                client: Optional[gdrive.DriveClient] = None,
                max_files: int = MAX_PER_SCAN) -> ScanResult:
    """
    Quét một thư mục Drive và đưa tệp mới vào hàng đợi số hóa.

    `enqueue` được TIÊM VÀO thay vì import từ `scripts.api`: hàm đó gắn với Redis và cấu hình của
    tiến trình API, còn việc quét chạy trong worker. Tiêm vào thì kiểm thử được toàn bộ luồng bằng
    một hàm giả, không cần Redis lẫn PostgreSQL.

    KHÔNG ném lỗi ra ngoài: một nguồn hỏng (thư mục bị gỡ chia sẻ, hết hạn token) không được làm
    dừng việc quét các nguồn còn lại, cũng không được làm chết worker.
    """
    result = ScanResult(source_id=source["id"])

    if not acquire_scan_lock(redis_client, source["id"]):
        result.error = "Một tiến trình khác đang quét nguồn này"
        return result

    try:
        return _scan_inner(source, base_dir=base_dir, enqueue=enqueue,
                           client=client, max_files=max_files, result=result)
    except gdrive.DriveError as e:
        # Lỗi Drive đã có thông điệp tiếng Việt nói rõ phải làm gì — chuyển thẳng cho cán bộ
        logger.error("Quét nguồn Drive #%s thất bại: %s", source["id"], e)
        result.error = str(e)
        return result
    except Exception as e:  # noqa: BLE001
        logger.exception("Lỗi không lường trước khi quét nguồn Drive #%s", source["id"])
        result.error = f"Lỗi không lường trước khi quét: {e}"
        return result
    finally:
        release_scan_lock(redis_client, source["id"])


def _scan_inner(source: Dict, *, base_dir: Path, enqueue, client, max_files: int,
                result: ScanResult) -> ScanResult:
    drive = client or gdrive.client_from_env()

    # Kiểm đĩa TRƯỚC khi tải byte nào: đĩa đầy giữa một mẻ 200 tệp để lại đống tệp dở dang
    disk = file_check.check_disk_space(str(base_dir))
    if not disk.ok:
        result.error = disk.reason
        return result

    da_xu_ly = db.drive_processed_file_ids(source["id"])
    ung_vien = []

    for item in drive.list_pdfs(source["folder_id"]):
        result.found += 1
        if item.id in da_xu_ly:
            continue                    # lớp 1: rẻ nhất, chặn trước khi tốn băng thông
        ung_vien.append(item)
        if len(ung_vien) >= max_files:
            logger.info("Nguồn Drive #%s: dừng ở %d tệp trong lượt này, phần còn lại để lượt sau",
                        source["id"], max_files)
            break

    if not ung_vien:
        logger.info("Nguồn Drive #%s: không có tệp mới (%d tệp trên thư mục)",
                    source["id"], result.found)
        return result

    # Mỗi lượt quét là MỘT LÔ: cán bộ theo dõi được "mẻ Drive sáng nay" như mọi mẻ nạp khác, dùng
    # chung màn hình /lo thay vì phải học một màn hình riêng.
    batch_name = f"Drive: {source['name']} ({len(ung_vien)} tệp)"
    result.batch_id = batches.create_batch(
        name=batch_name, source=batches.SOURCE_DRIVE, created_by=source.get("created_by"),
        priority=source.get("priority") or "low",
    )

    for item in ung_vien:
        _ingest_one(item, source=source, drive=drive, base_dir=base_dir,
                    enqueue=enqueue, batch_id=result.batch_id, result=result)

    batches.bump_counters(result.batch_id, total=result.ingested,
                          skipped=result.skipped + result.failed)
    logger.info("Nguồn Drive #%s: thấy %d, nạp %d, bỏ qua %d, lỗi %d",
                source["id"], result.found, result.ingested, result.skipped, result.failed)
    return result


def _ingest_one(item: gdrive.DriveFile, *, source: Dict, drive, base_dir: Path,
                enqueue, batch_id: str, result: ScanResult) -> None:
    """
    Tải một tệp về rồi đưa vào hàng đợi. Mọi nhánh kết thúc đều GHI SỔ `drive_files`.

    Ghi sổ cả trường hợp bỏ qua và lỗi, không chỉ trường hợp thành công: nếu chỉ ghi khi thành công
    thì lượt quét sau sẽ tải lại đúng những tệp vừa hỏng, mãi mãi, và cán bộ không bao giờ thấy
    danh sách "tệp nào không nạp được và vì sao".
    """
    def ghi_so(status: str, note: str, job_id: Optional[str] = None) -> None:
        db.record_drive_file(
            source_id=source["id"], drive_file_id=item.id, filename=item.name,
            size_bytes=item.size_bytes, drive_md5=item.md5,
            modified_time=item.modified_time or None, job_id=job_id,
            status=status, note=note,
        )

    ten_hop_le = file_check.check_filename(item.name or "")
    if not ten_hop_le.ok:
        result.skipped += 1
        result.details.append({"filename": item.name, "ly_do": ten_hop_le.reason})
        ghi_so("skipped", ten_hop_le.reason)
        return

    job_id = str(uuid.uuid4())
    job_dir = base_dir / job_id
    input_dir, output_dir = job_dir / "input", job_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    dich = input_dir / item.name

    try:
        size = drive.download(item.id, dich)
    except gdrive.DriveError as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        result.failed += 1
        result.details.append({"filename": item.name, "ly_do": str(e)})
        # 'failed' chứ không phải 'skipped': lỗi tải thường là tạm thời (mạng, giới hạn tần suất),
        # cán bộ bấm quét lại là được — nhưng phải THẤY nó trong danh sách lỗi trước đã.
        ghi_so("failed", str(e))
        return

    # Tệp Drive khai là PDF không có nghĩa nội dung là PDF thật — kiểm bằng nội dung như đường tải lên
    noi_dung = file_check.check_pdf_content(dich, expected_size=size)
    if not noi_dung.ok:
        shutil.rmtree(job_dir, ignore_errors=True)
        result.skipped += 1
        result.details.append({"filename": item.name, "ly_do": noi_dung.reason})
        ghi_so("skipped", noi_dung.reason)
        return

    # Lớp 2: cùng nội dung dưới tên khác vẫn là một tài liệu
    file_hash = uploads.hash_file(dich)
    dedup_mode = os.getenv("DEDUP_MODE", batches.DEDUP_SKIP).strip().lower()
    if dedup_mode != batches.DEDUP_REPROCESS:
        da_co = batches.find_by_hash(file_hash)
        if da_co:
            shutil.rmtree(job_dir, ignore_errors=True)
            ly_do = f"Trùng nội dung với tài liệu đã có: '{da_co['filename']}'"
            result.skipped += 1
            result.details.append({"filename": item.name, "ly_do": ly_do})
            ghi_so("skipped", ly_do)
            return

    payload = {
        "job_id": job_id, "filename": item.name,
        "input_file": str(dich), "output_dir": str(output_dir),
        # Bộ sưu tập ở đây mới là GỢI Ý cấu hình sẵn — cán bộ vẫn chốt ở màn hình duyệt trước
        # khi đẩy lên DSpace (YC-RV-04).
        "collection_id": source.get("collection_id") or "",
        "language": source.get("language") or "vie",
        # 'auto' = worker đoán loại theo nội dung sau khi OCR (YC-SC-09)
        "document_type": source.get("document_type") or "auto",
        "file_hash": file_hash, "file_size": size, "batch_id": batch_id,
        "drive_file_id": item.id,
    }

    try:
        enqueue(job_id, item.name, payload, priority=source.get("priority") or "low")
        db.set_document_batch_info(job_id, batch_id=batch_id, file_hash=file_hash,
                                   file_size=size, uploaded_by=source.get("created_by"),
                                   priority=source.get("priority") or "low")
    except Exception as e:  # noqa: BLE001
        logger.exception("Không đưa được '%s' vào hàng đợi", item.name)
        shutil.rmtree(job_dir, ignore_errors=True)
        result.failed += 1
        result.details.append({"filename": item.name, "ly_do": "Không đưa được vào hàng đợi"})
        ghi_so("failed", f"Không đưa được vào hàng đợi: {e}")
        return

    result.ingested += 1
    ghi_so("ingested", "", job_id=job_id)


# =====================================================================
# QUÉT MỌI NGUỒN ĐẾN HẠN
# =====================================================================

def scan_due_sources(*, base_dir: Path, enqueue, redis_client=None,
                     client: Optional[gdrive.DriveClient] = None) -> List[ScanResult]:
    """
    Quét mọi nguồn đang bật và đã tới hạn. Gọi từ vòng bảo trì của worker.

    Ghi kết quả từng lượt vào `drive_sources.last_scan_*` — cán bộ mở màn hình nguồn là thấy ngay
    lần quét gần nhất lúc nào, được bao nhiêu tệp, hỏng vì sao. Một tính năng nền mà không nói được
    lần chạy gần nhất ra sao thì không ai dám tin nó đang chạy.
    """
    ket_qua: List[ScanResult] = []

    try:
        sources = db.list_due_drive_sources()
    except Exception as e:  # noqa: BLE001 — DB chưa chạy migration 011 thì im lặng bỏ qua
        logger.debug("Chưa quét được nguồn Drive: %s", e)
        return ket_qua

    for source in sources:
        result = scan_source(source, base_dir=base_dir, enqueue=enqueue,
                             redis_client=redis_client, client=client)
        ket_qua.append(result)
        try:
            db.update_drive_scan_result(
                source["id"], status="ok" if result.ok else "error",
                message=result.error or "", found=result.found, ingested=result.ingested,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Không ghi được kết quả quét nguồn Drive #%s", source["id"])

    return ket_qua
