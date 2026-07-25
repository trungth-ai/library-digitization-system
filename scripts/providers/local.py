#!/usr/bin/env python3
"""
OllamaProvider — mô hình tại chỗ chạy qua Ollama (YC-MP-03, YC-MS). ADR-002.

**Ollama chỉ là MỘT trong nhiều lựa chọn tại chỗ.** Các lựa chọn còn lại (vLLM, llama.cpp, LM Studio,
TGI) dùng `OpenAICompatProvider`; xem `scripts/providers/registry.py` để biết bảng công cụ đầy đủ.
Ollama giữ lớp riêng vì nó có API GỐC (`/api/generate`, `/api/embeddings`) khác chuẩn OpenAI — và đó là
API ổn định nhất của nó (`format: "json"` buộc model trả JSON hợp lệ, rất hữu ích cho trích xuất).

- Gọi HTTP bằng `urllib` (stdlib) → KHÔNG thêm phụ thuộc, chạy được air-gapped (YC-MS-03).
- Logic trích xuất/dự phòng/nhật ký nằm ở `TextGenProvider` → dùng CHUNG với mọi provider khác,
  bảo đảm so sánh độ chính xác giữa các chế độ là công bằng (KT-CX-03).
- Tên lớp `LocalProvider` được giữ làm bí danh để không phá mã/kiểm thử đang dùng (bổ sung, không viết lại).
"""

import json
import logging
import urllib.error
import urllib.request
from typing import List

from scripts.providers.base import DEPLOY_LOCAL, ProviderHealth
from scripts.providers.textgen import TextGenProvider

logger = logging.getLogger("provider.ollama")


class OllamaProvider(TextGenProvider):
    """Trích xuất/embedding bằng mô hình mở chạy tại chỗ qua Ollama."""

    name = "ollama"
    deployment = DEPLOY_LOCAL

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b",
        config=None,
        timeout: int = 120,
        embed_model: str = "",
    ):
        super().__init__(config=config)
        self.base_url = base_url.rstrip("/")
        self.model = model
        # YC-MS-05: embedding nên dùng model chuyên dụng (vd bge-m3), không dùng model sinh văn bản
        self.embed_model = embed_model or ""
        self.version = ""
        self.endpoint = self.base_url
        self.timeout = timeout

    # -- HTTP helpers (urllib, stdlib) -------------------------------------
    def _post_json(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _call_generate(self, prompt: str) -> str:
        """Gọi Ollama /api/generate, ép format JSON, trả chuỗi response."""
        out = self._post_json("/api/generate", {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",   # Ollama ép model trả JSON hợp lệ
            "options": {"temperature": 0},
        })
        return out.get("response", "")

    # -- Điểm mở rộng của TextGenProvider ----------------------------------
    def _complete(self, prompt: str) -> str:
        return self._call_generate(prompt)

    # -- Embedding (YC-RG-02) ----------------------------------------------
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Tạo embedding tại chỗ — dùng cho RAG ở GĐ3."""
        model = self.embed_model or self.model
        vectors: List[List[float]] = []
        for t in texts:
            out = self._post_json("/api/embeddings", {"model": model, "prompt": t})
            vectors.append(out.get("embedding", []))
        return vectors

    # -- Sẵn sàng (YC-MS-04) -----------------------------------------------
    def health(self) -> ProviderHealth:
        """Kiểm tra Ollama sống — GET /api/tags; đồng thời soát model đã tải chưa."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status != 200:
                    return ProviderHealth(ready=False, detail="Ollama không phản hồi")
                tags = json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            return ProviderHealth(ready=False, detail=f"Ollama không phản hồi: {e}")

        names = [m.get("name", "") for m in tags.get("models", [])]
        if self.model and names and self.model not in names:
            return ProviderHealth(
                ready=False,
                detail=(f"Ollama sống nhưng CHƯA tải model '{self.model}'. "
                        f"Chạy: ollama pull {self.model}"),
            )
        return ProviderHealth(ready=True, detail="Ollama sẵn sàng")


#: Bí danh tương thích ngược — mã/kiểm thử cũ import `LocalProvider`.
LocalProvider = OllamaProvider
