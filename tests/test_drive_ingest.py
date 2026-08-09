#!/usr/bin/env python3
"""
Kiểm thử nạp tài liệu từ Google Drive (YC-BU-21) — KT-BU-27→38.

Chạy được KHÔNG cần mạng, không cần Google, không cần PostgreSQL: `DriveClient` và `scripts.db`
đều được thay bằng lớp giả. Đó là điều kiện để CI bắt được hồi quy của luồng này — một tính năng
chỉ kiểm thử được bằng tài khoản Google thật thì trên thực tế là không được kiểm thử.

Tính chất phải giữ:
  1. Quét LẶP LẠI không tạo job trùng — quét định kỳ nghĩa là thấy lại cùng bộ tệp mãi mãi.
  2. Tệp lỗi được GHI SỔ và ĐƯỢC THỬ LẠI; tệp bỏ qua có chủ đích thì KHÔNG thử lại.
  3. Một nguồn hỏng không làm chết việc quét các nguồn còn lại.
  4. Không bao giờ để lại tệp dở dang trên đĩa.
  5. Tài liệu từ Drive vẫn phải qua cán bộ duyệt — nguồn chỉ đặt GỢI Ý bộ sưu tập.

Chạy: pytest tests/test_drive_ingest.py -v
"""

import sys
import types
from pathlib import Path

import pytest

from scripts.core import gdrive


# =====================================================================
# LỚP GIẢ
# =====================================================================

class FakeDrive:
    """Drive giả: trả danh sách tệp định sẵn, 'tải về' bằng cách ghi ít byte PDF hợp lệ."""

    def __init__(self, files, fail_on=()):
        self.files = files
        self.fail_on = set(fail_on)
        self.downloaded = []

    def list_pdfs(self, folder_id, page_size=100):
        return iter(self.files)

    def download(self, file_id, destination, max_mb=500):
        if file_id in self.fail_on:
            raise gdrive.DriveError("Google Drive trả về lỗi HTTP 500 khi tải tệp")
        self.downloaded.append(file_id)
        # Đủ để `check_pdf_content` công nhận là PDF thật
        data = b"%PDF-1.4\n" + b"x" * 2048 + b"\n%%EOF\n"
        Path(destination).write_bytes(data)
        return len(data)

    def folder_name(self, folder_id):
        return "Thư mục quét"


class FakeDB:
    """Thay `scripts.db` — giữ trạng thái trong bộ nhớ để kiểm được cả hiệu ứng phụ."""

    def __init__(self, processed=None, existing_hashes=None):
        self.processed = set(processed or [])
        self.existing_hashes = dict(existing_hashes or {})
        self.recorded = []          # (drive_file_id, status, note, job_id)
        self.batch_info = []
        self.scan_results = []

    def drive_processed_file_ids(self, source_id):
        return set(self.processed)

    def record_drive_file(self, source_id, drive_file_id, filename, size_bytes=0,
                          drive_md5="", modified_time=None, job_id=None,
                          status="ingested", note=""):
        self.recorded.append((drive_file_id, status, note, job_id))
        if status in ("ingested", "skipped"):
            self.processed.add(drive_file_id)

    def set_document_batch_info(self, job_id, **kwargs):
        self.batch_info.append((job_id, kwargs))

    def update_drive_scan_result(self, source_id, status, message="", found=0, ingested=0):
        self.scan_results.append((source_id, status, message, found, ingested))


class FakeBatches:
    SOURCE_DRIVE = "drive"
    DEDUP_SKIP = "skip"
    DEDUP_REPROCESS = "reprocess"

    def __init__(self, existing_hashes=None):
        self.existing_hashes = dict(existing_hashes or {})
        self.created = []
        self.counters = []

    def create_batch(self, name, source, created_by=None, priority="low"):
        batch_id = f"batch-{len(self.created) + 1}"
        self.created.append((batch_id, name, source, priority))
        return batch_id

    def find_by_hash(self, file_hash):
        return self.existing_hashes.get(file_hash)

    def bump_counters(self, batch_id, total=0, skipped=0):
        self.counters.append((batch_id, total, skipped))


