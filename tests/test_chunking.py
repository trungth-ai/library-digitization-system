#!/usr/bin/env python3
"""
Test chia đoạn theo cấu trúc (YC-RG-03). Chạy: pytest tests/test_chunking.py -v
"""

from scripts.core.chunking import chunk_document, chunk_admin, chunk_paragraphs, Chunk

CONG_VAN = """TRƯỜNG ĐẠI HỌC ABC

Số: 123/QĐ-ABC

QUYẾT ĐỊNH
Về việc thành lập hội đồng

Căn cứ Quy chế tổ chức và hoạt động;
Căn cứ đề nghị của phòng ban chức năng;

QUYẾT ĐỊNH:
Điều 1. Thành lập hội đồng đánh giá.
Điều 2. Quyết định có hiệu lực kể từ ngày ký.

Nơi nhận:
- Như Điều 2;
- Lưu VT."""

VAN_BAN_THUONG = """Đoạn thứ nhất nói về nội dung A. Câu hai của đoạn một.

Đoạn thứ hai nói về nội dung B.

Đoạn thứ ba nói về nội dung C."""


def _assert_offsets_valid(text, chunks):
    """Mọi chunk phải trỏ đúng offset gốc — điều kiện cho dẫn nguồn (YC-RG-08)."""
    for c in chunks:
        assert text[c.char_start:c.char_end] == c.text
    # index liên tục
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_chunk_admin_co_cac_phan():
    chunks = chunk_admin(CONG_VAN)
    sections = {c.section for c in chunks}
    assert "can_cu" in sections       # phần căn cứ
    assert "noi_nhan" in sections     # phần nơi nhận
    assert "header" in sections       # phần đầu (số hiệu)
    _assert_offsets_valid(CONG_VAN, chunks)


def test_chunk_admin_gop_can_cu_lien_tiep():
    """2 dòng 'Căn cứ' liền nhau gộp vào cùng một chunk can_cu."""
    chunks = chunk_admin(CONG_VAN)
    can_cu = [c for c in chunks if c.section == "can_cu"]
    assert len(can_cu) == 1
    assert can_cu[0].text.count("Căn cứ") == 2


def test_chunk_paragraphs_offset_va_khong_cat_giua_cau():
    chunks = chunk_paragraphs(VAN_BAN_THUONG, max_chars=1000)
    _assert_offsets_valid(VAN_BAN_THUONG, chunks)
    # mỗi chunk là đoạn trọn vẹn, không kết thúc giữa câu (kết bằng '.' sau strip)
    for c in chunks:
        assert c.text.strip().endswith(".")


def test_chunk_document_auto():
    # công văn → admin (có phần can_cu)
    admin = chunk_document(CONG_VAN, mode="auto")
    assert any(c.section == "can_cu" for c in admin)
    # văn bản thường → paragraph
    para = chunk_document(VAN_BAN_THUONG, mode="auto")
    assert all(c.section == "paragraph" for c in para)


def test_chunk_paragraphs_gop_theo_max_chars():
    # max_chars nhỏ → mỗi đoạn 1 chunk (không gộp)
    chunks = chunk_paragraphs(VAN_BAN_THUONG, max_chars=10)
    assert len(chunks) == 3
    _assert_offsets_valid(VAN_BAN_THUONG, chunks)


def test_chunk_rong():
    assert chunk_document("", mode="auto") == []
    assert chunk_document("   \n  ", mode="auto") == []
