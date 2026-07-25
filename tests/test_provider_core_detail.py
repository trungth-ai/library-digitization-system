#!/usr/bin/env python3
"""
Kiểm thử CHI TIẾT phần lõi của lớp trừu tượng hóa mô hình (ADR-007).

`test_multi_provider.py` kiểm đường chính của từng công cụ. File này đi vào các nhánh dễ bị bỏ sót —
chính là nơi lỗi thật hay nằm:
  1. Hợp đồng của `TextGenProvider`: thêm một công cụ mới thật sự chỉ tốn mấy dòng không? (YC-MP-08)
  2. Trích xuất theo LƯỢC ĐỒ TỔNG QUÁT (không phải Dublin Core) — YC-SC + chống ảo giác.
  3. Nhánh lỗi/biên: phản hồi rỗng, model chưa tải, JSON rác, khóa bị lộ.
  4. Tương thích ngược tên biến môi trường/tên lớp cũ (nguyên tắc "bổ sung, không viết lại").

Toàn bộ dùng mock → chạy được khi ngắt mạng, không cần máy chủ model nào.
Chạy: pytest tests/test_provider_core_detail.py -v
"""

import json
import urllib.error
import pytest

from scripts.providers.base import (
    DEPLOY_CLOUD, DEPLOY_LOCAL, ExtractionSchema, ProviderHealth, SchemaField,
)
from scripts.providers.factory import get_provider, resolve_provider_name
from scripts.providers.gemini import GeminiProvider
from scripts.providers.local import LocalProvider, OllamaProvider
from scripts.providers.cloud import ClaudeProvider, CloudProvider
from scripts.providers.openai_compat import AzureOpenAIProvider, OpenAICompatProvider
from scripts.providers.registry import is_private_endpoint
from scripts.providers.textgen import TextGenProvider

CANNED_JSON = (
    '{"title":"Giáo trình CSDL","authors":["Phạm, E"],"subjects":["CSDL"],'
    '"abstract":"Tóm tắt.","type":"Book","language":"vi"}'
)
BOOK_SCHEMA = ExtractionSchema(code="dublin_core", document_type="book")

# Lược đồ công văn — dùng để kiểm đường trích xuất theo lược đồ bất kỳ (YC-SC)
CONG_VAN_SCHEMA = ExtractionSchema(
    code="cong_van", document_type="cong_van",
    fields=[
        SchemaField(key="so_hieu", label="Số hiệu", required=True),
        SchemaField(key="ngay_ban_hanh", label="Ngày ban hành", data_type="date"),
        SchemaField(key="noi_nhan", label="Nơi nhận", data_type="list"),
        SchemaField(key="do_mat", label="Độ mật"),
    ],
)


