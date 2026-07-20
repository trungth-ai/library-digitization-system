#!/usr/bin/env python3
"""
Định tuyến theo độ nhạy cảm (YC-DR) — quyết định chế độ xử lý (cloud|local) dựa trên độ nhạy cảm của
lược đồ, với RÀNG BUỘC CỨNG không được phép ghi đè.

Luật (SRS mục 2.3):
- YC-DR-02 Mặc định an toàn: không xác định được độ nhạy cảm → chế độ TẠI CHỖ (local).
- YC-DR-03 Ràng buộc cứng: tài liệu Nội bộ/Nhạy cảm KHÔNG BAO GIỜ ra đám mây, kể cả khi người dùng
  chọn thủ công → ném SensitivityViolation + ghi nhật ký (bằng chứng từ chối cho kiểm toán, KT-BM-06).
- Công khai: cho phép đám mây (giữ hành vi hiện tại) hoặc tại chỗ theo yêu cầu/cấu hình.
"""

import logging
from typing import Optional, Tuple

from scripts.providers.base import (
    ExtractionSchema,
    SENSITIVITY_PUBLIC, SENSITIVITY_INTERNAL, SENSITIVITY_SENSITIVE,
)
from scripts.core.exceptions import SensitivityViolation

logger = logging.getLogger("provider.router")

MODE_CLOUD = "cloud"
MODE_LOCAL = "local"

# Chỉ tài liệu Công khai mới được phép ra đám mây
_CLOUD_ALLOWED = {SENSITIVITY_PUBLIC}
_KNOWN = {SENSITIVITY_PUBLIC, SENSITIVITY_INTERNAL, SENSITIVITY_SENSITIVE}


def resolve_mode(schema: ExtractionSchema, requested_mode: Optional[str] = None) -> str:
    """
    Trả về chế độ hợp lệ ('cloud'|'local') cho một lược đồ.
    `requested_mode`: chế độ người dùng/cấu hình yêu cầu (có thể None).
    Ném SensitivityViolation nếu yêu cầu vi phạm ràng buộc cứng.
    """
    sensitivity = (schema.sensitivity or "").lower().strip()
    req = (requested_mode or "").lower().strip() or None

    # YC-DR-02: không rõ độ nhạy cảm → mặc định an toàn = tại chỗ
    if sensitivity not in _KNOWN:
        logger.info("Lược đồ '%s' không rõ độ nhạy cảm → mặc định TẠI CHỖ (YC-DR-02)", schema.code)
        return MODE_LOCAL

    # Công khai: cho phép đám mây; theo yêu cầu, mặc định cloud (giữ hành vi hiện tại)
    if sensitivity == SENSITIVITY_PUBLIC:
        return req or MODE_CLOUD

    # Nội bộ / Nhạy cảm: BẮT BUỘC tại chỗ
    if req == MODE_CLOUD:
        # YC-DR-03: ràng buộc cứng — từ chối + ghi nhật ký (bằng chứng cho kiểm toán)
        logger.warning(
            "TỪ CHỐI: cố xử lý tài liệu độ nhạy cảm '%s' (lược đồ '%s') bằng ĐÁM MÂY — "
            "ràng buộc cứng YC-DR-03, không được ghi đè.", sensitivity, schema.code,
        )
        raise SensitivityViolation(
            f"Tài liệu độ nhạy cảm '{sensitivity}' không được xử lý bằng chế độ đám mây "
            f"(ràng buộc cứng, không được ghi đè)."
        )
    return MODE_LOCAL


def get_routed_provider(schema: ExtractionSchema,
                        requested_mode: Optional[str] = None,
                        config=None) -> Tuple[object, str]:
    """Chọn provider theo độ nhạy cảm. Trả về (provider, mode)."""
    from scripts.providers.factory import get_provider  # lazy
    mode = resolve_mode(schema, requested_mode)
    provider = get_provider(kind=mode, config=config)
    logger.info("Định tuyến lược đồ '%s' (nhạy cảm=%s) → chế độ %s",
                schema.code, schema.sensitivity, mode)
    return provider, mode
