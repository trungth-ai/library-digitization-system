#!/usr/bin/env python3
"""
Database Layer - Library Digitization
PostgreSQL via psycopg2 với connection pooling

Cài đặt: pip install psycopg2-binary>=2.9.9
Biến môi trường: DATABASE_URL=postgresql://user:password@host:5432/library_digitization
"""

import json
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
    clear_error: bool = False,
) -> None:
    """
    Cập nhật trạng thái OCR job.
    - progress=None → tự lấy progress_value từ bảng job_statuses
    - Tự set finished_at khi status là terminal (is_terminal=TRUE)
    - `clear_error=True` → XÓA `error_message` (đặt NULL).

    Vì sao cần `clear_error`: `error_message` dùng `COALESCE` nên truyền `None` là GIỮ giá trị cũ —
    hợp lý khi cập nhật từng phần, nhưng từ khi có cơ chế thử lại (ADR-011) thì một tài liệu có thể
    thất bại rồi thành công ở lần sau. Không có cờ này thì tài liệu `completed` vẫn mang thông báo lỗi
    của lần thử trước — một trạng thái tự mâu thuẫn mà người dùng không hiểu được.
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
            error_message = CASE
                                WHEN %(clear_error)s THEN NULL
                                ELSE COALESCE(%(error_message)s, error_message)
                            END,
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
                "clear_error":   clear_error,
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
            d.updated_at,
            d.finished_at,
            -- Trích xuất bằng công cụ/chế độ nào (YC-AU-04, YC-DR-06)
            d.extraction_provider,
            d.extraction_mode,
            d.extraction_model,
            d.needs_review,
            d.review_note,
            -- Loại tài liệu MÁY đoán (YC-SC-09) — để màn hình duyệt hiện gợi ý kèm lý do
            d.detected_type,
            d.detected_confidence,
            d.detected_source,
            d.detected_reason,
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
    include_deleted: bool = False,
    needs_review: Optional[bool] = None,
) -> List[Dict]:
    """
    Liệt kê documents, tùy chọn lọc theo status OCR và/hoặc dspace_status.
    Sắp xếp mới nhất trước.

    - `include_deleted=False` (mặc định): ẩn tài liệu đã xóa mềm. Xóa mềm chỉ có ý nghĩa nếu danh
      sách mặc định không hiện chúng nữa.
    - `needs_review=True`: chỉ lấy tài liệu cần cán bộ xem lại (YC-CF-03).
    """
    conditions = []
    params = []

    if status:
        conditions.append("d.status = %s")
        params.append(status)
    elif not include_deleted:
        # Chỉ ẩn khi KHÔNG lọc status cụ thể — gọi status='deleted' vẫn xem được thùng rác
        conditions.append("d.status <> 'deleted'")

    if dspace_status:
        conditions.append("d.dspace_status = %s")
        params.append(dspace_status)

    if needs_review is not None:
        conditions.append("d.needs_review = %s")
        params.append(needs_review)

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
            d.updated_at,
            d.finished_at,
            -- Trích xuất bằng công cụ/chế độ nào (YC-AU-04, YC-DR-06)
            d.extraction_provider,
            d.extraction_mode,
            d.extraction_model,
            d.needs_review,
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
            -- Lý do đẩy DSpace thất bại: trước đây được ghi vào DB nhưng KHÔNG trả ra danh sách,
            -- nên toast tắt là mất dấu vết. Có cột này thì giao diện hiện lại được.
            d.dspace_error
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
    XÓA MỀM một document: đặt status='deleted' (chuẩn HPU — KHÔNG hard delete).

    Dữ liệu, metadata và nhật ký kiểm toán được GIỮ LẠI để còn truy được trách nhiệm (YC-AU);
    tài liệu chỉ bị ẩn khỏi danh sách và thống kê. Muốn xóa vật lý (vd theo yêu cầu pháp lý về dữ
    liệu cá nhân) thì phải là một thao tác riêng, có phê duyệt — không đi qua hàm này.

    Trả về True nếu có tài liệu bị chuyển sang 'deleted', False nếu không tìm thấy hoặc đã xóa trước đó.
    """
    sql = """
        UPDATE documents
        SET status = 'deleted'
        WHERE id = %s AND status <> 'deleted'
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (job_id,))
            deleted = cur.rowcount > 0

    logger.info(f"Soft-deleted document: {job_id} → {deleted}")
    return deleted


def restore_document(job_id: str, status: str = "completed") -> bool:
    """
    Phục hồi tài liệu đã xóa mềm. Có xóa mềm thì phải có đường về, nếu không thì
    "không hard delete" chỉ là hình thức.
    """
    sql = "UPDATE documents SET status = %s WHERE id = %s AND status = 'deleted'"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (status, job_id))
            restored = cur.rowcount > 0

    logger.info(f"Restored document: {job_id} → {restored}")
    return restored


def get_stats() -> Dict:
    """
    Thống kê số lượng job theo trạng thái OCR và DSpace.
    """
    # OCR stats — LOẠI tài liệu đã xóa mềm khỏi mọi con số, kể cả 'total'
    ocr_sql = """
        SELECT js.code, js.label, js.color, COUNT(d.id) AS count
        FROM job_statuses js
        LEFT JOIN documents d ON d.status = js.code
        WHERE js.code <> 'deleted'
        GROUP BY js.code, js.label, js.color, js.sort_order
        ORDER BY js.sort_order
    """

    # DSpace stats — cũng bỏ tài liệu đã xóa để hai bảng thống kê nhất quán
    dspace_sql = """
        SELECT ds.code, ds.label, ds.color, COUNT(d.id) AS count
        FROM dspace_upload_statuses ds
        LEFT JOIN documents d ON d.dspace_status = ds.code AND d.status <> 'deleted'
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
        INSERT INTO metadata_fields (document_id, key, value, language, confidence)
        VALUES %s
        ON CONFLICT (document_id, key, value) DO NOTHING
    """

    # confidence (YC-CF-01) chỉ có khi trích qua lớp provider; đường cũ không có → NULL
    rows = [
        (job_id, item["key"], item["value"], item.get("language"), item.get("confidence"))
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

        # confidence đi kèm để UI tô màu trường điểm thấp (YC-CF-04)
        sql = """
            SELECT key, value, language, confidence
            FROM metadata_fields
            WHERE document_id = %s
            ORDER BY id
        """
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (job_id,))
            rows = cur.fetchall()

    # NUMERIC của Postgres về Python là Decimal → JSON không serialize được; đổi sang float
    metadata = []
    for r in rows:
        item = dict(r)
        if item.get("confidence") is not None:
            item["confidence"] = float(item["confidence"])
        metadata.append(item)
    return {"metadata": metadata}


def update_metadata(job_id: str, metadata_list: List[Dict]) -> int:
    """
    Cập nhật metadata do cán bộ hiệu chỉnh. Dùng DELETE + INSERT để xử lý đúng multi-value fields
    (vd nhiều dc.contributor.author). Trigger ghi metadata_history khi value thay đổi.

    ĐIỂM TIN CẬY: mọi trường đi qua đường này được đặt **confidence = 1.0** — cán bộ đã xem và xác
    nhận cả biểu mẫu, nên giá trị là do con người quyết định, không còn là phỏng đoán của model
    ("con người giữ quyền quyết định"). Điểm gốc của model không được giữ lại per-field; muốn truy
    thì xem `audit_log` (old→new) và `model_calls` (công cụ/model đã dùng).

    Trả về số field đã lưu.
    """
    delete_sql = "DELETE FROM metadata_fields WHERE document_id = %s"
    insert_sql = """
        INSERT INTO metadata_fields (document_id, key, value, language, confidence)
        VALUES %s
    """

    rows = [
        (job_id, item["key"], item["value"], item.get("language"), 1.0)
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

# =============================================================
# TRÍCH XUẤT: công cụ đã dùng + nhật ký gọi model
# (YC-MP-06 nhật ký bền vững, YC-MS-07 tài nguyên, YC-AU-04 truy vết)
# =============================================================

def set_extraction_info(
    job_id: str,
    provider: Optional[str] = None,
    mode: Optional[str] = None,
    model: Optional[str] = None,
    needs_review: Optional[bool] = None,
    review_note: Optional[str] = None,
) -> None:
    """
    Ghi lại tài liệu này được trích bằng công cụ/chế độ/model nào, và có cần cán bộ xem lại không.

    Tách khỏi update_document_status vì hai việc khác nhau: status là vòng đời xử lý, còn đây là
    truy vết model (YC-AU-04). Tham số None = giữ nguyên giá trị cũ.
    """
    sql = """
        UPDATE documents
        SET extraction_provider = COALESCE(%(provider)s, extraction_provider),
            extraction_mode     = COALESCE(%(mode)s,     extraction_mode),
            extraction_model    = COALESCE(%(model)s,    extraction_model),
            needs_review        = COALESCE(%(needs_review)s, needs_review),
            review_note         = COALESCE(%(review_note)s,  review_note)
        WHERE id = %(job_id)s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {
                "job_id": job_id, "provider": provider, "mode": mode, "model": model,
                "needs_review": needs_review, "review_note": review_note,
            })

    logger.debug(f"Extraction info saved: {job_id} → {provider}/{mode}/{model}")


