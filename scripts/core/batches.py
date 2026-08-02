#!/usr/bin/env python3
"""
Lô nạp tài liệu + chống trùng (YC-BU-03/04 — sprint V5).

HAI VIỆC:

1. **Lô (batch)** — biến "300 job rời rạc" thành "một mẻ việc theo dõi được". Không có khái niệm này
   thì cán bộ nạp 300 tệp xong không biết còn bao nhiêu, tệp nào lỗi, và không dừng/chạy lại cả mẻ được.

2. **Chống trùng bằng SHA-256** — tải lại cùng một tệp hiện nay là xử lý lại từ đầu: tốn OCR (chặng
   đắt nhất) và tạo bản ghi trùng trên DSpace. Hash đã được tính SẴN ở đường tải lên từ ADR-010, nên
   ở đây chỉ là một truy vấn.

Bộ đếm của lô cập nhật bằng câu UPDATE cộng dồn thay vì đếm lại `COUNT(*)`: một lô đang chạy sẽ được
mở xem liên tục, và đếm lại toàn bảng mỗi lần làm mới là lãng phí không cần thiết.
"""

import logging
import uuid
from typing import Dict, List, Optional

import scripts.db as db

logger = logging.getLogger("core.batches")

SOURCE_WEB = "web"
SOURCE_ZIP = "zip"
SOURCE_WATCH = "watch"
SOURCE_API = "api"

STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

# Chế độ xử lý tệp trùng: bỏ qua (mặc định) hay xử lý lại
DEDUP_SKIP = "skip"
DEDUP_REPROCESS = "reprocess"


def _dict_cursor(conn):
    import psycopg2.extras
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


# ─────────────────────────────────────────────────────────────
# CHỐNG TRÙNG
# ─────────────────────────────────────────────────────────────

def find_by_hash(file_hash: str) -> Optional[Dict]:
    """
    Tìm tài liệu đã có cùng nội dung (YC-BU-04). Trả `None` nếu chưa có.

    Bỏ qua tài liệu đã xóa mềm: nếu cán bộ đã xóa một tài liệu rồi tải lại, đó là hành động có chủ
    đích — chặn nó lại sẽ khiến họ không hiểu vì sao "tệp đã tồn tại" mà tìm mãi không thấy đâu.
    """
    sql = """
        SELECT id, filename, status, created_at
        FROM documents
        WHERE file_hash = %s AND status <> 'deleted'
        ORDER BY created_at ASC
        LIMIT 1
    """
    try:
        with db.get_conn() as conn:
            with _dict_cursor(conn) as cur:
                cur.execute(sql, (file_hash,))
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:  # noqa: BLE001 - không tra được trùng thì cứ xử lý, đừng chặn việc
        logger.warning("Không tra được tài liệu trùng (hash=%s): %s", file_hash[:12], e)
        return None


# ─────────────────────────────────────────────────────────────
# LÔ
# ─────────────────────────────────────────────────────────────

