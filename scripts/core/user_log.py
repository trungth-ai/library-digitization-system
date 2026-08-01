#!/usr/bin/env python3
"""
Nhật ký hành vi người dùng (YC-NK — sprint V4). Lớp thứ ba trong bốn lớp nhật ký.

TRẢ LỜI: "ai đã làm gì, lúc nào, từ đâu" — kể cả những thao tác KHÔNG chạm vào tài liệu nào:
đăng nhập, đăng xuất, sai mật khẩu, **bị từ chối quyền**, tìm kiếm, kết xuất báo cáo.

Phân biệt với hai bảng đã có:
    audit_log      thao tác NGHIỆP VỤ trên TÀI LIỆU, bất biến, giữ vĩnh viễn (YC-AU)
    system_events  sự cố HẠ TẦNG (mất Redis/DB), xóa được sau 90 ngày (ADR-009)
    user_activity  hành vi NGƯỜI DÙNG, không sửa được, giữ 365 ngày        ← module này

NGUYÊN TẮC: ghi nhật ký KHÔNG BAO GIỜ được làm hỏng nghiệp vụ chính — cùng cách làm của
`scripts/core/audit.py:55`. Mọi hàm ghi ở đây nuốt ngoại lệ và chỉ ghi log.
"""

import json
import logging
from typing import Dict, List, Optional

import scripts.db as db
from scripts.core import context

logger = logging.getLogger("core.user_log")

# ── Hằng hành động ────────────────────────────────────────────
ACTION_LOGIN = "login"
ACTION_LOGOUT = "logout"
ACTION_LOGIN_FAILED = "login_failed"
ACTION_LOCKED = "account_locked"
ACTION_PERMISSION_DENIED = "permission_denied"
ACTION_UNAUTHENTICATED = "unauthenticated"      # nấc shadow: request thiếu xác thực
ACTION_PASSWORD_CHANGE = "password_change"
ACTION_VIEW = "view"
ACTION_DOWNLOAD = "download"
ACTION_EXPORT = "export"

# ── Kết quả ───────────────────────────────────────────────────
RESULT_OK = "ok"
RESULT_DENIED = "denied"
RESULT_FAILED = "failed"