def update_document_type(job_id: str, document_type: str) -> None:
    """Cán bộ chốt lại loại tài liệu. `detected_type` KHÔNG đụng tới — đó là ý kiến của máy."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE documents SET document_type = %s WHERE id = %s",
                (document_type, job_id),
            )
    logger.info("Đổi loại tài liệu %s → %s", job_id, document_type)


def set_detected_type(
    job_id: str,
    detected_type: str,
    confidence: Optional[float] = None,
    source: Optional[str] = None,
    reason: Optional[str] = None,
    apply_to_document: bool = False,
) -> None:
    """
    Ghi loại tài liệu MÁY đoán được (YC-SC-09).

    `apply_to_document=True` chỉ khi cán bộ đã chọn "để hệ thống tự đoán" — lúc đó loại đoán được
    trở thành loại đang dùng. Nếu cán bộ đã chọn tay thì KHÔNG ghi đè: ý kiến của máy vẫn được lưu
    để đối chiếu, nhưng lựa chọn của con người thắng (nguyên tắc SRS).

    Việc ghi đè dùng câu điều kiện phòng khi loại đoán được không có trong `document_types` (model
    trả mã lạ) — khóa ngoại sẽ từ chối, và một tài liệu đã OCR xong không đáng bị hỏng vì đoán sai.
    """
    sql = """
        UPDATE documents
        SET detected_type       = %(detected_type)s,
            detected_confidence = %(confidence)s,
            detected_source     = %(source)s,
            detected_reason     = %(reason)s,
            document_type       = CASE
                WHEN %(apply)s AND EXISTS (
                    SELECT 1 FROM document_types WHERE code = %(detected_type)s AND is_active
                ) THEN %(detected_type)s
                ELSE document_type
            END
        WHERE id = %(job_id)s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {
                "job_id": job_id, "detected_type": detected_type, "confidence": confidence,
                "source": source, "reason": reason, "apply": bool(apply_to_document),
            })

    logger.info("Loại tài liệu đoán được cho %s: %s (%.2f, %s)",
                job_id, detected_type, confidence or 0.0, source)


