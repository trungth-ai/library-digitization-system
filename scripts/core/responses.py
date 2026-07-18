#!/usr/bin/env python3
"""
Response envelope chuẩn HPU — áp dụng cho MỌI endpoint code MỚI.

Định dạng bắt buộc (theo _shared/api-conventions.md):
    Thành công:  {"status": "success", "data": ..., "message": ...}
    Danh sách:   {"status": "success", "data": [...], "meta": {page, per_page, total, total_pages}}
    Lỗi:         {"status": "error", "message": ..., "code": ..., "errors": [...]}

Lưu ý (ADR-003): các endpoint CŨ (/api/v1/process, /api/v2/*) giữ nguyên định dạng thô để không
phá frontend đang chạy; chỉ code mới bắt buộc dùng envelope này, di trú dần.
"""

from typing import Any, List, Optional


def success(data: Any, message: str = "Thành công", meta: Optional[dict] = None) -> dict:
    """Envelope thành công. Kèm meta khi có phân trang."""
    response: dict = {"status": "success", "data": data, "message": message}
    if meta:
        response["meta"] = meta
    return response


def error(message: str, code: str = "ERROR", errors: Optional[List[dict]] = None) -> dict:
    """Envelope lỗi. `errors` là danh sách chi tiết lỗi từng field (validation)."""
    return {
        "status": "error",
        "message": message,
        "code": code,
        "errors": errors or [],
    }


def paginated(data: list, page: int, per_page: int, total: int) -> dict:
    """Envelope danh sách có phân trang — tự tính total_pages."""
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    return success(
        data=data,
        meta={
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    )