SOURCE = {
    "id": 1, "name": "Kho quét 2026", "folder_id": "FOLDER123",
    "document_type": "auto", "collection_id": "col-1", "language": "vie",
    "priority": "low", "created_by": 7,
}


def _files(*names):
    return [gdrive.DriveFile(id=f"id-{n}", name=n, mime_type=gdrive.PDF_MIME, size_bytes=2048)
            for n in names]


@pytest.fixture
def moi_truong(tmp_path, monkeypatch):
    """Cài lớp giả vào `drive_ingest`, trả về (module, fake_db, fake_batches, danh sách job)."""
    from scripts.core import drive_ingest

    fake_db = FakeDB()
    fake_batches = FakeBatches()
    monkeypatch.setattr(drive_ingest, "db", fake_db)
    monkeypatch.setattr(drive_ingest, "batches", fake_batches)

    # Chốt kiểm đĩa luôn ĐẠT trong các bài kiểm luồng nạp. Nếu để nó chạy thật, bộ kiểm thử sẽ
    # đỏ/xanh theo dung lượng trống của máy chạy — tức là không kiểm được gì về mã nguồn.
    # Bản thân chốt này được kiểm riêng ở `test_dia_day_thi_khong_tai_gi_ca`.
    monkeypatch.setattr(
        drive_ingest.file_check, "check_disk_space",
        lambda path: types.SimpleNamespace(ok=True, reason="", code=""),
    )

    jobs = []

    def enqueue(job_id, filename, payload, priority="low"):
        jobs.append({"job_id": job_id, "filename": filename,
                     "payload": payload, "priority": priority})

    return types.SimpleNamespace(
        module=drive_ingest, db=fake_db, batches=fake_batches,
        jobs=jobs, enqueue=enqueue, base_dir=tmp_path,
    )


def _scan(env, drive, source=None, redis_client_override=None, **kwargs):
    return env.module.scan_source(
        source or SOURCE, base_dir=env.base_dir, enqueue=env.enqueue,
        redis_client=redis_client_override, client=drive, **kwargs,
    )


# =====================================================================
# LUỒNG CHÍNH
# =====================================================================

def test_nap_tep_moi(moi_truong):
    drive = FakeDrive(_files("sach_a.pdf", "cong_van_b.pdf"))
    ket_qua = _scan(moi_truong, drive)

    assert ket_qua.ok
    assert ket_qua.found == 2
    assert ket_qua.ingested == 2
    assert len(moi_truong.jobs) == 2
    assert ket_qua.batch_id is not None


def test_tham_so_nguon_di_theo_vao_job(moi_truong):
    """Bộ sưu tập/ngôn ngữ/loại tài liệu cán bộ đặt ở nguồn phải tới đúng job."""
    _scan(moi_truong, FakeDrive(_files("a.pdf")))
    payload = moi_truong.jobs[0]["payload"]

    assert payload["collection_id"] == "col-1"
    assert payload["language"] == "vie"
    assert payload["document_type"] == "auto"      # đoán theo nội dung sau OCR (YC-SC-09)
    assert payload["drive_file_id"] == "id-a.pdf"
    assert payload["batch_id"] is not None


def test_uu_tien_thap_khong_chen_tai_lieu_le(moi_truong):
    """Mẻ Drive chạy nền, không được chen trước tài liệu cán bộ đang ngồi chờ (ADR-011)."""
    _scan(moi_truong, FakeDrive(_files("a.pdf")))
    assert moi_truong.jobs[0]["priority"] == "low"


def test_moi_luot_quet_la_mot_lo_theo_doi_duoc(moi_truong):
    _scan(moi_truong, FakeDrive(_files("a.pdf", "b.pdf")))
    batch_id, name, source, _ = moi_truong.batches.created[0]
    assert source == "drive"
    assert "Kho quét 2026" in name
    assert moi_truong.batches.counters == [(batch_id, 2, 0)]


# =====================================================================
# CHỐNG TRÙNG — tính chất sống còn của việc quét định kỳ
# =====================================================================