def create_batch(name: str, source: str = SOURCE_WEB, created_by: Optional[int] = None,
                 priority: str = "normal", total_files: int = 0,
                 note: Optional[str] = None) -> str:
    """Tạo lô mới, trả về `batch_id`."""
    batch_id = str(uuid.uuid4())
    sql = """
        INSERT INTO batches (id, name, source, created_by, priority, total_files, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (batch_id, name.strip() or "Lô không tên", source,
                              created_by, priority, total_files, note))

    logger.info("Tạo lô '%s' (%s), nguồn=%s, %d tệp", name, batch_id[:8], source, total_files)
    return batch_id


def bump_counters(batch_id: Optional[str], done: int = 0, failed: int = 0,
                  skipped: int = 0, total: int = 0) -> None:
    """
    Cộng dồn bộ đếm của lô. Không ném lỗi — số liệu tiến độ không được chặn việc xử lý tài liệu.

    Tự đánh dấu `completed` khi đã xử lý hết: kiểm ngay trong câu UPDATE để không có cửa sổ đua giữa
    hai worker cùng hoàn tất tệp cuối cùng.
    """
    if not batch_id:
        return

    sql = """
        UPDATE batches
        SET done_files    = done_files + %(done)s,
            failed_files  = failed_files + %(failed)s,
            skipped_files = skipped_files + %(skipped)s,
            total_files   = total_files + %(total)s,
            status = CASE
                WHEN status = 'running'
                     AND done_files + %(done)s + failed_files + %(failed)s
                         + skipped_files + %(skipped)s >= total_files + %(total)s
                THEN 'completed' ELSE status
            END,
            finished_at = CASE
                WHEN status = 'running'
                     AND done_files + %(done)s + failed_files + %(failed)s
                         + skipped_files + %(skipped)s >= total_files + %(total)s
                THEN NOW() ELSE finished_at
            END
        WHERE id = %(id)s
    """
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"id": batch_id, "done": done, "failed": failed,
                                  "skipped": skipped, "total": total})
    except Exception as e:  # noqa: BLE001
        logger.warning("Không cập nhật được bộ đếm lô %s: %s", batch_id, e)


def get_batch(batch_id: str) -> Optional[Dict]:
    sql = """
        SELECT b.*, u.username AS nguoi_tao
        FROM batches b
        LEFT JOIN users u ON u.id = b.created_by
        WHERE b.id = %s
    """
    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            try:
                cur.execute(sql, (batch_id,))
            except Exception:  # noqa: BLE001 - bảng users có thể chưa di trú
                conn.rollback()
                cur.execute("SELECT * FROM batches WHERE id = %s", (batch_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def list_batches(status: Optional[str] = None, created_by: Optional[int] = None,
                 limit: int = 50, offset: int = 0) -> List[Dict]:
    conditions, params = ["b.status <> 'deleted'"], []
    if status:
        conditions.append("b.status = %s"); params.append(status)
    if created_by is not None:
        conditions.append("b.created_by = %s"); params.append(created_by)

    sql = f"""
        SELECT b.*, u.username AS nguoi_tao
        FROM batches b
        LEFT JOIN users u ON u.id = b.created_by
        WHERE {' AND '.join(conditions)}
        ORDER BY b.created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            try:
                cur.execute(sql, params)
            except Exception:  # noqa: BLE001
                conn.rollback()
                cur.execute(
                    f"SELECT * FROM batches WHERE {' AND '.join(conditions)} "
                    f"ORDER BY created_at DESC LIMIT %s OFFSET %s".replace("b.", ""), params)
            return [dict(r) for r in cur.fetchall()]


def set_batch_status(batch_id: str, status: str, actor: Optional[str] = None) -> bool:
    """
    Đổi trạng thái lô: tạm dừng / tiếp tục / hủy (YC-BU-16).

    Chỉ đổi được từ trạng thái đang hoạt động: một lô đã `completed` mà bị "tạm dừng" là trạng thái
    vô nghĩa, và cho phép nó sẽ tạo ra những lô kẹt vĩnh viễn.
    """
    if status not in (STATUS_RUNNING, STATUS_PAUSED, STATUS_CANCELLED):
        raise ValueError(f"Trạng thái lô không hợp lệ: {status}")

    sql = """
        UPDATE batches
        SET status = %s,
            finished_at = CASE WHEN %s = 'cancelled' THEN NOW() ELSE finished_at END
        WHERE id = %s AND status IN ('running', 'paused')
    """
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (status, status, batch_id))
            changed = cur.rowcount

    if changed:
        logger.info("Lô %s → %s (bởi %s)", batch_id[:8], status, actor or "?")
    return bool(changed)


def batch_documents(batch_id: str, limit: int = 500, offset: int = 0) -> List[Dict]:
    """Danh sách tài liệu trong một lô, kèm nhãn trạng thái để giao diện hiện thẳng."""
    sql = """
        SELECT d.id, d.filename, d.status, d.progress, d.error_message,
               d.needs_review, d.created_at, d.finished_at,
               js.label AS status_label, js.color AS status_color
        FROM documents d
        LEFT JOIN job_statuses js ON js.code = d.status
        WHERE d.batch_id = %s
        ORDER BY d.created_at ASC
        LIMIT %s OFFSET %s
    """
    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute(sql, (batch_id, limit, offset))
            return [dict(r) for r in cur.fetchall()]


def is_paused(batch_id: Optional[str]) -> bool:
    """
    Lô này có đang tạm dừng không? Worker hỏi trước khi bắt đầu một tài liệu (YC-BU-16).

    Lỗi truy vấn → trả `False` (cứ xử lý): không xử lý được tài liệu vì không đọc nổi trạng thái lô
    là đánh đổi sai — tạm dừng là tiện ích, xử lý tài liệu là việc chính.
    """
    if not batch_id:
        return False
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM batches WHERE id = %s", (batch_id,))
                row = cur.fetchone()
                return bool(row) and row[0] in (STATUS_PAUSED, STATUS_CANCELLED)
    except Exception as e:  # noqa: BLE001
        logger.debug("Không đọc được trạng thái lô %s: %s", batch_id, e)
        return False
