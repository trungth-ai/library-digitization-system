#!/usr/bin/env python3
"""
Dự phòng chéo công cụ (YC-MP-05 mức chuỗi): công cụ chính không sẵn sàng → chuyển sang công cụ khác
TRONG CÙNG CHẾ ĐỘ.

QUYẾT ĐỊNH NGHIỆP VỤ (ADR-008): chỉ dự phòng **trong cùng chế độ triển khai**.
  - vLLM chết → Ollama (đều tại chỗ): ĐƯỢC.
  - Ollama chết → Claude (tại chỗ → đám mây): **KHÔNG BAO GIỜ**, kể cả khi tài liệu là Công khai.
Lý do: một sự cố hạ tầng không được phép âm thầm đổi nơi dữ liệu đi qua. Nếu chấp nhận vượt chế độ,
thì ràng buộc cứng YC-DR-03 chỉ còn đúng lúc bình thường và sai đúng lúc bất thường — tức là vô nghĩa.
Muốn đổi chế độ thì phải là quyết định của con người, không phải hệ quả của một container chết.

CẤU HÌNH:
    LOCAL_FALLBACK_PROVIDERS=ollama,llamacpp     # thứ tự thử khi chế độ tại chỗ lỗi
    CLOUD_FALLBACK_PROVIDERS=openai,gemini       # thứ tự thử khi chế độ đám mây lỗi
Để trống (mặc định) = KHÔNG dự phòng, giữ nguyên hành vi hiện tại.

CHI PHÍ: chỉ kiểm tra sẵn sàng khi có cấu hình dự phòng. Không cấu hình thì không mất một lần gọi
health nào — chuỗi rỗng thì kiểm tra để làm gì.
"""

import logging
import os
from typing import List, Optional, Tuple

from scripts.providers.base import DEPLOY_LOCAL, ModelProvider

logger = logging.getLogger("provider.fallback")

_FALLBACK_ENV = {
    "local": "LOCAL_FALLBACK_PROVIDERS",
    "cloud": "CLOUD_FALLBACK_PROVIDERS",
}


def fallback_names(mode: str) -> List[str]:
    """Danh sách tên công cụ dự phòng cho một chế độ, theo thứ tự ưu tiên."""
    env_key = _FALLBACK_ENV.get(mode)
    if not env_key:
        return []
    raw = os.getenv(env_key, "")
    return [n.strip().lower() for n in raw.split(",") if n.strip()]


def select_provider(mode: str, config=None) -> Tuple[ModelProvider, Optional[str]]:
    """
    Chọn công cụ dùng được cho `mode`. Trả về (provider, fallback_from).
    `fallback_from` = tên công cụ chính đã bị bỏ qua, hoặc None nếu dùng công cụ chính.

    Không ném lỗi: nếu KHÔNG công cụ nào sẵn sàng thì vẫn trả về công cụ chính để tài liệu được xử lý
    (rơi về basic extraction, đánh dấu cần xem lại) — mất một phần chất lượng còn hơn mất tài liệu.
    """
    from scripts.providers.factory import get_provider   # lazy: tránh phụ thuộc vòng

    primary = get_provider(kind=mode, config=config)
    names = fallback_names(mode)
    if not names:
        return primary, None      # không cấu hình dự phòng → không tốn một lần health nào

    if primary.health().ready:
        return primary, None

    logger.warning("[dự phòng] Công cụ chính '%s' (%s) không sẵn sàng → thử chuỗi dự phòng: %s",
                   primary.name, mode, ", ".join(names))

    for name in names:
        if name == primary.name:
            continue
        try:
            candidate = get_provider(kind=name, config=config)
        except ValueError as e:
            logger.error("[dự phòng] Bỏ qua '%s': cấu hình không dùng được — %s", name, e)
            continue

        # RÀNG BUỘC CỨNG: dự phòng KHÔNG được đổi chế độ triển khai
        if candidate.deployment != mode:
            logger.error(
                "[dự phòng] TỪ CHỐI '%s': công cụ này ở chế độ '%s' còn tài liệu cần chế độ '%s'. "
                "Dự phòng không được phép đổi nơi dữ liệu đi qua (YC-DR-03).",
                name, candidate.deployment, mode,
            )
            continue

        if candidate.health().ready:
            logger.warning("[dự phòng] Chuyển '%s' → '%s' (cùng chế độ %s)", primary.name, name, mode)
            return candidate, primary.name

        logger.warning("[dự phòng] '%s' cũng không sẵn sàng, thử tiếp", name)

    logger.error(
        "[dự phòng] KHÔNG công cụ nào ở chế độ '%s' sẵn sàng (đã thử: %s, %s). Vẫn xử lý bằng '%s' — "
        "kết quả sẽ kém và tài liệu bị đánh dấu cần xem lại.",
        mode, primary.name, ", ".join(names) or "(không có dự phòng)", primary.name,
    )
    return primary, None


def describe_chain() -> dict:
    """Mô tả cấu hình dự phòng — cho giao diện quản trị (YC-MS-08) và chẩn đoán."""
    return {
        "local": fallback_names(DEPLOY_LOCAL),
        "cloud": fallback_names("cloud"),
        "note": "Dự phòng chỉ diễn ra trong cùng chế độ triển khai (ADR-008).",
    }
