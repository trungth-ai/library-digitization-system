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
    """
    Chọn provider theo độ nhạy cảm. Trả về (provider, mode).

    Định tuyến chỉ quyết định CHẾ ĐỘ (cloud/local); công cụ nào đảm nhiệm chế độ đó (Ollama, vLLM,
    llama.cpp, Claude, Gemini...) là việc của cấu hình — xem `factory._MODE_ALIASES`.
    """
    from scripts.providers.factory import get_provider  # lazy
    mode = resolve_mode(schema, requested_mode)
    provider = get_provider(kind=mode, config=config)

    # PHÒNG VỆ NHIỀU LỚP (YC-DR-03): chế độ tại chỗ mà công cụ được cấu hình lại là dịch vụ đám mây thì
    # ràng buộc cứng đã bị vô hiệu hóa qua đường cấu hình → DỪNG, không xử lý. Chiều ngược lại (chế độ
    # đám mây nhưng dùng công cụ tại chỗ) là an toàn hơn yêu cầu nên vẫn cho chạy.
    if mode == MODE_LOCAL and provider.deployment != MODE_LOCAL:
        logger.error(
            "TỪ CHỐI: lược đồ '%s' (nhạy cảm=%s) cần chế độ TẠI CHỖ nhưng LOCAL_PROVIDER đang là "
            "'%s' — một công cụ ĐÁM MÂY. Cấu hình này làm vô hiệu ràng buộc cứng YC-DR-03.",
            schema.code, schema.sensitivity, provider.name,
        )
        raise SensitivityViolation(
            f"Cấu hình sai: chế độ tại chỗ đang trỏ tới công cụ đám mây '{provider.name}'. "
            f"Sửa LOCAL_PROVIDER về một công cụ chạy trong hạ tầng của Nhà trường "
            f"(ollama | vllm | llamacpp | lmstudio | tgi) trước khi xử lý tài liệu nhạy cảm."
        )

    if mode == MODE_CLOUD and provider.deployment == MODE_LOCAL:
        logger.info("Chế độ đám mây đang dùng công cụ tại chỗ '%s' — an toàn hơn yêu cầu, cho phép.",
                    provider.name)

    logger.info("Định tuyến lược đồ '%s' (nhạy cảm=%s) → chế độ %s, công cụ %s",
                schema.code, schema.sensitivity, mode, provider.name)
    return provider, mode
