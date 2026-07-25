#!/usr/bin/env python3
"""
Factory chọn ModelProvider theo CẤU HÌNH (YC-MP-04, YC-MS-06): đổi nhà cung cấp bằng biến môi trường,
không sửa mã, không biên dịch lại (KT-CN-05).

    MODEL_PROVIDER=<tên công cụ>   # xem `scripts/providers/registry.py` để biết danh sách đầy đủ
                                   # vd: claude | ollama | vllm | llamacpp | openai | gemini | groq ...

HAI BÍ DANH THEO CHẾ ĐỘ (giữ tương thích cấu hình đang chạy + phục vụ định tuyến theo độ nhạy cảm):
    MODEL_PROVIDER=cloud  →  công cụ đám mây đang chọn   (CLOUD_PROVIDER, mặc định `claude`)
    MODEL_PROVIDER=local  →  công cụ tại chỗ đang chọn   (LOCAL_PROVIDER, mặc định `ollama`)

Nhờ hai bí danh này, `router.py` chỉ cần quyết định CHẾ ĐỘ (cloud/local) theo độ nhạy cảm — việc chế độ
tại chỗ đang chạy bằng Ollama, vLLM hay llama.cpp là chuyện cấu hình, không phải chuyện của định tuyến.

THÊM MỘT CÔNG CỤ MỚI (YC-MP-08):
  1. Nói được giao thức đã có (tương thích OpenAI)  → thêm MỘT dòng vào `registry.PRESETS`. Hết.
  2. Giao thức mới                                   → thêm một lớp `ModelProvider` + một dòng `_BUILDERS`.
Không sửa `base.py`, không sửa pipeline, không sửa `router.py`.
"""

import logging
import os
from typing import Optional

from scripts.providers.base import DEPLOY_CLOUD, DEPLOY_LOCAL, ModelProvider
from scripts.providers.registry import (
    KIND_ANTHROPIC, KIND_AZURE_OPENAI, KIND_GEMINI, KIND_OLLAMA, KIND_OPENAI_COMPAT,
    PRESETS, ProviderPreset, get_preset, is_private_endpoint,
)

logger = logging.getLogger("provider.factory")

DEFAULT_PROVIDER = "cloud"          # giữ nguyên hành vi hiện tại của hệ đang chạy
DEFAULT_CLOUD_PROVIDER = "claude"
DEFAULT_LOCAL_PROVIDER = "ollama"

#: Bí danh theo chế độ → (biến môi trường chọn công cụ, giá trị mặc định)
_MODE_ALIASES = {
    DEPLOY_CLOUD: ("CLOUD_PROVIDER", DEFAULT_CLOUD_PROVIDER),
    DEPLOY_LOCAL: ("LOCAL_PROVIDER", DEFAULT_LOCAL_PROVIDER),
}


# =====================================================================
# Đọc cấu hình: quy ước <TÊN>_<HẬU_TỐ>, có chấp nhận tên biến CŨ
# =====================================================================

def _env(preset: ProviderPreset, suffix: str, *legacy_names: str, default: str = "") -> str:
    """Lấy biến môi trường `<TÊN>_<SUFFIX>`; không có thì thử các tên cũ; rồi tới `default`."""
    keys = [f"{preset.name.upper()}_{suffix}", *legacy_names]
    for key in keys:
        value = os.getenv(key)
        if value:
            return value.strip()
    return default


def _resolve_model(preset: ProviderPreset) -> str:
    """Model trích xuất. `LOCAL_MODEL`/`CLOUD_MODEL` là tên cũ, vẫn dùng được cho đúng chế độ."""
    legacy = ("LOCAL_MODEL",) if preset.deployment == DEPLOY_LOCAL else ("CLOUD_MODEL",)
    return _env(preset, "MODEL", *legacy, default=preset.default_model)


def _resolve_embed_model(preset: ProviderPreset) -> str:
    """Model embedding — YC-MS-05: tác vụ khác nhau được dùng model khác nhau."""
    return _env(preset, "EMBED_MODEL", "EMBED_MODEL", default=preset.default_embed_model)


