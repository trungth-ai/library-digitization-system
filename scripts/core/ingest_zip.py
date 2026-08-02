#!/usr/bin/env python3
"""
Nạp tài liệu từ tệp ZIP (YC-BU-07 — sprint V5).

BỐI CẢNH THỰC TẾ: cán bộ số hóa thường có sẵn cả thư mục đã quét, nén lại rồi gửi. Bắt họ chọn từng
tệp trên trình duyệt cho 300 tài liệu là công việc vô ích và dễ sót.

🔴 AN TOÀN LÀ PHẦN QUAN TRỌNG NHẤT Ở ĐÂY. Ba rủi ro của việc giải nén tệp do người dùng cung cấp:

  1. **zip-slip** — mục tên `../../etc/passwd` ghi đè tệp hệ thống. Chặn bằng
     `file_check.safe_extract_path` (đã có bộ kiểm thử riêng, KT-BM-20).
  2. **zip bomb** — tệp nén 1 MB giải nén thành 10 GB, làm đầy đĩa. Chặn bằng trần tổng dung lượng
     giải nén và trần tỉ lệ nén, kiểm TRƯỚC khi ghi byte nào.
  3. **quá nhiều mục** — hàng trăm nghìn tệp rỗng làm treo tiến trình. Chặn bằng trần số mục.

Cả ba đều kiểm trên **siêu dữ liệu của ZIP** trước khi giải nén, chứ không phải phát hiện giữa chừng.
"""

import logging
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scripts.core import file_check

logger = logging.getLogger("core.ingest_zip")

# Trần tổng dung lượng SAU giải nén — chống zip bomb
MAX_UNCOMPRESSED_MB = int(os.getenv("ZIP_MAX_UNCOMPRESSED_MB", "5000"))
# Trần số mục trong một tệp ZIP
MAX_ENTRIES = int(os.getenv("ZIP_MAX_ENTRIES", "1000"))
# Tỉ lệ nén tối đa cho phép. PDF vốn đã nén nên tỉ lệ thật thường dưới 5; trên 100 gần như chắc chắn
# là zip bomb chứ không phải tài liệu.
MAX_COMPRESSION_RATIO = int(os.getenv("ZIP_MAX_RATIO", "100"))


@dataclass
class ZipEntry:
    """Một tệp PDF hợp lệ trong ZIP, đã giải nén ra đĩa."""
    filename: str          # tên gốc (không kèm đường dẫn) — dùng làm tên tài liệu
    path: Path             # nơi đã giải nén
    size: int
    folder: str = ""       # thư mục cha trong ZIP — gợi ý bộ sưu tập