def log_model_call(
    provider: str,
    deployment: str,
    document_id: Optional[str] = None,
    model: Optional[str] = None,
    model_version: Optional[str] = None,
    schema_code: Optional[str] = None,
    used_ai: bool = True,
    attempts: int = 1,
    latency_ms: Optional[int] = None,
    rss_mb: Optional[float] = None,
    gpu_mem_mb: Optional[float] = None,
    n_fields: int = 0,
    fallback_from: Optional[str] = None,
    error: Optional[str] = None,
    status: str = "success",
    analytics: Optional[Dict] = None,
) -> Optional[int]:
    """
    Ghi một lần gọi model (YC-MP-06). Trả về `id` của bản ghi, hoặc `None` nếu ghi thất bại.

    KHÔNG ném lỗi ra ngoài: nhật ký hỏng không được làm gãy việc số hóa của cán bộ — cùng nguyên tắc
    với `audit.log_action`.

    `analytics` (sprint V2, tùy chọn) mang thêm token/chi phí/độ tin cậy. Truyền dưới dạng dict thay
    vì mười tham số mới để không phá chữ ký hàm với mọi nơi gọi hiện có; khóa lạ bị bỏ qua, nên mã cũ
    và DB chưa chạy migration 005 vẫn hoạt động bình thường.

    Trả về `id` để `model_call_fields` gắn được vào đúng lượt gọi (YC-AN-02).
    """
    # Danh sách trắng cột phân tích — KHÔNG nhận tên cột tùy ý từ nơi gọi (chúng đi thẳng vào SQL)
    _ANALYTICS_COLUMNS = (
        "prompt_tokens", "completion_tokens", "total_tokens", "cost_micro_usd", "cost_vnd",
        "prompt_version", "prompt_hash", "context_chars", "context_pages", "retry_reason",
        "confidence_avg", "confidence_min", "grounded_ratio", "request_id",
    )

    columns = ["document_id", "provider", "deployment", "model", "model_version", "schema_code",
               "used_ai", "attempts", "latency_ms", "rss_mb", "gpu_mem_mb", "n_fields",
               "fallback_from", "error", "status"]
    values = [document_id, provider, deployment, model, model_version, schema_code,
              used_ai, attempts, latency_ms, rss_mb, gpu_mem_mb, n_fields,
              fallback_from, error, status]

    for column in _ANALYTICS_COLUMNS:
        if analytics and analytics.get(column) is not None:
            columns.append(column)
            values.append(analytics[column])

    sql = (f"INSERT INTO model_calls ({', '.join(columns)}) "
           f"VALUES ({', '.join(['%s'] * len(columns))}) RETURNING id")

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)
                return int(cur.fetchone()[0])
    except Exception as e:  # noqa: BLE001 - nhật ký không được chặn nghiệp vụ chính
        logger.error(f"Ghi model_calls thất bại (provider={provider}, doc={document_id}): {e}")
        return None