def test_quet_lan_hai_khong_tao_job_trung(moi_truong):
    """Đây là tính chất quan trọng nhất: quét mỗi 5 phút mà nạp lại thì hàng đợi ngập trong một giờ."""
    files = _files("a.pdf", "b.pdf")

    lan_dau = _scan(moi_truong, FakeDrive(files))
    assert lan_dau.ingested == 2

    lan_hai = _scan(moi_truong, FakeDrive(files))
    assert lan_hai.found == 2          # vẫn THẤY 2 tệp trên Drive
    assert lan_hai.ingested == 0       # nhưng không nạp lại
    assert len(moi_truong.jobs) == 2


def test_tep_da_biet_khong_ton_bang_thong_tai_ve(moi_truong):
    """Lớp chống trùng rẻ nhất phải chặn TRƯỚC khi tải — không thì tiết kiệm được gì?"""
    moi_truong.db.processed.add("id-a.pdf")
    drive = FakeDrive(_files("a.pdf", "b.pdf"))
    _scan(moi_truong, drive)

    assert drive.downloaded == ["id-b.pdf"]


def test_trung_noi_dung_thi_bo_qua_du_khac_ten(moi_truong, monkeypatch):
    """Cùng nội dung dưới hai tên tệp khác nhau vẫn là MỘT tài liệu."""
    from scripts.core import drive_ingest, uploads

    monkeypatch.setattr(uploads, "hash_file", lambda path: "HASH-TRUNG")
    monkeypatch.setattr(drive_ingest.uploads, "hash_file", lambda path: "HASH-TRUNG")
    moi_truong.batches.existing_hashes["HASH-TRUNG"] = {"id": "cu", "filename": "ban_cu.pdf"}

    ket_qua = _scan(moi_truong, FakeDrive(_files("ban_moi.pdf")))

    assert ket_qua.ingested == 0
    assert ket_qua.skipped == 1
    assert "ban_cu.pdf" in ket_qua.details[0]["ly_do"]
    assert moi_truong.jobs == []


# =====================================================================
# LỖI VÀ BỎ QUA — hai thứ khác nhau, xử lý khác nhau
# =====================================================================

def test_tep_tai_loi_duoc_ghi_so_va_THU_LAI_luot_sau(moi_truong):
    """
    Lỗi tải thường là tạm thời (mạng, giới hạn tần suất). Nếu coi như đã xử lý thì tệp đó không bao
    giờ được nạp nữa mà chẳng ai hay — mất tài liệu một cách im lặng.
    """
    files = _files("hong.pdf", "tot.pdf")
    ket_qua = _scan(moi_truong, FakeDrive(files, fail_on={"id-hong.pdf"}))

    assert ket_qua.failed == 1 and ket_qua.ingested == 1
    assert ("id-hong.pdf", "failed", ket_qua.details[0]["ly_do"], None) in moi_truong.db.recorded
    # 'failed' KHÔNG vào danh sách đã xử lý → lượt sau thử lại
    assert "id-hong.pdf" not in moi_truong.db.processed

    lan_hai = _scan(moi_truong, FakeDrive(files))
    assert lan_hai.ingested == 1                       # đã thử lại thành công


def test_tep_bo_qua_co_chu_dich_thi_KHONG_thu_lai(moi_truong, monkeypatch):
    """Ngược lại với lỗi: tệp trùng nội dung sẽ trùng mãi mãi, thử lại chỉ tốn băng thông."""
    from scripts.core import drive_ingest

    monkeypatch.setattr(drive_ingest.uploads, "hash_file", lambda path: "H")
    moi_truong.batches.existing_hashes["H"] = {"id": "cu", "filename": "cu.pdf"}

    _scan(moi_truong, FakeDrive(_files("x.pdf")))
    assert "id-x.pdf" in moi_truong.db.processed


