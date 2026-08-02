#!/usr/bin/env python3
"""
Truy vấn người dùng, vai trò, quyền (YC-QT — ADR-012). Dùng connection pool của `scripts.db`.

Theo đúng mẫu của `scripts/core/audit.py`: import `psycopg2.extras` BÊN TRONG hàm để module này
import được trên máy chưa cài driver, và không phình `scripts/db.py` (đã 1000 dòng).

NGUYÊN TẮC AN TOÀN trong module này:
  - Không bao giờ trả `password_hash` ra ngoài trong hàm dùng cho API (`_PUBLIC_COLUMNS`).
  - Xóa MỀM, không xóa cứng (YC-QT-08) — `audit_log` tham chiếu tới người dùng.
  - Mọi truy vấn theo tên đăng nhập chỉ lấy tài khoản `status='active'`, trừ hàm quản trị.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set

import scripts.db as db
from scripts.auth import policy
from scripts.core import passwords

logger = logging.getLogger("core.users")

# Cột an toàn để trả ra API — cố ý KHÔNG có `password_hash`
_PUBLIC_COLUMNS = """
    id, username, email, full_name, role, must_change_password,
    failed_attempts, locked_until, last_login_at, last_login_ip,
    status, created_at, updated_at
"""


def _dict_cursor(conn):
    import psycopg2.extras
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


# ─────────────────────────────────────────────────────────────
# ĐỌC
# ─────────────────────────────────────────────────────────────

def get_user_by_username(username: str, include_hash: bool = False) -> Optional[Dict]:
    """
    Lấy người dùng theo tên đăng nhập. Chỉ tài khoản chưa bị xóa mềm.

    `include_hash=True` CHỈ dùng cho đường xác thực — không bao giờ cho đường API.
    Tài khoản `disabled` vẫn trả về (kèm `status`) để thông báo lỗi nói đúng lý do "đã bị vô hiệu hóa"
    thay vì "sai mật khẩu" — nhầm hai thứ này làm người dùng gọi hỗ trợ vô ích.
    """
    columns = _PUBLIC_COLUMNS + (", password_hash" if include_hash else "")
    sql = f"SELECT {columns} FROM users WHERE lower(username) = lower(%s) AND status <> 'deleted'"
    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute(sql, (username,))
            row = cur.fetchone()
            return dict(row) if row else None


def get_user(user_id: int) -> Optional[Dict]:
    sql = f"SELECT {_PUBLIC_COLUMNS} FROM users WHERE id = %s AND status <> 'deleted'"
    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute(sql, (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def list_users(status: Optional[str] = None, role: Optional[str] = None,
               limit: int = 100, offset: int = 0) -> List[Dict]:
    """Danh sách người dùng cho trang quản trị. Mặc định ẩn tài khoản đã xóa mềm."""
    conditions, params = ["status <> 'deleted'"], []
    if status:
        conditions = [f"status = %s"]
        params.append(status)
    if role:
        conditions.append("role = %s")
        params.append(role)

    sql = f"""
        SELECT {_PUBLIC_COLUMNS} FROM users
        WHERE {' AND '.join(conditions)}
        ORDER BY username
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def count_users(status: Optional[str] = None) -> int:
    sql = "SELECT COUNT(*) FROM users WHERE status <> 'deleted'"
    params = []
    if status:
        sql = "SELECT COUNT(*) FROM users WHERE status = %s"
        params = [status]
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return int(cur.fetchone()[0])


def get_role_permissions(role: str) -> Set[str]:
    """
    Quyền của một vai trò, đọc từ DB (nguồn chân lý lúc chạy — YC-QT-09).

    Nếu bảng chưa được di trú hoặc chưa seed thì LÙI về bảng trong mã (`policy.py`). Đây là lựa chọn
    có chủ đích: hệ thống phải chạy được ngay sau khi cập nhật mã mà chưa chạy migration, thay vì
    mọi người mất hết quyền — nhưng có ghi cảnh báo để không âm thầm chạy sai nguồn cấu hình.
    """
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT permission FROM role_permissions WHERE role_code = %s", (role,))
                rows = {r[0] for r in cur.fetchall()}
        if rows:
            return rows
        logger.warning("Vai trò '%s' chưa có quyền nào trong DB → dùng bảng quyền trong mã", role)
    except Exception as e:  # noqa: BLE001
        logger.warning("Không đọc được quyền từ DB (%s) → dùng bảng quyền trong mã", e)

    return set(policy.permissions_for_role(role))


def list_roles() -> List[Dict]:
    """Vai trò + quyền của từng vai trò, cho trang quản trị."""
    sql = """
        SELECT r.code, r.label, r.description, r.is_system, r.sort_order,
               COALESCE(array_agg(rp.permission ORDER BY rp.permission)
                        FILTER (WHERE rp.permission IS NOT NULL), '{}') AS permissions
        FROM roles r
        LEFT JOIN role_permissions rp ON rp.role_code = r.code
        WHERE r.status = 'active'
        GROUP BY r.code, r.label, r.description, r.is_system, r.sort_order
        ORDER BY r.sort_order
    """
    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


# ─────────────────────────────────────────────────────────────
# GHI
# ─────────────────────────────────────────────────────────────

