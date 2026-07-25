#!/usr/bin/env python3
"""
Kiểm thử nhiều nhà cung cấp mô hình — Ollama chỉ là MỘT lựa chọn (YC-MP-03/04/08, YC-MS-05/06, YC-DR-03).

Toàn bộ test dùng MOCK HTTP → chạy được ở máy dev không có vLLM/llama.cpp/khóa API, và chạy được khi
ngắt mạng. Test THẬT với công cụ thật phải chạy trên máy chủ (xem docs/LOCAL_MODE.md).

Chạy: pytest tests/test_multi_provider.py -v
"""

import json
import pytest

from scripts.providers.base import (
    DEPLOY_CLOUD, DEPLOY_LOCAL, ExtractionSchema, ModelProvider,
    SENSITIVITY_PUBLIC, SENSITIVITY_SENSITIVE,
)
from scripts.providers.factory import get_provider, resolve_provider_name
from scripts.providers.gemini import GeminiProvider
from scripts.providers.openai_compat import AzureOpenAIProvider, OpenAICompatProvider
from scripts.providers.registry import PRESETS, is_private_endpoint, list_presets
from scripts.providers.router import get_routed_provider
from scripts.core.exceptions import SensitivityViolation

BOOK_SCHEMA = ExtractionSchema(code="dublin_core", document_type="book")
CONG_VAN_SCHEMA = ExtractionSchema(
    code="cong_van", document_type="cong_van",
    fields=[], sensitivity=SENSITIVITY_SENSITIVE,
)

CANNED_JSON = (
    '{"title":"Giáo trình CSDL","authors":["Phạm, E"],"subjects":["CSDL"],'
    '"abstract":"Tóm tắt.","type":"Book","language":"vi"}'
)


def _chat_response(content: str) -> dict:
    """Phản hồi đúng khuôn OpenAI /chat/completions."""
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


# =====================================================================
# 1. OpenAICompatProvider — phủ vLLM / llama.cpp / LM Studio / TGI / OpenAI / Groq...
# =====================================================================

def test_openai_compat_trich_xuat_giong_parser_chung(monkeypatch):
    """Kết quả phải đi qua ĐÚNG parser dùng chung với các provider khác (KT-CX-03)."""
    prov = OpenAICompatProvider(
        base_url="http://vllm:8000/v1", model="Qwen/Qwen2.5-7B-Instruct",
        deployment=DEPLOY_LOCAL, name="vllm",
    )
    monkeypatch.setattr(prov, "_request", lambda p, payload=None, method="POST": _chat_response(CANNED_JSON))

    result = prov.extract_fields("nội dung", BOOK_SCHEMA).to_metadata_list()
    expected = prov._extractor._build_metadata(json.loads(CANNED_JSON))["metadata"]
    assert result == expected
    assert any(f["key"] == "dc.title" and f["value"] == "Giáo trình CSDL" for f in result)


def test_openai_compat_gui_dung_dinh_dang_yeu_cau(monkeypatch):
    """YC-MP-03: gửi đúng định dạng — model, messages, temperature 0, JSON mode."""
    prov = OpenAICompatProvider(base_url="http://vllm:8000/v1", model="m1", deployment=DEPLOY_LOCAL)
    seen = {}

    def _fake(path, payload=None, method="POST"):
        seen["path"], seen["payload"] = path, payload
        return _chat_response(CANNED_JSON)

    monkeypatch.setattr(prov, "_request", _fake)
    prov.extract_fields("nội dung", BOOK_SCHEMA)

    assert seen["path"] == "/chat/completions"
    assert seen["payload"]["model"] == "m1"
    assert seen["payload"]["messages"][0]["role"] == "user"
    assert seen["payload"]["temperature"] == 0          # trích xuất phải tái lập được
    assert seen["payload"]["response_format"] == {"type": "json_object"}


def test_openai_compat_may_chu_khong_ho_tro_json_mode(monkeypatch):
    """llama.cpp/TGI bản cũ báo lỗi 'response_format' → thử lại một lần không dùng JSON mode."""
    prov = OpenAICompatProvider(base_url="http://llamacpp:8080/v1", model="m1", deployment=DEPLOY_LOCAL)
    calls = []

    def _fake(path, payload=None, method="POST"):
        calls.append(payload)
        if len(calls) == 1:
            raise RuntimeError("HTTP 400: unknown field response_format")
        return _chat_response(CANNED_JSON)

    monkeypatch.setattr(prov, "_request", _fake)
    result = prov.extract_fields("nội dung", BOOK_SCHEMA).to_metadata_list()

    assert len(calls) == 2
    assert "response_format" not in calls[1]
    assert any(f["key"] == "dc.title" for f in result)


