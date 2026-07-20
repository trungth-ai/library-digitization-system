#!/usr/bin/env python3
"""
Generic schema-driven prompt (mầm mống YC-SC): dựng prompt + parse kết quả theo LƯỢC ĐỒ bất kỳ
(số hiệu, ngày ban hành, ...). Dùng cho lược đồ KHÔNG phải dublin_core (vd công văn).

Tách riêng để CloudProvider & LocalProvider DÙNG CHUNG: mỗi provider chỉ cung cấp một hàm
`complete_fn(prompt) -> text` (gọi model), còn build-prompt/parse ở đây → test được bằng mock.

Chống ảo giác (YC-CF-05 tinh thần): prompt yêu cầu trả `null` khi không tìm thấy, TUYỆT ĐỐI không bịa.
"""

import re
import json
from typing import Callable

from scripts.providers.base import ExtractionSchema, ExtractionResult, FieldValue


def build_schema_prompt(text: str, schema: ExtractionSchema) -> str:
    """Dựng prompt liệt kê các trường của lược đồ, yêu cầu trả JSON đúng khóa."""
    field_lines = []
    for f in schema.fields:
        hint = ""
        if f.data_type == "list":
            hint = " [mảng]"
        elif f.data_type == "date":
            hint = " [ngày dạng DD/MM/YYYY]"
        elif f.data_type == "number":
            hint = " [số]"
        req = " (bắt buộc)" if f.required else ""
        field_lines.append(f'- "{f.key}": {f.label or f.key}{hint}{req}')
    fields_desc = "\n".join(field_lines)
    example = "{\n" + ",\n".join(f'  "{f.key}": null' for f in schema.fields) + "\n}"

    return f"""Trích xuất thông tin từ tài liệu loại "{schema.document_type}" theo ĐÚNG các trường dưới đây.
CHỈ dùng thông tin CÓ trong văn bản. Trường nào không tìm thấy thì để null — TUYỆT ĐỐI KHÔNG bịa giá trị.

VĂN BẢN:
{text}

CÁC TRƯỜNG CẦN TRÍCH:
{fields_desc}

TRẢ VỀ DUY NHẤT một JSON (không markdown, không giải thích), đúng khóa, thiếu thì null:
{example}"""


def parse_schema_response(raw_text: str, schema: ExtractionSchema) -> ExtractionResult:
    """Parse JSON model trả về thành ExtractionResult theo lược đồ (hỗ trợ multi-value)."""
    cleaned = re.sub(r"```json\s*|\s*```", "", (raw_text or "").strip())
    data = json.loads(cleaned) if cleaned else {}

    fields = []
    for f in schema.fields:
        value = data.get(f.key)
        if value is None:
            continue
        if isinstance(value, list):
            for item in value:
                s = str(item).strip()
                if s and s.lower() != "null":
                    fields.append(FieldValue(key=f.key, value=s, language=f.language))
        else:
            s = str(value).strip()
            if s and s.lower() != "null":
                fields.append(FieldValue(key=f.key, value=s, language=f.language))
    return ExtractionResult(fields=fields, raw=data if isinstance(data, dict) else None)


def extract_with_schema(complete_fn: Callable[[str], str],
                        text: str, schema: ExtractionSchema) -> ExtractionResult:
    """Điều phối: dựng prompt → gọi model (complete_fn) → parse theo lược đồ."""
    prompt = build_schema_prompt(text, schema)
    raw = complete_fn(prompt)
    return parse_schema_response(raw, schema)
