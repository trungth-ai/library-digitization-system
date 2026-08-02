#!/usr/bin/env python3
"""
Kiểm thử đo chất lượng OCR (sprint V2) — KT-AN-05.

Chỉ số quan trọng nhất là `pages_without_text`: tài liệu có trang không tạo được lớp text vẫn "xử lý
thành công" theo mọi thước đo hiện có, nhưng nội dung KHÔNG tra cứu được sau khi lên DSpace. Đây là
loại hỏng im lặng — nên phép đếm phải đúng.

Dùng trang giả (`extract_text()`) thay vì PDF thật: `pypdf` không có trên máy dev, và phần cần kiểm
thử là logic đếm chứ không phải khả năng đọc PDF của thư viện.
"""

import pytest

from scripts.core import ocr_metrics


class FakePage:
    """Trang giả — chỉ cần `extract_text()`, đúng phần `analyze_text_layer` dùng tới."""

    def __init__(self, text="", loi=False):
        self._text = text
        self._loi = loi

    def extract_text(self):
        if self._loi:
            raise ValueError("trang hỏng")
        return self._text


def _trang_co_chu(n=1):
    return [FakePage("Đây là nội dung đầy đủ của một trang tài liệu tiếng Việt.") for _ in range(n)]


# ─────────────────────────────────────────────────────────────
# ĐẾM TRANG & LỚP TEXT
# ─────────────────────────────────────────────────────────────

def test_dem_dung_so_trang():
    stats = ocr_metrics.analyze_text_layer(_trang_co_chu(5))
    assert stats.pages == 5
    assert stats.pages_without_text == 0


def test_trang_rong_bi_dem_la_khong_co_text():
    stats = ocr_metrics.analyze_text_layer([FakePage(""), *_trang_co_chu(2)])
    assert stats.pages == 3
    assert stats.pages_without_text == 1


def test_trang_chi_co_nhieu_bi_dem_la_khong_co_text():
    """
    OCR hay để lại vài ký tự nhiễu (số trang, dấu chấm) trên một trang thực chất không đọc được.

    Dùng ngưỡng ký tự thay vì `== 0` để những trang đó vẫn bị đếm đúng là hỏng.
    """
    stats = ocr_metrics.analyze_text_layer([FakePage("12 ."), FakePage("  \n  ")])
    assert stats.pages_without_text == 2


def test_nguong_ky_tu_doi_duoc():
    it_chu = [FakePage("Ngắn")]
    assert ocr_metrics.analyze_text_layer(it_chu, min_chars=100).pages_without_text == 1
    assert ocr_metrics.analyze_text_layer(it_chu, min_chars=2).pages_without_text == 0


def test_trang_loi_duoc_ghi_nhan_rieng():
    """
    Trang trích xuất lỗi phải được đếm riêng, không im lặng bỏ qua.

    Một PDF mà nửa số trang không đọc được là thông tin cần biết, không phải chi tiết kỹ thuật đáng nuốt.
    """
    stats = ocr_metrics.analyze_text_layer([FakePage(loi=True), *_trang_co_chu(1)])

    assert stats.unreadable_pages == [1]
    assert stats.pages_without_text == 1, "trang không đọc được cũng là trang không có text"
    assert stats.pages == 2


def test_dem_tong_so_ky_tu():
    stats = ocr_metrics.analyze_text_layer([FakePage("abcde"), FakePage("xyz")])
    assert stats.text_chars == 8


def test_ty_le_trang_hong():
    stats = ocr_metrics.analyze_text_layer([FakePage(""), *_trang_co_chu(3)])
    assert stats.ratio_without_text == 0.25


def test_tai_lieu_rong_khong_chia_cho_khong():
    stats = ocr_metrics.analyze_text_layer([])
    assert stats.pages == 0
    assert stats.ratio_without_text is None, "không có trang thì tỉ lệ là CHƯA BIẾT, không phải 0"


# ─────────────────────────────────────────────────────────────
# THU CHỈ SỐ (chạm tệp)
# ─────────────────────────────────────────────────────────────

def test_collect_do_dung_dung_luong_tep(tmp_path):
    vao = tmp_path / "vao.pdf"
    ra = tmp_path / "ra.pdf"
    vao.write_bytes(b"x" * 5000)
    ra.write_bytes(b"y" * 3000)

    result = ocr_metrics.collect("job-1", str(vao), str(ra), duration_ms=1234)

    assert result["size_in_bytes"] == 5000
    assert result["size_out_bytes"] == 3000
    assert result["duration_ms"] == 1234


def test_collect_tep_khong_ton_tai_khong_gay_loi():
    """Số liệu thiếu phải để `None`, và tuyệt đối không ném lỗi — tài liệu đã OCR xong rồi."""
    result = ocr_metrics.collect("job-1", "/khong/co.pdf", "/cung/khong/co.pdf")

    assert result["size_in_bytes"] is None
    assert result["size_out_bytes"] is None
    assert result["status"] == "success"


def test_collect_giu_lai_cau_hinh_dpi():
    """DPI đi kèm chỉ số để so được chất lượng giữa các cấu hình nén khác nhau."""
    result = ocr_metrics.collect("job-1", None, None, dpi_pre=150, dpi_post=120, language="vie")

    assert result["dpi_pre"] == 150
    assert result["dpi_post"] == 120
    assert result["language"] == "vie"


def test_collect_khong_bia_so_khi_khong_doc_duoc_pdf():
    """
    Không đọc được PDF thì KHÔNG có khóa `pages` — chứ không phải `pages=0`.

    `pages=0` sẽ bị hiểu là "tài liệu rỗng"; thiếu khóa thì báo cáo biết là chưa đo được.
    """
    result = ocr_metrics.collect("job-1", None, None)
    assert "pages" not in result
