#!/usr/bin/env python3
"""
Ghi & truy vấn nhật ký kiểm toán (YC-AU). Dùng connection pool của scripts.db.

- log_action: ghi 1 bản ghi audit (append-only; DB chặn sửa/xóa — YC-AU-03).
- get_document_audit_trail: toàn bộ vòng đời 1 tài liệu (YC-AU-01).
- list_audit: kết xuất theo thời gian/người dùng/tài liệu (YC-AU-05).

Các hằng action chuẩn để nhất quán khi ghi log.
"""

import json
import logging
from typing import Dict, List, Optional

import scripts.db as db

logger = logging.getLogger("core.audit")

# Hằng action (YC-AU-01: mọi thao tác)
ACTION_UPLOAD = "upload"
ACTION_PROCESS = "process"
ACTION_EDIT_FIELD = "edit_field"
ACTION_CONFIRM = "confirm"
ACTION_DSPACE_PUSH = "dspace_push"
ACTION_SENSITIVITY_CHANGE = "sensitivity_change"
ACTION_DELETE = "delete"
ACTION_ROUTE_DENIED = "route_denied"   # YC-DR-03: từ chối gửi tài liệu nhạy cảm ra cloud


def log_action(
    action: str,
    document_id: Optional[str] = None,
    actor: Optional[str] = None,
    field_key: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    mode: Optional[str] = None,
    model: Optional[str] = None,
    detail: Optional[dict] = None,
) -> None:
    """Ghi một bản ghi kiểm toán. Không ném lỗi ra ngoài (audit hỏng không được chặn nghiệp vụ chính)."""
    sql = """
        INSERT INTO audit_log
            (document_id, action, actor, field_key, old_value, new_value, mode, model, detail)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    document_id, action, actor, field_key, old_value, new_value,
                    mode, model, json.dumps(detail, ensure_ascii=False) if detail else None,
                ))
    except Exception as e:  # noqa: BLE001 - audit không được làm gãy luồng nghiệp vụ
        logger.error("Ghi audit thất bại (action=%s, doc=%s): %s", action, document_id, e)


def get_document_audit_trail(document_id: str) -> List[Dict]:
    """Toàn bộ nhật ký của 1 tài liệu, cũ→mới (YC-AU-01)."""
    sql = """
        SELECT id, action, actor, field_key, old_value, new_value, mode, model, detail, created_at
        FROM audit_log
        WHERE document_id = %s
        ORDER BY created_at ASC, id ASC
    """
    import psycopg2.extras
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (document_id,))
            return [dict(r) for r in cur.fetchall()]


def list_audit(
    document_id: Optional[str] = None,
    actor: Optional[str] = None,
    action: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
) -> List[Dict]:
    """Kết xuất nhật ký theo bộ lọc (YC-AU-05). Mới nhất trước."""
    conditions, params = [], []
    if document_id:
        conditions.append("document_id = %s"); params.append(document_id)
    if actor:
        conditions.append("actor = %s"); params.append(actor)
    if action:
        conditions.append("action = %s"); params.append(action)
    if date_from:
        conditions.append("created_at >= %s"); params.append(date_from)
    if date_to:
        conditions.append("created_at <= %s"); params.append(date_to)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    sql = f"""
        SELECT id, document_id, action, actor, field_key, old_value, new_value,
               mode, model, detail, created_at
        FROM audit_log
        {where}
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    import psycopg2.extras
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