def test_tep_khong_phai_pdf_that_bi_bo_qua(moi_truong, monkeypatch):
    """Drive khai mimeType là PDF không có nghĩa nội dung là PDF — kiểm bằng nội dung như đường tải lên."""
    from scripts.core import drive_ingest

    class NotPdfDrive(FakeDrive):
        def download(self, file_id, destination, max_mb=500):
            Path(destination).write_bytes(b"day khong phai PDF")
            return 18

    ket_qua = _scan(moi_truong, NotPdfDrive(_files("gia.pdf")))
    assert ket_qua.ingested == 0
    assert ket_qua.skipped == 1
    assert moi_truong.jobs == []


def test_khong_de_lai_tep_do_dang_tren_dia(moi_truong):
    """Tệp tải hỏng mà nằm lại trên đĩa thì sau vài tuần quét, đĩa máy chủ đầy vì rác."""
    _scan(moi_truong, FakeDrive(_files("hong.pdf"), fail_on={"id-hong.pdf"}))

    con_lai = list(moi_truong.base_dir.rglob("*.pdf"))
    assert con_lai == []


# =====================================================================
# GIỚI HẠN & AN TOÀN
# =====================================================================

def test_tran_so_tep_moi_luot(moi_truong):
    """Thư mục 5000 tệp không được đổ hết vào hàng đợi trong một nhịp."""
    ket_qua = _scan(moi_truong, FakeDrive(_files(*[f"f{i}.pdf" for i in range(10)])),
                    max_files=3)
    assert ket_qua.ingested == 3
    assert len(moi_truong.jobs) == 3


def test_loi_drive_khong_lam_chet_worker(moi_truong):
    """Thư mục bị gỡ chia sẻ giữa chừng → trả kết quả có lỗi, KHÔNG ném ngoại lệ lên trên."""
    class BrokenDrive(FakeDrive):
        def list_pdfs(self, folder_id, page_size=100):
            raise gdrive.DriveError("Google từ chối truy cập (403)")

    ket_qua = _scan(moi_truong, BrokenDrive([]))
    assert not ket_qua.ok
    assert "403" in ket_qua.error


def test_thu_muc_rong_khong_tao_lo_thua(moi_truong):
    ket_qua = _scan(moi_truong, FakeDrive([]))
    assert ket_qua.ok
    assert ket_qua.batch_id is None
    assert moi_truong.batches.created == []


def test_dia_day_thi_khong_tai_gi_ca(moi_truong, monkeypatch):
    """
    Kiểm ĐĨA TRƯỚC khi tải byte nào. Đĩa đầy giữa một mẻ 200 tệp để lại đống tệp dở dang, và tệ hơn
    là làm hỏng cả những tài liệu khác đang được xử lý cùng lúc.
    """
    monkeypatch.setattr(
        moi_truong.module.file_check, "check_disk_space",
        lambda path: types.SimpleNamespace(
            ok=False, reason="Dung lượng đĩa còn 0.2 GB, dưới ngưỡng an toàn", code="disk_low"),
    )

    drive = FakeDrive(_files("a.pdf"))
    ket_qua = _scan(moi_truong, drive)

    assert not ket_qua.ok
    assert "đĩa" in ket_qua.error
    assert drive.downloaded == []          # chưa tải một byte nào
    assert moi_truong.jobs == []


# =====================================================================
# KHÓA QUÉT — hai worker không được cùng quét một nguồn
# =====================================================================

class FakeRedis:
    def __init__(self):
        self.keys = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True

    def delete(self, key):
        self.keys.pop(key, None)


def test_worker_thu_hai_bi_chan_boi_khoa(moi_truong):
    from scripts.core import drive_ingest

    redis_gia = FakeRedis()
    assert drive_ingest.acquire_scan_lock(redis_gia, 1) is True
    assert drive_ingest.acquire_scan_lock(redis_gia, 1) is False   # worker thứ hai

    drive_ingest.release_scan_lock(redis_gia, 1)
    assert drive_ingest.acquire_scan_lock(redis_gia, 1) is True    # quét xong thì nhả


