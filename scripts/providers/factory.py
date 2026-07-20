#!/usr/bin/env python3
"""
Factory chọn ModelProvider theo CẤU HÌNH (YC-MP-04): đổi nhà cung cấp bằng biến môi trường,
không sửa mã, không biên dịch lại (KT-CN-05).

Biến môi trường:
    MODEL_PROVIDER = cloud | local        (mặc định: cloud — giữ nguyên hành vi hiện tại)
    CLAUDE_API_KEY = ...                   (cloud)
    CLOUD_MODEL    = claude-...            (cloud, tùy chọn — mặc định theo ProcessingConfig)
    OLLAMA_URL     = http://localhost:11434 (local)
    LOCAL_MODEL    = qwen2.5:7b            (local)

Thêm provider mới (YC-MP-08): viết một lớp con ModelProvider + thêm một nhánh ở đây — KHÔNG sửa nơi khác.
"""

import os
import logging
from typing import Optional

from scripts.providers.base import ModelProvider

logger = logging.getLogger("provider.factory")

DEFAULT_PROVIDER = "cloud"


def get_provider(kind: Optional[str] = None, config=None) -> ModelProvider:
    """Trả về provider theo `kind` (hoặc env MODEL_PROVIDER)."""
    kind = (kind or os.getenv("MODEL_PROVIDER", DEFAULT_PROVIDER)).lower().strip()

    if kind == "cloud":
        from scripts.providers.cloud import CloudProvider
        provider = CloudProvider(
            api_key=os.getenv("CLAUDE_API_KEY"),
            config=config,
            model=os.getenv("CLOUD_MODEL") or None,
        )
    elif kind == "local":
        from scripts.providers.local import LocalProvider
        provider = LocalProvider(
            base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
            model=os.getenv("LOCAL_MODEL", "qwen2.5:7b"),
            config=config,
        )
    else:
        raise ValueError(
            f"MODEL_PROVIDER không hợp lệ: '{kind}'. Chỉ nhận: cloud | local"
        )

    logger.info("Đã chọn model provider: %s (model=%s)", provider.name, provider.model)
    return provider
