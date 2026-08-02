#!/usr/bin/env python3
"""
Kiểm thử log có cấu trúc + che bí mật (sprint V1) — KT-LG-01 → KT-LG-07, KT-BM-17.

Trọng tâm là `test_che_*`: YC-BM-03 ("không ghi khóa API/mật khẩu ra log") trước đây **không có cơ
chế nào cưỡng chế**, chỉ dựa vào việc lập trình viên nhớ. Các test dưới đây là cơ chế đó.
"""

import json
import logging

import pytest

from scripts.core import context, logging_setup


@pytest.fixture(autouse=True)
def _sach_ngu_canh():
    """Mỗi test bắt đầu với ngữ cảnh trống — nếu không, request_id của test trước rò sang test sau."""
    context.clear()
    yield
    context.clear()


def _ghi_va_lay_json(func):
    """
    Chạy `func(logger)` với handler dựng ĐÚNG như production, trả về các dòng JSON đã ghi.

    Dùng handler thật thay vì định dạng lại `caplog.records` sau khi chạy: ngữ cảnh (`request_id`,
    `job_id`) được đọc lúc ĐỊNH DẠNG, mà định dạng chỉ xảy ra đồng bộ trong lời gọi log khi có
    handler thật. Định dạng lại sau khi ngữ cảnh đã thoát thì các trường đó rỗng — bản đầu của test
    này mắc đúng lỗi ấy và báo hỏng trong khi mã production đúng.
    """
    import io

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging_setup.JsonFormatter())
    handler.addFilter(logging_setup.SecretRedactionFilter())

    logger = logging.getLogger("test_target")
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    try:
        func(logger)
    finally:
        handler.flush()
        logger.handlers = []

    return [json.loads(line) for line in stream.getvalue().strip().splitlines() if line]


# ─────────────────────────────────────────────────────────────
# KT-LG-01: log là JSON hợp lệ
# ─────────────────────────────────────────────────────────────

def test_dong_log_la_json_hop_le():
    rows = _ghi_va_lay_json(lambda lg: lg.info("xin chào"))

    assert rows[0]["msg"] == "xin chào"
    assert rows[0]["level"] == "INFO"
    assert rows[0]["logger"] == "test_target"
    assert "ts" in rows[0]


def test_tieng_viet_khong_bi_escape(caplog):
    """`ensure_ascii=False`: log tiếng Việt phải đọc được trực tiếp trong tệp, không thành \\uXXXX."""
    formatter = logging_setup.JsonFormatter()
    with caplog.at_level(logging.INFO):
        logging.getLogger("t").info("Tài liệu đã xử lý xong")

    raw = formatter.format(caplog.records[0])
    assert "Tài liệu đã xử lý xong" in raw


def test_ngoai_le_duoc_ghi_kem():
    def ghi(lg):
        try:
            raise ValueError("PDF hỏng")
        except ValueError:
            lg.exception("xử lý thất bại")

    rows = _ghi_va_lay_json(ghi)
    assert "ValueError" in rows[0]["exc"]


# ─────────────────────────────────────────────────────────────
# KT-LG-02/03: request_id & job_id
# ─────────────────────────────────────────────────────────────

def test_request_id_di_vao_moi_dong_log():
    def ghi(lg):
        with context.request_context(request_id="abc123", actor="nguyenvanan"):
            lg.info("đang xử lý")

    rows = _ghi_va_lay_json(ghi)
    assert rows[0]["request_id"] == "abc123"
    assert rows[0]["actor"] == "nguyenvanan"


def test_job_id_theo_suot_vong_doi():
    """KT-LG-04: grep một job_id phải ra đủ chuỗi OCR → trích xuất → xuất."""
    def ghi(lg):
        with context.job_context("job-1", actor="worker"):
            lg.info("bắt đầu OCR")
            lg.info("trích metadata")
            lg.info("hoàn tất")

    rows = _ghi_va_lay_json(ghi)
    assert [r["job_id"] for r in rows] == ["job-1"] * 3


