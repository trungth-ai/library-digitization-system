#!/usr/bin/env python3
"""
Bảng đăng ký công cụ mô hình (YC-MP-04, YC-MS-06, YC-MS-08).

TRIẾT LÝ: Ollama **không** phải "chế độ tại chỗ"; nó là MỘT DÒNG trong bảng dưới đây. Thêm một công cụ
mới = thêm một dòng (nếu nói được giao thức đã có) hoặc thêm một dòng + một lớp `ModelProvider` (nếu
giao thức mới). Không sửa giao diện, không sửa pipeline — đúng phép thử YC-MP-08 / KT-CN-06c.

Bảng này cũng là nguồn dữ liệu cho giao diện quản trị "công cụ/model đang dùng + tình trạng" (YC-MS-08).

QUY ƯỚC BIẾN MÔI TRƯỜNG (đồng nhất cho mọi công cụ — `<TÊN>` là cột `name` viết HOA):
    <TÊN>_BASE_URL      điểm cuối         (vd VLLM_BASE_URL=http://vllm:8000/v1)
    <TÊN>_MODEL         model trích xuất  (vd VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct)
    <TÊN>_EMBED_MODEL   model embedding   (YC-MS-05 — tác vụ khác dùng model khác)
    <TÊN>_API_KEY       khóa (nếu cần)    (vd GROQ_API_KEY — trùng đúng quy ước của các nhà cung cấp)
Một số tên cũ vẫn được chấp nhận để không phá cấu hình đang chạy (xem `factory.py`).

⚠️ GIẤY PHÉP TRƯỚC, HIỆU NĂNG SAU: cột `default_model` chỉ là GỢI Ý cấu hình, KHÔNG phải kết luận được
phép dùng. Mọi model phải rà giấy phép và điền `docs/LICENSES.md` TRƯỚC khi tải/dùng (YC-PL-01/02).
"""

import ipaddress
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlparse

from scripts.providers.base import DEPLOY_CLOUD, DEPLOY_LOCAL

logger = logging.getLogger("provider.registry")

# Khóa `kind` = họ giao thức (quyết định dùng lớp hiện thực nào — xem factory._BUILDERS)
KIND_ANTHROPIC = "anthropic"
KIND_OLLAMA = "ollama"
KIND_OPENAI_COMPAT = "openai_compat"
KIND_AZURE_OPENAI = "azure_openai"
KIND_GEMINI = "gemini"


@dataclass(frozen=True)
class ProviderPreset:
    """Một lựa chọn công cụ mô hình đã cấu hình sẵn."""
    name: str                       # định danh dùng trong MODEL_PROVIDER
    label: str                      # nhãn tiếng Việt cho giao diện quản trị (YC-MS-08)
    kind: str                       # họ giao thức
    deployment: str                 # cloud | local — cơ sở của ràng buộc cứng YC-DR-03
    base_url: str = ""              # điểm cuối mặc định
    key_env: str = ""               # tên biến chứa khóa (chỉ TÊN, không bao giờ log giá trị)
    default_model: str = ""         # gợi ý, PHẢI rà giấy phép trước khi dùng (YC-PL)
    default_embed_model: str = ""
    json_mode: bool = True          # máy chủ có hỗ trợ response_format=json_object không
    note: str = ""


