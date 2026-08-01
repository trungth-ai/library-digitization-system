#!/usr/bin/env python3
"""
Phiên đăng nhập lưu trong PostgreSQL (YC-QT-02 — ADR-012, QĐ-01 + QĐ-02).

VÌ SAO PHIÊN PHÍA MÁY CHỦ, KHÔNG JWT: thu hồi được ngay. Với JWT không trạng thái, một token đã phát
ra vẫn dùng được tới khi hết hạn — nghĩa là "vô hiệu hóa tài khoản" không có hiệu lực tức thì, đúng
lúc cần nó nhất (nhân sự rời cơ quan, tài khoản bị chiếm).

VÌ SAO POSTGRESQL, KHÔNG REDIS: Redis ở hệ này là hàng đợi, không bật `appendonly` → Redis restart
là đăng xuất toàn bộ. Số phiên rất nhỏ (một Trung tâm, vài chục người) nên PostgreSQL thừa sức.

TOKEN KHÔNG ĐƯỢC LƯU THÔ: DB chỉ giữ SHA-256 của token. Rò cơ sở dữ liệu không đồng nghĩa với chiếm
được phiên của người khác — cùng lý do không lưu mật khẩu thô.
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import scripts.db as db

logger = logging.getLogger("auth.sessions")

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "docuflow_session")
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "12"))
# 32 byte = 256 bit ngẫu nhiên: không dò được bằng vét cạn
TOKEN_BYTES = 32


def _hash_token(token: str) -> str:
    """
    Băm token bằng SHA-256 (KHÔNG phải PBKDF2 như mật khẩu).

    Khác biệt là có chủ đích: token đã là 256 bit ngẫu nhiên nên không cần làm chậm để chống vét cạn
    từ điển; mà kiểm phiên xảy ra ở MỌI request nên PBKDF2 600.000 vòng sẽ làm mỗi request chậm hàng
    trăm ms. Mật khẩu do người chọn (entropy thấp) thì bắt buộc phải làm chậm.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: int, ip: Optional[str] = None, user_agent: Optional[str] = None,
                   ttl_hours: Optional[int] = None) -> str:
    """
    Tạo phiên mới, trả về token THÔ (chỉ lần này) để đặt vào cookie. DB chỉ giữ bản băm.
    """
    token = secrets.token_urlsafe(TOKEN_BYTES)
    ttl = ttl_hours or SESSION_TTL_HOURS
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl)

    sql = """
        INSERT INTO user_sessions (token_hash, user_id, ip, user_agent, expires_at)
        VALUES (%s, %s, %s, %s, %s)
    """
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (_hash_token(token), user_id, ip,
                              (user_agent or "")[:500], expires_at))

    logger.info("Tạo phiên cho user_id=%s, hết hạn %s", user_id, expires_at.isoformat())
    return token


def resolve_session(token: str) -> Optional[Dict]:
    """
    Đổi token thành thông tin người dùng, hoặc `None` nếu phiên không dùng được.

    Một truy vấn JOIN duy nhất — chạy ở MỌI request nên phải rẻ. Điều kiện lọc gộp cả bốn lý do phiên
    không dùng được: bị thu hồi, hết hạn, tài khoản bị vô hiệu hóa, tài khoản đã xóa mềm. Kiểm tài
    khoản ngay trong câu truy vấn là điều làm cho "vô hiệu hóa tài khoản" có hiệu lực TỨC THÌ.
    """
    if not token:
        return None

    sql = """
        SELECT s.token_hash, s.expires_at, s.user_id,
               u.username, u.full_name, u.email, u.role, u.status AS user_status,
               u.must_change_password
        FROM user_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = %s
          AND s.status = 'active'
          AND s.revoked_at IS NULL
          AND s.expires_at > NOW()
          AND u.status = 'active'
    """
    import psycopg2.extras
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (_hash_token(token),))
            row = cur.fetchone()

    return dict(row) if row else None