def test_openai_compat_loi_thi_khong_mat_du_lieu(monkeypatch):
    """YC-MP-05: điểm cuối chết → rơi về basic extraction, không ném ra ngoài, không mất dữ liệu."""
    prov = OpenAICompatProvider(base_url="http://vllm:8000/v1", model="m1", deployment=DEPLOY_LOCAL)

    def _boom(path, payload=None, method="POST"):
        raise RuntimeError("vLLM chết")

    monkeypatch.setattr(prov, "_request", _boom)
    keys = [f["key"] for f in prov.extract_fields("Tiêu đề tài liệu\nnội dung", BOOK_SCHEMA).to_metadata_list()]
    assert "dc.title" in keys and "dc.type" in keys


def test_openai_compat_embed_dung_model_rieng(monkeypatch):
    """YC-MS-05: embedding dùng `embed_model`, KHÔNG dùng model sinh văn bản."""
    prov = OpenAICompatProvider(
        base_url="http://vllm:8000/v1", model="qwen-chat", embed_model="bge-m3",
        deployment=DEPLOY_LOCAL,
    )
    seen = {}

    def _fake(path, payload=None, method="POST"):
        seen["payload"] = payload
        # Trả lệch thứ tự index để kiểm tra việc sắp lại đúng thứ tự đầu vào
        return {"data": [{"index": 1, "embedding": [0.3]}, {"index": 0, "embedding": [0.1]}]}

    monkeypatch.setattr(prov, "_request", _fake)
    vecs = prov.embed(["a", "b"])

    assert seen["payload"]["model"] == "bge-m3"
    assert vecs == [[0.1], [0.3]]


def test_openai_compat_health_bao_thieu_model(monkeypatch):
    """YC-MS-04: điểm cuối sống nhưng chưa nạp model cấu hình → ready=False, thông báo tiếng Việt rõ."""
    prov = OpenAICompatProvider(base_url="http://vllm:8000/v1", model="thieu-model", deployment=DEPLOY_LOCAL)
    monkeypatch.setattr(prov, "_request",
                        lambda p, payload=None, method="POST": {"data": [{"id": "model-khac"}]})
    h = prov.health()
    assert h.ready is False
    assert "thieu-model" in h.detail


def test_openai_compat_khong_gui_header_khoa_khi_khong_co_khoa():
    """Máy chủ tại chỗ không cần khóa → tuyệt đối không gửi Authorization rỗng."""
    prov = OpenAICompatProvider(base_url="http://vllm:8000/v1", model="m1", deployment=DEPLOY_LOCAL)
    assert "Authorization" not in prov._headers()

    prov_key = OpenAICompatProvider(base_url="https://api.groq.com/openai/v1", model="m1", api_key="k")
    assert prov_key._headers()["Authorization"] == "Bearer k"


def test_azure_dung_duong_dan_va_header_rieng():
    """Azure: đường dẫn theo deployment + header `api-key` (không phải Bearer)."""
    prov = AzureOpenAIProvider(
        base_url="https://hpu.openai.azure.com", model="gpt4o-hpu", api_key="k",
        api_version="2024-10-21",
    )
    url = prov._url("/chat/completions")
    assert "/openai/deployments/gpt4o-hpu/chat/completions" in url
    assert "api-version=2024-10-21" in url
    assert prov._headers()["api-key"] == "k"
    assert "Authorization" not in prov._headers()


# =====================================================================
# 2. GeminiProvider — định dạng dây khác hẳn (phép thử YC-MP-08)
# =====================================================================

def test_gemini_trich_xuat(monkeypatch):
    prov = GeminiProvider(api_key="k", model="gemini-2.0-flash")
    seen = {}

    def _fake(path, payload=None, method="POST"):
        seen["path"], seen["payload"] = path, payload
        return {"candidates": [{"content": {"parts": [{"text": CANNED_JSON}]}}]}

    monkeypatch.setattr(prov, "_request", _fake)
    result = prov.extract_fields("nội dung", BOOK_SCHEMA).to_metadata_list()

    assert seen["path"] == "/models/gemini-2.0-flash:generateContent"
    assert seen["payload"]["contents"][0]["parts"][0]["text"]
    assert seen["payload"]["generationConfig"]["responseMimeType"] == "application/json"
    assert any(f["key"] == "dc.title" for f in result)


def test_gemini_khoa_di_qua_header_khong_qua_url():
    """Khóa API phải nằm ở header, không nằm trong query string (YC-BM-03: không lộ khóa vào log)."""
    prov = GeminiProvider(api_key="secret-key")
    assert prov._headers()["x-goog-api-key"] == "secret-key"
    assert "secret-key" not in prov.endpoint
    assert "secret-key" not in json.dumps(prov.describe())


