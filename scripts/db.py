#!/usr/bin/env python3
"""
Database Layer - Library Digitization
PostgreSQL via psycopg2 với connection pooling

Cài đặt: pip install psycopg2-binary>=2.9.9
Biến môi trường: DATABASE_URL=postgresql://user:password@host:5432/library_digitization
"""

import os
import logging
from contextlib import contextmanager
from typing import Dict, List, Optional

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool


logger = logging.getLogger("db")

# =============================================================
# CONNECTION POOL
# =============================================================

# Đọc từng tham số riêng — tránh vấn đề ký tự đặc biệt trong password khi dùng URL
_DB_PARAMS = {
    "host":     os.getenv("POSTGRES_HOST", "postgres"),
    "port":     int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname":   os.getenv("POSTGRES_DB", "library_digitization"),
    "user":     os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

# min=2 luôn giữ sẵn 2 conn, max=10 đủ cho 2-4 worker + API (2 uvicorn workers)
_pool: Optional[ThreadedConnectionPool] = None


def init_pool(min_conn: int = 2, max_conn: int = 10) -> None:
    """Khởi tạo connection pool — gọi 1 lần khi startup"""
    global _pool
    _pool = ThreadedConnectionPool(min_conn, max_conn, **_DB_PARAMS)
    logger.info(
        f"DB pool initialized (min={min_conn}, max={max_conn}) → "
        f"{_DB_PARAMS['user']}@{_DB_PARAMS['host']}:{_DB_PARAMS['port']}"
        f"/{_DB_PARAMS['dbname']}"
    )


def close_pool() -> None:
    """Đóng toàn bộ pool — gọi khi shutdown"""
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("DB pool closed")


@contextmanager
def get_conn():
    """
    Context manager lấy/trả connection từ pool.

    Dùng:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
    """
    if _pool is None:
        raise RuntimeError("DB pool chưa được khởi tạo. Gọi init_pool() trước.")

    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


# =============================================================
# DOCUMENTS
# =============================================================

def create_document(
    job_id: str,
    filename: str,
    collection_id: str = "",
    document_type: str = "book",
) -> None:
    """
    Tạo document mới khi job được enqueue.
    Status mặc định = 'queued', dspace_status = 'pending'.
    """
    sql = """
        INSERT INTO documents (
            id, filename, collection_id, document_type,
            status, progress,
            dspace_status,
            created_at
        )
        VALUES (%s, %s, %s, %s, 'queued', 10, 'pending', NOW())
        ON CONFLICT (id) DO NOTHING
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (job_id, filename, collection_id, document_type))

    logger.debug(f"Created document: {job_id}")


def update_document_status(
    job_id: str,
    status: str,
    progress: Optional[int] = None,
    pdf_path: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """
    Cập nhật trạng thái OCR job.
    - progress=None → tự lấy progress_value từ bảng job_statuses
    - Tự set finished_at khi status là terminal (is_terminal=TRUE)
    """
    sql = """
        UPDATE documents
        SET
            status        = %(status)s,
            progress      = COALESCE(
                                %(progress)s,
                                (SELECT progress_value FROM job_statuses WHERE code = %(status)s)
                            ),
            pdf_path      = COALESCE(%(pdf_path)s, pdf_path),
            error_message = COALESCE(%(error_message)s, error_message),
            finished_at   = CASE
                                WHEN (SELECT is_terminal FROM job_statuses WHERE code = %(status)s)
                                THEN NOW()
                                ELSE finished_at
                            END
        WHERE id = %(job_id)s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {
                "job_id":        job_id,
                "status":        status,
                "progress":      progress,
                "pdf_path":      pdf_path,
                "error_message": error_message,
            })

    logger.debug(f"Updated document status: {job_id} → {status}")


