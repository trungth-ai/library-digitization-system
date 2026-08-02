#!/usr/bin/env python3
"""
Cưỡng chế phân quyền ở MÁY CHỦ + ba nấc `AUTH_MODE` (YC-QT-03/04 — ADR-012).

Đây là module DUY NHẤT trong `scripts/auth/` import fastapi. Logic quyết định nằm ở `policy.py`
(thuần, kiểm thử được); ở đây chỉ là phần nối vào FastAPI.

BA NẤC (ADR-012 mục 2) — đổi bằng biến môi trường, KHÔNG build lại image:

    off     Không kiểm gì. Hệ thống hành xử ĐÚNG NHƯ trước khi có xác thực.
    shadow  Vẫn phục vụ, nhưng GHI CẢNH BÁO mỗi request thiếu xác thực kèm endpoint + IP + user-agent.
            → chạy ≥ 1 tuần, đọc cảnh báo, sửa hết chỗ còn sót (script cá nhân, n8n, tab cũ).
            → điều kiện sang `on`: 0 cảnh báo trong 48 giờ liên tiếp.
    on      Chặn thật: 401 khi chưa đăng nhập, 403 khi thiếu quyền.

⚠️ Ẩn nút trên giao diện là TIỆN ÍCH, không phải cơ chế bảo vệ. Mọi endpoint ghi phải có `require(...)`
— `tests/test_auth_coverage.py` liệt kê tự động và làm hỏng build nếu có endpoint ghi bị bỏ sót.
"""

import logging
from typing import Callable, Dict, Optional, Set

from fastapi import Depends, HTTPException, Request

from scripts.auth import policy, sessions
from scripts.core import users

logger = logging.getLogger("auth.deps")


class Principal:
    """
    Chủ thể thực hiện request: người dùng đã đăng nhập, hoặc chủ thể "chưa xác thực" ở nấc off/shadow.

    `is_authenticated=False` + `permissions` = toàn quyền chỉ xảy ra ở nấc off/shadow — đây là cách
    diễn đạt "chưa bật xác thực" mà không phải rải `if AUTH_MODE` khắp các endpoint.
    """

    __slots__ = ("user_id", "username", "full_name", "role", "permissions",
                 "is_authenticated", "must_change_password", "session_ref")

    def __init__(self, user_id: Optional[int] = None, username: str = policy.LEGACY_ACTOR,
                 full_name: str = "", role: str = "", permissions: Optional[Set[str]] = None,
                 is_authenticated: bool = False, must_change_password: bool = False,
                 session_ref: Optional[str] = None):
        self.user_id = user_id
        self.username = username
        self.full_name = full_name
        self.role = role
        self.permissions = permissions or set()
        self.is_authenticated = is_authenticated
        self.must_change_password = must_change_password
        self.session_ref = session_ref

    @property
    def actor(self) -> str:
        """Giá trị ghi vào `audit_log.actor` — tên thật khi đã đăng nhập (YC-AU-02, YC-QT-11)."""
        return self.username

    def can(self, permission: str) -> bool:
        return policy.has_permission(self.permissions, permission)

    def as_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "full_name": self.full_name,
            "role": self.role,
            "role_label": policy.ROLE_LABELS.get(self.role, self.role),
            "permissions": sorted(self.permissions),
            "is_authenticated": self.is_authenticated,
            "must_change_password": self.must_change_password,
        }


def _legacy_principal() -> Principal:
    """
    Chủ thể cho request thiếu xác thực ở nấc off/shadow: có ĐỦ quyền để hệ thống chạy như cũ.

    Tên là `policy.LEGACY_ACTOR` = "(chưa xác thực)" — ghi vào nhật ký để về sau còn phân biệt được
    thao tác nào diễn ra trước khi bật xác thực. Không bao giờ ghi lẫn thành tên một người thật.
    """
    return Principal(username=policy.LEGACY_ACTOR, role="", is_authenticated=False,
                     permissions=set(policy.ALL_PERMISSIONS))


def _resolve_principal(request: Request) -> Principal:
    """Đọc cookie phiên → chủ thể. Không có/không hợp lệ → chủ thể chưa xác thực."""
    token = request.cookies.get(sessions.SESSION_COOKIE_NAME)
    if not token:
        return Principal()

    try:
        row = sessions.resolve_session(token)
    except Exception as e:  # noqa: BLE001 - DB lỗi thì coi như chưa xác thực, không trả 500
        logger.error("Không đọc được phiên: %s", e)
        return Principal()

    if not row:
        return Principal()

    try:
        perms = users.get_role_permissions(row["role"])
    except Exception as e:  # noqa: BLE001
        logger.error("Không đọc được quyền của vai trò '%s': %s", row["role"], e)
        perms = set(policy.permissions_for_role(row["role"]))

    return Principal(
        user_id=row["user_id"], username=row["username"], full_name=row["full_name"],
        role=row["role"], permissions=set(perms), is_authenticated=True,
        must_change_password=bool(row.get("must_change_password")),
        session_ref=row["token_hash"][:8],
    )


async def current_principal(request: Request) -> Principal:
    """
    Dependency cơ bản: xác định ai đang gọi. KHÔNG chặn — dùng cho endpoint đọc công khai và cho
    việc ghi `actor` vào nhật ký.

    Gắn vào `request.state` để middleware ghi log lấy được `actor` mà không phải giải mã phiên lần hai.
    """
    principal = _resolve_principal(request)
    request.state.principal = principal
    return principal