def test_gemini_bi_chan_thi_khong_mat_du_lieu(monkeypatch):
    """Bộ lọc an toàn chặn → không có candidates → rơi về basic, không ném ra ngoài (YC-MP-05)."""
    prov = GeminiProvider(api_key="k")
    monkeypatch.setattr(prov, "_request",
                        lambda p, payload=None, method="POST": {"promptFeedback": {"blockReason": "SAFETY"}})
    keys = [f["key"] for f in prov.extract_fields("Tiêu đề\nnội dung", BOOK_SCHEMA).to_metadata_list()]
    assert "dc.title" in keys


def test_gemini_thieu_khoa_thi_health_bao_ro():
    h = GeminiProvider(api_key=None).health()
    assert h.ready is False and "GEMINI_API_KEY" in h.detail


# =====================================================================
# 3. Bảng đăng ký + factory (YC-MP-04, YC-MS-06)
# =====================================================================

def test_moi_preset_deu_dung_duoc_va_khai_bao_day_du():
    """Bảng đăng ký phải nhất quán: chế độ hợp lệ, có nhãn tiếng Việt, có công cụ ở CẢ HAI chế độ."""
    for name, preset in PRESETS.items():
        assert preset.deployment in (DEPLOY_CLOUD, DEPLOY_LOCAL), name
        assert preset.label, name
    assert len(list_presets(DEPLOY_LOCAL)) >= 4     # Ollama KHÔNG còn là lựa chọn duy nhất
    assert len(list_presets(DEPLOY_CLOUD)) >= 4


@pytest.mark.parametrize("name,expect_deployment", [
    ("ollama", DEPLOY_LOCAL),
    ("vllm", DEPLOY_LOCAL),
    ("llamacpp", DEPLOY_LOCAL),
    ("lmstudio", DEPLOY_LOCAL),
    ("tgi", DEPLOY_LOCAL),
    ("ollama_openai", DEPLOY_LOCAL),
    ("claude", DEPLOY_CLOUD),
    ("openai", DEPLOY_CLOUD),
    ("gemini", DEPLOY_CLOUD),
    ("groq", DEPLOY_CLOUD),
    ("openrouter", DEPLOY_CLOUD),
    ("together", DEPLOY_CLOUD),
    ("deepseek", DEPLOY_CLOUD),
    ("mistral", DEPLOY_CLOUD),
])
def test_factory_dung_duoc_moi_cong_cu_qua_cau_hinh(monkeypatch, name, expect_deployment):
    """KT-CN-05: đổi công cụ CHỈ bằng biến môi trường, không sửa mã."""
    monkeypatch.setenv("MODEL_PROVIDER", name)
    p = get_provider()
    assert isinstance(p, ModelProvider)
    assert p.name == name
    assert p.deployment == expect_deployment