def get_document(job_id: str) -> Optional[Dict]:
    """
    Lấy thông tin 1 document kèm label và color từ bảng lookup.
    Trả về None nếu không tìm thấy.
    """
    sql = """
        SELECT
            d.id,
            d.filename,
            d.collection_id,
            d.document_type,
            dt.label            AS document_type_label,
            d.status,
            js.label            AS status_label,
            js.color            AS status_color,
            d.progress,
            d.pdf_path,
            d.error_message,
            d.created_at,
            d.finished_at,
            -- DSpace fields
            d.dspace_status,
            ds.label            AS dspace_status_label,
            ds.color            AS dspace_status_color,
            d.dspace_collection_id,
            d.dspace_collection_name,
            d.dspace_community_name,
            d.dspace_item_id,
            d.dspace_handle,
            d.dspace_uploaded_at,
            d.dspace_error
        FROM documents d
        JOIN document_types         dt ON dt.code = d.document_type
        JOIN job_statuses           js ON js.code = d.status
        JOIN dspace_upload_statuses ds ON ds.code = d.dspace_status
        WHERE d.id = %s
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (job_id,))
            row = cur.fetchone()

    return dict(row) if row else None


def list_documents(
    status: Optional[str] = None,
    dspace_status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict]:
    """
    Liệt kê documents, tùy chọn lọc theo status OCR và/hoặc dspace_status.
    Sắp xếp mới nhất trước.
    """
    conditions = []
    params = []

    if status:
        conditions.append("d.status = %s")
        params.append(status)

    if dspace_status:
        conditions.append("d.dspace_status = %s")
        params.append(dspace_status)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    sql = f"""
        SELECT
            d.id,
            d.filename,
            d.collection_id,
            d.document_type,
            dt.label            AS document_type_label,
            d.status,
            js.label            AS status_label,
            js.color            AS status_color,
            d.progress,
            d.error_message,
            d.created_at,
            d.finished_at,
            -- DSpace fields
            d.dspace_status,
            ds.label            AS dspace_status_label,
            ds.color            AS dspace_status_color,
            d.dspace_collection_id,
            d.dspace_collection_name,
            d.dspace_community_name,
            d.dspace_item_id,
            d.dspace_handle,
            d.dspace_uploaded_at
        FROM documents d
        JOIN document_types         dt ON dt.code = d.document_type
        JOIN job_statuses           js ON js.code = d.status
        JOIN dspace_upload_statuses ds ON ds.code = d.dspace_status
        {where}
        ORDER BY d.created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [dict(r) for r in rows]


def delete_document(job_id: str) -> bool:
    """
    Xóa document và toàn bộ metadata liên quan (CASCADE).
    Trả về True nếu xóa thành công, False nếu không tìm thấy.
    """
    sql = "DELETE FROM documents WHERE id = %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (job_id,))
            deleted = cur.rowcount > 0

    logger.debug(f"Deleted document: {job_id} → {deleted}")
    return deleted


def get_stats() -> Dict:
    """
    Thống kê số lượng job theo trạng thái OCR và DSpace.
    """
    # OCR stats
    ocr_sql = """
        SELECT js.code, js.label, js.color, COUNT(d.id) AS count
        FROM job_statuses js
        LEFT JOIN documents d ON d.status = js.code
        GROUP BY js.code, js.label, js.color, js.sort_order
        ORDER BY js.sort_order
    """

    # DSpace stats
    dspace_sql = """
        SELECT ds.code, ds.label, ds.color, COUNT(d.id) AS count
        FROM dspace_upload_statuses ds
        LEFT JOIN documents d ON d.dspace_status = ds.code
        GROUP BY ds.code, ds.label, ds.color, ds.sort_order
        ORDER BY ds.sort_order
    """

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(ocr_sql)
            ocr_rows = cur.fetchall()

            cur.execute(dspace_sql)
            dspace_rows = cur.fetchall()

    ocr_stats = {row["code"]: row["count"] for row in ocr_rows}
    ocr_stats["total"] = sum(ocr_stats.values())

    dspace_stats = {row["code"]: row["count"] for row in dspace_rows}

    return {
        "ocr":    ocr_stats,
        "dspace": dspace_stats,
    }


# =============================================================
# METADATA
# =============================================================