def log_model_call_fields(model_call_id: Optional[int], document_id: Optional[str],
                          fields: List[Dict], preview_chars: int = 200) -> int:
    """
    Ghi kết quả TỪNG TRƯỜNG của một lượt gọi model (YC-AN-02). Trả về số dòng đã ghi.

    Đây là dữ liệu để đo độ chính xác trên việc thật: so giá trị AI trả về với giá trị cán bộ duyệt
    sau đó (xem `scripts/core/analytics.py`).

    `value_preview` cắt ngắn có chủ đích — đủ để đối chiếu, mà không biến bảng nhật ký thành bản sao
    thứ hai của nội dung tài liệu (vừa phình DB, vừa nhân đôi bề mặt rủi ro dữ liệu nhạy cảm).
    """
    if not fields:
        return 0

    sql = """
        INSERT INTO model_call_fields
            (model_call_id, document_id, field_key, value_preview, confidence, grounded, attempt)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    rows = []
    for field in fields:
        value = field.get("value")
        rows.append((
            model_call_id, document_id, field.get("key"),
            (str(value)[:preview_chars] if value is not None else None),
            field.get("confidence"), field.get("grounded"), field.get("attempt", 1),
        ))

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        return len(rows)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ghi model_call_fields thất bại (doc={document_id}): {e}")
        return 0


def confirm_document(job_id: str, actor: str) -> bool:
    """
    Cán bộ xác nhận một tài liệu (YC-RV-04). Trả `True` nếu vừa xác nhận, `False` nếu đã xác nhận rồi.

    `confirmed_at IS NULL` trong điều kiện WHERE là chốt chống xác nhận hai lần: hai cán bộ cùng bấm
    thì người sau nhận `False` và giao diện nói rõ "đã được duyệt bởi ...", thay vì ghi đè tên người
    trước một cách im lặng.

    Xác nhận CŨNG gỡ cờ `needs_review`: cán bộ đã xem và đồng ý thì tài liệu không còn nằm trong
    danh sách chờ nữa — nếu không nó sẽ ở đó mãi và danh sách chờ mất ý nghĩa.
    """
    sql = """
        UPDATE documents
        SET confirmed_at = NOW(), confirmed_by = %s, needs_review = FALSE
        WHERE id = %s AND confirmed_at IS NULL AND status = 'completed'
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (actor, job_id))
            return bool(cur.rowcount)


