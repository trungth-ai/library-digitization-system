#!/usr/bin/env python3
"""
Kiểm thử kiểm tra tệp đầu vào (sprint V5) — KT-BU-03/06/07/08/09, KT-BM-20.

Test quan trọng nhất: `test_chan_zip_slip*` — lỗ hổng cho phép một tệp ZIP ghi đè tệp hệ thống. Đây
là lỗi cổ điển, vẫn rất phổ biến, và hậu quả không sửa được bằng bản vá sau khi đã bị khai thác.
"""

from pathlib import Path

import pytest

from scripts.core import file_check


def _pdf_that(path: Path, noi_dung=b"noi dung tai lieu"):
    path.write_bytes(b"%PDF-1.7\n" + noi_dung)
    return path


# ─────────────────────────────────────────────────────────────
# TÊN TỆP
# ─────────────────────────────────────────────────────────────

def test_ten_tep_pdf_hop_le():
    assert file_check.check_filename("Báo cáo tổng kết 2026.pdf").ok is True


def test_ten_tep_tieng_viet_co_dau_va_khoang_trang():
    """KT-BU-08: tên tệp tiếng Việt là chuyện bình thường ở đây, không phải ca biên."""
    assert file_check.check_filename("Quyết định số 123-QĐ ngày 01.03.2026.pdf").ok is True


def test_tu_choi_khong_phai_pdf():
    result = file_check.check_filename("anh.jpg")
    assert result.ok is False
    assert result.code == "not_pdf_extension"
    assert "PDF" in result.reason


def test_tu_choi_ten_rong():
    assert file_check.check_filename("").ok is False
    assert file_check.check_filename("   ").ok is False


@pytest.mark.parametrize("ten", [
    "../../etc/passwd.pdf",
    "..\\..\\windows\\system32\\a.pdf",
    "thu-muc/tep.pdf",
])
def test_chan_ten_tep_chua_duong_dan(ten):
    """
    🔴 Tên tệp đến từ người dùng và sẽ được ghép vào đường dẫn đĩa.

    `../../etc/passwd.pdf` là đường thoát khỏi thư mục đích.
    """
    result = file_check.check_filename(ten)
    assert result.ok is False
    assert result.code == "unsafe_name"


def test_duoi_pdf_viet_hoa_van_duoc():
    assert file_check.check_filename("BAO_CAO.PDF").ok is True


# ─────────────────────────────────────────────────────────────
# NỘI DUNG TỆP
# ─────────────────────────────────────────────────────────────

def test_pdf_that_duoc_chap_nhan(tmp_path):
    assert file_check.check_pdf_content(_pdf_that(tmp_path / "a.pdf")).ok is True


def test_tu_choi_tep_rong(tmp_path):
    tep = tmp_path / "rong.pdf"
    tep.write_bytes(b"")

    result = file_check.check_pdf_content(tep)
    assert result.ok is False
    assert result.code == "empty_file"


def test_tu_choi_anh_doi_ten_thanh_pdf(tmp_path):
    """
    KT-BU-06: kiểm theo CHỮ KÝ tệp, không theo phần mở rộng.

    Phần mở rộng là thứ người dùng gõ; chữ ký là thứ tệp thật sự chứa. Không kiểm thì tệp này chiếm
    một suất worker, chạy OCR vài chục giây rồi hỏng với lỗi kỹ thuật của Ghostscript.
    """
    tep = tmp_path / "gia.pdf"
    tep.write_bytes(b"\xff\xd8\xff\xe0" + b"day la anh JPEG" * 100)   # chữ ký JPEG

    result = file_check.check_pdf_content(tep)
    assert result.ok is False
    assert result.code == "not_pdf_content"


def test_tu_choi_zip_doi_ten_thanh_pdf(tmp_path):
    tep = tmp_path / "gia.pdf"
    tep.write_bytes(b"PK\x03\x04" + b"noi dung zip" * 100)

    assert file_check.check_pdf_content(tep).code == "not_pdf_content"


def test_chap_nhan_pdf_co_byte_rac_truoc_header(tmp_path):
    """Một số công cụ chèn vài byte trước `%PDF-` — vẫn là PDF hợp lệ, không được từ chối."""
    tep = tmp_path / "a.pdf"
    tep.write_bytes(b"\n\n   %PDF-1.4\nnoi dung")

    assert file_check.check_pdf_content(tep).ok is True


