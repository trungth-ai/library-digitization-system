#!/usr/bin/env python3
"""
Khởi tạo quản trị viên đầu tiên (YC-QT-05 — ADR-012).

Bài toán con gà & quả trứng: cần quản trị viên để tạo người dùng, nhưng chưa có ai để tạo quản trị
viên. Giải bằng biến môi trường, chạy MỘT LẦN lúc API khởi động.

BA CHỐT AN TOÀN, vì "tài khoản admin mặc định" là một trong những nguyên nhân lộ hệ thống phổ biến nhất:
  1. Chỉ tạo khi CHƯA có tài khoản admin nào — không bao giờ ghi đè tài khoản đang dùng.
  2. Bắt buộc đổi mật khẩu ở lần đăng nhập đầu (`must_change_password=True`).
  3. Không có mật khẩu trong biến môi trường → KHÔNG tạo tài khoản (không tự sinh mật khẩu mặc định
     nào cả). Thà chưa có admin còn hơn có admin với mật khẩu ai cũng đoán được.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger("auth.bootstrap")

ENV_USER = "ADMIN_BOOTSTRAP_USER"
ENV_PASSWORD = "ADMIN_BOOTSTRAP_PASSWORD"
ENV_FULLNAME = "ADMIN_BOOTSTRAP_FULLNAME"


def ensure_admin() -> Optional[str]:
    """
    Tạo quản trị viên đầu tiên nếu cần. Trả về tên đăng nhập vừa tạo, hoặc `None` nếu không tạo gì.

    Không bao giờ ném ngoại lệ ra ngoài: API phải khởi động được kể cả khi bảng `users` chưa được di
    trú (mã mới + chưa chạy migration là tình huống bình thường trong lúc triển khai).
    """
    username = (os.getenv(ENV_USER) or "").strip()
    password = os.getenv(ENV_PASSWORD) or ""

    if not username:
        return None

    if not password:
        logger.error(
            "%s được đặt nhưng %s rỗng → KHÔNG tạo tài khoản quản trị. "
            "Đặt cả hai biến rồi khởi động lại (không có mật khẩu mặc định nào).",
            ENV_USER, ENV_PASSWORD,
        )
        return None

    try:
        from scripts.core import users
        from scripts.auth import policy

        # Chốt 1: đã có admin thì không làm gì
        existing_admins = users.list_users(role=policy.ROLE_ADMIN, limit=1)
        if existing_admins:
            logger.debug("Đã có tài khoản quản trị — bỏ qua khởi tạo")
            return None

        if users.get_user_by_username(username):
            logger.warning("Tài khoản '%s' đã tồn tại (không phải admin) — không tạo, không ghi đè",
                           username)
            return None

        users.create_user(
            username=username,
            full_name=(os.getenv(ENV_FULLNAME) or "Quản trị hệ thống").strip(),
            password=password,
            role=policy.ROLE_ADMIN,
            must_change_password=True,          # chốt 2
        )
        logger.warning(
            "ĐÃ TẠO tài khoản quản trị đầu tiên: '%s'. Đăng nhập và ĐỔI MẬT KHẨU ngay "
            "(hệ thống sẽ buộc đổi), rồi XÓA %s/%s khỏi cấu hình.",
            username, ENV_USER, ENV_PASSWORD,
        )
        return username

    except Exception as e:  # noqa: BLE001 - không được làm API không khởi động được
        logger.error("Không khởi tạo được tài khoản quản trị: %s "
                     "(bảng users đã được di trú chưa? chạy migration 003)", e)
        return None