def confirmation_status(job_id: str) -> Optional[Dict]:
    """
    Trạng thái xác nhận của một tài liệu, hoặc `None` nếu KHÔNG XÁC ĐỊNH ĐƯỢC.

    Truy vấn riêng thay vì thêm cột vào `get_document()`: cột `confirmed_at` chỉ tồn tại sau
    migration 008, và thêm nó vào `get_document` sẽ làm **toàn bộ trang chi tiết tài liệu hỏng** nếu
    mã mới được triển khai trước khi chạy migration — đúng tình huống bình thường lúc deploy.

    Trả `None` (không biết) chứ không phải `{}` (chưa duyệt): nơi gọi phải phân biệt hai điều này.
    Chốt chặn đẩy DSpace xử lý "không biết" bằng cách CHẶN kèm thông báo yêu cầu chạy migration —
    một chốt an toàn mà im lặng cho qua khi không đọc được dữ liệu là một chốt nói dối.
    """
    try:
        import psycopg2.extras
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT confirmed_at, confirmed_by FROM documents WHERE id = %s", (job_id,))
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:  # noqa: BLE001
        logger.warning("Không đọc được trạng thái xác nhận của %s: %s", job_id, e)
        return None


def assign_document(job_id: str, user_id: Optional[int]) -> bool:
    """Giao tài liệu cho một cán bộ duyệt (YC-RV-07). `user_id=None` = bỏ phân công."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE documents SET assigned_to = %s WHERE id = %s", (user_id, job_id))
            return bool(cur.rowcount)


def list_pending_review(assigned_to: Optional[int] = None, only_unassigned: bool = False,
                        limit: int = 100, offset: int = 0) -> List[Dict]:
    """
    Danh sách tài liệu chờ duyệt (YC-RV-01).

    Sắp theo `updated_at` TĂNG DẦN — tài liệu chờ lâu nhất lên đầu. Sắp theo mới nhất trước sẽ làm
    những tài liệu tồn đọng lâu bị đẩy xuống cuối và không bao giờ được xử lý.
    """
    conditions = ["d.status = 'completed'", "d.confirmed_at IS NULL"]
    params: list = []

    if assigned_to is not None:
        conditions.append("(d.assigned_to = %s OR d.assigned_to IS NULL)")
        params.append(assigned_to)
    elif only_unassigned:
        conditions.append("d.assigned_to IS NULL")

    sql = f"""
        SELECT d.id, d.filename, d.status, d.needs_review, d.review_note,
               d.created_at, d.updated_at, d.assigned_to, d.batch_id,
               d.extraction_provider, d.extraction_mode,
               d.document_type, dt.label AS document_type_label,
               -- Máy đoán loại gì và vì sao: cán bộ duyệt cần thấy để đồng ý hay sửa lại
               d.detected_type, d.detected_confidence, d.detected_source, d.detected_reason,
               ROUND(EXTRACT(EPOCH FROM (NOW() - d.updated_at)) / 3600) AS gio_cho,
               (SELECT COUNT(*) FROM metadata_fields m
                 WHERE m.document_id = d.id AND m.confidence IS NOT NULL AND m.confidence < 0.5)
                   AS so_truong_diem_thap
        FROM documents d
        JOIN document_types dt ON dt.code = d.document_type
        WHERE {' AND '.join(conditions)}
        ORDER BY d.needs_review DESC, d.updated_at ASC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    import psycopg2.extras
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def log_queue_sample(depth: Dict, workers_alive: Optional[int] = None) -> None:
    """
    Ghi một mẫu độ sâu hàng đợi (YC-BU-18). Không ném lỗi — số liệu không được chặn việc xử lý.

    `workers_alive=None` được lưu là NULL chứ không phải 0: "không đọc được Redis" và "không có
    worker nào" dẫn tới hai hành động hoàn toàn khác nhau (cùng nguyên tắc với ADR-009 mục 6).
    """
    sql = """
        INSERT INTO queue_samples (high, normal, low, delayed, dead, processing, workers_alive)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    depth.get("high", 0), depth.get("normal", 0), depth.get("low", 0),
                    depth.get("delayed", 0), depth.get("dead", 0), depth.get("processing", 0),
                    workers_alive,
                ))
    except Exception as e:  # noqa: BLE001 - chưa chạy migration 007 thì bỏ qua, không làm ồn log
        logger.debug(f"Không ghi được mẫu hàng đợi: {e}")


def queue_history(hours: int = 24, bucket_minutes: int = 15) -> List[Dict]:
    """
    Lịch sử độ sâu hàng đợi, gộp theo khoảng thời gian (YC-DB-06).

    Gộp theo `bucket_minutes` thay vì trả từng mẫu: 24 giờ × 60 mẫu = 1440 điểm, vẽ ra thì rối và
    truyền qua mạng thì lãng phí. Lấy giá trị LỚN NHẤT trong mỗi khoảng chứ không phải trung bình —
    câu hỏi là "lúc cao điểm dồn bao nhiêu", mà trung bình sẽ làm phẳng mất đỉnh.
    """
    sql = """
        SELECT to_char(
                   to_timestamp(floor(extract(epoch FROM created_at) / (%(bucket)s * 60))
                                * (%(bucket)s * 60)),
                   'YYYY-MM-DD HH24:MI') AS moc_thoi_gian,
               MAX(high + normal + low) AS cho_xu_ly,
               MAX(high)                AS uu_tien_cao,
               MAX(delayed)             AS cho_thu_lai,
               MAX(dead)                AS da_chet,
               MAX(processing)          AS dang_xu_ly,
               MIN(workers_alive)       AS worker_it_nhat
        FROM queue_samples
        WHERE created_at > NOW() - (%(hours)s || ' hours')::interval
        GROUP BY moc_thoi_gian
        ORDER BY moc_thoi_gian
    """
    import psycopg2.extras
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, {"hours": hours, "bucket": bucket_minutes})
            return [dict(r) for r in cur.fetchall()]


def set_document_batch_info(job_id: str, batch_id: Optional[str] = None,
                            file_hash: Optional[str] = None, file_size: Optional[int] = None,
                            page_count: Optional[int] = None, uploaded_by: Optional[int] = None,
                            priority: Optional[str] = None) -> None:
    """
    Gắn thông tin lô/tệp cho một tài liệu (sprint V5). Không ném lỗi ra ngoài.

    Tách khỏi `create_document` thay vì thêm tham số: `create_document` được gọi từ đường nạp CŨ
    (`/api/v1/process`) vốn không có khái niệm lô, và đổi chữ ký của nó là chạm vào đường đang chạy
    thật mà không được gì.

    Chỉ cập nhật trường được truyền vào — `COALESCE` giữ nguyên giá trị cũ cho phần bỏ trống.
    """
    sql = """
        UPDATE documents
        SET batch_id    = COALESCE(%(batch_id)s, batch_id),
            file_hash   = COALESCE(%(file_hash)s, file_hash),
            file_size   = COALESCE(%(file_size)s, file_size),
            page_count  = COALESCE(%(page_count)s, page_count),
            uploaded_by = COALESCE(%(uploaded_by)s, uploaded_by),
            priority    = COALESCE(%(priority)s, priority)
        WHERE id = %(job_id)s
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {
                    "job_id": job_id, "batch_id": batch_id, "file_hash": file_hash,
                    "file_size": file_size, "page_count": page_count,
                    "uploaded_by": uploaded_by, "priority": priority,
                })
    except Exception as e:  # noqa: BLE001 - chưa chạy migration 006 thì vẫn phải nạp được tài liệu
        logger.warning(f"Không gắn được thông tin lô cho {job_id}: {e}")


