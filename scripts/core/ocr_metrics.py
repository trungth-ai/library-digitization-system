#!/usr/bin/env python3
"""
Đo chất lượng & chi phí một lượt OCR (YC-AN-03 — sprint V2).

CHỈ SỐ QUAN TRỌNG NHẤT: `pages_without_text` — số trang mà sau khi OCR vẫn KHÔNG có lớp text. Nghĩa
là ảnh quá mờ, lệch, hoặc là trang trắng. Tài liệu như vậy vẫn "xử lý thành công" theo mọi thước đo
hiện có, nhưng nội dung **không tra cứu được** sau khi lên DSpace — hỏng một cách im lặng, đúng loại
lỗi khó phát hiện nhất.

Biết sớm thì đề nghị quét lại khi tài liệu giấy còn trong tay; phát hiện sau sáu tháng thì phải tìm
lại bản giấy.

TÁCH LÀM HAI TẦNG để kiểm thử được: `analyze_text_layer` là hàm thuần nhận danh sách trang (bất kỳ
đối tượng nào có `extract_text()`), còn `collect` mới chạm tệp và `pypdf`. Máy dev không cài `pypdf`
(xem `requirements.txt` so với môi trường dev) nên tầng thuần là phần duy nhất kiểm thử được tại chỗ.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger("core.ocr_metrics")

# Trang có ít hơn ngần này ký tự coi như KHÔNG có lớp text. Không dùng 0 vì OCR hay để lại vài ký tự
# nhiễu (dấu chấm, số trang) trên một trang thực chất không đọc được.
MIN_CHARS_PER_PAGE = int(os.getenv("OCR_MIN_CHARS_PER_PAGE", "20"))


@dataclass
class TextLayerStats:
    pages: int = 0
    pages_without_text: int = 0
    text_chars: int = 0
    # Số trang không đọc được nội dung (lỗi khi trích) — khác với "trang không có text"
    unreadable_pages: List[int] = field(default_factory=list)

    @property
    def ratio_without_text(self) -> Optional[float]:
        return round(self.pages_without_text / self.pages, 3) if self.pages else None


def analyze_text_layer(pages: Iterable[Any],
                       min_chars: int = MIN_CHARS_PER_PAGE) -> TextLayerStats:
    """
    Đếm trang, trang không có lớp text, tổng số ký tự — từ danh sách trang đã mở.

    Nhận bất kỳ đối tượng nào có `extract_text()` (khớp `pypdf.PageObject`) nên kiểm thử được bằng
    lớp giả, không cần tệp PDF thật và không cần `pypdf`.

    Trang trích xuất lỗi được đếm vào `unreadable_pages` chứ không im lặng bỏ qua: một PDF mà nửa số
    trang không đọc được là thông tin cần biết, không phải chi tiết kỹ thuật đáng nuốt.
    """
    stats = TextLayerStats()

    for index, page in enumerate(pages, start=1):
        stats.pages += 1
        try:
            text = page.extract_text() or ""
        except Exception as e:  # noqa: BLE001 - một trang hỏng không được làm hỏng cả phép đo
            logger.debug("Không trích được text trang %d: %s", index, e)
            stats.unreadable_pages.append(index)
            stats.pages_without_text += 1
            continue

        chars = len(text.strip())
        stats.text_chars += chars
        if chars < min_chars:
            stats.pages_without_text += 1

    return stats


def collect(document_id: str, input_pdf: Optional[str], output_pdf: Optional[str],
            duration_ms: Optional[int] = None, language: Optional[str] = None,
            dpi_pre: Optional[int] = None, dpi_post: Optional[int] = None,
            warnings: Optional[str] = None) -> Dict:
    """
    Thu chỉ số một lượt OCR. KHÔNG ném lỗi ra ngoài — đây là số liệu, không phải nghiệp vụ.

    Trả về dict truyền thẳng được cho `db.log_ocr_run(**...)`. Trường không đo được để `None` chứ
    không để 0: "không đo được" và "bằng 0" dẫn tới hai kết luận khác nhau về chất lượng scan.
    """
    result: Dict = {
        "engine": "ocrmypdf",
        "language": language,
        "dpi_pre": dpi_pre,
        "dpi_post": dpi_post,
        "duration_ms": duration_ms,
        "warnings": warnings,
        "status": "success",
    }

    result["size_in_bytes"] = _file_size(input_pdf)
    result["size_out_bytes"] = _file_size(output_pdf)

    stats = _read_text_layer(output_pdf)
    if stats is not None:
        result["pages"] = stats.pages
        result["pages_without_text"] = stats.pages_without_text
        result["text_chars"] = stats.text_chars
        if stats.unreadable_pages:
            note = f"{len(stats.unreadable_pages)} trang không đọc được nội dung"
            result["warnings"] = f"{warnings}; {note}" if warnings else note
            result["status"] = "degraded"

    return result


def _file_size(path: Optional[str]) -> Optional[int]:
    if not path:
        return None
    try:
        return Path(path).stat().st_size
    except OSError:
        return None


def _read_text_layer(pdf_path: Optional[str]) -> Optional[TextLayerStats]:
    """
    Mở PDF và phân tích lớp text. Trả `None` nếu không mở được.

    `pypdf` import lazy theo đúng mẫu ADR-005: module này phải import được trên máy không cài pypdf
    để phần logic thuần còn kiểm thử được.
    """
    if not pdf_path or not Path(pdf_path).exists():
        return None
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        return analyze_text_layer(reader.pages)
    except Exception as e:  # noqa: BLE001
        logger.info("Không phân tích được lớp text của '%s': %s", pdf_path, e)
        return None
