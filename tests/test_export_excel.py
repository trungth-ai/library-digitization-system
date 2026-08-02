#!/usr/bin/env python3
"""
Kiểm thử xuất bảng tính (sprint V2) — KT-AN-14, KT-NK-08.

Trọng tâm là **tiếng Việt hiển thị đúng trong Excel trên Windows**. Đây là lỗi hay gặp nhất khi xuất
dữ liệu tiếng Việt và cũng là lỗi khó lần ra nhất: tệp trông hỏng font, không ai biết sửa ở đâu, và
người dùng kết luận "chức năng xuất bị lỗi".
"""

import csv
import io

import pytest

from scripts.core import export_excel


# ─────────────────────────────────────────────────────────────
# TIẾNG VIỆT TRONG EXCEL 🔴
# ─────────────────────────────────────────────────────────────

def test_csv_co_bom_utf8():
    """
    🔴 CSV PHẢI có BOM UTF-8.

    Excel trên Windows đoán bảng mã theo codepage hệ thống chứ không mặc định UTF-8. Không có BOM
    thì "Báo cáo tổng kết" hiển thị thành "BÃ¡o cÃ¡o tá»•ng káº¿t".
    """
    content = export_excel.to_csv_bytes([["Trường"], ["Báo cáo tổng kết"]])

    assert content.startswith(b"\xef\xbb\xbf"), "thiếu BOM → Excel sẽ hiển thị sai dấu tiếng Việt"


def test_csv_giu_nguyen_dau_tieng_viet():
    content = export_excel.to_csv_bytes([["Tiêu đề"], ["Nguyễn Văn An — Khóa luận tốt nghiệp"]])
    text = content.decode("utf-8-sig")

    assert "Nguyễn Văn An — Khóa luận tốt nghiệp" in text


def test_csv_dung_ket_thuc_dong_cua_excel():
    """Thiếu `\\r\\n` thì một số phiên bản Excel gộp các dòng lại thành một."""
    content = export_excel.to_csv_bytes([["a"], ["b"]])
    assert b"\r\n" in content


def test_csv_thoat_dau_phay_trong_gia_tri():
    """Trích yếu công văn thường có dấu phẩy — không thoát đúng là lệch toàn bộ cột."""
    content = export_excel.to_csv_bytes([["Trích yếu"], ["Về việc A, B và C"]])
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))

    assert rows[1] == ["Về việc A, B và C"]


# ─────────────────────────────────────────────────────────────
# ĐỊNH DẠNG Ô
# ─────────────────────────────────────────────────────────────

def test_ngay_theo_quy_uoc_du_an():
    """Quy ước: lưu `YYYY-MM-DD`, hiển thị `DD/MM/YYYY`."""
    from datetime import date, datetime

    assert export_excel.format_cell(date(2026, 3, 1)) == "01/03/2026"
    assert export_excel.format_cell(datetime(2026, 3, 1, 14, 30)) == "01/03/2026 14:30"


def test_none_thanh_o_rong_khong_phai_chu_None():
    """"None" trong ô Excel là thứ người dùng không hiểu và trông như lỗi phần mềm."""
    assert export_excel.format_cell(None) == ""


def test_boolean_hien_bang_tieng_viet():
    """Bảng báo cáo dành cho cán bộ nghiệp vụ, không phải cho lập trình viên."""
    assert export_excel.format_cell(True) == "Có"
    assert export_excel.format_cell(False) == "Không"


def test_so_giu_nguyen():
    assert export_excel.format_cell(1234567) == "1234567"


# ─────────────────────────────────────────────────────────────
# DỰNG BẢNG
# ─────────────────────────────────────────────────────────────

def test_dong_dau_la_tieu_de_tieng_viet():
    rows = export_excel.build_rows(
        [{"field_key": "dc.title", "sample_size": 42}],
        [("field_key", "Trường"), ("sample_size", "Cỡ mẫu")],
    )

    assert rows[0] == ["Trường", "Cỡ mẫu"]
    assert rows[1] == ["dc.title", "42"]


def test_thieu_khoa_thi_o_rong_khong_gay_loi():
    """Dữ liệu thiếu trường không được làm hỏng cả tệp xuất."""
    rows = export_excel.build_rows([{"a": 1}], [("a", "A"), ("b", "B")])
    assert rows[1] == ["1", ""]


def test_thu_tu_cot_theo_noi_goi():
    rows = export_excel.build_rows(
        [{"x": 1, "y": 2}], [("y", "Y trước"), ("x", "X sau")])
    assert rows[0] == ["Y trước", "X sau"]
    assert rows[1] == ["2", "1"]


def test_danh_sach_rong_van_co_tieu_de():
    """Tệp xuất rỗng vẫn phải có tiêu đề cột — mở ra thấy cột trống khác hẳn mở ra thấy tệp hỏng."""
    rows = export_excel.build_rows([], [("a", "Cột A")])
    assert rows == [["Cột A"]]


# ─────────────────────────────────────────────────────────────
# CHỌN ĐỊNH DẠNG & PHƯƠNG ÁN LÙI
# ─────────────────────────────────────────────────────────────

def test_lui_ve_csv_khi_khong_co_openpyxl(monkeypatch):
    """
    Không có `openpyxl` thì vẫn xuất được, chỉ mất định dạng.

    Trên máy chủ air-gapped, `openpyxl` là một thứ nữa phải tải trước khi ngắt mạng — chức năng xuất
    không được phụ thuộc vào việc ai đó nhớ làm điều đó.
    """
    import builtins
    real_import = builtins.__import__

    def chan_openpyxl(name, *args, **kwargs):
        if name.startswith("openpyxl"):
            raise ImportError("giả lập không cài openpyxl")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", chan_openpyxl)

    content, extension, media_type = export_excel.export({"Sheet1": [["A"], ["1"]]})

    assert extension == "csv"
    assert content.startswith(b"\xef\xbb\xbf")
    assert "charset=utf-8" in media_type


def test_ten_sheet_bo_ky_tu_excel_khong_nhan():
    assert export_excel._safe_sheet_name("Báo cáo/2026") == "Báo cáo-2026"
    assert export_excel._safe_sheet_name("a" * 50) == "a" * 31


def test_ten_sheet_rong_van_hop_le():
    assert export_excel._safe_sheet_name("") == "Sheet1"
