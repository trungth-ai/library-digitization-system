#!/usr/bin/env python3
"""
Middleware gắn `request_id` và ghi một dòng tổng kết mỗi request (YC-LG-02/04 — sprint V1).

TRẢ LỜI ĐƯỢC BA CÂU HỎI mà hôm nay phải SSH mới trả lời được:
  • "Request này hỏng ở đâu?"      → grep một `request_id` ra đủ chuỗi xử lý
  • "Endpoint nào đang chậm?"      → dòng tổng kết có `duration_ms`
  • "Ai gọi cái này?"              → dòng tổng kết có `actor` (từ phiên đã xác thực)

Nhận `X-Request-Id` từ ngoài nếu có: giao diện Next chuyển tiếp header này qua proxy same-origin,
nên một thao tác trên trình duyệt lần được xuyên suốt tới log của API.
"""

import logging
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from scripts.core import context

logger = logging.getLogger("api.request")

# Không ghi dòng tổng kết cho các đường này: chúng bị gọi rất dày và không mang thông tin gỡ lỗi.
# `/api/v2/jobs/stream` là SSE — một kết nối sống rất lâu, đo `duration_ms` của nó vô nghĩa.
_QUIET_PATHS = frozenset({"/health", "/api/health", "/metrics"})
_QUIET_PREFIXES = ("/api/v2/jobs/stream", "/api/v2/jobs/")


def _is_quiet(path: str) -> bool:
    if path in _QUIET_PATHS:
        return True
    return path.endswith("/stream")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Đặt ngữ cảnh cho mỗi request rồi ghi kết quả.

    `actor` được đọc SAU khi xử lý xong, từ `request.state.principal` mà dependency phân quyền đã
    gắn (xem `scripts/auth/deps.py`): lúc middleware bắt đầu thì chưa ai giải mã phiên cả, nên đọc
    sớm sẽ luôn ra rỗng.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        incoming = request.headers.get("x-request-id")

        with context.request_context(request_id=incoming) as request_id:
            started = time.perf_counter()
            status_code = 500          # nếu handler ném ngoại lệ thì đây là kết quả thực tế

            try:
                response = await call_next(request)
                status_code = response.status_code
                return response
            finally:
                duration_ms = int((time.perf_counter() - started) * 1000)

                principal = getattr(request.state, "principal", None)
                if principal is not None:
                    context.set_actor(principal.actor)

                if not _is_quiet(request.url.path):
                    # Mức log theo kết quả: lỗi máy chủ là ERROR, lỗi client là WARNING. Nếu để hết
                    # ở INFO thì lọc theo mức không tách được sự cố thật ra khỏi nhiễu.
                    level = (
                        logging.ERROR if status_code >= 500
                        else logging.WARNING if status_code >= 400
                        else logging.INFO
                    )
                    logger.log(
                        level, "%s %s → %s (%d ms)",
                        request.method, request.url.path, status_code, duration_ms,
                        extra={
                            "http_method": request.method,
                            "http_path": request.url.path,
                            "http_status": status_code,
                            "duration_ms": duration_ms,
                            "client_ip": request.client.host if request.client else None,
                        },
                    )

                # Trả `request_id` về cho client: người dùng báo lỗi kèm mã này là tra được ngay,
                # không phải đoán theo dấu thời gian.
                try:
                    response.headers["X-Request-Id"] = request_id
                except (NameError, AttributeError):
                    pass       # handler ném ngoại lệ nên chưa có response — không có gì để gắn
