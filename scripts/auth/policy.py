#!/usr/bin/env python3
"""
Mô hình quyền & ba nấc bật xác thực (YC-QT-03, YC-QT-04, YC-QT-09 — ADR-012).

Module THUẦN: không import fastapi/psycopg2 → kiểm thử được trên máy dev. Phần gắn vào FastAPI nằm ở
`scripts/auth/deps.py`; phần đọc/ghi DB nằm ở `scripts/core/users.py`.

Bảng quyền dưới đây là **giá trị khởi tạo** (seed) cho `roles`/`role_permissions` trong DB, không phải
nguồn chân lý lúc chạy — quyền là DỮ LIỆU (YC-QT-09), cùng triết lý với lược đồ trích xuất (YC-SC-01).
Giữ bản trong mã để: (a) seed lần đầu, (b) còn chạy được khi bảng chưa được di trú, (c) kiểm thử
không cần DB.
"""

import os
from typing import Dict, FrozenSet, Iterable, Optional, Set

# ─────────────────────────────────────────────────────────────
# QUYỀN — đặt tên theo `tài_nguyên:hành_động`
# ─────────────────────────────────────────────────────────────

DOCUMENT_READ = "document:read"
DOCUMENT_UPLOAD = "document:upload"
DOCUMENT_EDIT = "document:edit"
DOCUMENT_APPROVE = "document:approve"
DOCUMENT_DELETE = "document:delete"          # xóa mềm
DOCUMENT_PURGE = "document:purge"            # xóa vĩnh viễn — chỉ admin
DOCUMENT_DOWNLOAD = "document:download"
DSPACE_PUSH = "dspace:push"
SCHEMA_READ = "schema:read"
SCHEMA_WRITE = "schema:write"
SCHEMA_SENSITIVITY = "schema:sensitivity"    # YC-DR-04: chỉ quản trị viên đổi được độ nhạy cảm
REPORT_READ = "report:read"
AUDIT_READ = "audit:read"
LOG_READ = "log:read"
QUEUE_MANAGE = "queue:manage"                # chạy lại hàng đợi chết, tạm dừng lô
USER_MANAGE = "user:manage"
SYSTEM_CONFIG = "system:config"

ALL_PERMISSIONS: FrozenSet[str] = frozenset({
    DOCUMENT_READ, DOCUMENT_UPLOAD, DOCUMENT_EDIT, DOCUMENT_APPROVE, DOCUMENT_DELETE,
    DOCUMENT_PURGE, DOCUMENT_DOWNLOAD, DSPACE_PUSH, SCHEMA_READ, SCHEMA_WRITE,
    SCHEMA_SENSITIVITY, REPORT_READ, AUDIT_READ, LOG_READ, QUEUE_MANAGE,
    USER_MANAGE, SYSTEM_CONFIG,
})

# Nhãn tiếng Việt để hiển thị trên trang quản trị — người cấp quyền không phải là lập trình viên
PERMISSION_LABELS: Dict[str, str] = {
    DOCUMENT_READ: "Xem tài liệu",
    DOCUMENT_UPLOAD: "Tải tài liệu lên",
    DOCUMENT_EDIT: "Sửa metadata",
    DOCUMENT_APPROVE: "Duyệt tài liệu",
    DOCUMENT_DELETE: "Xóa tài liệu (vào thùng rác)",
    DOCUMENT_PURGE: "Xóa vĩnh viễn",
    DOCUMENT_DOWNLOAD: "Tải tệp về",
    DSPACE_PUSH: "Đẩy lên DSpace",
    SCHEMA_READ: "Xem lược đồ",
    SCHEMA_WRITE: "Sửa lược đồ",
    SCHEMA_SENSITIVITY: "Đổi độ nhạy cảm của lược đồ",
    REPORT_READ: "Xem báo cáo",
    AUDIT_READ: "Xem nhật ký kiểm toán",
    LOG_READ: "Xem log hệ thống",
    QUEUE_MANAGE: "Quản lý hàng đợi",
    USER_MANAGE: "Quản trị người dùng",
    SYSTEM_CONFIG: "Đổi cấu hình hệ thống",
}

# ─────────────────────────────────────────────────────────────
# VAI TRÒ
# ─────────────────────────────────────────────────────────────

ROLE_ADMIN = "admin"
ROLE_APPROVER = "approver"
ROLE_LIBRARIAN = "librarian"
ROLE_VIEWER = "viewer"
ROLE_SERVICE = "service"
ALL_ROLES = (ROLE_ADMIN, ROLE_APPROVER, ROLE_LIBRARIAN, ROLE_VIEWER, ROLE_SERVICE)

