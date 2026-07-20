#!/usr/bin/env python3
"""
Kho lược đồ trích xuất (YC-SC): nạp/lưu lược đồ dạng DỮ LIỆU từ PostgreSQL, thay cho định nghĩa
hard-code. Cho phép thêm lược đồ mới mà KHÔNG sửa mã (YC-SC-01), nhân bản (YC-SC-06), xuất/nhập (YC-SC-07).

Phần chuyển đổi (rows ↔ ExtractionSchema ↔ dict) là THUẦN → test được không cần DB.
Phần truy vấn (load/list/save/clone) dùng scripts.db.
"""

import logging
from typing import Dict, List, Optional

from scripts.providers.base import ExtractionSchema, SchemaField

logger = logging.getLogger("core.schema_store")


# ---------------------------------------------------------------------
# Chuyển đổi thuần (unit-test được)
# ---------------------------------------------------------------------

def rows_to_schema(schema_row: Dict, field_rows: List[Dict]) -> ExtractionSchema:
    """Dựng ExtractionSchema từ dòng DB (1 schema + n field)."""
    fields = [
        SchemaField(
            key=r["key"],
            label=r.get("label") or "",
            required=bool(r.get("required", False)),
            data_type=r.get("data_type") or "text",
            language=r.get("language"),
            description=r.get("description") or "",
        )
        for r in sorted(field_rows, key=lambda x: x.get("sort_order", 0))
    ]
    return ExtractionSchema(
        code=schema_row["code"],
        name=schema_row.get("name") or schema_row["code"],
        document_type=schema_row["document_type"],
        fields=fields,
        context_strategy=schema_row.get("context_strategy") or "first8_last2",
        sensitivity=schema_row.get("sensitivity") or "public",
    )


def schema_to_dict(schema: ExtractionSchema) -> Dict:
    """Xuất lược đồ ra dict (YC-SC-07: xuất tệp để chia sẻ giữa đơn vị)."""
    return {
        "code": schema.code,
        "name": schema.name or schema.code,
        "document_type": schema.document_type,
        "context_strategy": schema.context_strategy,
        "sensitivity": schema.sensitivity,
        "fields": [
            {
                "key": f.key, "label": f.label, "required": f.required,
                "data_type": f.data_type, "language": f.language, "description": f.description,
                "sort_order": i + 1,
            }
            for i, f in enumerate(schema.fields)
        ],
    }


def dict_to_schema(data: Dict) -> ExtractionSchema:
    """Nhập lược đồ từ dict (YC-SC-07)."""
    fields = [
        SchemaField(
            key=f["key"], label=f.get("label", ""), required=bool(f.get("required", False)),
            data_type=f.get("data_type", "text"), language=f.get("language"),
            description=f.get("description", ""),
        )
        for f in sorted(data.get("fields", []), key=lambda x: x.get("sort_order", 0))
    ]
    return ExtractionSchema(
        code=data["code"], name=data.get("name", data["code"]),
        document_type=data.get("document_type", "book"), fields=fields,
        context_strategy=data.get("context_strategy", "first8_last2"),
        sensitivity=data.get("sensitivity", "public"),
    )


# ---------------------------------------------------------------------
# Truy vấn DB
# ---------------------------------------------------------------------

def load_schema(code: str) -> Optional[ExtractionSchema]:
    """Nạp 1 lược đồ từ DB. Trả None nếu không có."""
    import psycopg2.extras
    import scripts.db as db
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM extraction_schemas WHERE code = %s AND is_active = TRUE", (code,))
            srow = cur.fetchone()
            if not srow:
                return None
            cur.execute("SELECT * FROM schema_fields WHERE schema_code = %s ORDER BY sort_order", (code,))
            frows = cur.fetchall()
    return rows_to_schema(dict(srow), [dict(r) for r in frows])


def list_schemas() -> List[Dict]:
    """Danh sách lược đồ đang active (cho UI chọn)."""
    import psycopg2.extras
    import scripts.db as db
    sql = """
        SELECT s.code, s.name, s.document_type, s.sensitivity, s.context_strategy,
               COUNT(f.id) AS so_truong
        FROM extraction_schemas s
        LEFT JOIN schema_fields f ON f.schema_code = s.code
        WHERE s.is_active = TRUE
        GROUP BY s.code, s.name, s.document_type, s.sensitivity, s.context_strategy
        ORDER BY s.name
    """
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


def save_schema(schema: ExtractionSchema) -> None:
    """Tạo/cập nhật lược đồ (upsert schema + thay toàn bộ field)."""
    import scripts.db as db
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO extraction_schemas (code, name, document_type, context_strategy, sensitivity, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name, document_type = EXCLUDED.document_type,
                    context_strategy = EXCLUDED.context_strategy, sensitivity = EXCLUDED.sensitivity,
                    updated_at = NOW()
                """,
                (schema.code, schema.name or schema.code, schema.document_type,
                 schema.context_strategy, schema.sensitivity),
            )
            cur.execute("DELETE FROM schema_fields WHERE schema_code = %s", (schema.code,))
            for i, f in enumerate(schema.fields):
                cur.execute(
                    """INSERT INTO schema_fields
                       (schema_code, key, label, required, data_type, language, description, sort_order)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (schema.code, f.key, f.label, f.required, f.data_type, f.language, f.description, i + 1),
                )
    logger.info("Đã lưu lược đồ '%s' (%d trường)", schema.code, len(schema.fields))


def clone_schema(src_code: str, new_code: str, new_name: str) -> ExtractionSchema:
    """Nhân bản lược đồ để tạo biến thể (YC-SC-06)."""
    src = load_schema(src_code)
    if not src:
        raise ValueError(f"Không tìm thấy lược đồ nguồn '{src_code}'")
    clone = ExtractionSchema(
        code=new_code, name=new_name, document_type=src.document_type,
        fields=list(src.fields), context_strategy=src.context_strategy, sensitivity=src.sensitivity,
    )
    save_schema(clone)
    return clone