@dataclass
class ZipResult:
    entries: List[ZipEntry] = field(default_factory=list)
    skipped: List[Dict] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def inspect(zip_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Kiểm ZIP trên SIÊU DỮ LIỆU trước khi giải nén. Trả `(hợp_lệ, lý_do_tiếng_Việt)`.

    Kiểm trước là điểm mấu chốt: phát hiện zip bomb sau khi đã ghi 10 GB xuống đĩa thì đĩa đã đầy rồi.
    """
    try:
        with zipfile.ZipFile(zip_path) as archive:
            infos = archive.infolist()

            if len(infos) > MAX_ENTRIES:
                return False, (f"Tệp nén chứa {len(infos)} mục, vượt giới hạn {MAX_ENTRIES}. "
                               f"Vui lòng chia thành nhiều tệp nén nhỏ hơn")

            total_uncompressed = sum(info.file_size for info in infos)
            total_compressed = sum(info.compress_size for info in infos) or 1

            if total_uncompressed > MAX_UNCOMPRESSED_MB * 1024 * 1024:
                return False, (f"Sau khi giải nén sẽ chiếm {total_uncompressed / 1024 / 1024:.0f} MB, "
                               f"vượt giới hạn {MAX_UNCOMPRESSED_MB} MB")

            ratio = total_uncompressed / total_compressed
            if ratio > MAX_COMPRESSION_RATIO:
                logger.warning("Từ chối tệp nén có tỉ lệ nén bất thường: %.0f lần", ratio)
                return False, ("Tệp nén có tỉ lệ nén bất thường — bị từ chối vì lý do an toàn. "
                               "Nếu đây là tài liệu hợp lệ, vui lòng nén lại bằng công cụ khác")

    except zipfile.BadZipFile:
        return False, "Tệp nén hỏng hoặc không phải định dạng ZIP"
    except Exception as e:  # noqa: BLE001
        return False, f"Không đọc được tệp nén: {e}"

    return True, None


def extract_pdfs(zip_path: Path, dest_dir: Path) -> ZipResult:
    """
    Giải nén các tệp PDF trong ZIP ra `dest_dir`. Bỏ qua mục không hợp lệ, ghi rõ lý do từng mục.

    Giữ tên thư mục cha làm **gợi ý bộ sưu tập**: cán bộ thường nén theo cấu trúc
    `Công văn 2026/Quý 1/*.pdf`, và thông tin đó có ích cho việc phân loại — nhưng chỉ là GỢI Ý,
    con người vẫn quyết định (nguyên tắc SRS).
    """
    result = ZipResult()

    hop_le, ly_do = inspect(zip_path)
    if not hop_le:
        result.error = ly_do
        return result

    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue

                # 🔴 Chống zip-slip (KT-BM-20) — kiểm ĐƯỜNG DẪN ĐẦY ĐỦ trong tệp nén, TRƯỚC khi
                # cắt lấy tên tệp.
                #
                # VÌ SAO PHẢI KIỂM BẢN ĐẦY ĐỦ: việc chỉ ghi theo tên tệp (bỏ đường dẫn) đã đủ để tệp
                # không thoát ra ngoài — nhưng khi đó một mục `../../etc/passwd.pdf` sẽ được ÂM THẦM
                # chấp nhận dưới tên `passwd.pdf`, và không ai biết vừa nhận một tệp nén có ý đồ.
                # An toàn nhờ tình cờ thì lần sửa mã sau có thể làm mất, và không để lại dấu vết nào.
                if file_check.safe_extract_path(dest_dir, info.filename) is None:
                    logger.warning("Chặn mục ZIP có đường dẫn thoát thư mục: %r", info.filename)
                    result.skipped.append({
                        "filename": info.filename,
                        "ly_do": "Đường dẫn trong tệp nén không an toàn (cố thoát khỏi thư mục đích)",
                        "code": "unsafe_path"})
                    continue

                # Chỉ lấy TÊN tệp: nơi ghi xuống đĩa do ta quyết định, không bao giờ theo đường dẫn
                # trong tệp nén — kể cả khi đường dẫn đó đã qua được kiểm tra ở trên.
                raw_name = Path(info.filename).name
                folder = str(Path(info.filename).parent).replace("\\", "/").strip(".")

                name_check = file_check.check_filename(raw_name)
                if not name_check.ok:
                    result.skipped.append({"filename": info.filename,
                                           "ly_do": name_check.reason, "code": name_check.code})
                    continue

                safe_path = file_check.safe_extract_path(dest_dir, raw_name)
                if safe_path is None:
                    result.skipped.append({"filename": info.filename,
                                           "ly_do": "Tên tệp không an toàn",
                                           "code": "unsafe_path"})
                    continue

                # Tên trùng trong cùng ZIP: thêm hậu tố thay vì ghi đè lặng lẽ
                safe_path = _unique_path(safe_path)

                try:
                    with archive.open(info) as source, safe_path.open("wb") as target:
                        # Chép theo mảnh: một tệp lớn không nên nạp hết vào RAM
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            target.write(chunk)
                except Exception as e:  # noqa: BLE001
                    result.skipped.append({"filename": info.filename,
                                           "ly_do": f"Không giải nén được: {e}",
                                           "code": "extract_failed"})
                    continue

                content_check = file_check.check_pdf_content(safe_path)
                if not content_check.ok:
                    result.skipped.append({"filename": info.filename,
                                           "ly_do": content_check.reason,
                                           "code": content_check.code})
                    safe_path.unlink(missing_ok=True)
                    continue

                result.entries.append(ZipEntry(
                    filename=safe_path.name, path=safe_path,
                    size=safe_path.stat().st_size, folder=folder if folder != "." else "",
                ))

    except Exception as e:  # noqa: BLE001
        result.error = f"Lỗi khi giải nén: {e}"

    logger.info("Giải nén '%s': %d tệp hợp lệ, %d bị bỏ qua",
                zip_path.name, len(result.entries), len(result.skipped))
    return result


def _unique_path(path: Path) -> Path:
    """Thêm hậu tố `_1`, `_2`... nếu tên đã tồn tại — không bao giờ ghi đè lặng lẽ."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for index in range(1, 1000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{stem}_{os.getpid()}{suffix}")