# =====================================================================
# TẠI CHỖ (on-premise) — dữ liệu KHÔNG ra khỏi hạ tầng Nhà trường.
# Đây là nhóm được phép xử lý tài liệu Nội bộ/Nhạy cảm (YC-DR-03).
# =====================================================================
_LOCAL_PRESETS = [
    ProviderPreset(
        name="ollama", label="Ollama (tại chỗ)", kind=KIND_OLLAMA, deployment=DEPLOY_LOCAL,
        base_url="http://localhost:11434", default_model="qwen2.5:7b",
        note="Dựng nhanh nhất, chạy CPU. Lựa chọn của GĐ0 (ADR-002). API gốc, không phải chuẩn OpenAI.",
    ),
    ProviderPreset(
        name="ollama_openai", label="Ollama (cổng tương thích OpenAI)", kind=KIND_OPENAI_COMPAT,
        deployment=DEPLOY_LOCAL, base_url="http://localhost:11434/v1", default_model="qwen2.5:7b",
        note="Cùng máy chủ Ollama nhưng qua /v1 — dùng khi cần một giao thức duy nhất cho mọi công cụ.",
    ),
    ProviderPreset(
        name="vllm", label="vLLM (tại chỗ, thông lượng cao)", kind=KIND_OPENAI_COMPAT,
        deployment=DEPLOY_LOCAL, base_url="http://localhost:8000/v1", key_env="VLLM_API_KEY",
        default_model="Qwen/Qwen2.5-7B-Instruct",
        note="Ứng viên thay Ollama khi nghẽn thông lượng (ADR-002). Cần GPU để phát huy; dựng phức tạp hơn.",
    ),
    ProviderPreset(
        name="llamacpp", label="llama.cpp (tại chỗ, nhẹ nhất)", kind=KIND_OPENAI_COMPAT,
        deployment=DEPLOY_LOCAL, base_url="http://localhost:8080/v1", default_model="local-model",
        json_mode=False,
        note="`llama-server` chạy GGUF. Tốn ít RAM nhất, phù hợp máy chủ không GPU. Bản cũ chưa có JSON mode.",
    ),
    ProviderPreset(
        name="lmstudio", label="LM Studio (máy trạm, thử nghiệm)", kind=KIND_OPENAI_COMPAT,
        deployment=DEPLOY_LOCAL, base_url="http://localhost:1234/v1", default_model="local-model",
        note="Dùng để cán bộ thử nhanh trên máy cá nhân trước khi đưa lên máy chủ.",
    ),
    ProviderPreset(
        name="tgi", label="HF text-generation-inference (tại chỗ)", kind=KIND_OPENAI_COMPAT,
        deployment=DEPLOY_LOCAL, base_url="http://localhost:8080/v1", default_model="tgi",
        note="TGI của Hugging Face; có cổng /v1 tương thích OpenAI ở bản mới.",
    ),
]

# =====================================================================
# ĐÁM MÂY — dữ liệu RA KHỎI tổ chức.
# ⚠️ Theo YC-DR-03, nhóm này CHỈ nhận tài liệu Công khai. Ràng buộc cứng, không được ghi đè.
# =====================================================================
_CLOUD_PRESETS = [
    ProviderPreset(
        name="claude", label="Anthropic Claude (đám mây)", kind=KIND_ANTHROPIC,
        deployment=DEPLOY_CLOUD, key_env="CLAUDE_API_KEY",
        note="Công cụ đang vận hành thật từ 2025. Mặc định của hệ thống — giữ nguyên hành vi (YC-MP-02).",
    ),
    ProviderPreset(
        name="openai", label="OpenAI (đám mây)", kind=KIND_OPENAI_COMPAT, deployment=DEPLOY_CLOUD,
        base_url="https://api.openai.com/v1", key_env="OPENAI_API_KEY",
        default_model="gpt-4o-mini", default_embed_model="text-embedding-3-small",
    ),
    ProviderPreset(
        name="azure_openai", label="Azure OpenAI (đám mây)", kind=KIND_AZURE_OPENAI,
        deployment=DEPLOY_CLOUD, key_env="AZURE_OPENAI_API_KEY",
        note="AZURE_OPENAI_BASE_URL = endpoint tài nguyên; AZURE_OPENAI_MODEL = TÊN DEPLOYMENT, "
             "không phải tên model gốc. Tùy chọn AZURE_OPENAI_API_VERSION.",
    ),
    ProviderPreset(
        name="gemini", label="Google Gemini (đám mây)", kind=KIND_GEMINI, deployment=DEPLOY_CLOUD,
        base_url="https://generativelanguage.googleapis.com/v1beta", key_env="GEMINI_API_KEY",
        default_model="gemini-2.0-flash", default_embed_model="text-embedding-004",
    ),
    ProviderPreset(
        name="openrouter", label="OpenRouter (đám mây, nhiều model)", kind=KIND_OPENAI_COMPAT,
        deployment=DEPLOY_CLOUD, base_url="https://openrouter.ai/api/v1", key_env="OPENROUTER_API_KEY",
        default_model="qwen/qwen-2.5-7b-instruct",
        note="Cổng trung gian tới nhiều nhà cung cấp — hữu ích để so sánh model NHANH trước khi tự dựng.",
    ),
    ProviderPreset(
        name="groq", label="Groq (đám mây, độ trễ thấp)", kind=KIND_OPENAI_COMPAT,
        deployment=DEPLOY_CLOUD, base_url="https://api.groq.com/openai/v1", key_env="GROQ_API_KEY",
        default_model="llama-3.3-70b-versatile",
    ),
    ProviderPreset(
        name="together", label="Together AI (đám mây)", kind=KIND_OPENAI_COMPAT,
        deployment=DEPLOY_CLOUD, base_url="https://api.together.xyz/v1", key_env="TOGETHER_API_KEY",
        default_model="Qwen/Qwen2.5-7B-Instruct-Turbo",
    ),
    ProviderPreset(
        name="deepseek", label="DeepSeek (đám mây)", kind=KIND_OPENAI_COMPAT,
        deployment=DEPLOY_CLOUD, base_url="https://api.deepseek.com/v1", key_env="DEEPSEEK_API_KEY",
        default_model="deepseek-chat",
    ),
    ProviderPreset(
        name="mistral", label="Mistral AI (đám mây)", kind=KIND_OPENAI_COMPAT,
        deployment=DEPLOY_CLOUD, base_url="https://api.mistral.ai/v1", key_env="MISTRAL_API_KEY",
        default_model="mistral-small-latest", default_embed_model="mistral-embed",
    ),
    # Lối mở tổng quát: bất kỳ điểm cuối tương thích OpenAI chưa có trong bảng (dịch vụ trong nước,
    # máy chủ nội bộ của đơn vị khác...). MẶC ĐỊNH AN TOÀN là `cloud`: một điểm cuối lạ phải bị coi là
    # "ra ngoài" cho tới khi người quản trị khai báo ngược lại (OPENAI_COMPAT_DEPLOYMENT=local).
    ProviderPreset(
        name="openai_compat", label="Điểm cuối tương thích OpenAI (tự khai báo)",
        kind=KIND_OPENAI_COMPAT, deployment=DEPLOY_CLOUD,
        key_env="OPENAI_COMPAT_API_KEY",
        note="Đặt OPENAI_COMPAT_BASE_URL + OPENAI_COMPAT_MODEL. Nếu là máy chủ trong hạ tầng của "
             "trường thì PHẢI khai báo OPENAI_COMPAT_DEPLOYMENT=local để được xử lý tài liệu nhạy cảm.",
    ),
]

