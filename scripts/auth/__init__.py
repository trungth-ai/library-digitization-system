"""
Danh tính & phân quyền (ADR-012).

Tổ chức module theo NGUYÊN TẮC KIỂM THỬ ĐƯỢC — phần nào cần kiểm thử thì không được phụ thuộc
fastapi/psycopg2 (máy dev không cài `fastapi`; xem `scripts/core/uploads.py`):

    policy.py     — quyền, vai trò, ba nấc AUTH_MODE           (thuần, kiểm thử được)
    sessions.py   — phiên đăng nhập lưu trong PostgreSQL       (cần DB)
    local.py      — nền tảng xác thực nội bộ (tên + mật khẩu)  (cần DB)
    deps.py       — dependency `require()` cho FastAPI         (cần fastapi)
    bootstrap.py  — khởi tạo quản trị viên đầu tiên            (cần DB)
    cli.py        — cứu hộ mật khẩu từ trong container         (cần DB)

`scripts/core/users.py` giữ phần truy vấn bảng `users`/`roles`; `scripts/core/passwords.py` giữ phần
băm mật khẩu (thuần).
"""