ROLE_LABELS: Dict[str, str] = {
    ROLE_ADMIN: "Quản trị hệ thống",
    ROLE_APPROVER: "Cán bộ duyệt",
    ROLE_LIBRARIAN: "Cán bộ nghiệp vụ",
    ROLE_VIEWER: "Người xem",
    ROLE_SERVICE: "Tài khoản dịch vụ",
}

_VIEWER_PERMS = frozenset({DOCUMENT_READ, REPORT_READ})

_LIBRARIAN_PERMS = _VIEWER_PERMS | {
    DOCUMENT_UPLOAD, DOCUMENT_EDIT, DOCUMENT_DOWNLOAD, SCHEMA_READ,
}

# `approver` duyệt được MỌI tài liệu, kể cả tài liệu do chính mình tải lên (QĐ-05 — ADR-012 mục 4):
# quyền duyệt do phân quyền quyết định, KHÔNG do quan hệ sở hữu.
_APPROVER_PERMS = _LIBRARIAN_PERMS | {
    DOCUMENT_APPROVE, DOCUMENT_DELETE, DSPACE_PUSH, QUEUE_MANAGE, AUDIT_READ,
}

ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    ROLE_ADMIN: ALL_PERMISSIONS,
    ROLE_APPROVER: frozenset(_APPROVER_PERMS),
    ROLE_LIBRARIAN: frozenset(_LIBRARIAN_PERMS),
    ROLE_VIEWER: _VIEWER_PERMS,
    # Tài khoản dịch vụ KHÔNG có quyền mặc định nào: quyền được cấp rõ ràng cho từng API key (YC-TK-02).
    # Mặc định rỗng là chủ ý — một tài khoản tự động có quyền rộng là rủi ro khó phát hiện.
    ROLE_SERVICE: frozenset(),
}


def permissions_for_role(role: str) -> FrozenSet[str]:
    """Quyền mặc định của một vai trò. Vai trò lạ → rỗng (mặc định an toàn, không phải mặc định mở)."""
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(granted: Iterable[str], needed: str) -> bool:
    """
    Tập quyền `granted` có chứa `needed` không?

    KHÔNG hỗ trợ ký tự thay thế (`document:*`): quyền phải liệt kê tường minh. Một dấu `*` đặt sai chỗ
    trong cấu hình sẽ mở quyền mà không ai nhận ra khi đọc bảng phân quyền.
    """
    return needed in set(granted)


# ─────────────────────────────────────────────────────────────
# BA NẤC BẬT XÁC THỰC (YC-QT-04)
# ─────────────────────────────────────────────────────────────

AUTH_OFF = "off"        # như trước khi có xác thực — hành vi hệ thống không đổi
AUTH_SHADOW = "shadow"  # vẫn phục vụ, nhưng GHI NHẬN mọi request thiếu xác thực
AUTH_ON = "on"          # chặn thật
AUTH_MODES = (AUTH_OFF, AUTH_SHADOW, AUTH_ON)

# Người dùng ảo cho request không xác thực ở nấc off/shadow. Ghi tên này vào nhật ký để phân biệt rõ
# "chưa bật xác thực" với một người dùng thật — không bao giờ ghi lẫn thành tên người.
LEGACY_ACTOR = "(chưa xác thực)"


def resolve_auth_mode(raw: Optional[str] = None) -> str:
    """
    Đọc nấc xác thực từ biến môi trường `AUTH_MODE`.

    Giá trị lạ → `off`, KÈM cảnh báo của nơi gọi. Chọn `off` thay vì `on` cho giá trị sai là có chủ
    đích: một lỗi chính tả trong `.env` không được làm cả Trung tâm không đăng nhập được vào hệ thống
    đang phục vụ thật. Rủi ro "mở quá" ở đây nhỏ hơn rủi ro "khóa cả hệ thống", vì nấc `off` đúng là
    trạng thái hệ thống đang chạy hôm nay.
    """
    value = (raw if raw is not None else os.getenv("AUTH_MODE", AUTH_OFF)).strip().lower()
    return value if value in AUTH_MODES else AUTH_OFF


def mode_blocks_requests(mode: str) -> bool:
    """Nấc này có CHẶN request thiếu xác thực không? Chỉ `on` chặn."""
    return mode == AUTH_ON


def mode_records_gaps(mode: str) -> bool:
    """Nấc này có ghi nhận request thiếu xác thực không? `shadow` ghi (để tìm hết chỗ còn sót)."""
    return mode == AUTH_SHADOW
