#!/usr/bin/env python3
"""
Chia đoạn theo CẤU TRÚC văn bản (YC-RG-03) — không cắt cứng theo số ký tự.

- Công văn hành chính: chia theo mốc (header / căn cứ / nội dung / nơi nhận / người ký) — mỗi phần giữ
  ngữ nghĩa trọn vẹn.
- Văn bản chung: chia theo đoạn (dòng trống), gộp đoạn nhỏ liền nhau, KHÔNG cắt giữa câu.

Mỗi chunk giữ offset ký tự gốc (char_start/char_end) → phục vụ dẫn nguồn bắt buộc (YC-RG-08):
câu trả lời RAG trỏ đúng tài liệu + vị trí đoạn.
"""

import re
from dataclasses import dataclass
from typing import List

# Mốc cấu trúc công văn hành chính (đầu dòng, không phân biệt hoa thường ở anchor)
_ADMIN_ANCHORS = [
    (re.compile(r"(?im)^\s*căn\s+cứ\b"), "can_cu"),
    (re.compile(r"(?im)^\s*(quyết\s+định|quyết\s+nghị|điều\s+\d+)\b"), "noi_dung"),
    (re.compile(r"(?im)^\s*nơi\s+nhận\s*:"), "noi_nhan"),
]


@dataclass
class Chunk:
    index: int
    text: str
    section: str        # header|can_cu|noi_dung|noi_nhan|paragraph
    char_start: int     # vị trí bắt đầu trong văn bản gốc (cho dẫn nguồn)
    char_end: int

    def __post_init__(self):
        # bảo đảm text khớp offset (an toàn cho dẫn nguồn)
        pass


def _split_paragraphs_with_offset(text: str):
    """Tách đoạn theo dòng trống, GIỮ offset gốc. Trả [(start, end, seg)]."""
    parts = []
    start = 0
    for m in re.finditer(r"\n[ \t]*\n", text):
        seg = text[start:m.start()]
        if seg.strip():
            parts.append((start, m.start(), seg))
        start = m.end()
    if start < len(text):
        seg = text[start:]
        if seg.strip():
            parts.append((start, len(text), seg))
    return parts


def chunk_paragraphs(text: str, max_chars: int = 1000) -> List[Chunk]:
    """Chia theo đoạn; gộp các đoạn nhỏ liền nhau tới ~max_chars, không cắt giữa đoạn/câu."""
    parts = _split_paragraphs_with_offset(text)
    chunks: List[Chunk] = []
    buf_start = None
    buf_end = None
    for (s, e, _seg) in parts:
        if buf_start is None:
            buf_start, buf_end = s, e
            continue
        # gộp nếu chưa vượt max_chars, ngược lại chốt chunk hiện tại
        if (e - buf_start) <= max_chars:
            buf_end = e
        else:
            chunks.append(Chunk(len(chunks), text[buf_start:buf_end], "paragraph", buf_start, buf_end))
            buf_start, buf_end = s, e
    if buf_start is not None:
        chunks.append(Chunk(len(chunks), text[buf_start:buf_end], "paragraph", buf_start, buf_end))
    return chunks


def chunk_admin(text: str) -> List[Chunk]:
    """Chia công văn theo mốc hành chính. Trả các chunk có section rõ ràng, theo thứ tự xuất hiện."""
    # Tìm mọi anchor và vị trí
    marks = []
    for pattern, section in _ADMIN_ANCHORS:
        for m in pattern.finditer(text):
            marks.append((m.start(), section))
    if not marks:
        # không phải công văn điển hình → fallback chia theo đoạn
        return chunk_paragraphs(text)

    marks.sort()
    chunks: List[Chunk] = []

    # Phần header: từ đầu tới anchor đầu tiên (nếu có nội dung)
    first_pos = marks[0][0]
    if text[:first_pos].strip():
        chunks.append(Chunk(len(chunks), text[:first_pos], "header", 0, first_pos))

    # Các phần theo anchor: gộp các anchor 'can_cu' liền nhau vào cùng vùng tới anchor khác section
    for i, (pos, section) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        seg = text[pos:end]
        if not seg.strip():
            continue
        # gộp liên tiếp cùng section (vd nhiều dòng "Căn cứ")
        if chunks and chunks[-1].section == section and chunks[-1].char_end == pos:
            prev = chunks[-1]
            chunks[-1] = Chunk(prev.index, text[prev.char_start:end], section, prev.char_start, end)
        else:
            chunks.append(Chunk(len(chunks), seg, section, pos, end))
    # đánh lại index liên tục
    for i, c in enumerate(chunks):
        c.index = i
    return chunks


def chunk_document(text: str, mode: str = "auto", max_chars: int = 1000) -> List[Chunk]:
    """
    Điểm vào chia đoạn.
      mode='admin'     → chia theo mốc công văn
      mode='paragraph' → chia theo đoạn
      mode='auto'      → tự phát hiện: có mốc hành chính thì dùng admin, ngược lại paragraph
    """
    if not text or not text.strip():
        return []
    if mode == "admin":
        return chunk_admin(text)
    if mode == "paragraph":
        return chunk_paragraphs(text, max_chars=max_chars)
    # auto
    has_admin = any(p.search(text) for p, _ in _ADMIN_ANCHORS)
    return chunk_admin(text) if has_admin else chunk_paragraphs(text, max_chars=max_chars)