def _resolve_deployment(preset: ProviderPreset) -> str:
    """
    Chế độ triển khai thực tế. Cho phép ghi đè bằng `<TÊN>_DEPLOYMENT` vì cùng một công cụ có thể
    được dựng ở hai nơi (vLLM trong phòng máy chủ ≠ vLLM thuê trên máy ảo ngoài).
    Giá trị lạ → giữ nguyên khai báo của preset (không đoán).
    """
    value = _env(preset, "DEPLOYMENT", default=preset.deployment).lower()
    if value not in (DEPLOY_CLOUD, DEPLOY_LOCAL):
        logger.warning("Giá trị %s_DEPLOYMENT không hợp lệ ('%s') → dùng '%s' theo bảng đăng ký",
                       preset.name.upper(), value, preset.deployment)
        return preset.deployment
    return value


def _assert_local_endpoint_is_internal(name: str, base_url: str) -> None:
    """
    Chốt an toàn cho ràng buộc cứng YC-DR-03: một provider khai báo `local` mà điểm cuối lại nằm ngoài
    hạ tầng nội bộ thì tài liệu Nhạy cảm sẽ bị gửi ra ngoài trong khi hệ thống vẫn tưởng an toàn.
    Trường hợp đó DỪNG ngay, buộc người quản trị xác nhận có ý thức.
    """
    if is_private_endpoint(base_url):
        return
    if os.getenv("ALLOW_PUBLIC_LOCAL_ENDPOINT", "").strip() in ("1", "true", "yes"):
        logger.warning(
            "Provider '%s' khai báo TẠI CHỖ nhưng điểm cuối '%s' KHÔNG thuộc dải nội bộ. "
            "Đã bỏ qua chốt an toàn vì ALLOW_PUBLIC_LOCAL_ENDPOINT được bật — "
            "người quản trị chịu trách nhiệm bảo đảm đường truyền này nằm trong tầm kiểm soát.",
            name, base_url,
        )
        return
    raise ValueError(
        f"Provider '{name}' được khai báo chế độ TẠI CHỖ nhưng điểm cuối '{base_url}' không thuộc "
        f"dải mạng nội bộ. Tài liệu Nội bộ/Nhạy cảm sẽ được gửi tới đây (ràng buộc cứng YC-DR-03), "
        f"nên hệ thống từ chối khởi tạo. Cách xử lý: (1) sửa {name.upper()}_BASE_URL về địa chỉ nội bộ, "
        f"hoặc (2) khai báo {name.upper()}_DEPLOYMENT=cloud nếu đây thực sự là dịch vụ ngoài, "
        f"hoặc (3) đặt ALLOW_PUBLIC_LOCAL_ENDPOINT=1 nếu đường truyền này đã được kiểm soát "
        f"(vd VPN/đường riêng của Nhà trường)."
    )


# =====================================================================
# Dựng provider theo họ giao thức
# =====================================================================

def _build_anthropic(preset: ProviderPreset, config) -> ModelProvider:
    from scripts.providers.cloud import ClaudeProvider
    return ClaudeProvider(
        api_key=os.getenv(preset.key_env),
        config=config,
        model=_resolve_model(preset) or None,   # None = giữ mặc định của ProcessingConfig
    )


def _build_ollama(preset: ProviderPreset, config) -> ModelProvider:
    from scripts.providers.local import OllamaProvider
    provider = OllamaProvider(
        base_url=_env(preset, "BASE_URL", "OLLAMA_URL", default=preset.base_url),
        model=_resolve_model(preset),
        embed_model=_resolve_embed_model(preset),
        config=config,
    )
    # Ollama gần như luôn chạy tại chỗ, nhưng vẫn cho khai báo ngược lại (vd Ollama trên máy ảo thuê ngoài)
    provider.deployment = _resolve_deployment(preset)
    return provider