def test_factory_azure_thieu_endpoint_bao_loi_ro(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "azure_openai")
    monkeypatch.delenv("AZURE_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    with pytest.raises(ValueError, match="AZURE_OPENAI_BASE_URL"):
        get_provider()


def test_bi_danh_che_do_tro_toi_cong_cu_dang_cau_hinh(monkeypatch):
    """Chế độ tại chỗ có thể là vLLM thay vì Ollama — chỉ đổi LOCAL_PROVIDER."""
    monkeypatch.setenv("LOCAL_PROVIDER", "vllm")
    monkeypatch.setenv("CLOUD_PROVIDER", "gemini")
    assert resolve_provider_name("local") == "vllm"
    assert resolve_provider_name("cloud") == "gemini"

    p = get_provider(kind="local")
    assert p.name == "vllm" and p.deployment == DEPLOY_LOCAL


def test_ghi_de_diem_cuoi_va_model_bang_bien_moi_truong(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "vllm")
    monkeypatch.setenv("VLLM_BASE_URL", "http://10.1.1.101:8000/v1")
    monkeypatch.setenv("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct")
    monkeypatch.setenv("VLLM_EMBED_MODEL", "BAAI/bge-m3")
    p = get_provider()
    assert p.endpoint == "http://10.1.1.101:8000/v1"
    assert p.model == "Qwen/Qwen2.5-14B-Instruct"
    assert p.embed_model == "BAAI/bge-m3"


def test_describe_ghi_du_thong_tin_cho_nhat_ky(monkeypatch):
    """YC-MP-06: nhật ký phải phân biệt được công cụ + chế độ + model."""
    monkeypatch.setenv("MODEL_PROVIDER", "vllm")
    info = get_provider().describe()
    assert info["provider"] == "vllm"
    assert info["deployment"] == DEPLOY_LOCAL
    assert "model" in info and "endpoint" in info


# =====================================================================
# 4. Chốt an toàn: "khai báo tại chỗ" phải THỰC SỰ nội bộ (YC-DR-03)
# =====================================================================

@pytest.mark.parametrize("url,expected", [
    ("http://localhost:11434", True),
    ("http://127.0.0.1:8000/v1", True),
    ("http://10.1.1.101:8000/v1", True),
    ("http://192.168.1.50:8080/v1", True),
    ("http://ollama:11434", True),           # tên service Docker
    ("http://vllm.local:8000/v1", True),
    ("https://api.groq.com/openai/v1", False),
    ("https://openrouter.ai/api/v1", False),
])
def test_nhan_dien_diem_cuoi_noi_bo(url, expected):
    assert is_private_endpoint(url) is expected


def test_tu_choi_khi_khai_bao_tai_cho_nhung_diem_cuoi_ra_ngoai(monkeypatch):
    """Cấu hình nguy hiểm nhất: điểm cuối công cộng đội lốt 'tại chỗ' → phải DỪNG, không âm thầm chạy."""
    monkeypatch.setenv("MODEL_PROVIDER", "vllm")
    monkeypatch.setenv("VLLM_BASE_URL", "https://vllm-thue-ngoai.example.com/v1")
    monkeypatch.delenv("ALLOW_PUBLIC_LOCAL_ENDPOINT", raising=False)
    with pytest.raises(ValueError, match="ràng buộc cứng YC-DR-03"):
        get_provider()


def test_cho_phep_khi_nguoi_quan_tri_xac_nhan_co_y_thuc(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "vllm")
    monkeypatch.setenv("VLLM_BASE_URL", "https://vllm-qua-vpn.example.com/v1")
    monkeypatch.setenv("ALLOW_PUBLIC_LOCAL_ENDPOINT", "1")
    assert get_provider().deployment == DEPLOY_LOCAL


def test_khai_bao_lai_thanh_dam_may_thi_khong_bi_chan(monkeypatch):
    """Cách xử lý đúng khi công cụ thực sự ở ngoài: khai báo cloud → được chạy, nhưng mất quyền
    xử lý tài liệu nhạy cảm (đúng ý nghĩa YC-DR-03)."""
    monkeypatch.setenv("MODEL_PROVIDER", "vllm")
    monkeypatch.setenv("VLLM_BASE_URL", "https://vllm-thue-ngoai.example.com/v1")
    monkeypatch.setenv("VLLM_DEPLOYMENT", "cloud")
    p = get_provider()
    assert p.name == "vllm" and p.deployment == DEPLOY_CLOUD


# =====================================================================
# 5. Định tuyến vẫn đúng khi chế độ tại chỗ KHÔNG phải Ollama (YC-DR-03)
# =====================================================================

def test_dinh_tuyen_tai_lieu_nhay_cam_toi_cong_cu_tai_cho_bat_ky(monkeypatch):
    monkeypatch.setenv("LOCAL_PROVIDER", "llamacpp")
    provider, mode = get_routed_provider(CONG_VAN_SCHEMA)
    assert mode == DEPLOY_LOCAL
    assert provider.name == "llamacpp" and provider.deployment == DEPLOY_LOCAL


def test_dinh_tuyen_chan_cau_hinh_lam_vo_hieu_rang_buoc_cung(monkeypatch):
    """
    Kịch bản rò rỉ nguy hiểm: người quản trị đặt LOCAL_PROVIDER=groq (dịch vụ đám mây).
    Nếu định tuyến chỉ tin vào chuỗi 'local' thì tài liệu Nhạy cảm sẽ ra ngoài.
    """
    monkeypatch.setenv("LOCAL_PROVIDER", "groq")
    with pytest.raises(SensitivityViolation, match="đám mây"):
        get_routed_provider(CONG_VAN_SCHEMA)


def test_tai_lieu_cong_khai_van_ra_dam_may_theo_cau_hinh(monkeypatch):
    monkeypatch.setenv("CLOUD_PROVIDER", "openai")
    provider, mode = get_routed_provider(
        ExtractionSchema(code="dublin_core", sensitivity=SENSITIVITY_PUBLIC)
    )
    assert mode == DEPLOY_CLOUD and provider.name == "openai"


def test_che_do_dam_may_dung_cong_cu_tai_cho_thi_cho_phep(monkeypatch):
    """An toàn hơn yêu cầu (public nhưng xử lý tại chỗ) → không được chặn."""
    monkeypatch.setenv("CLOUD_PROVIDER", "ollama")
    provider, mode = get_routed_provider(
        ExtractionSchema(code="dublin_core", sensitivity=SENSITIVITY_PUBLIC)
    )
    assert mode == DEPLOY_CLOUD and provider.deployment == DEPLOY_LOCAL