def log_activity(
    action: str,
    username: Optional[str] = None,
    user_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    result: str = RESULT_OK,
    detail: Optional[dict] = None,
) -> None:
    """
    Ghi một bản ghi hành vi. KHÔNG ném lỗi ra ngoài.

    `username` và `request_id` tự lấy từ ngữ cảnh nếu nơi gọi không truyền: nhờ vậy phần lớn nơi gọi
    chỉ cần nói *việc gì đã xảy ra*, không phải mang theo danh tính qua từng tầng.
    """
    sql = """
        INSERT INTO user_activity
            (user_id, username, action, resource_type, resource_id, ip, user_agent,
             request_id, result, detail)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    user_id,
                    username or context.get_actor(),
                    action, resource_type, resource_id, ip,
                    (user_agent or "")[:500] or None,
                    context.get_request_id(),
                    result,
                    json.dumps(detail, ensure_ascii=False) if detail else None,
                ))
    except Exception as e:  # noqa: BLE001 - nhật ký hỏng không được chặn nghiệp vụ
        logger.error("Ghi nhật ký người dùng thất bại (action=%s): %s", action, e)


def log_denied(username: str, method: str, path: str, role: Optional[str] = None,
               missing: Optional[List[str]] = None, ip: Optional[str] = None,
               user_agent: Optional[str] = None) -> None:
    """
    Ghi một lần BỊ TỪ CHỐI QUYỀN (YC-NK-03).

    Đây là tín hiệu an ninh quan trọng nhất trong bảng: người dùng thật rất ít khi gọi API mà họ
    không có quyền, nên một chuỗi 403 thường nghĩa là có gì đó bất thường — hoặc phân quyền đang
    cản trở công việc thật và cần xem lại.
    """
    log_activity(
        action=ACTION_PERMISSION_DENIED, username=username, result=RESULT_DENIED,
        resource_type="endpoint", resource_id=f"{method} {path}",
        ip=ip, user_agent=user_agent,
        detail={"role": role, "missing": list(missing or [])},
    )


def list_activity(
    username: Optional[str] = None,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    result: Optional[str] = None,
    ip: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict]:
    """Tra cứu nhật ký theo bộ lọc (YC-NK-05). Mới nhất trước."""
    conditions, params = [], []
    for column, value in (("username", username), ("user_id", user_id),
                          ("action", action), ("result", result), ("ip", ip)):
        if value is not None:
            conditions.append(f"{column} = %s")
            params.append(value)
    if date_from:
        conditions.append("created_at >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("created_at <= %s")
        params.append(date_to)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT id, user_id, username, action, resource_type, resource_id,
               ip, user_agent, request_id, result, detail, created_at
        FROM user_activity
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


def count_failed_logins(username: str, minutes: int = 5) -> int:
    """Số lần đăng nhập sai gần đây của một tài khoản — đầu vào cho cảnh báo bất thường (YC-NK-08)."""
    sql = """
        SELECT COUNT(*) FROM user_activity
        WHERE username = %s AND action = %s
          AND created_at > NOW() - (%s || ' minutes')::interval
    """
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (username, ACTION_LOGIN_FAILED, minutes))
                return int(cur.fetchone()[0])
    except Exception as e:  # noqa: BLE001
        logger.warning("Không đếm được số lần đăng nhập sai: %s", e)
        return 0


def document_timeline(document_id: str) -> List[Dict]:
    """
    Dòng thời gian đầy đủ của MỘT tài liệu (YC-NK-07): gộp bốn nguồn thành một danh sách theo thời gian.

    VÌ SAO ĐÁNG LÀM: bốn nguồn dữ liệu đã tồn tại nhưng nằm rời rạc, nên câu hỏi "tài liệu này đã qua
    tay ai, model nào trích, ai sửa gì, ai duyệt" phải mở bốn chỗ và tự ghép theo dấu thời gian.
    Một truy vấn UNION biến việc đó thành một màn hình — công sức nhỏ, đổi hẳn khả năng giải trình
    khi có tranh chấp về một tài liệu cụ thể.
    """
    sql = """
        SELECT created_at, 'audit'    AS nguon, action AS su_kien, actor AS nguoi,
               COALESCE(field_key, '') AS chi_tiet,
               COALESCE(old_value, '') AS gia_tri_cu, COALESCE(new_value, '') AS gia_tri_moi
        FROM audit_log WHERE document_id = %(doc)s

        UNION ALL
        SELECT created_at, 'nguoi_dung', action, COALESCE(username, ''),
               COALESCE(resource_type, ''), '', COALESCE(result, '')
        FROM user_activity WHERE resource_id = %(doc)s

        UNION ALL
        SELECT created_at, 'model', 'extract', COALESCE(provider, ''),
               COALESCE(model, ''), '', COALESCE(status, '')
        FROM model_calls WHERE document_id = %(doc)s

        UNION ALL
        SELECT created_at, 'ocr', 'ocr', '',
               COALESCE(engine, ''), '', COALESCE(status, '')
        FROM ocr_runs WHERE document_id = %(doc)s

        ORDER BY created_at ASC
    """
    import psycopg2.extras
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            try:
                cur.execute(sql, {"doc": document_id})
                return [dict(r) for r in cur.fetchall()]
            except Exception as e:  # noqa: BLE001
                # `ocr_runs` thuộc sprint V2, có thể chưa được di trú. Lùi về ba nguồn còn lại thay
                # vì để cả dòng thời gian hỏng chỉ vì thiếu một bảng.
                conn.rollback()
                logger.info("Dòng thời gian lùi về 3 nguồn (thiếu bảng: %s)", e)
                cur.execute(sql.split("UNION ALL\n        SELECT created_at, 'ocr'")[0]
                            + "ORDER BY created_at ASC", {"doc": document_id})
                return [dict(r) for r in cur.fetchall()]