def _build_openai_compat(preset: ProviderPreset, config) -> ModelProvider:
    from scripts.providers.openai_compat import OpenAICompatProvider
    base_url = _env(preset, "BASE_URL", default=preset.base_url)
    if not base_url:
        raise ValueError(
            f"Provider '{preset.name}' cần điểm cuối: đặt {preset.name.upper()}_BASE_URL "
            f"(vd http://vllm:8000/v1)."
        )
    return OpenAICompatProvider(
        base_url=base_url,
        model=_resolve_model(preset),
        embed_model=_resolve_embed_model(preset),
        api_key=os.getenv(preset.key_env) if preset.key_env else None,
        deployment=_resolve_deployment(preset),
        name=preset.name,
        json_mode=_env(preset, "JSON_MODE", default="1" if preset.json_mode else "0") not in ("0", "false", "no"),
        config=config,
    )


def _build_azure_openai(preset: ProviderPreset, config) -> ModelProvider:
    from scripts.providers.openai_compat import AzureOpenAIProvider
    base_url = _env(preset, "BASE_URL", "AZURE_OPENAI_ENDPOINT", default="")
    if not base_url:
        raise ValueError(
            "Azure OpenAI cần AZURE_OPENAI_BASE_URL (endpoint tài nguyên, "
            "vd https://<ten>.openai.azure.com)."
        )
    return AzureOpenAIProvider(
        base_url=base_url,
        model=_resolve_model(preset),          # ở Azure: TÊN DEPLOYMENT, không phải tên model gốc
        embed_model=_resolve_embed_model(preset),
        api_key=os.getenv(preset.key_env),
        deployment=_resolve_deployment(preset),
        name=preset.name,
        api_version=_env(preset, "API_VERSION", default="2024-10-21"),
        config=config,
    )


def _build_gemini(preset: ProviderPreset, config) -> ModelProvider:
    from scripts.providers.gemini import GeminiProvider
    return GeminiProvider(
        api_key=os.getenv(preset.key_env),
        model=_resolve_model(preset),
        base_url=_env(preset, "BASE_URL", default=preset.base_url),
        embed_model=_resolve_embed_model(preset),
        config=config,
    )


#: Họ giao thức → hàm dựng. THÊM GIAO THỨC MỚI = thêm một dòng ở đây (YC-MP-08).
_BUILDERS = {
    KIND_ANTHROPIC: _build_anthropic,
    KIND_OLLAMA: _build_ollama,
    KIND_OPENAI_COMPAT: _build_openai_compat,
    KIND_AZURE_OPENAI: _build_azure_openai,
    KIND_GEMINI: _build_gemini,
}


# =====================================================================
# API công khai
# =====================================================================

def resolve_provider_name(kind: Optional[str] = None) -> str:
    """Chuyển `kind` (tên công cụ hoặc bí danh chế độ cloud/local) thành TÊN CÔNG CỤ cụ thể."""
    kind = (kind or os.getenv("MODEL_PROVIDER", DEFAULT_PROVIDER)).lower().strip()
    if kind in _MODE_ALIASES:
        env_key, default_name = _MODE_ALIASES[kind]
        return os.getenv(env_key, default_name).lower().strip() or default_name
    return kind


def get_provider(kind: Optional[str] = None, config=None) -> ModelProvider:
    """
    Trả về provider theo `kind` (tên công cụ, bí danh `cloud`/`local`, hoặc env MODEL_PROVIDER).
    Ném ValueError nếu tên không có trong bảng đăng ký hoặc cấu hình thiếu/không an toàn.
    """
    name = resolve_provider_name(kind)
    preset = get_preset(name)
    if preset is None:
        raise ValueError(
            f"MODEL_PROVIDER không hợp lệ: '{name}'. Các lựa chọn: "
            f"{', '.join(sorted(PRESETS))} (hoặc bí danh 'cloud'/'local')."
        )

    provider = _BUILDERS[preset.kind](preset, config)

    # Chốt an toàn: chỉ kiểm điểm cuối HTTP của provider khai báo tại chỗ
    if provider.deployment == DEPLOY_LOCAL and provider.endpoint:
        _assert_local_endpoint_is_internal(provider.name, provider.endpoint)

    logger.info("Đã chọn model provider: %s", provider.describe())
    return provider
