#!/usr/bin/env python3
"""
Nền tảng xác thực NỘI BỘ: tên đăng nhập + mật khẩu trong PostgreSQL (YC-QT-10 — ADR-012 mục 7).

Interface `authenticate(username, password) -> AuthOutcome` được viết TRƯỚC, hiện thực `local` làm
trước. Thêm LDAP/AD của Nhà trường về sau chỉ cần một lớp hiện thực mới + một dòng trong `BACKENDS`,
KHÔNG sửa nơi gọi — cùng mẫu đã dùng thành công cho lớp mô hình (YC-MP-08).

THÔNG BÁO LỖI: nói đủ để người dùng tự xử lý, không nói đủ để người ngoài dò tài khoản.
  - Sai tên HOẶC sai mật khẩu → cùng một thông báo (không tiết lộ tên nào tồn tại).
  - Bị khóa / bị vô hiệu hóa → nói rõ, vì đây là thông tin người dùng thật CẦN biết và người ngoài
    không khai thác được (họ vẫn phải có mật khẩu đúng để làm gì đó).
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from scripts.core import passwords, users

logger = logging.getLogger("auth.local")

LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCK_MINUTES = int(os.getenv("LOGIN_LOCK_MINUTES", "15"))

# Lý do thất bại — dùng mã để nhật ký người dùng phân loại được, kèm thông báo tiếng Việt cho giao diện
FAIL_BAD_CREDENTIALS = "bad_credentials"
FAIL_LOCKED = "locked"
FAIL_DISABLED = "disabled"

MESSAGES = {
    FAIL_BAD_CREDENTIALS: "Tên đăng nhập hoặc mật khẩu không đúng",
    FAIL_LOCKED: "Tài khoản đang tạm bị khóa do nhập sai mật khẩu nhiều lần",
    FAIL_DISABLED: "Tài khoản đã bị vô hiệu hóa. Liên hệ quản trị viên",
}


@dataclass
class AuthOutcome:
    """Kết quả xác thực. `user` chỉ có khi thành công và KHÔNG chứa `password_hash`."""
    ok: bool
    user: Optional[Dict] = None
    reason: Optional[str] = None
    message: Optional[str] = None
    locked_until: Optional[datetime] = None

    @property
    def must_change_password(self) -> bool:
        return bool(self.user and self.user.get("must_change_password"))


def authenticate(username: str, password: str, ip: Optional[str] = None) -> AuthOutcome:
    """
    Xác thực bằng tên đăng nhập + mật khẩu.

    Thứ tự kiểm tra có chủ đích: trạng thái tài khoản và khóa được kiểm TRƯỚC khi so mật khẩu, để một
    tài khoản đã bị vô hiệu hóa không thể dùng việc "mật khẩu đúng" làm tín hiệu nào cả.
    """
    if not username or not password:
        return AuthOutcome(False, reason=FAIL_BAD_CREDENTIALS,
                           message=MESSAGES[FAIL_BAD_CREDENTIALS])

    user = users.get_user_by_username(username, include_hash=True)

    if user is None:
        # Vẫn băm một lần để thời gian phản hồi không tiết lộ "tên này không tồn tại".
        # Không làm việc này thì đo thời gian là dò được danh sách tài khoản có thật.
        passwords.verify_password(password, passwords.hash_password("khong-ton-tai", iterations=1000))
        logger.info("Đăng nhập thất bại: tên '%s' không tồn tại (IP %s)", username, ip)
        return AuthOutcome(False, reason=FAIL_BAD_CREDENTIALS,
                           message=MESSAGES[FAIL_BAD_CREDENTIALS])

    if user["status"] != "active":
        return AuthOutcome(False, reason=FAIL_DISABLED, message=MESSAGES[FAIL_DISABLED])

    if users.is_locked(user):
        return AuthOutcome(False, reason=FAIL_LOCKED, locked_until=user["locked_until"],
                           message=_locked_message(user["locked_until"]))

    if not passwords.verify_password(password, user["password_hash"]):
        locked_until = users.register_failed_login(
            username, max_attempts=LOGIN_MAX_ATTEMPTS, lock_minutes=LOGIN_LOCK_MINUTES)
        if locked_until:
            return AuthOutcome(False, reason=FAIL_LOCKED, locked_until=locked_until,
                               message=_locked_message(locked_until))
        return AuthOutcome(False, reason=FAIL_BAD_CREDENTIALS,
                           message=MESSAGES[FAIL_BAD_CREDENTIALS])

    users.register_successful_login(user["id"], ip=ip)

    # Nâng cấp bản băm khi số vòng lặp đã được nâng — mỗi lần đăng nhập đúng là một cơ hội nâng cấp,
    # không cần đặt lại mật khẩu hàng loạt.
    if passwords.needs_rehash(user["password_hash"]):
        try:
            users.set_password(user["id"], password,
                               must_change=user.get("must_change_password", False))
            logger.info("Đã nâng cấp bản băm mật khẩu của '%s'", username)
        except Exception as e:  # noqa: BLE001 - nâng cấp hỏng không được chặn việc đăng nhập
            logger.warning("Không nâng cấp được bản băm của '%s': %s", username, e)

    user.pop("password_hash", None)          # không để hash đi ra ngoài module này
    return AuthOutcome(True, user=user)


def _locked_message(locked_until) -> str:
    """Thông báo khóa có kèm SỐ PHÚT còn lại — 'hãy thử lại sau' không giúp người dùng quyết định gì."""
    if not locked_until:
        return MESSAGES[FAIL_LOCKED]
    remaining = locked_until - datetime.now(timezone.utc)
    minutes = max(1, int(remaining.total_seconds() // 60) + 1)
    return f"{MESSAGES[FAIL_LOCKED]}. Vui lòng thử lại sau {minutes} phút"


# Bảng nền tảng xác thực — thêm LDAP/OIDC là thêm MỘT dòng ở đây (YC-QT-10)
BACKENDS = {
    "local": authenticate,
}


def get_backend(name: Optional[str] = None):
    """
    Lấy nền tảng xác thực theo `AUTH_BACKEND`. Tên lạ → lùi về `local` kèm cảnh báo.

    Lùi về `local` thay vì ném lỗi: cấu hình sai không được làm cả hệ thống không đăng nhập được.
    """
    name = (name or os.getenv("AUTH_BACKEND", "local")).strip().lower()
    if name not in BACKENDS:
        logger.warning("AUTH_BACKEND='%s' chưa được hiện thực → dùng 'local'", name)
        name = "local"
    return BACKENDS[name]
