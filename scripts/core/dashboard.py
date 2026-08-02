#!/usr/bin/env python3
"""
Bảng điều khiển theo dõi công việc (YC-DB — sprint V7).

HAI CÂU HỎI, HAI ĐỐI TƯỢNG:
  • Cán bộ:   "hôm nay tôi phải làm gì?"
  • Quản lý:  "việc đang tắc ở đâu, ai đang quá tải?"

PHÂN BIỆT VỚI HAI TRANG ĐÃ CÓ — cả ba cùng tồn tại, không thay thế nhau:
  `/bao-cao`   phân tích LỊCH SỬ (thông lượng, tỉ lệ theo chế độ)
  `/cong-cu`   sức khỏe KỸ THUẬT (thành phần nào sống, thời gian xử lý p50/p95)
  `/bang-dieu-khien`  điều hành CÔNG VIỆC HÀNG NGÀY  ← module này

🔴 RÀNG BUỘC QUAN TRỌNG NHẤT (KT-DB-02): số liệu ở đây phải KHỚP với `/api/v2/stats` và `/bao-cao`.
Hai màn hình mâu thuẫn nhau còn tệ hơn một màn hình không có — người dùng mất niềm tin vào cả hai và
quay lại đếm tay. Vì vậy mọi truy vấn đếm tài liệu ở đây đều lặp lại đúng bộ lọc của `get_stats()`:
**loại trừ `status = 'deleted'`**.
"""

import logging
import os
from typing import Dict, List, Optional

import scripts.db as db

logger = logging.getLogger("core.dashboard")

# Ngưỡng SLA theo trạng thái (giờ). Tài liệu nằm quá lâu ở một trạng thái là dấu hiệu tắc nghẽn —
# nhưng "quá lâu" khác nhau tùy trạng thái: chờ hàng đợi vài giờ là bình thường, chờ duyệt vài ngày
# thì không.
SLA_HOURS = {
    "queued": int(os.getenv("SLA_HOURS_QUEUED", "6")),
    "ocr": int(os.getenv("SLA_HOURS_OCR", "3")),
    "extracting": int(os.getenv("SLA_HOURS_EXTRACTING", "2")),
    "exporting": int(os.getenv("SLA_HOURS_EXPORTING", "2")),
    # Tài liệu đã xong nhưng cần cán bộ xem lại — đây là chỗ hay tồn đọng nhất trong thực tế
    "needs_review": int(os.getenv("SLA_HOURS_REVIEW", "72")),
}

# Bộ lọc dùng CHUNG với get_stats() — nếu hai nơi lọc khác nhau thì số sẽ vênh (KT-DB-02)
NOT_DELETED = "status <> 'deleted'"


def _dict_cursor(conn):
    import psycopg2.extras
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


# ─────────────────────────────────────────────────────────────
# VIỆC CỦA TÔI (YC-DB-01)
# ─────────────────────────────────────────────────────────────

def my_work(user_id: Optional[int], username: Optional[str] = None) -> Dict:
    """
    Việc của một cán bộ cụ thể: tôi tải lên gì, gì đang chờ tôi duyệt, tôi đã duyệt bao nhiêu hôm nay.

    `user_id=None` (chưa bật xác thực, hoặc chủ thể chưa đăng nhập) → trả về số liệu TOÀN HỆ THỐNG
    kèm cờ `theo_ca_nhan=False`. Trả về rỗng sẽ khiến trang trông như hỏng ở nấc `AUTH_MODE=off`,
    còn trả số toàn hệ thống thì trang vẫn có ích và nói rõ đây không phải số của riêng ai.
    """
    if user_id is None:
        return {**_system_wide_work(), "theo_ca_nhan": False}

    sql = f"""
        SELECT
            COUNT(*) FILTER (WHERE uploaded_by = %(uid)s
                             AND status IN ('queued','ocr','extracting','exporting'))
                AS toi_tai_len_dang_xu_ly,
            COUNT(*) FILTER (WHERE uploaded_by = %(uid)s AND status = 'failed')
                AS toi_tai_len_bi_loi,
            COUNT(*) FILTER (WHERE needs_review AND status = 'completed'
                             AND (assigned_to = %(uid)s OR assigned_to IS NULL))
                AS cho_toi_duyet,
            COUNT(*) FILTER (WHERE assigned_to = %(uid)s AND needs_review AND status = 'completed')
                AS duoc_giao_cho_toi
        FROM documents
        WHERE {NOT_DELETED}
    """
    sql_today = """
        SELECT COUNT(DISTINCT document_id) AS toi_duyet_hom_nay
        FROM audit_log
        WHERE action = 'confirm' AND actor = %(username)s
          AND created_at >= date_trunc('day', NOW())
    """

    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute(sql, {"uid": user_id})
            result = dict(cur.fetchone() or {})
            try:
                cur.execute(sql_today, {"username": username})
                result.update(dict(cur.fetchone() or {}))
            except Exception:  # noqa: BLE001
                conn.rollback()
                result["toi_duyet_hom_nay"] = None

    result["theo_ca_nhan"] = True
    return result