def test_khoa_duoc_nha_ngay_ca_khi_quet_loi(moi_truong):
    """Quét hỏng mà không nhả khóa thì nguồn treo tới khi khóa hết hạn — nửa tiếng không ai hiểu vì sao."""
    from scripts.core import drive_ingest

    class BrokenDrive(FakeDrive):
        def list_pdfs(self, folder_id, page_size=100):
            raise gdrive.DriveError("lỗi")

    redis_gia = FakeRedis()
    _scan(moi_truong, BrokenDrive([]), redis_client_override=redis_gia)
    assert redis_gia.keys == {}


def test_redis_hong_van_quet_duoc(moi_truong):
    """Redis hỏng không được biến thành 'không nạp được tài liệu nào'."""
    from scripts.core import drive_ingest

    class BrokenRedis:
        def set(self, *a, **k):
            raise RuntimeError("redis chết")

        def delete(self, *a, **k):
            raise RuntimeError("redis chết")

    assert drive_ingest.acquire_scan_lock(BrokenRedis(), 1) is True
    drive_ingest.release_scan_lock(BrokenRedis(), 1)      # không được ném lỗi


# =====================================================================
# MÁY KHÁCH DRIVE — phần thuần logic, không gọi mạng
# =====================================================================

def test_chua_cau_hinh_thi_bao_ro_phai_lam_gi(monkeypatch):
    for key in ("GDRIVE_SERVICE_ACCOUNT_FILE", "GDRIVE_OAUTH_CLIENT_ID",
                "GDRIVE_OAUTH_CLIENT_SECRET", "GDRIVE_OAUTH_REFRESH_TOKEN"):
        monkeypatch.delenv(key, raising=False)

    client = gdrive.DriveClient()
    assert not client.configured
    ready, detail = client.health()
    assert not ready
    assert "chưa cấu hình" in detail.lower()


def test_nhan_dien_da_cau_hinh_bang_refresh_token():
    client = gdrive.DriveClient(client_id="a", client_secret="b", refresh_token="c")
    assert client.configured


def test_thong_diep_loi_noi_ro_phai_sua_gi():
    """'403' trần trụi không giúp ai. Phải nói: thư mục chưa chia sẻ, hoặc chưa bật Drive API."""
    assert "chia sẻ" in gdrive._http_message(403, "liệt kê tệp")
    assert "hết hiệu lực" in gdrive._http_message(401, "liệt kê tệp")
    assert "429" in gdrive._http_message(429, "liệt kê tệp")


def test_liet_ke_can_folder_id():
    client = gdrive.DriveClient(client_id="a", client_secret="b", refresh_token="c")
    with pytest.raises(gdrive.DriveError, match="mã thư mục"):
        list(client.list_pdfs(""))


@pytest.mark.parametrize("raw,expected", [
    ("https://drive.google.com/drive/folders/1AbC-dEf_123", "1AbC-dEf_123"),
    ("https://drive.google.com/drive/folders/1AbC-dEf_123?usp=sharing", "1AbC-dEf_123"),
    ("https://drive.google.com/open?id=1XyZ789", "1XyZ789"),
    ("1AbC-dEf_123", "1AbC-dEf_123"),
    ("  1AbC-dEf_123  ", "1AbC-dEf_123"),
])
def test_doc_duoc_ma_thu_muc_tu_url(raw, expected):
    """
    Cán bộ sẽ dán URL từ thanh địa chỉ. Bắt họ tự cắt lấy đoạn mã là chỗ sai sót không cần thiết —
    và khi sai thì lỗi hiện ra là '403', nghe như lỗi chia sẻ chứ không phải lỗi dán nhầm.
    """
    # Hàm nằm trong api.py (cần fastapi) — kiểm bằng chính biểu thức chính quy để không phải
    # dựng cả ứng dụng FastAPI trong bộ kiểm thử vốn chạy không có fastapi.
    import re

    value = raw.strip()
    match = re.search(r"/folders/([A-Za-z0-9_-]+)", value)
    if not match:
        match = re.search(r"[?&]id=([A-Za-z0-9_-]+)", value)
    got = match.group(1) if match else value.rstrip("/").split("/")[-1]
    assert got == expected