PRESETS: Dict[str, ProviderPreset] = {p.name: p for p in (_LOCAL_PRESETS + _CLOUD_PRESETS)}


def get_preset(name: str) -> Optional[ProviderPreset]:
    return PRESETS.get((name or "").lower().strip())


def list_presets(deployment: Optional[str] = None) -> List[ProviderPreset]:
    """Danh sách công cụ khả dụng (cho giao diện quản trị YC-MS-08 / trợ giúp CLI)."""
    items = list(PRESETS.values())
    if deployment:
        items = [p for p in items if p.deployment == deployment]
    return items


# =====================================================================
# CHỐT AN TOÀN: "khai báo tại chỗ" phải THỰC SỰ là tại chỗ
# =====================================================================

def is_private_endpoint(base_url: str) -> bool:
    """
    Điểm cuối có nằm trong hạ tầng nội bộ không?

    VÌ SAO CẦN: ràng buộc cứng YC-DR-03 dựa vào `deployment`. Nếu người quản trị vô tình khai báo một
    dịch vụ đám mây là `local`, tài liệu Nhạy cảm sẽ được gửi ra ngoài mà hệ thống vẫn tưởng an toàn —
    đúng loại sự cố mà YC-DR-03 sinh ra để chặn. Hàm này là lớp phòng vệ thứ hai.

    Coi là nội bộ: localhost/127.x, dải IP riêng (RFC1918/CGNAT), tên miền .local/.internal/.lan/.intranet,
    và tên máy một nhãn (vd "ollama", "vllm" — tên service trong mạng Docker).
    """
    host = (urlparse(base_url).hostname or "").lower()
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass  # là tên máy, không phải IP
    if host in ("localhost",) or host.endswith(".localhost"):
        return True
    if any(host.endswith(sfx) for sfx in (".local", ".internal", ".lan", ".intranet", ".home.arpa")):
        return True
    return "." not in host   # tên một nhãn = tên service nội bộ (Docker/K8s)
