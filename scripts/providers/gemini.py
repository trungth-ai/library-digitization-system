#!/usr/bin/env python3
"""
GeminiProvider — Google Gemini qua Generative Language API (YC-MP-03).

VÌ SAO CHỌN GEMINI LÀM PROVIDER THỨ BA:
Anthropic và OpenAI-compat đã phủ hai họ giao thức. Gemini dùng **định dạng dây khác hẳn**
(`contents/parts` thay vì `messages`, `:generateContent` thay vì `/chat/completions`,
`:batchEmbedContents` cho embedding). Hiện thực được nó mà KHÔNG phải sửa `ModelProvider` chính là
bằng chứng thực nghiệm cho YC-MP-08 / KT-CN-06c — giao diện đủ tổng quát, không bị đúc theo hình một
nhà cung cấp nào.

Về nghiệp vụ: đây là provider ĐÁM MÂY (`deployment = cloud`) → theo ràng buộc cứng YC-DR-03, nó KHÔNG
BAO GIỜ được nhận tài liệu Nội bộ/Nhạy cảm, dù người dùng có chọn thủ công.

Xác thực: dùng header `x-goog-api-key` (KHÔNG đưa khóa vào query string — tránh khóa rơi vào log truy
cập/URL, YC-BM-03).
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Dict, List, Optional

from scripts.providers.base import DEPLOY_CLOUD, ProviderHealth
from scripts.providers.textgen import TextGenProvider

logger = logging.getLogger("provider.gemini")

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(TextGenProvider):
    """Trích xuất/embedding bằng Google Gemini."""

    name = "gemini"
    deployment = DEPLOY_CLOUD

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.0-flash",
        base_url: str = DEFAULT_BASE_URL,
        embed_model: str = "text-embedding-004",
        config=None,
        timeout: int = 120,
    ):
        super().__init__(config=config)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embed_model = embed_model
        self.version = ""
        self.endpoint = self.base_url
        self.timeout = timeout
        self._api_key = api_key or None

    # -- HTTP ---------------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["x-goog-api-key"] = self._api_key
        return headers

    def _request(self, path: str, payload: Optional[dict] = None, method: str = "POST") -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=self._headers(), method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(f"HTTP {e.code} từ Gemini tại {path}: {body}") from e

    # -- Sinh văn bản -------------------------------------------------------
    def _complete(self, prompt: str) -> str:
        if not self._api_key:
            raise RuntimeError("Thiếu GEMINI_API_KEY → không gọi được Gemini")

        out = self._request(f"/models/{self.model}:generateContent", {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,                       # trích xuất: cần tái lập được
                "maxOutputTokens": self.config.max_tokens,
                "responseMimeType": "application/json",  # tương đương JSON mode
            },
        })

        candidates = out.get("candidates") or []
        if not candidates:
            # Bị chặn bởi bộ lọc an toàn cũng vào nhánh này → nêu rõ lý do cho cán bộ vận hành
            reason = (out.get("promptFeedback") or {}).get("blockReason", "không rõ")
            raise RuntimeError(f"Gemini không trả kết quả (lý do: {reason})")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts)

    # -- Embedding (YC-MS-05: model embedding riêng) ------------------------
    def embed(self, texts: List[str]) -> List[List[float]]:
        if not self._api_key:
            raise RuntimeError("Thiếu GEMINI_API_KEY → không gọi được Gemini")
        out = self._request(f"/models/{self.embed_model}:batchEmbedContents", {
            "requests": [
                {"model": f"models/{self.embed_model}", "content": {"parts": [{"text": t}]}}
                for t in texts
            ],
        })
        return [e.get("values", []) for e in out.get("embeddings", [])]

    # -- Sẵn sàng (YC-MS-04) -----------------------------------------------
    def health(self) -> ProviderHealth:
        if not self._api_key:
            return ProviderHealth(ready=False, detail="thiếu GEMINI_API_KEY")
        try:
            self._request(f"/models/{self.model}", method="GET")
            return ProviderHealth(ready=True, detail=f"Gemini sẵn sàng (model {self.model})")
        except Exception as e:  # noqa: BLE001
            return ProviderHealth(ready=False, detail=f"Gemini không phản hồi: {e}")