def test_truong_chua_dat_thi_khong_xuat_hien():
    """Không đặt ngữ cảnh thì không có khóa rỗng — "chưa đặt" khác với "đặt bằng rỗng"."""
    rows = _ghi_va_lay_json(lambda lg: lg.info("không có ngữ cảnh"))

    assert "request_id" not in rows[0]
    assert "job_id" not in rows[0]


def test_ngu_canh_long_nhau_khoi_phuc_dung():
    """Thoát ngữ cảnh trong phải trả lại ngữ cảnh ngoài, không xóa trắng."""
    with context.request_context(request_id="ngoai"):
        with context.request_context(request_id="trong"):
            assert context.get_request_id() == "trong"
        assert context.get_request_id() == "ngoai"


def test_extra_duoc_dua_vao_json():
    def ghi(lg):
        lg.info("xong", extra={"duration_ms": 1234, "provider": "claude"})

    rows = _ghi_va_lay_json(ghi)
    assert rows[0]["duration_ms"] == 1234
    assert rows[0]["provider"] == "claude"


# ─────────────────────────────────────────────────────────────
# KT-LG-05 / KT-BM-17: CHE BÍ MẬT  🔴
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bi_mat,nguyen_van", [
    ("sk-ant-api03-abcdefghijklmnop", "CLAUDE_API_KEY=sk-ant-api03-abcdefghijklmnop"),
    ("AIzaSyD-1234567890abcdefg", "key AIzaSyD-1234567890abcdefg dùng cho Gemini"),
    ("gsk_abcdefghij1234567890", "GROQ_API_KEY=gsk_abcdefghij1234567890"),
    ("hf_abcdefghij1234567890", "token hf_abcdefghij1234567890"),
])
def test_che_khoa_api_theo_tien_to(bi_mat, nguyen_van):
    """Khóa của các nhà cung cấp model — thứ dễ rò nhất qua một dòng log cấu hình."""
    ket_qua = logging_setup.redact(nguyen_van)
    assert bi_mat not in ket_qua
    assert logging_setup.MASK in ket_qua


@pytest.mark.parametrize("nguyen_van,bi_mat", [
    ("password=MatKhauCuaToi2026", "MatKhauCuaToi2026"),
    ("api_key: abcd1234efgh", "abcd1234efgh"),
    ('{"token": "xyz789abcdef"}', "xyz789abcdef"),
    ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9", "eyJhbGciOiJIUzI1NiJ9"),
    ("cookie=docuflow_session=abcdef123456", "abcdef123456"),
    ("SECRET = 'sieu-bi-mat-123'", "sieu-bi-mat-123"),
])
def test_che_gan_khoa_gia_tri(nguyen_van, bi_mat):
    ket_qua = logging_setup.redact(nguyen_van)
    assert bi_mat not in ket_qua, f"còn lộ bí mật trong: {ket_qua}"


def test_giu_lai_ten_truong_khi_che():
    """
    Che GIÁ TRỊ nhưng giữ TÊN: người gỡ lỗi vẫn biết "có khóa API ở đây" — thông tin cần thiết —
    mà không đọc được khóa.
    """
    ket_qua = logging_setup.redact("api_key=sk-ant-abcdefghijkl")
    assert "api_key" in ket_qua
    assert "sk-ant-abcdefghijkl" not in ket_qua


def test_bo_loc_che_ca_trong_tham_so_dinh_dang():
    """
    Bí mật nằm trong tham số `%s` cũng phải bị che.

    `logger.info("khóa: %s", key)` là cách viết phổ biến hơn cả nối chuỗi — che mỗi `record.msg` là
    bỏ sót đúng dạng hay gặp nhất.
    """
    rows = _ghi_va_lay_json(lambda lg: lg.info("dùng khóa %s", "sk-ant-abcdefghijkl"))

    assert "sk-ant-abcdefghijkl" not in rows[0]["msg"]


