#!/usr/bin/env python3
"""
Kiểm soát chất lượng trích xuất (YC-CF): điểm tin cậy + kiểm tra hợp lệ + thử lại + chống ảo giác.

- YC-CF-01 Điểm tin cậy từng trường: suy từ mức "bám" văn bản gốc (grounding).
- YC-CF-02 Kiểm tra hợp lệ: đủ trường bắt buộc, đúng kiểu (date/number).
- YC-CF-03 Thử lại tối đa N lần; hết vẫn lỗi → đánh dấu cần xử lý thủ công (không ghi dữ liệu hỏng).
- YC-CF-05 Phát hiện giá trị bịa: giá trị không xuất hiện trong văn bản gốc → điểm tin cậy thấp.

Thuần (không gọi mạng) → unit-test được; `extract_with_quality` nhận provider bất kỳ (mock được).
"""

import re
import logging
from datetime import datetime
from typing import List, Optional, Tuple

from scripts.providers.base import ExtractionResult, ExtractionSchema

logger = logging.getLogger("core.quality")

_DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d")


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _looks_like_date(s: str) -> bool:
    s = (s or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            datetime.strptime(s, fmt)
            return True
        except ValueError:
            continue
    return False


def _looks_like_number(s: str) -> bool:
    return bool(re.fullmatch(r"[\d.,]+", (s or "").strip()))


# ---------------------------------------------------------------------
# YC-CF-01 + YC-CF-05: điểm tin cậy từ mức bám văn bản gốc (grounding)
# ---------------------------------------------------------------------

def grounding_confidence(value: str, source_text: str) -> float:
    """Điểm tin cậy 0.0–0.95: giá trị bám văn bản gốc bao nhiêu.
    Xuất hiện nguyên văn → 0.95; theo tỉ lệ token xuất hiện → 0.3–0.9; không token nào → 0.3."""
    v = _normalize(value)
    s = _normalize(source_text)
    if not v:
        return 0.0
    if v in s:
        return 0.95
    tokens = [t for t in re.split(r"\W+", v) if t]
    if not tokens:
        return 0.3
    hit = sum(1 for t in tokens if t in s)
    return round(0.3 + 0.6 * (hit / len(tokens)), 2)


def apply_grounding_confidence(result: ExtractionResult, source_text: str) -> ExtractionResult:
    """Gán confidence cho từng trường theo mức bám văn bản gốc (in-place)."""
    for fv in result.fields:
        fv.confidence = grounding_confidence(fv.value, source_text)
    return result


def low_confidence_fields(result: ExtractionResult, threshold: float = 0.5) -> List[str]:
    """Danh sách key có điểm tin cậy dưới ngưỡng (để UI tô màu — YC-CF-04)."""
    return [fv.key for fv in result.fields
            if fv.confidence is not None and fv.confidence < threshold]


# ---------------------------------------------------------------------
# YC-CF-02: kiểm tra tính hợp lệ đầu ra
# ---------------------------------------------------------------------

def validate_extraction(result: ExtractionResult, schema: ExtractionSchema) -> List[str]:
    """Trả về danh sách lỗi (rỗng = hợp lệ): thiếu trường bắt buộc, sai kiểu date/number."""
    errors: List[str] = []
    present = {fv.key for fv in result.fields if fv.value.strip()}
    for sf in schema.fields:
        if sf.required and sf.key not in present:
            errors.append(f"Thiếu trường bắt buộc: {sf.key}")

    by_key = {sf.key: sf for sf in schema.fields}
    for fv in result.fields:
        sf = by_key.get(fv.key)
        if not sf:
            continue
        if sf.data_type == "date" and fv.value.strip() and not _looks_like_date(fv.value):
            errors.append(f"Trường '{fv.key}' không đúng định dạng ngày: {fv.value}")
        if sf.data_type == "number" and fv.value.strip() and not _looks_like_number(fv.value):
            errors.append(f"Trường '{fv.key}' không phải số: {fv.value}")
    return errors


# ---------------------------------------------------------------------
# YC-CF-03: trích xuất kèm kiểm tra + thử lại
# ---------------------------------------------------------------------

def extract_with_quality(provider, text: str, schema: ExtractionSchema,
                         max_retries: int = 2,
                         source_text: Optional[str] = None) -> Tuple[ExtractionResult, List[str], int, bool]:
    """
    Trích xuất + kiểm hợp lệ + thử lại + gán điểm tin cậy.
    Trả về (result, errors, attempts, needs_manual).
      - needs_manual=True nếu hết số lần thử vẫn không hợp lệ (YC-CF-03) → caller chuyển trạng thái thủ công.
    """
    source = source_text if source_text is not None else text
    result: Optional[ExtractionResult] = None
    errors: List[str] = []
    attempts = 0

    for attempt in range(max_retries + 1):
        attempts = attempt + 1
        result = provider.extract_fields(text, schema)
        errors = validate_extraction(result, schema)
        if not errors:
            break
        logger.warning("Trích xuất lần %d không hợp lệ: %s", attempts, errors)

    apply_grounding_confidence(result, source)
    needs_manual = bool(errors)
    if needs_manual:
        logger.warning("Hết %d lần thử vẫn không hợp lệ → cần xử lý thủ công (YC-CF-03)", attempts)
    return result, errors, attempts, needs_manual