def _system_wide_work() -> Dict:
    """Số liệu toàn hệ thống — dùng khi chưa có danh tính người dùng."""
    sql = f"""
        SELECT
            COUNT(*) FILTER (WHERE status IN ('queued','ocr','extracting','exporting'))
                AS toi_tai_len_dang_xu_ly,
            COUNT(*) FILTER (WHERE status = 'failed')          AS toi_tai_len_bi_loi,
            COUNT(*) FILTER (WHERE needs_review AND status = 'completed') AS cho_toi_duyet,
            0 AS duoc_giao_cho_toi
        FROM documents
        WHERE {NOT_DELETED}
    """
    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute(sql)
            row = dict(cur.fetchone() or {})
    row["toi_duyet_hom_nay"] = None
    return row


# ─────────────────────────────────────────────────────────────
# CẢNH BÁO SLA (YC-DB-04)
# ─────────────────────────────────────────────────────────────

def sla_breaches(limit: int = 50) -> Dict:
    """
    Tài liệu nằm quá lâu ở một trạng thái (YC-DB-04).

    VÌ SAO ĐÁNG LÀM: tài liệu chờ duyệt ba tuần không gây ra lỗi nào cả — nó chỉ nằm im. Không có
    cảnh báo thì cách duy nhất phát hiện là ai đó tình cờ lọc đúng bộ lọc.

    Đo bằng `updated_at`, KHÔNG phải `created_at`: câu hỏi là "nằm ở TRẠNG THÁI NÀY bao lâu rồi",
    mà một tài liệu tạo từ tháng trước và vừa chuyển sang chờ duyệt hôm nay thì chưa quá hạn.
    """
    # Xây điều kiện từ bảng ngưỡng: mỗi trạng thái một ngưỡng riêng
    conditions = []
    params: Dict = {}
    for index, (status, hours) in enumerate(SLA_HOURS.items()):
        key = f"h{index}"
        params[key] = hours
        if status == "needs_review":
            conditions.append(
                f"(needs_review AND status = 'completed' "
                f"AND updated_at < NOW() - (%({key})s || ' hours')::interval)")
        else:
            conditions.append(
                f"(status = '{status}' AND updated_at < NOW() - (%({key})s || ' hours')::interval)")

    where = " OR ".join(conditions)

    sql_count = f"SELECT COUNT(*) AS so_luong FROM documents WHERE {NOT_DELETED} AND ({where})"
    sql_list = f"""
        SELECT id, filename, status, needs_review, review_note, updated_at,
               ROUND(EXTRACT(EPOCH FROM (NOW() - updated_at)) / 3600) AS gio_ton_dong
        FROM documents
        WHERE {NOT_DELETED} AND ({where})
        ORDER BY updated_at ASC
        LIMIT %(limit)s
    """

    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute(sql_count, params)
            total = (cur.fetchone() or {}).get("so_luong", 0)
            cur.execute(sql_list, {**params, "limit": limit})
            rows = [dict(r) for r in cur.fetchall()]

    for row in rows:
        if row.get("updated_at"):
            row["updated_at"] = row["updated_at"].isoformat()
        row["gio_ton_dong"] = int(row["gio_ton_dong"] or 0)

    return {"tong_so": total, "danh_sach": rows, "nguong_gio": dict(SLA_HOURS)}


# ─────────────────────────────────────────────────────────────
# NĂNG SUẤT THEO CÁN BỘ (YC-DB-05 — công khai theo QĐ-06)
# ─────────────────────────────────────────────────────────────