def test_che_truoc_khi_dinh_dang_nen_moi_handler_deu_sach(caplog):
    """
    Bộ lọc sửa `record.msg` TẠI CHỖ, nên handler nào cũng nhận bản đã che.

    Nếu chỉ che ở khâu định dạng của một handler thì handler khác (vd tệp riêng) vẫn ghi bản gốc.
    """
    redaction = logging_setup.SecretRedactionFilter()
    with caplog.at_level(logging.INFO):
        logging.getLogger("t").info("password=RatBiMat123")

    record = caplog.records[0]
    redaction.filter(record)
    assert "RatBiMat123" not in record.msg
    assert "RatBiMat123" not in record.getMessage()


def test_khong_che_nham_van_ban_binh_thuong():
    """
    Che nhầm quá tay làm log mất giá trị gỡ lỗi.

    Các chuỗi dưới đây KHÔNG phải bí mật và phải được giữ nguyên.
    """
    for van_ban in [
        "Xử lý tài liệu Báo cáo tổng kết năm 2026",
        "job_id=abc-123-def",
        "provider=claude deployment=cloud",
        "status=completed progress=100",
    ]:
        assert logging_setup.redact(van_ban) == van_ban, f"che nhầm: {van_ban}"


def test_van_ban_rong_khong_gay_loi():
    assert logging_setup.redact("") == ""
    assert logging_setup.redact(None) is None


# ─────────────────────────────────────────────────────────────
# THIẾT LẬP & VAN LÙI
# ─────────────────────────────────────────────────────────────

def test_van_lui_ve_dinh_dang_chu_thuan(tmp_path):
    """KT-LG-12: `LOG_FORMAT=text` khôi phục đúng định dạng đang dùng trước sprint này."""
    logging_setup.configure("test", log_format="text", log_dir=str(tmp_path))
    root = logging.getLogger()

    assert not isinstance(root.handlers[0].formatter, logging_setup.JsonFormatter)
    # Che bí mật vẫn phải hoạt động ở chế độ text — đây là yêu cầu bảo mật, không phải tùy chọn hiển thị
    assert any(isinstance(f, logging_setup.SecretRedactionFilter)
               for f in root.handlers[0].filters)


def test_khong_gan_handler_trung_lap(tmp_path):
    """Gọi `configure` hai lần không được làm log ghi đúp — `basicConfig` cũ phải bị gỡ."""
    logging_setup.configure("test", log_dir=str(tmp_path))
    so_luong = len(logging.getLogger().handlers)
    logging_setup.configure("test", log_dir=str(tmp_path))

    assert len(logging.getLogger().handlers) == so_luong


def test_ghi_ra_tep_jsonl(tmp_path):
    """KT-LG-06: có tệp JSONL để tra được sau khi log container đã bị cắt vòng."""
    logging_setup.configure("worker", log_dir=str(tmp_path))
    logging.getLogger("worker").info("có việc mới")
    for handler in logging.getLogger().handlers:
        handler.flush()

    tep = tmp_path / "worker.jsonl"
    assert tep.exists()
    dong = json.loads(tep.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert dong["msg"] == "có việc mới"


def test_khong_ghi_duoc_tep_van_khoi_dong_duoc(tmp_path):
    """
    Thư mục log không dùng được thì vẫn phải chạy, chỉ mất phần ghi tệp.

    Dừng cả API vì không mở được tệp log là đánh đổi sai: mất toàn bộ dịch vụ để đổi lấy một tiện
    ích vận hành.
    """
    chan_duong = tmp_path / "la-mot-tep"
    chan_duong.write_text("khong phai thu muc", encoding="utf-8")

    logging_setup.configure("test", log_dir=str(chan_duong / "con"))

    assert logging.getLogger().handlers, "phải còn ít nhất handler stdout"
