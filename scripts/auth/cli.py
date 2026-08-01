#!/usr/bin/env python3
"""
Cứu hộ tài khoản từ trong container (ADR-012 — hệ quả ⚠️ "mất mật khẩu quản trị khóa cả hệ thống").

VÌ SAO CẦN: khi phân quyền đã bật và không ai đăng nhập được bằng tài khoản quản trị, không còn đường
nào vào hệ thống qua giao diện. Không có lệnh này thì cách duy nhất là sửa trực tiếp bằng SQL — việc
đó không có ghi audit và rất dễ làm sai.

Mọi thao tác ở đây ĐỀU ghi `audit_log` với `actor='cli'`: người có quyền vào container thì có quyền
rất lớn, nên tối thiểu phải để lại dấu vết.

Dùng:
    docker compose exec api python -m scripts.auth.cli list-users
    docker compose exec api python -m scripts.auth.cli reset-password <tên_đăng_nhập>
    docker compose exec api python -m scripts.auth.cli create-admin <tên> "Họ và tên"
    docker compose exec api python -m scripts.auth.cli unlock <tên_đăng_nhập>
"""

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("auth.cli")


def _init_db():
    import scripts.db as db
    db.init_pool(min_conn=1, max_conn=2)
    return db


def cmd_list_users(args) -> int:
    from scripts.core import users
    _init_db()

    rows = users.list_users(limit=500)
    if not rows:
        print("Chưa có người dùng nào. Tạo bằng: create-admin <tên> \"Họ và tên\"")
        return 0

    print(f"{'ID':>4}  {'Tên đăng nhập':<20} {'Vai trò':<12} {'Trạng thái':<10} Họ và tên")
    print("-" * 78)
    for u in rows:
        khoa = " (đang bị khóa)" if users.is_locked(u) else ""
        print(f"{u['id']:>4}  {u['username']:<20} {u['role']:<12} "
              f"{u['status']:<10} {u['full_name']}{khoa}")
    return 0


def cmd_reset_password(args) -> int:
    """
    Đặt lại mật khẩu và IN RA mật khẩu tạm.

    In ra màn hình thay vì gửi email: hệ thống chạy air-gapped, và người chạy lệnh này đã ở trong
    container nên không có gì bị lộ thêm. Mật khẩu tạm buộc phải đổi ở lần đăng nhập đầu.
    """
    from scripts.core import passwords, users
    from scripts.core import audit
    _init_db()

    user = users.get_user_by_username(args.username)
    if not user:
        print(f"LỖI: không có người dùng '{args.username}'", file=sys.stderr)
        return 1

    new_password = args.password or passwords.generate_password()
    try:
        users.set_password(user["id"], new_password, must_change=True)
    except ValueError as e:
        print(f"LỖI: mật khẩu không đạt chính sách — {e}", file=sys.stderr)
        return 1

    users.unlock_user(user["id"])
    audit.log_action(action="password_reset", actor="cli",
                     detail={"target_user": user["username"], "via": "cli"})

    print(f"Đã đặt lại mật khẩu cho '{user['username']}'.")
    print(f"Mật khẩu tạm: {new_password}")
    print("Người dùng BUỘC phải đổi mật khẩu ở lần đăng nhập đầu. Mọi phiên cũ đã bị thu hồi.")
    return 0


def cmd_create_admin(args) -> int:
    from scripts.core import passwords, users
    from scripts.auth import policy
    from scripts.core import audit
    _init_db()

    if users.get_user_by_username(args.username):
        print(f"LỖI: '{args.username}' đã tồn tại", file=sys.stderr)
        return 1

    new_password = args.password or passwords.generate_password()
    try:
        users.create_user(username=args.username, full_name=args.full_name,
                          password=new_password, role=policy.ROLE_ADMIN,
                          must_change_password=True)
    except ValueError as e:
        print(f"LỖI: {e}", file=sys.stderr)
        return 1

    audit.log_action(action="user_create", actor="cli",
                     detail={"target_user": args.username, "role": policy.ROLE_ADMIN, "via": "cli"})

    print(f"Đã tạo quản trị viên '{args.username}'.")
    print(f"Mật khẩu tạm: {new_password}")
    print("BUỘC đổi mật khẩu ở lần đăng nhập đầu.")
    return 0


def cmd_unlock(args) -> int:
    from scripts.core import users
    from scripts.core import audit
    _init_db()

    user = users.get_user_by_username(args.username)
    if not user:
        print(f"LỖI: không có người dùng '{args.username}'", file=sys.stderr)
        return 1

    users.unlock_user(user["id"])
    audit.log_action(action="user_unlock", actor="cli",
                     detail={"target_user": user["username"], "via": "cli"})
    print(f"Đã mở khóa '{user['username']}'.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.auth.cli",
        description="Cứu hộ tài khoản DocuFlow HP (chạy từ trong container)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-users", help="Liệt kê người dùng")

    p_reset = sub.add_parser("reset-password", help="Đặt lại mật khẩu")
    p_reset.add_argument("username")
    p_reset.add_argument("--password", help="Mật khẩu cụ thể (mặc định: sinh tự động)")

    p_admin = sub.add_parser("create-admin", help="Tạo tài khoản quản trị")
    p_admin.add_argument("username")
    p_admin.add_argument("full_name")
    p_admin.add_argument("--password", help="Mật khẩu cụ thể (mặc định: sinh tự động)")

    p_unlock = sub.add_parser("unlock", help="Mở khóa tài khoản bị khóa do nhập sai nhiều lần")
    p_unlock.add_argument("username")

    args = parser.parse_args(argv)
    handlers = {
        "list-users": cmd_list_users,
        "reset-password": cmd_reset_password,
        "create-admin": cmd_create_admin,
        "unlock": cmd_unlock,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