def save_metadata(job_id: str, metadata_list: List[Dict]) -> None:
    """
    Save all metadata after pipeline completes.
    Deletes old metadata first, then inserts new rows.

    Supports multi-value fields (e.g. multiple dc.contributor.author).
    ON CONFLICT (document_id, key, value) DO NOTHING prevents duplicate errors.

    metadata_list: [{"key": "dc.title", "value": "...", "language": "vi_VN"}, ...]
    """
    delete_sql = "DELETE FROM metadata_fields WHERE document_id = %s"

    # ON CONFLICT DO NOTHING: safe when pipeline returns duplicate key+value pairs
    insert_sql = """
        INSERT INTO metadata_fields (document_id, key, value, language)
        VALUES %s
        ON CONFLICT (document_id, key, value) DO NOTHING
    """

    rows = [
        (job_id, item["key"], item["value"], item.get("language"))
        for item in metadata_list
        if item.get("key") and item.get("value")
    ]

    if not rows:
        logger.warning(f"save_metadata: no valid fields for job {job_id}")
        return

    # Deduplicate in Python first (preserve order, keep first occurrence)
    seen = set()
    deduped = []
    for row in rows:
        k = (row[1], row[2])  # (dc_key, value)
        if k not in seen:
            seen.add(k)
            deduped.append(row)

    skipped = len(rows) - len(deduped)
    if skipped:
        logger.warning(f"save_metadata: skipped {skipped} duplicate fields for job {job_id}")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(delete_sql, (job_id,))
            psycopg2.extras.execute_values(cur, insert_sql, deduped)

    logger.info(f"Saved {len(deduped)} metadata fields for job {job_id}")


def get_metadata(job_id: str) -> Optional[Dict]:
    """
    Lấy metadata của 1 document.
    Trả về format {"metadata": [...]} giữ nguyên cấu trúc JSON cũ
    để không phải sửa nhiều ở api.py và frontend.
    Trả về None nếu document không tồn tại.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM documents WHERE id = %s", (job_id,))
            if not cur.fetchone():
                return None

        sql = """
            SELECT key, value, language
            FROM metadata_fields
            WHERE document_id = %s
            ORDER BY id
        """
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (job_id,))
            rows = cur.fetchall()

    return {"metadata": [dict(r) for r in rows]}


def update_metadata(job_id: str, metadata_list: List[Dict]) -> int:
    """
    Cập nhật metadata do thủ thư hiệu chỉnh.
    Dùng DELETE + INSERT để xử lý đúng multi-value fields
    (vd: nhiều dc.contributor.author).
    Trigger sẽ tự ghi vào metadata_history khi value thay đổi.

    Trả về số field đã lưu.
    """
    return save_metadata.__wrapped__(job_id, metadata_list) if hasattr(save_metadata, '__wrapped__') else _update_metadata_impl(job_id, metadata_list)


def _update_metadata_impl(job_id: str, metadata_list: List[Dict]) -> int:
    """Implementation thực của update_metadata"""
    delete_sql = "DELETE FROM metadata_fields WHERE document_id = %s"
    insert_sql = """
        INSERT INTO metadata_fields (document_id, key, value, language)
        VALUES %s
    """

    rows = [
        (job_id, item["key"], item["value"], item.get("language"))
        for item in metadata_list
        if item.get("key") and item.get("value")
    ]

    if not rows:
        logger.warning(f"update_metadata: không có field hợp lệ cho job {job_id}")
        return 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(delete_sql, (job_id,))
            psycopg2.extras.execute_values(cur, insert_sql, rows)

    logger.info(f"Updated {len(rows)} metadata fields for job {job_id}")
    return len(rows)


# Gán lại update_metadata về implementation thực
update_metadata = _update_metadata_impl


def get_metadata_history(job_id: str) -> List[Dict]:
    """
    Lấy lịch sử hiệu chỉnh metadata của 1 document.
    Mới nhất trước.
    """
    sql = """
        SELECT key, old_value, new_value, changed_at, changed_by
        FROM metadata_history
        WHERE document_id = %s
        ORDER BY changed_at DESC
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (job_id,))
            rows = cur.fetchall()

    return [dict(r) for r in rows]


# =============================================================
# DSPACE UPLOAD TRACKING
# =============================================================

