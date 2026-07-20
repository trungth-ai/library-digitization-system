#!/usr/bin/env python3
"""
Báo cáo & thống kê (YC-DR-06, YC-CF-07, YC-AU-05 + throughput). Query trên audit_log + documents.

- report_by_mode: tài liệu theo chế độ xử lý cloud/local (YC-DR-06) — phục vụ kiểm toán.
- report_field_edit_rate: trường bị cán bộ sửa nhiều nhất (YC-CF-07) — đầu vào cải thiện lược đồ.
- report_action_summary: số thao tác theo loại (tổng quan hoạt động).
- report_throughput: tài liệu theo ngày + tỉ lệ hoàn thành/thất bại (mở rộng /stats).

Query kèm bộ lọc thời gian; kết quả trả list[dict] để API bọc envelope HPU (success/paginated).
"""

import logging
from typing import Dict, List, Optional

import psycopg2.extras

import scripts.db as db

logger = logging.getLogger("core.reports")


def _date_clause(field: str, date_from: Optional[str], date_to: Optional[str], params: list) -> str:
    clause = ""
    if date_from:
        clause += f" AND {field} >= %s"; params.append(date_from)
    if date_to:
        clause += f" AND {field} <= %s"; params.append(date_to)
    return clause


def report_by_mode(date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Dict]:
    """YC-DR-06: số tài liệu đã xử lý theo từng chế độ (cloud/local)."""
    params: list = []
    sql = f"""
        SELECT COALESCE(mode, '(không rõ)') AS mode,
               COUNT(DISTINCT document_id)  AS so_tai_lieu,
               COUNT(*)                     AS so_lan_goi
        FROM audit_log
        WHERE action = 'process'{_date_clause('created_at', date_from, date_to, params)}
        GROUP BY mode
        ORDER BY so_tai_lieu DESC
    """
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def report_field_edit_rate(date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Dict]:
    """YC-CF-07: trường bị cán bộ sửa nhiều nhất — chỉ dấu lược đồ/model cần cải thiện."""
    params: list = []
    sql = f"""
        SELECT field_key,
               COUNT(*)                    AS so_lan_sua,
               COUNT(DISTINCT document_id) AS so_tai_lieu
        FROM audit_log
        WHERE action = 'edit_field' AND field_key IS NOT NULL
              {_date_clause('created_at', date_from, date_to, params)}
        GROUP BY field_key
        ORDER BY so_lan_sua DESC
    """
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def report_action_summary(date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Dict]:
    """Tổng quan số thao tác theo loại (upload/process/edit_field/...)."""
    params: list = []
    where = "WHERE 1=1" + _date_clause('created_at', date_from, date_to, params)
    sql = f"""
        SELECT action, COUNT(*) AS so_lan, COUNT(DISTINCT document_id) AS so_tai_lieu
        FROM audit_log
        {where}
        GROUP BY action
        ORDER BY so_lan DESC
    """
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def report_throughput(date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Dict]:
    """Số tài liệu tạo theo ngày + số hoàn thành/thất bại (throughput OCR)."""
    params: list = []
    sql = f"""
        SELECT to_char(created_at, 'YYYY-MM-DD') AS ngay,
               COUNT(*)                                   AS tong,
               COUNT(*) FILTER (WHERE status = 'completed') AS hoan_thanh,
               COUNT(*) FILTER (WHERE status = 'failed')    AS that_bai
        FROM documents
        WHERE 1=1{_date_clause('created_at', date_from, date_to, params)}
        GROUP BY ngay
        ORDER BY ngay DESC
    """
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