def log_ocr_run(document_id: str, **fields) -> None:
    """
    Ghi chỉ số một lượt OCR (YC-AN-03). Không ném lỗi ra ngoài.

    Nhận `**fields` theo danh sách trắng: pipeline OCR sẽ còn được bổ sung chỉ số mới theo thời gian,
    và không nên phải sửa chữ ký hàm mỗi lần.
    """
    allowed = ("engine", "language", "pages", "pages_without_text", "dpi_pre", "dpi_post",
               "size_in_bytes", "size_out_bytes", "text_chars", "duration_ms", "warnings", "status")

    columns = ["document_id"]
    values = [document_id]
    for column in allowed:
        if fields.get(column) is not None:
            columns.append(column)
            values.append(fields[column])

    sql = (f"INSERT INTO ocr_runs ({', '.join(columns)}) "
           f"VALUES ({', '.join(['%s'] * len(columns))})")

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ghi ocr_runs thất bại (doc={document_id}): {e}")


def list_model_calls(
    document_id: Optional[str] = None,
    provider: Optional[str] = None,
    deployment: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict]:
    """Nhật ký gọi model, mới nhất trước (YC-MP-06 truy vấn được)."""
    conditions, params = [], []
    if document_id:
        conditions.append("document_id = %s"); params.append(document_id)
    if provider:
        conditions.append("provider = %s"); params.append(provider)
    if deployment:
        conditions.append("deployment = %s"); params.append(deployment)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    sql = f"""
        SELECT id, document_id, provider, deployment, model, model_version, schema_code,
               used_ai, attempts, latency_ms, rss_mb, gpu_mem_mb, n_fields,
               fallback_from, error, status, created_at
        FROM model_calls
        {where}
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    # NUMERIC → Decimal; đổi sang float để JSON serialize được
    out = []
    for r in rows:
        item = dict(r)
        for k in ("rss_mb", "gpu_mem_mb"):
            if item.get(k) is not None:
                item[k] = float(item[k])
        out.append(item)
    return out


def purge_document(job_id: str) -> bool:
    """
    XÓA VẬT LÝ một document (CASCADE xóa metadata + history). Chỉ dùng cho yêu cầu xóa dữ liệu thật
    sự — vd yêu cầu pháp lý về dữ liệu cá nhân (YC-PL-06).

    KHÁC `delete_document` (xóa mềm): hàm này KHÔNG thể phục hồi. Vì vậy nó không phải hành vi mặc
    định của nút "Xóa" trên giao diện, và nơi gọi phải ghi audit trước khi gọi — sau khi xóa thì
    không còn tài liệu để gắn bản ghi kiểm toán vào nữa.
    """
    sql = "DELETE FROM documents WHERE id = %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (job_id,))
            purged = cur.rowcount > 0

    logger.warning(f"PURGED (xóa vật lý) document: {job_id} → {purged}")
    return purged


# =============================================================
# THEO DÕI VẬN HÀNH: thời gian xử lý + sự kiện hệ thống
# =============================================================

def set_job_timing(job_id: str, duration_ms: int,
                   stage_timings: Optional[Dict] = None) -> None:
    """
    Ghi thời gian worker THỰC SỰ xử lý tài liệu (không tính thời gian nằm chờ hàng đợi).

    `finished_at - created_at` không dùng được cho mục đích này: tài liệu có thể nằm chờ hàng giờ
    nếu hàng đợi dài, con số đó nói về tải hệ thống chứ không nói về hiệu năng xử lý.
    """
    sql = """
        UPDATE documents
        SET duration_ms   = %(duration_ms)s,
            stage_timings = %(stage_timings)s::jsonb
        WHERE id = %(job_id)s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {
                "job_id": job_id,
                "duration_ms": duration_ms,
                "stage_timings": json.dumps(stage_timings, ensure_ascii=False) if stage_timings else None,
            })

    logger.debug(f"Job timing saved: {job_id} → {duration_ms}ms {stage_timings}")


