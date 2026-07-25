#!/usr/bin/env python3
"""
OpenAICompatProvider — provider cho MỌI công cụ nói được "OpenAI Chat Completions API" (YC-MP-03/08).

VÌ SAO MỘT LỚP NÀY LẠI QUAN TRỌNG:
Giao thức `/v1/chat/completions` đã thành chuẩn thực tế. Một lớp hiện thực duy nhất phủ được:

  • TẠI CHỖ (on-premise, hạ tầng của trường):
      - vLLM            (thông lượng cao, có GPU — ứng viên thay Ollama ở GĐ1, xem ADR-002)
      - llama.cpp       (`llama-server`, chạy CPU tốt, nhẹ nhất)
      - LM Studio       (dựng nhanh trên máy cán bộ để thử nghiệm)
      - TGI             (Hugging Face text-generation-inference)
      - Ollama          (Ollama cũng có cổng tương thích `/v1` — xem `ollama_openai` trong registry)
  • ĐÁM MÂY: OpenAI, Azure OpenAI, Groq, OpenRouter, Together, DeepSeek, Mistral, xAI...
    (và phần lớn dịch vụ LLM trong nước, vốn cũng phơi ra giao diện tương thích OpenAI)

→ "Ollama chỉ là MỘT trong các lựa chọn": đổi công cụ = đổi biến môi trường, không sửa mã (YC-MP-04,
  YC-MS-06 — phép thử chống khóa nhà cung cấp).

RÀNG BUỘC KỸ THUẬT:
- Gọi HTTP bằng `urllib` (stdlib) → KHÔNG thêm phụ thuộc, chạy được ở môi trường air-gapped (YC-MS-03).
  Cố tình KHÔNG dùng SDK `openai` để chế độ tại chỗ không cần cài thêm gói nào.
- `deployment` do CẤU HÌNH quyết định, không suy diễn từ tên model: một điểm cuối tương thích OpenAI có
  thể là máy trong phòng máy chủ HOẶC dịch vụ ngoài. Ràng buộc cứng YC-DR-03 dựa vào giá trị này.
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Dict, List, Optional

from scripts.providers.base import DEPLOY_CLOUD, ProviderHealth
from scripts.providers.textgen import TextGenProvider

logger = logging.getLogger("provider.openai_compat")


def _tu_choi_json_mode(message: str) -> bool:
    """
    Lỗi này có phải do máy chủ không hỗ trợ `response_format` không?

    Mỗi nhà cung cấp báo một kiểu: vLLM/llama.cpp nêu thẳng tên tham số, còn DashScope (Qwen) hay một số
    cổng khác chỉ nói "tham số không hợp lệ / không được hỗ trợ". Nhận diện rộng một chút để đường lùi
    thực sự hoạt động, nhưng vẫn KHÔNG nuốt các lỗi khác (401 khóa sai, 404 sai model, 429 quá hạn mức)
    — những lỗi đó phải nổi lên cho cán bộ vận hành thấy.
    """
    msg = (message or "").lower()
    if "response_format" in msg:
        return True
    # Thông điệp chung chung: chỉ coi là từ chối JSON mode khi có dấu hiệu "không hỗ trợ" + "json"
    khong_ho_tro = any(k in msg for k in ("not support", "unsupported", "not_supported",
                                         "invalid parameter", "invalid_parameter",
                                         "unknown field", "unrecognized"))
    return khong_ho_tro and "json" in msg


class OpenAICompatProvider(TextGenProvider):
    """Trích xuất/embedding qua điểm cuối tương thích OpenAI."""

    name = "openai_compat"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: Optional[str] = None,
        deployment: str = DEPLOY_CLOUD,
        name: Optional[str] = None,
        embed_model: str = "",
        config=None,
        timeout: int = 120,
        json_mode: bool = True,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(config=config)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embed_model = embed_model or ""
        self.version = ""
        self.deployment = deployment
        self.endpoint = self.base_url          # chỉ URL, không kèm khóa (YC-BM-03)
        self.timeout = timeout
        # Một số máy chủ tại chỗ (bản cũ của llama.cpp/TGI) chưa hỗ trợ `response_format`
        # → cho phép tắt để không vỡ; prompt vẫn yêu cầu JSON nên vẫn parse được.
        self.json_mode = json_mode
        # Có đối chiếu tên model với danh sách `/models` khi kiểm tra sẵn sàng không
        # (Azure trả tên model gốc chứ không phải tên deployment → phải tắt)
        self.verify_model_in_health = True
        self._api_key = api_key or None
        self._extra_headers = extra_headers or {}
        if name:
            self.name = name

    # -- HTTP (urllib, stdlib) ---------------------------------------------
    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        # Máy chủ tại chỗ thường KHÔNG cần khóa → chỉ gửi header khi có
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        headers.update(self._extra_headers)
        return headers

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(self, path: str, payload: Optional[dict] = None, method: str = "POST") -> dict:
        """Gọi HTTP, trả JSON. Ném RuntimeError với thông báo gọn (KHÔNG lộ khóa API)."""
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            self._url(path), data=data, headers=self._headers(), method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:  # noqa: BLE001 - lỗi khi đọc thân phản hồi thì bỏ qua
                pass
            raise RuntimeError(f"HTTP {e.code} từ {self.name} tại {path}: {body}") from e

    # -- Sinh văn bản -------------------------------------------------------
    def _complete(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.config.max_tokens,
            "temperature": 0,   # trích xuất dữ liệu: cần tái lập được, không sáng tạo
            "stream": False,
        }
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            out = self._request("/chat/completions", payload)
        except RuntimeError as e:
            # Máy chủ không hiểu `response_format` → thử lại một lần không có nó (tương thích ngược)
            if self.json_mode and _tu_choi_json_mode(str(e)):
                logger.info("[%s] Máy chủ không hỗ trợ response_format → gọi lại không dùng JSON mode",
                            self.name)
                payload.pop("response_format")
                out = self._request("/chat/completions", payload)
            else:
                raise

        choices = out.get("choices") or []
        if not choices:
            raise RuntimeError(f"[{self.name}] Phản hồi không có 'choices': {str(out)[:200]}")
        return (choices[0].get("message") or {}).get("content") or ""

    # -- Embedding (YC-RG-02, YC-MS-05) ------------------------------------
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Tạo embedding qua `/embeddings`. Dùng `embed_model` nếu có (model sinh văn bản ≠ model embedding)."""
        model = self.embed_model or self.model
        out = self._request("/embeddings", {"model": model, "input": list(texts)})
        # Giữ đúng thứ tự đầu vào: chuẩn OpenAI trả kèm `index`
        items = sorted(out.get("data", []), key=lambda d: d.get("index", 0))
        return [item.get("embedding", []) for item in items]

    # -- Sẵn sàng (YC-MS-04) -----------------------------------------------
    def health(self) -> ProviderHealth:
        try:
            out = self._request("/models", method="GET")
            names = [m.get("id", "") for m in out.get("data", [])]
            # Máy chủ tại chỗ chỉ nạp 1 model; cảnh báo nếu model cấu hình không nằm trong danh sách
            if self.verify_model_in_health and names and self.model and self.model not in names:
                return ProviderHealth(
                    ready=False,
                    detail=(f"Điểm cuối sống nhưng KHÔNG có model '{self.model}'. "
                            f"Model sẵn có: {', '.join(names[:5])}"),
                )
            return ProviderHealth(ready=True, detail=f"{self.name} sẵn sàng ({self.base_url})")
        except Exception as e:  # noqa: BLE001
            return ProviderHealth(ready=False, detail=f"{self.name} không phản hồi: {e}")


class AzureOpenAIProvider(OpenAICompatProvider):
    """
    Azure OpenAI — cùng thân yêu cầu nhưng KHÁC đường dẫn và cách xác thực:
    `{endpoint}/openai/deployments/{ten_deployment}/chat/completions?api-version=...`, header `api-key`.
    Ở Azure, `model` là **tên deployment** do người quản trị đặt, không phải tên model gốc.
    """

    name = "azure_openai"

    def __init__(self, *args, api_version: str = "2024-10-21", **kwargs):
        super().__init__(*args, **kwargs)
        self.api_version = api_version
        # `/openai/models` của Azure liệt kê model gốc, không phải tên deployment → không đối chiếu
        self.verify_model_in_health = False

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["api-key"] = self._api_key      # Azure dùng header riêng, không phải Bearer
        headers.update(self._extra_headers)
        return headers

    def _url(self, path: str) -> str:
        if path == "/models":
            return f"{self.base_url}/openai/models?api-version={self.api_version}"
        return (f"{self.base_url}/openai/deployments/{self.model}{path}"
                f"?api-version={self.api_version}")