def create_user(username: str, full_name: str, password: str, role: str,
                email: Optional[str] = None, must_change_password: bool = True,
                created_by: Optional[int] = None) -> Dict:
    """
    Tạo người dùng. Kiểm chính sách mật khẩu TRƯỚC khi băm.

    `must_change_password=True` là mặc định: mật khẩu do quản trị viên đặt thì quản trị viên biết —
    người dùng phải đổi ở lần đăng nhập đầu để chỉ họ biết mật khẩu của mình (YC-QT-05).
    """
    if role not in policy.ALL_ROLES:
        raise ValueError(f"Vai trò không hợp lệ: {role}")

    check = passwords.check_policy(password, username=username, full_name=full_name)
    if not check.ok:
        raise ValueError("; ".join(check.errors))

    sql = """
        INSERT INTO users (username, email, full_name, password_hash, role,
                           must_change_password, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (username.strip(), email, full_name.strip(),
                              passwords.hash_password(password), role,
                              must_change_password, created_by))
            user_id = cur.fetchone()[0]

    logger.info("Đã tạo người dùng '%s' (vai trò %s)", username, role)
    return get_user(user_id)


def set_password(user_id: int, password: str, must_change: bool = False) -> None:
    """Đặt mật khẩu mới. Kiểm chính sách trước khi băm; thu hồi TOÀN BỘ phiên hiện có của người này."""
    user = get_user(user_id)
    if not user:
        raise ValueError("Không tìm thấy người dùng")

    check = passwords.check_policy(password, username=user["username"],
                                   full_name=user["full_name"])
    if not check.ok:
        raise ValueError("; ".join(check.errors))

    sql = """
        UPDATE users
        SET password_hash = %s, must_change_password = %s, failed_attempts = 0, locked_until = NULL
        WHERE id = %s
    """
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (passwords.hash_password(password), must_change, user_id))

    # Đổi mật khẩu PHẢI đăng xuất mọi phiên khác: nếu không, kẻ đã chiếm được phiên vẫn giữ được
    # quyền truy cập kể cả sau khi chủ tài khoản đổi mật khẩu — đúng tình huống người ta đổi mật khẩu.
    from scripts.auth import sessions
    sessions.revoke_all_for_user(user_id)


def update_user(user_id: int, full_name: Optional[str] = None, email: Optional[str] = None,
                role: Optional[str] = None, status: Optional[str] = None) -> Optional[Dict]:
    """Cập nhật thông tin/vai trò/trạng thái. Chỉ đổi trường được truyền vào."""
    if role is not None and role not in policy.ALL_ROLES:
        raise ValueError(f"Vai trò không hợp lệ: {role}")
    if status is not None and status not in ("active", "disabled"):
        raise ValueError("Trạng thái chỉ nhận 'active' hoặc 'disabled'")

    sets, params = [], []
    for column, value in (("full_name", full_name), ("email", email),
                          ("role", role), ("status", status)):
        if value is not None:
            sets.append(f"{column} = %s")
            params.append(value)
    if not sets:
        return get_user(user_id)

    params.append(user_id)
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = %s", params)

    # Vô hiệu hóa hoặc hạ quyền thì phải đăng xuất ngay, không chờ phiên hết hạn
    if status == "disabled" or role is not None:
        from scripts.auth import sessions
        sessions.revoke_all_for_user(user_id)

    return get_user(user_id)


def soft_delete_user(user_id: int) -> bool:
    """
    Xóa MỀM (YC-QT-08). KHÔNG xóa cứng: `audit_log` tham chiếu tới người dùng này, và nhật ký kiểm
    toán phải truy được trách nhiệm kể cả với người đã rời cơ quan.
    """
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET status = 'deleted' WHERE id = %s AND status <> 'deleted'",
                        (user_id,))
            changed = cur.rowcount

    if changed:
        from scripts.auth import sessions
        sessions.revoke_all_for_user(user_id)
    return bool(changed)


# ─────────────────────────────────────────────────────────────
# KHÓA TÀI KHOẢN SAU N LẦN SAI (YC-QT-06)
# ─────────────────────────────────────────────────────────────

def register_failed_login(username: str, max_attempts: int, lock_minutes: int) -> Optional[datetime]:
    """
    Ghi một lần đăng nhập sai. Đủ `max_attempts` thì khóa `lock_minutes` phút.

    Trả về thời điểm hết khóa nếu vừa bị khóa, `None` nếu chưa. Khóa TẠM THỜI (không khóa vĩnh viễn):
    khóa vĩnh viễn biến một lần gõ sai thành một cuộc gọi hỗ trợ, và tạo ra cách để người ngoài khóa
    tài khoản người khác chỉ bằng cách gõ sai mật khẩu.
    """
    sql = """
        UPDATE users
        SET failed_attempts = failed_attempts + 1,
            locked_until = CASE
                WHEN failed_attempts + 1 >= %(max_attempts)s
                THEN NOW() + (%(lock_minutes)s || ' minutes')::interval
                ELSE locked_until
            END
        WHERE lower(username) = lower(%(username)s) AND status = 'active'
        RETURNING failed_attempts, locked_until
    """
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"username": username, "max_attempts": max_attempts,
                              "lock_minutes": lock_minutes})
            row = cur.fetchone()

    if not row:
        return None
    attempts, locked_until = row
    if attempts >= max_attempts:
        logger.warning("Tài khoản '%s' bị khóa tới %s sau %d lần đăng nhập sai",
                       username, locked_until, attempts)
        return locked_until
    return None


def register_successful_login(user_id: int, ip: Optional[str] = None) -> None:
    """Đặt lại bộ đếm sai + ghi thời điểm/IP đăng nhập."""
    sql = """
        UPDATE users
        SET failed_attempts = 0, locked_until = NULL, last_login_at = NOW(), last_login_ip = %s
        WHERE id = %s
    """
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (ip, user_id))


def unlock_user(user_id: int) -> None:
    """Mở khóa thủ công (quản trị viên) — không phải chờ hết thời gian khóa."""
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = %s",
                (user_id,))


def is_locked(user: Dict, now: Optional[datetime] = None) -> bool:
    """Tài khoản có đang bị khóa tạm thời không?"""
    locked_until = user.get("locked_until")
    if not locked_until:
        return False
    now = now or datetime.now(timezone.utc)
    return locked_until > now