def staff_workload(days: int = 7) -> Dict:
    """
    Năng suất duyệt theo từng cán bộ (QĐ-06: số liệu CÔNG KHAI).

    ⚠️ HAI RÀNG BUỘC BẮT BUỘC theo quyết định của Trung tâm — số liệu minh bạch chỉ có ích khi được
    đọc đúng:

      1. Kèm **bối cảnh**, không chỉ số đếm: số trang đã duyệt và tỉ lệ trường phải sửa. Một công văn
         2 trang và một khóa luận 200 trang đều là "1 tài liệu" nếu chỉ đếm đầu mục.
      2. Kèm **ghi chú mục đích** ngay trong dữ liệu trả về, để giao diện không thể quên hiển thị.

    Vì vậy `so_tai_lieu` KHÔNG so sánh trực tiếp được giữa các cán bộ, và điều đó được nói rõ ra.
    """
    sql = """
        SELECT a.actor                          AS can_bo,
               COUNT(DISTINCT a.document_id)    AS so_tai_lieu,
               COALESCE(SUM(o.pages), 0)        AS so_trang,
               MIN(a.created_at)                AS lan_dau,
               MAX(a.created_at)                AS lan_cuoi
        FROM audit_log a
        LEFT JOIN LATERAL (
            SELECT pages FROM ocr_runs r WHERE r.document_id = a.document_id LIMIT 1
        ) o ON TRUE
        WHERE a.action = 'confirm'
          AND a.created_at > NOW() - (%(days)s || ' days')::interval
          AND a.actor IS NOT NULL
        GROUP BY a.actor
        ORDER BY so_tai_lieu DESC
    """
    sql_edits = """
        SELECT actor AS can_bo, COUNT(*) AS so_truong_da_sua
        FROM audit_log
        WHERE action = 'edit_field'
          AND created_at > NOW() - (%(days)s || ' days')::interval
          AND actor IS NOT NULL
        GROUP BY actor
    """

    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            try:
                cur.execute(sql, {"days": days})
                rows = [dict(r) for r in cur.fetchall()]
            except Exception as e:  # noqa: BLE001 - `ocr_runs` có thể chưa di trú (migration 005)
                conn.rollback()
                logger.info("Năng suất lùi về bản không có số trang: %s", e)
                cur.execute("""
                    SELECT actor AS can_bo, COUNT(DISTINCT document_id) AS so_tai_lieu,
                           0 AS so_trang, MIN(created_at) AS lan_dau, MAX(created_at) AS lan_cuoi
                    FROM audit_log
                    WHERE action = 'confirm'
                      AND created_at > NOW() - (%(days)s || ' days')::interval
                      AND actor IS NOT NULL
                    GROUP BY actor ORDER BY so_tai_lieu DESC
                """, {"days": days})
                rows = [dict(r) for r in cur.fetchall()]

            cur.execute(sql_edits, {"days": days})
            edits = {r["can_bo"]: r["so_truong_da_sua"] for r in cur.fetchall()}

    for row in rows:
        row["so_truong_da_sua"] = edits.get(row["can_bo"], 0)
        for field in ("lan_dau", "lan_cuoi"):
            if row.get(field):
                row[field] = row[field].isoformat()

    return {
        "so_ngay": days,
        "can_bo": rows,
        # Ghi chú nằm TRONG dữ liệu để giao diện không thể quên hiển thị (QĐ-06)
        "ghi_chu": (
            "Số liệu vận hành để cân đối công việc, KHÔNG phải bảng xếp hạng thi đua. "
            "Tài liệu có độ khó rất khác nhau — một công văn 2 trang và một khóa luận 200 trang "
            "đều tính là 1 tài liệu — nên số tài liệu/ngày không so sánh trực tiếp được giữa các cán bộ."
        ),
    }


# ─────────────────────────────────────────────────────────────
# TIẾN ĐỘ LÔ & TỔNG QUAN
# ─────────────────────────────────────────────────────────────

def active_batches(limit: int = 10) -> List[Dict]:
    """Các lô đang chạy hoặc tạm dừng, kèm tiến độ tính sẵn (YC-DB-03)."""
    sql = """
        SELECT id, name, status, total_files, done_files, failed_files, skipped_files,
               created_at, source
        FROM batches
        WHERE status IN ('running', 'paused')
        ORDER BY created_at DESC
        LIMIT %s
    """
    try:
        with db.get_conn() as conn:
            with _dict_cursor(conn) as cur:
                cur.execute(sql, (limit,))
                rows = [dict(r) for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001 - chưa chạy migration 006
        logger.debug("Chưa có bảng lô: %s", e)
        return []

    for row in rows:
        if row.get("created_at"):
            row["created_at"] = row["created_at"].isoformat()
        total = row.get("total_files") or 0
        xong = ((row.get("done_files") or 0) + (row.get("failed_files") or 0)
                + (row.get("skipped_files") or 0))
        row["tien_do_phan_tram"] = round(xong * 100 / total) if total else 0
        row["con_lai"] = max(0, total - xong)

    return rows


def summary() -> Dict:
    """
    Tổng quan hôm nay + tồn đọng.

    Dùng ĐÚNG bộ lọc của `get_stats()` (loại `status='deleted'`) để hai màn hình không vênh nhau —
    ràng buộc KT-DB-02.
    """
    sql = f"""
        SELECT
            COUNT(*) FILTER (WHERE created_at >= date_trunc('day', NOW()))    AS nap_hom_nay,
            COUNT(*) FILTER (WHERE status = 'completed'
                             AND finished_at >= date_trunc('day', NOW()))     AS xong_hom_nay,
            COUNT(*) FILTER (WHERE status = 'failed'
                             AND finished_at >= date_trunc('day', NOW()))     AS loi_hom_nay,
            COUNT(*) FILTER (WHERE needs_review AND status = 'completed')     AS cho_duyet,
            COUNT(*) FILTER (WHERE status IN ('queued','ocr','extracting','exporting'))
                                                                              AS dang_xu_ly,
            COUNT(*) FILTER (WHERE dspace_status = 'uploaded')                AS da_day_dspace
        FROM documents
        WHERE {NOT_DELETED}
    """
    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute(sql)
            return dict(cur.fetchone() or {})