def _chat(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class _FakeResp:
    """Giả lập phản hồi của urllib (context manager)."""

    def __init__(self, payload, status=200):
        self._data = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# =====================================================================
# 1. HỢP ĐỒNG TextGenProvider — phép thử YC-MP-08 / KT-CN-06c
# =====================================================================

class _CongCuMoi(TextGenProvider):
    """Toàn bộ một công cụ mô hình mới: 5 dòng thân lớp. Đây chính là điều YC-MP-08 đòi hỏi."""

    name = "cong_cu_moi"
    deployment = DEPLOY_LOCAL
    model = "model-gia-lap"

    def _complete(self, prompt: str) -> str:
        return CANNED_JSON

    def health(self) -> ProviderHealth:
        return ProviderHealth(ready=True, detail="ok")


def test_them_cong_cu_moi_chi_can_ham_complete():
    """Lớp con KHÔNG viết lại prompt/parse/dự phòng/nhật ký mà vẫn trích xuất đầy đủ."""
    prov = _CongCuMoi()
    fields = prov.extract_fields("nội dung", BOOK_SCHEMA).to_metadata_list()

    assert any(f["key"] == "dc.title" and f["value"] == "Giáo trình CSDL" for f in fields)
    # Kết quả phải trùng KHỚP TỪNG BIT với parser dùng chung → hai chế độ so sánh được công bằng
    assert fields == prov._extractor._build_metadata(json.loads(CANNED_JSON))["metadata"]
    assert prov.health().ready is True


def test_cong_cu_moi_khong_ho_tro_embedding_thi_bao_ro():
    """Mặc định `embed()` ném lỗi CÓ TÊN provider — không trả vector rỗng âm thầm."""
    with pytest.raises(NotImplementedError) as e:
        _CongCuMoi().embed(["a"])
    assert "cong_cu_moi" in str(e.value)


def test_moi_provider_deu_khai_bao_che_do_hop_le():
    """Bất biến toàn lớp: `deployment` phải là cloud|local để ràng buộc cứng YC-DR-03 có nghĩa."""
    provs = [
        _CongCuMoi(),
        OllamaProvider(),
        ClaudeProvider(api_key=None),
        GeminiProvider(api_key=None),
        OpenAICompatProvider(base_url="http://x:8000/v1", model="m", deployment=DEPLOY_LOCAL),
    ]
    for p in provs:
        assert p.deployment in (DEPLOY_CLOUD, DEPLOY_LOCAL), p.name
        assert p.describe()["deployment"] == p.deployment


def test_json_rac_thi_roi_ve_basic_khong_nem_ra_ngoai():
    """Model trả chuỗi không phải JSON → YC-MP-05: vẫn có metadata, không mất tài liệu."""

    class _TraRac(_CongCuMoi):
        def _complete(self, prompt):
            return "Xin lỗi, tôi không thể trả JSON."

    keys = [f["key"] for f in _TraRac().extract_fields("Tiêu đề\nnội dung", BOOK_SCHEMA).to_metadata_list()]
    assert "dc.title" in keys and "dc.type" in keys


def test_json_boc_trong_markdown_van_parse_duoc():
    """Model hay bọc ```json ... ``` — phải bóc được, không rơi oan về basic."""

    class _BocMarkdown(_CongCuMoi):
        def _complete(self, prompt):
            return f"```json\n{CANNED_JSON}\n```"

    fields = _BocMarkdown().extract_fields("nội dung", BOOK_SCHEMA).to_metadata_list()
    assert any(f["value"] == "Giáo trình CSDL" for f in fields)


# =====================================================================
# 2. TRÍCH XUẤT THEO LƯỢC ĐỒ TỔNG QUÁT (YC-SC) + chống ảo giác
# =====================================================================

def test_luoc_do_tong_quat_prompt_liet_ke_dung_truong():
    """Prompt phải nêu đủ khóa + nhãn tiếng Việt, và yêu cầu null khi không thấy (chống bịa)."""
    prov = OpenAICompatProvider(base_url="http://vllm:8000/v1", model="m", deployment=DEPLOY_LOCAL)
    seen = {}

    def _fake(path, payload=None, method="POST"):
        seen["prompt"] = payload["messages"][0]["content"]
        return _chat('{"so_hieu":"123/QĐ-ĐHQLCN","ngay_ban_hanh":"15/03/2024","noi_nhan":null,"do_mat":null}')

    monkey_prompt = prov._request
    prov._request = _fake
    result = prov.extract_fields("Văn bản mẫu", CONG_VAN_SCHEMA)
    prov._request = monkey_prompt

    for key in ("so_hieu", "ngay_ban_hanh", "noi_nhan", "do_mat"):
        assert key in seen["prompt"]
    assert "Số hiệu" in seen["prompt"] and "null" in seen["prompt"]

    # Trường null KHÔNG được sinh ra giá trị (KT-CX-05: bịa = SAI)
    got = {f.key: f.value for f in result.fields}
    assert got == {"so_hieu": "123/QĐ-ĐHQLCN", "ngay_ban_hanh": "15/03/2024"}


def test_luoc_do_tong_quat_ho_tro_da_gia_tri():
    """Trường `list` (nơi nhận, nhiều tác giả) → nhiều FieldValue cùng khóa."""
    prov = OpenAICompatProvider(base_url="http://vllm:8000/v1", model="m", deployment=DEPLOY_LOCAL)
    prov._request = lambda path, payload=None, method="POST": _chat(
        '{"so_hieu":"01/TB","noi_nhan":["Phòng Đào tạo","Thư viện"]}'
    )
    values = [(f.key, f.value) for f in prov.extract_fields("x", CONG_VAN_SCHEMA).fields]
    assert ("noi_nhan", "Phòng Đào tạo") in values
    assert ("noi_nhan", "Thư viện") in values


def test_luoc_do_tong_quat_loi_thi_tra_rong_khong_bia():
    """Lược đồ tổng quát KHÔNG có basic extraction → lỗi phải trả RỖNG, tuyệt đối không bịa."""
    prov = OpenAICompatProvider(base_url="http://vllm:8000/v1", model="m", deployment=DEPLOY_LOCAL)

    def _boom(path, payload=None, method="POST"):
        raise RuntimeError("máy chủ chết")

    prov._request = _boom
    assert prov.extract_fields("x", CONG_VAN_SCHEMA).fields == []


def test_gemini_cung_di_duong_luoc_do_tong_quat():
    """Cùng một lược đồ, cùng một parser — bất kể công cụ nào (KT-CX-03)."""
    prov = GeminiProvider(api_key="k")
    prov._request = lambda path, payload=None, method="POST": {
        "candidates": [{"content": {"parts": [{"text": '{"so_hieu":"07/CV","do_mat":null}'}]}}]
    }
    got = {f.key: f.value for f in prov.extract_fields("x", CONG_VAN_SCHEMA).fields}
    assert got == {"so_hieu": "07/CV"}


# =====================================================================
# 3. NHÁNH LỖI / BIÊN
# =====================================================================

def test_phan_hoi_thieu_choices_bao_loi_ro():
    prov = OpenAICompatProvider(base_url="http://vllm:8000/v1", model="m", deployment=DEPLOY_LOCAL)
    prov._request = lambda path, payload=None, method="POST": {"usage": {}}
    with pytest.raises(RuntimeError, match="choices"):
        prov._complete("prompt")


def test_loi_http_khong_lo_khoa_api(monkeypatch):
    """Thông báo lỗi được phép chứa thân phản hồi, nhưng KHÔNG BAO GIỜ chứa khóa (YC-BM-03)."""
    prov = OpenAICompatProvider(
        base_url="https://api.groq.com/openai/v1", model="m", api_key="sk-bi-mat-tuyet-doi",
    )

    def _raise(req, timeout=None):
        raise urllib.error.HTTPError(
            "https://api.groq.com/openai/v1/chat/completions", 401, "Unauthorized", {},
            __import__("io").BytesIO(b'{"error":"invalid api key"}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    with pytest.raises(RuntimeError) as e:
        prov._request("/chat/completions", {"a": 1})
    assert "401" in str(e.value) and "invalid api key" in str(e.value)
    assert "sk-bi-mat-tuyet-doi" not in str(e.value)


def test_ollama_health_bao_chua_tai_model(monkeypatch):
    """YC-MS-04: Ollama sống nhưng chưa `pull` model → ready=False + câu lệnh cần chạy."""
    prov = OllamaProvider(model="qwen2.5:7b")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _FakeResp({"models": [{"name": "llama3:8b"}]}),
    )
    h = prov.health()
    assert h.ready is False
    assert "ollama pull qwen2.5:7b" in h.detail


def test_ollama_health_san_sang_khi_da_co_model(monkeypatch):
    prov = OllamaProvider(model="qwen2.5:7b")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _FakeResp({"models": [{"name": "qwen2.5:7b"}]}),
    )
    assert prov.health().ready is True


def test_ollama_gui_dung_tham_so_ep_json(monkeypatch):
    """Ollama có `format: json` — lợi thế riêng, phải thực sự được gửi."""
    prov = OllamaProvider(model="qwen2.5:7b")
    seen = {}
    monkeypatch.setattr(prov, "_post_json",
                        lambda path, payload: (seen.update(path=path, payload=payload),
                                               {"response": CANNED_JSON})[1])
    prov.extract_fields("x", BOOK_SCHEMA)
    assert seen["path"] == "/api/generate"
    assert seen["payload"]["format"] == "json"
    assert seen["payload"]["options"]["temperature"] == 0
    assert seen["payload"]["stream"] is False


def test_ollama_embed_dung_model_rieng(monkeypatch):
    """YC-MS-05: `OLLAMA_EMBED_MODEL` (vd bge-m3) thay vì model sinh văn bản."""
    prov = OllamaProvider(model="qwen2.5:7b", embed_model="bge-m3")
    seen = []
    monkeypatch.setattr(prov, "_post_json",
                        lambda path, payload: (seen.append(payload), {"embedding": [0.5]})[1])
    assert prov.embed(["a", "b"]) == [[0.5], [0.5]]
    assert all(p["model"] == "bge-m3" for p in seen)


def test_azure_khong_doi_chieu_ten_model_khi_health(monkeypatch):
    """Azure liệt kê model GỐC, không phải tên deployment → không được báo sai 'thiếu model'."""
    prov = AzureOpenAIProvider(base_url="https://hpu.openai.azure.com", model="gpt4o-hpu", api_key="k")
    prov._request = lambda path, payload=None, method="POST": {"data": [{"id": "gpt-4o"}]}
    assert prov.health().ready is True


def test_describe_khong_bao_gio_chua_khoa():
    """Nhật ký YC-MP-06 nhúng `describe()` → phải sạch khóa với MỌI provider."""
    provs = [
        OpenAICompatProvider(base_url="https://api.openai.com/v1", model="m", api_key="sk-lo-khoa"),
        AzureOpenAIProvider(base_url="https://hpu.openai.azure.com", model="d", api_key="sk-lo-khoa"),
        GeminiProvider(api_key="sk-lo-khoa"),
    ]
    for p in provs:
        assert "sk-lo-khoa" not in json.dumps(p.describe(), ensure_ascii=False)


@pytest.mark.parametrize("url", ["", "khong-phai-url", "http://", "file:///etc/passwd"])
def test_diem_cuoi_khong_phan_giai_duoc_thi_khong_coi_la_noi_bo(url):
    """Mặc định an toàn: không xác định được host → KHÔNG coi là nội bộ (thà từ chối oan)."""
    assert is_private_endpoint(url) is False


# =====================================================================
# 3b. ĐƯỜNG TRUYỀN HTTP THẬT (chỉ chặn ở `urlopen`)
#
# Các test trên đây mock `_request`, nên KHÔNG kiểm được phần dễ sai nhất khi trỏ vào máy chủ thật:
# URL ghép có đúng không, header có thực sự được gửi không, thân yêu cầu có phải JSON UTF-8 không.
# Nhóm test này chỉ chặn ở `urllib.request.urlopen` → chạy qua toàn bộ `_request`.
# =====================================================================

def _bat_request(monkeypatch, payload_tra_ve: dict) -> dict:
    """Chặn urlopen, ghi lại đối tượng Request đã dựng, trả về phản hồi giả."""
    bat = {}

    def _fake_urlopen(req, timeout=None):
        bat["url"] = req.full_url
        bat["method"] = req.get_method()
        bat["headers"] = dict(req.header_items())
        bat["body"] = json.loads(req.data.decode("utf-8")) if req.data else None
        bat["timeout"] = timeout
        return _FakeResp(payload_tra_ve)

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    return bat


def test_openai_compat_ghep_url_va_header_dung(monkeypatch):
    prov = OpenAICompatProvider(
        base_url="http://vllm:8000/v1/", model="Qwen/Qwen2.5-7B-Instruct",  # cố ý có dấu / thừa
        api_key="sk-test", deployment=DEPLOY_LOCAL, name="vllm",
    )
    bat = _bat_request(monkeypatch, _chat(CANNED_JSON))
    fields = prov.extract_fields("nội dung", BOOK_SCHEMA).to_metadata_list()

    assert bat["url"] == "http://vllm:8000/v1/chat/completions"   # không sinh '//'
    assert bat["method"] == "POST"
    assert bat["headers"]["Authorization"] == "Bearer sk-test"
    assert bat["headers"]["Content-type"] == "application/json"
    assert bat["body"]["model"] == "Qwen/Qwen2.5-7B-Instruct"
    assert bat["timeout"] == prov.timeout
    assert any(f["key"] == "dc.title" for f in fields)


def test_openai_compat_than_yeu_cau_giu_dung_utf8(monkeypatch):
    """Văn bản tiếng Việt có dấu phải đi qua nguyên vẹn (không mất dấu, không mojibake)."""
    prov = OpenAICompatProvider(base_url="http://vllm:8000/v1", model="m", deployment=DEPLOY_LOCAL)
    bat = _bat_request(monkeypatch, _chat(CANNED_JSON))
    prov.extract_fields("Quyết định về việc thành lập Thư viện", BOOK_SCHEMA)
    assert "Quyết định về việc thành lập Thư viện" in bat["body"]["messages"][0]["content"]


def test_openai_compat_health_ghep_url_models(monkeypatch):
    prov = OpenAICompatProvider(base_url="http://vllm:8000/v1", model="m", deployment=DEPLOY_LOCAL)
    bat = _bat_request(monkeypatch, {"data": [{"id": "m"}]})
    assert prov.health().ready is True
    assert bat["url"] == "http://vllm:8000/v1/models"
    assert bat["method"] == "GET" and bat["body"] is None


def test_azure_ghep_url_deployment_va_api_version(monkeypatch):
    """Sai URL Azure là lỗi im lặng khó tìm nhất — chốt cả hai điểm cuối."""
    prov = AzureOpenAIProvider(
        base_url="https://hpu.openai.azure.com", model="gpt4o-hpu", api_key="k",
        api_version="2024-10-21",
    )
    bat = _bat_request(monkeypatch, _chat(CANNED_JSON))
    prov.extract_fields("nội dung", BOOK_SCHEMA)
    assert bat["url"] == ("https://hpu.openai.azure.com/openai/deployments/gpt4o-hpu"
                          "/chat/completions?api-version=2024-10-21")
    assert bat["headers"]["Api-key"] == "k"

    # Điểm cuối liệt kê model đi đường khác (không theo deployment)
    assert prov._url("/models") == "https://hpu.openai.azure.com/openai/models?api-version=2024-10-21"


def test_gemini_ghep_url_va_header(monkeypatch):
    prov = GeminiProvider(api_key="k", model="gemini-2.0-flash")
    bat = _bat_request(monkeypatch, {"candidates": [{"content": {"parts": [{"text": CANNED_JSON}]}}]})
    prov.extract_fields("nội dung", BOOK_SCHEMA)

    assert bat["url"] == ("https://generativelanguage.googleapis.com/v1beta"
                          "/models/gemini-2.0-flash:generateContent")
    assert bat["headers"]["X-goog-api-key"] == "k"
    assert "k" not in bat["url"]          # khóa KHÔNG nằm trong URL (YC-BM-03)


def test_gemini_embed_ghep_url_batch(monkeypatch):
    prov = GeminiProvider(api_key="k", embed_model="text-embedding-004")
    bat = _bat_request(monkeypatch, {"embeddings": [{"values": [0.1]}, {"values": [0.2]}]})
    assert prov.embed(["a", "b"]) == [[0.1], [0.2]]
    assert bat["url"].endswith("/models/text-embedding-004:batchEmbedContents")
    assert len(bat["body"]["requests"]) == 2


def test_ollama_ghep_url_generate(monkeypatch):
    prov = OllamaProvider(base_url="http://ollama:11434", model="qwen2.5:7b")
    bat = _bat_request(monkeypatch, {"response": CANNED_JSON})
    prov.extract_fields("nội dung", BOOK_SCHEMA)
    assert bat["url"] == "http://ollama:11434/api/generate"
    assert "Authorization" not in bat["headers"]      # máy chủ tại chỗ: không gửi khóa


# =====================================================================
# 4. TƯƠNG THÍCH NGƯỢC (bổ sung, không viết lại)
# =====================================================================

def test_bi_danh_lop_cu_van_dung_duoc():
    """Mã cũ `from ... import CloudProvider/LocalProvider` không được vỡ."""
    assert CloudProvider is ClaudeProvider
    assert LocalProvider is OllamaProvider
    assert isinstance(LocalProvider(), OllamaProvider)


def test_ten_bien_moi_truong_cu_van_co_hieu_luc(monkeypatch):
    """`OLLAMA_URL` + `LOCAL_MODEL` (cấu hình đang chạy trên server) phải còn tác dụng."""
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://10.1.1.101:11434")
    monkeypatch.setenv("LOCAL_MODEL", "qwen2.5:14b")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    p = get_provider()
    assert p.endpoint == "http://10.1.1.101:11434"
    assert p.model == "qwen2.5:14b"


def test_bien_ten_moi_uu_tien_hon_ten_cu(monkeypatch):
    """Có cả hai thì tên theo quy ước mới thắng — tránh nhập nhằng khi di trú cấu hình."""
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://cu:11434")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://moi:11434")
    assert get_provider().endpoint == "http://moi:11434"


def test_cloud_model_cu_van_doi_duoc_model_claude(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "claude")
    monkeypatch.setenv("CLOUD_MODEL", "claude-sonnet-4-5-20250929")
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    assert get_provider().model == "claude-sonnet-4-5-20250929"


def test_gia_tri_deployment_khong_hop_le_thi_giu_theo_bang(monkeypatch):
    """Cấu hình sai chính tả KHÔNG được âm thầm hạ cấp an toàn — giữ khai báo của bảng đăng ký."""
    monkeypatch.setenv("MODEL_PROVIDER", "vllm")
    monkeypatch.setenv("VLLM_DEPLOYMENT", "on-prem")   # sai, phải là 'local'
    assert get_provider().deployment == DEPLOY_LOCAL


def test_local_provider_rong_thi_dung_mac_dinh(monkeypatch):
    """Biến đặt rỗng (lỗi thường gặp khi sinh .env) → về mặc định, không vỡ."""
    monkeypatch.setenv("LOCAL_PROVIDER", "")
    monkeypatch.setenv("CLOUD_PROVIDER", "")
    assert resolve_provider_name("local") == "ollama"
    assert resolve_provider_name("cloud") == "claude"