def touch_session(token_hash: str) -> None:
    """
    Cập nhật `last_seen_at`. Tách khỏi `resolve_session` để nơi gọi quyết định có ghi hay không —
    ghi mỗi request là một lượt UPDATE cho mỗi lần bấm chuột, không đáng.
    """
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE user_sessions SET last_seen_at = NOW() WHERE token_hash = %s",
                    (token_hash,))
    except Exception as e:  # noqa: BLE001 - số liệu phụ, không được làm gãy request
        logger.debug("Không cập nhật được last_seen_at: %s", e)


def revoke_session(token: str) -> bool:
    """Đăng xuất một phiên (người dùng tự bấm đăng xuất)."""
    sql = """
        UPDATE user_sessions
        SET revoked_at = NOW(), status = 'revoked'
        WHERE token_hash = %s AND revoked_at IS NULL
    """
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (_hash_token(token),))
            return bool(cur.rowcount)


def revoke_all_for_user(user_id: int) -> int:
    """
    Thu hồi mọi phiên của một người (YC-QT-02).

    Gọi khi: quản trị viên thu hồi, đổi mật khẩu, đổi vai trò, vô hiệu hóa tài khoản. Đây là thứ mà
    JWT không trạng thái không làm được — lý do chính của QĐ-01.
    """
    sql = """
        UPDATE user_sessions
        SET revoked_at = NOW(), status = 'revoked'
        WHERE user_id = %s AND revoked_at IS NULL
    """
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user_id,))
                count = cur.rowcount
    except Exception as e:  # noqa: BLE001
        logger.error("Không thu hồi được phiên của user_id=%s: %s", user_id, e)
        return 0

    if count:
        logger.info("Đã thu hồi %d phiên của user_id=%s", count, user_id)
    return count


def list_sessions(user_id: Optional[int] = None, active_only: bool = True,
                  limit: int = 100) -> List[Dict]:
    """Phiên đang hoạt động, cho trang quản trị (YC-QT-07)."""
    conditions, params = [], []
    if user_id is not None:
        conditions.append("s.user_id = %s")
        params.append(user_id)
    if active_only:
        conditions.append("s.revoked_at IS NULL AND s.expires_at > NOW() AND s.status = 'active'")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    sql = f"""
        SELECT s.user_id, u.username, u.full_name, s.ip, s.user_agent,
               s.created_at, s.last_seen_at, s.expires_at, s.status,
               -- KHÔNG trả token_hash ra ngoài: dù đã băm, nó vẫn là thứ dùng để tra cứu phiên
               left(s.token_hash, 8) AS session_ref
        FROM user_sessions s
        JOIN users u ON u.id = s.user_id
        {where}
        ORDER BY s.last_seen_at DESC
        LIMIT %s
    """
    params.append(limit)

    import psycopg2.extras
    with db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def revoke_by_ref(session_ref: str) -> int:
    """
    Thu hồi một phiên theo `session_ref` (8 ký tự đầu của bản băm) từ trang quản trị.

    Dùng tiền tố thay vì token: trang quản trị không bao giờ nhìn thấy token thô, kể cả bản băm đầy đủ.
    """
    if not session_ref or len(session_ref) < 8:
        return 0
    sql = """
        UPDATE user_sessions
        SET revoked_at = NOW(), status = 'revoked'
        WHERE left(token_hash, 8) = %s AND revoked_at IS NULL
    """
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (session_ref[:8],))
            return cur.rowcount


def cleanup_expired(older_than_days: int = 30) -> int:
    """
    Dọn phiên đã hết hạn/thu hồi quá lâu (nối vào cơ chế dọn theo tuổi của YC-LG-07).

    Không dọn ngay khi hết hạn: giữ một thời gian để còn tra được "ai đăng nhập từ IP nào" khi cần
    điều tra sự cố.
    """
    sql = """
        DELETE FROM user_sessions
        WHERE (expires_at < NOW() - (%s || ' days')::interval)
           OR (revoked_at IS NOT NULL AND revoked_at < NOW() - (%s || ' days')::interval)
    """
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (older_than_days, older_than_days))
            return cur.rowcount