def log_system_event(
    source: str,
    kind: str,
    message: str,
    level: str = "error",
    detail: Optional[str] = None,
    instance: Optional[str] = None,
    document_id: Optional[str] = None,
) -> None:
    """
    Ghi một sự kiện hạ tầng (mất kết nối, lỗi vòng lặp, công cụ mô hình không dùng được).

    KHÔNG ném lỗi ra ngoài: nếu chính DB đang có vấn đề thì việc ghi sự kiện sẽ thất bại, và nó
    tuyệt đối không được làm sập luồng đang chạy — cùng nguyên tắc với audit.log_action.
    """
    sql = """
        INSERT INTO system_events (source, instance, kind, level, message, detail, document_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (source, instance, kind, level, message, detail, document_id))
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ghi system_events thất bại (kind={kind}): {e}")


def resolve_system_events(kind: str, instance: Optional[str] = None) -> int:
    """
    Đánh dấu các sự kiện cùng loại là đã khắc phục — dùng khi kết nối được nối lại.
    Nhờ vậy giao diện phân biệt được "đang mất kết nối" với "từng mất kết nối hôm qua".
    """
    sql = "UPDATE system_events SET status = 'resolved' WHERE kind = %s AND status = 'new'"
    params = [kind]
    if instance:
        sql += " AND instance = %s"
        params.append(instance)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount


def list_system_events(
    level: Optional[str] = None,
    kind: Optional[str] = None,
    status: Optional[str] = None,
    since_hours: Optional[int] = None,
    limit: int = 100,
) -> List[Dict]:
    """Sự kiện hệ thống, mới nhất trước — nguồn cho trang theo dõi vận hành."""
    conditions, params = [], []
    if level:
        conditions.append("level = %s"); params.append(level)
    if kind:
        conditions.append("kind = %s"); params.append(kind)
    if status:
        conditions.append("status = %s"); params.append(status)
    if since_hours:
        conditions.append("created_at >= NOW() - (%s || ' hours')::interval")
        params.append(str(since_hours))
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    sql = f"""
        SELECT id, source, instance, kind, level, message, detail, document_id, status, created_at
        FROM system_events
        {where}
        ORDER BY created_at DESC, id DESC
        LIMIT %s
    """
    params.append(limit)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def processing_time_summary(since_hours: int = 24) -> Dict:
    """
    Tổng hợp thời gian xử lý (theo dõi hiệu năng — YC-HN).

    Dùng phân vị thay vì chỉ trung bình: một tài liệu 500 trang sẽ kéo trung bình lên và che mất
    thực tế của phần lớn tài liệu. p50 nói "thường mất bao lâu", p95 nói "trường hợp xấu tới đâu".
    """
    sql = """
        SELECT COUNT(*)                                                    AS so_tai_lieu,
               ROUND(AVG(duration_ms))                                     AS tb_ms,
               MIN(duration_ms)                                            AS min_ms,
               MAX(duration_ms)                                            AS max_ms,
               ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_ms))  AS p50_ms,
               ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)) AS p95_ms
        FROM documents
        WHERE duration_ms IS NOT NULL
          AND status <> 'deleted'
          AND created_at >= NOW() - (%s || ' hours')::interval
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (str(since_hours),))
            row = dict(cur.fetchone() or {})

    # NUMERIC → Decimal; đổi sang int để JSON hóa được. None nghĩa là CHƯA CÓ SỐ, không phải 0.
    return {k: (int(v) if v is not None else None) for k, v in row.items()}