def set_dspace_collection(
    job_id: str,
    collection_id: str,
    collection_name: str,
    community_name: str = "",
) -> None:
    """
    Lưu collection mà người dùng đã chọn (hoặc AI gợi ý).
    Gọi khi người dùng confirm collection trên UI trước khi upload.
    """
    sql = """
        UPDATE documents
        SET
            dspace_collection_id   = %s,
            dspace_collection_name = %s,
            dspace_community_name  = %s
        WHERE id = %s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (collection_id, collection_name, community_name, job_id))

    logger.debug(f"Set DSpace collection for {job_id}: {collection_name} ({community_name})")


def update_dspace_status(
    job_id: str,
    dspace_status: str,
    item_id: Optional[str] = None,
    handle: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """
    Cập nhật trạng thái upload DSpace.

    Các luồng gọi điển hình:
    - Bắt đầu upload:  update_dspace_status(id, 'uploading')
    - Upload thành công: update_dspace_status(id, 'uploaded', item_id=..., handle=...)
    - Upload thất bại:   update_dspace_status(id, 'upload_failed', error=...)
    """
    sql = """
        UPDATE documents
        SET
            dspace_status       = %(dspace_status)s,
            dspace_item_id      = COALESCE(%(item_id)s, dspace_item_id),
            dspace_handle       = COALESCE(%(handle)s, dspace_handle),
            dspace_error        = %(error)s,
            dspace_uploaded_at  = CASE
                                      WHEN %(dspace_status)s = 'uploaded'
                                      THEN NOW()
                                      ELSE dspace_uploaded_at
                                  END
        WHERE id = %(job_id)s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {
                "job_id":       job_id,
                "dspace_status": dspace_status,
                "item_id":      item_id,
                "handle":       handle,
                "error":        error,
            })

    logger.info(f"DSpace status {job_id} → {dspace_status}" +
                (f" (handle: {handle})" if handle else "") +
                (f" ERROR: {error}" if error else ""))


def get_dspace_info(job_id: str) -> Optional[Dict]:
    """
    Lấy thông tin DSpace của 1 document.
    Dùng cho frontend để hiển thị trạng thái upload và link đến item.
    """
    sql = """
        SELECT
            d.dspace_status,
            ds.label            AS dspace_status_label,
            ds.color            AS dspace_status_color,
            d.dspace_collection_id,
            d.dspace_collection_name,
            d.dspace_community_name,
            d.dspace_item_id,
            d.dspace_handle,
            d.dspace_uploaded_at,
            d.dspace_error
        FROM documents d
        JOIN dspace_upload_statuses ds ON ds.code = d.dspace_status
        WHERE d.id = %s
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (job_id,))
            row = cur.fetchone()

    return dict(row) if row else None


def list_pending_dspace_uploads(limit: int = 100) -> List[Dict]:
    """
    Lấy danh sách các document đã hoàn thành OCR nhưng chưa upload DSpace.
    Dùng cho trang preview/upload của frontend.
    """
    sql = """
        SELECT
            d.id,
            d.filename,
            d.document_type,
            dt.label            AS document_type_label,
            d.pdf_path,
            d.finished_at,
            d.dspace_status,
            ds.label            AS dspace_status_label,
            ds.color            AS dspace_status_color,
            d.dspace_collection_id,
            d.dspace_collection_name,
            d.dspace_community_name,
            d.dspace_item_id,
            d.dspace_handle
        FROM documents d
        JOIN document_types         dt ON dt.code = d.document_type
        JOIN dspace_upload_statuses ds ON ds.code = d.dspace_status
        WHERE d.status = 'completed'
          AND d.dspace_status IN ('pending', 'upload_failed')
        ORDER BY d.finished_at DESC
        LIMIT %s
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()

    return [dict(r) for r in rows]


def reset_dspace_upload(job_id: str) -> None:
    """
    Reset trạng thái DSpace để thử upload lại.
    Xóa item_id, handle, error cũ.
    """
    sql = """
        UPDATE documents
        SET
            dspace_status      = 'pending',
            dspace_item_id     = NULL,
            dspace_handle      = NULL,
            dspace_error       = NULL,
            dspace_uploaded_at = NULL
        WHERE id = %s
          AND dspace_status = 'upload_failed'
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (job_id,))

    logger.info(f"Reset DSpace upload for {job_id}")


# =============================================================
# LOOKUP TABLES
# =============================================================

def get_document_types() -> List[Dict]:
    """Trả về danh sách loại tài liệu đang active"""
    sql = """
        SELECT code, label, description
        FROM document_types
        WHERE is_active = TRUE
        ORDER BY sort_order
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def get_job_statuses() -> List[Dict]:
    """Trả về danh sách OCR status kèm metadata cho UI/SSE"""
    sql = """
        SELECT code, label, progress_value, is_terminal, color
        FROM job_statuses
        ORDER BY sort_order
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def get_dspace_upload_statuses() -> List[Dict]:
    """Trả về danh sách DSpace upload status cho UI"""
    sql = """
        SELECT code, label, is_terminal, color
        FROM dspace_upload_statuses
        ORDER BY sort_order
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [dict(r) for r in rows]