def require(*permissions: str) -> Callable:
    """
    Dependency cưỡng chế quyền. Dùng: `@app.post(..., dependencies=[Depends(require("document:upload"))])`

    Nhiều quyền = phải có ĐỦ (AND), không phải chỉ cần một. Chọn AND vì mỗi endpoint chỉ nên đòi
    những quyền nó thực sự cần; OR làm bảng phân quyền khó đọc và dễ mở quá tay.
    """
    for perm in permissions:
        if perm not in policy.ALL_PERMISSIONS:
            # Lỗi lập trình — phát hiện ngay lúc nạp module, không đợi tới lúc có request
            raise ValueError(f"Quyền không tồn tại: {perm!r}")

    async def _guard(request: Request,
                     principal: Principal = Depends(current_principal)) -> Principal:
        mode = policy.resolve_auth_mode()

        if not principal.is_authenticated:
            if policy.mode_records_gaps(mode):
                _record_gap(request)
            if not policy.mode_blocks_requests(mode):
                # Nấc off/shadow: phục vụ như cũ. Chủ thể đủ quyền để hành vi không đổi.
                legacy = _legacy_principal()
                request.state.principal = legacy
                return legacy
            raise HTTPException(
                status_code=401,
                detail="Bạn chưa đăng nhập. Vui lòng đăng nhập để tiếp tục.",
            )

        # Đã đăng nhập nhưng buộc phải đổi mật khẩu: chỉ cho đi qua đường đổi mật khẩu (YC-QT-05)
        if principal.must_change_password and not _is_password_change_path(request):
            raise HTTPException(
                status_code=403,
                detail="Bạn cần đổi mật khẩu trước khi sử dụng hệ thống.",
            )

        missing = [p for p in permissions if not principal.can(p)]
        if missing:
            nhan = ", ".join(policy.PERMISSION_LABELS.get(p, p) for p in missing)
            logger.warning("Từ chối quyền: '%s' (vai trò %s) gọi %s %s — thiếu: %s",
                           principal.username, principal.role,
                           request.method, request.url.path, ", ".join(missing))
            _record_denied(request, principal, missing)
            raise HTTPException(
                status_code=403,
                detail=f"Bạn không có quyền thực hiện việc này (cần: {nhan}).",
            )

        return principal

    return _guard


def _is_password_change_path(request: Request) -> bool:
    return request.url.path.rstrip("/").endswith("/auth/change-password")


def _record_gap(request: Request) -> None:
    """
    Ghi nhận một request THIẾU XÁC THỰC ở nấc `shadow`.

    Đây là toàn bộ giá trị của nấc `shadow`: biến câu hỏi "còn chỗ nào đang gọi API mà ta chưa biết?"
    từ phỏng đoán thành dữ liệu đọc được. Ghi vào `system_events` để tra được sau khi log container
    đã bị cắt vòng — cùng lý do của ADR-009.
    """
    client = request.client.host if request.client else "?"
    agent = (request.headers.get("user-agent") or "")[:200]
    message = f"Request THIẾU XÁC THỰC: {request.method} {request.url.path} từ {client}"

    logger.warning("%s (user-agent: %s)", message, agent)
    try:
        import scripts.db as db
        db.log_system_event(source="api", kind="auth_missing", level="warning",
                            message=message, detail=f"user-agent: {agent}")
    except Exception as e:  # noqa: BLE001 - ghi nhận hỏng không được chặn request
        logger.debug("Không ghi được sự kiện thiếu xác thực: %s", e)

    # Ghi cả vào nhật ký người dùng: `system_events` để người vận hành thấy tổng thể, còn ở đây thì
    # lọc được theo IP/endpoint để tìm chính xác client nào còn sót trước khi bật `AUTH_MODE=on`.
    try:
        from scripts.core import user_log
        user_log.log_activity(
            action=user_log.ACTION_UNAUTHENTICATED, username=policy.LEGACY_ACTOR,
            resource_type="endpoint", resource_id=f"{request.method} {request.url.path}",
            ip=client, user_agent=agent, result=user_log.RESULT_FAILED,
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("Không ghi được nhật ký thiếu xác thực: %s", e)


def _record_denied(request: Request, principal: Principal, missing) -> None:
    """
    Ghi nhận mọi lần BỊ TỪ CHỐI QUYỀN (YC-NK-03).

    Đây là tín hiệu an ninh quan trọng nhất trong nhật ký: người dùng thật rất ít khi gọi API họ không
    có quyền, nên một chuỗi 403 thường nghĩa là có gì đó bất thường.
    """
    try:
        from scripts.core import user_log
        user_log.log_denied(
            username=principal.actor, method=request.method, path=request.url.path,
            role=principal.role, missing=missing,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("Không ghi được nhật ký từ chối quyền: %s", e)


def require_authenticated() -> Callable:
    """
    Chỉ cần đã đăng nhập, không cần quyền cụ thể (dùng cho `/auth/me`, đổi mật khẩu).

    Ở nấc off/shadow vẫn trả về chủ thể chưa xác thực để không phá hành vi cũ.
    """

    async def _guard(request: Request,
                     principal: Principal = Depends(current_principal)) -> Principal:
        mode = policy.resolve_auth_mode()
        if principal.is_authenticated:
            return principal
        if policy.mode_records_gaps(mode):
            _record_gap(request)
        if not policy.mode_blocks_requests(mode):
            legacy = _legacy_principal()
            request.state.principal = legacy
            return legacy
        raise HTTPException(status_code=401, detail="Bạn chưa đăng nhập.")

    return _guard
