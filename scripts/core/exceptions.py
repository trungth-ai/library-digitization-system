#!/usr/bin/env python3
"""
Exception chuẩn HPU + mapping sang HTTP status + error code.

Dùng cùng response envelope (core/responses.py). Global exception handler trong api.py sẽ bắt các
exception này và trả về `error(message, code)` với đúng HTTP status.
"""


class AppError(Exception):
    """Lỗi nghiệp vụ gốc — mọi lỗi có chủ đích kế thừa từ đây."""
    code: str = "ERROR"
    http_status: int = 400

    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


class ResourceNotFound(AppError):
    """404 — Resource không tồn tại."""
    code = "NOT_FOUND"
    http_status = 404


class ValidationError(AppError):
    """422 — Dữ liệu không hợp lệ."""
    code = "VALIDATION_ERROR"
    http_status = 422


class DuplicateResource(AppError):
    """409 — Trùng unique constraint."""
    code = "DUPLICATE"
    http_status = 409


class BusinessRuleViolation(AppError):
    """422 — Vi phạm quy tắc nghiệp vụ."""
    code = "BUSINESS_RULE_ERROR"
    http_status = 422


class InsufficientPermission(AppError):
    """403 — Đã đăng nhập nhưng không đủ quyền."""
    code = "FORBIDDEN"
    http_status = 403


class ProviderUnavailable(AppError):
    """503 — Model provider (đám mây/tại chỗ) không phản hồi (YC-MP-05)."""
    code = "PROVIDER_UNAVAILABLE"
    http_status = 503


class SensitivityViolation(AppError):
    """
    403 — Cố gửi tài liệu Nội bộ/Nhạy cảm ra đám mây (YC-DR-03).
    Ràng buộc cứng, không được phép ghi đè.
    """
    code = "SENSITIVITY_VIOLATION"
    http_status = 403