def test_tu_choi_pdf_co_mat_khau(tmp_path):
    """
    KT-BU-07: PDF mã hóa làm OCR hỏng giữa chừng với thông báo khó hiểu.

    Chặn ngay và nói rõ "gỡ mật khẩu trước khi tải lên" — người dùng biết phải làm gì.
    """
    tep = tmp_path / "khoa.pdf"
    tep.write_bytes(b"%PDF-1.7\n" + b"x" * 200 + b"/Encrypt 5 0 R\ntrailer")

    result = file_check.check_pdf_content(tep)
    assert result.ok is False
    assert result.code == "encrypted"
    assert "mật khẩu" in result.reason


def test_phat_hien_tai_len_bi_gian_doan(tmp_path):
    """Dung lượng ghi xuống khác dung lượng khai báo = tải lên đứt giữa chừng."""
    tep = _pdf_that(tmp_path / "a.pdf")

    result = file_check.check_pdf_content(tep, expected_size=999999)
    assert result.ok is False
    assert result.code == "size_mismatch"


# ─────────────────────────────────────────────────────────────
# HẠN MỨC & ĐĨA
# ─────────────────────────────────────────────────────────────

def test_trong_han_muc_thi_cho_qua():
    assert file_check.check_batch_limits(200, 100 * 1024 * 1024).ok is True


def test_vuot_so_tep_bao_ro_han_muc():
    """KT-BU-03: thông báo phải nói rõ hạn mức VÀ số hiện tại, để người dùng biết chia lô thế nào."""
    result = file_check.check_batch_limits(600, 1024, max_files=500)

    assert result.ok is False
    assert result.code == "too_many_files"
    assert "600" in result.reason and "500" in result.reason


def test_vuot_dung_luong_du_it_tep():
    """500 tệp nhỏ và 20 tệp 500MB là hai loại tải khác hẳn nhau — phải chặn cả hai chiều."""
    result = file_check.check_batch_limits(20, 6000 * 1024 * 1024, max_files=500, max_mb=5000)

    assert result.ok is False
    assert result.code == "batch_too_large"


def test_dia_du_cho_thi_cho_qua(tmp_path):
    assert file_check.check_disk_space(str(tmp_path), min_free_gb=0).ok is True


def test_dia_gan_day_thi_tu_choi(tmp_path):
    """
    KT-BU-09: đĩa đầy giữa lúc nạp lô lớn làm PostgreSQL không ghi được và worker không lưu được —
    hỏng theo cách rất khó gỡ. Từ chối trước rẻ hơn nhiều so với dọn sau.
    """
    result = file_check.check_disk_space(str(tmp_path), min_free_gb=10 ** 9)

    assert result.ok is False
    assert result.code == "disk_full"
    assert "quản trị viên" in result.reason


def test_khong_doc_duoc_thong_tin_dia_thi_cho_qua():
    """
    Không đo được dung lượng → CHO QUA.

    Chặn nhận tài liệu vì không đọc được thông tin đĩa là phản ứng quá tay: lỗi này thường do đường
    dẫn chưa tồn tại, không phải do hết chỗ.
    """
    assert file_check.check_disk_space("/duong/dan/khong/ton/tai/o/dau").ok is True


# ─────────────────────────────────────────────────────────────
# CHỐNG ZIP-SLIP — KT-BM-20 🔴
# ─────────────────────────────────────────────────────────────

def test_giai_nen_muc_binh_thuong(tmp_path):
    duong_dan = file_check.safe_extract_path(tmp_path, "cong-van/a.pdf")

    assert duong_dan is not None
    assert duong_dan.is_relative_to(tmp_path.resolve())


@pytest.mark.parametrize("muc", [
    "../thoat.pdf",
    "../../etc/passwd",
    "a/../../thoat.pdf",
    "./../../thoat.pdf",
])
def test_chan_zip_slip_duong_dan_tuong_doi(tmp_path, muc):
    """
    🔴 KT-BM-20: một mục ZIP tên `../../etc/passwd` sẽ ghi đè tệp hệ thống nếu ghép đường dẫn ngây thơ.
    """
    assert file_check.safe_extract_path(tmp_path, muc) is None


def test_chan_zip_slip_duong_dan_tuyet_doi(tmp_path):
    """
    Kiểm bằng đường dẫn tuyệt đối đã phân giải, KHÔNG bằng cách tìm chuỗi "..".

    Tìm ".." sẽ bỏ lọt đường dẫn tuyệt đối và các cách mã hóa khác của cùng ký tự.
    """
    import os
    tuyet_doi = "C:\\Windows\\system32\\a.pdf" if os.name == "nt" else "/etc/passwd"
    assert file_check.safe_extract_path(tmp_path, tuyet_doi) is None


def test_bo_qua_muc_thu_muc(tmp_path):
    """Mục thư mục trong ZIP không phải tệp cần giải nén."""
    assert file_check.safe_extract_path(tmp_path, "thu-muc/") is None
    assert file_check.safe_extract_path(tmp_path, "") is None
