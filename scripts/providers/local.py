#!/usr/bin/env python3
"""
LocalProvider — nhà cung cấp mô hình tại chỗ qua Ollama (YC-MP-03, YC-MS).

- Gọi Ollama qua HTTP bằng `urllib` (stdlib) → KHÔNG thêm phụ thuộc, chạy được ở môi trường tối giản
  / air-gapped (phù hợp yêu cầu chạy khi ngắt Internet — YC-MS-03).
- Tái dùng `_get_unified_prompt` + `_build_metadata` + `_basic_extraction` của AIMetadataExtractor để
  DÙNG CHUNG một lược đồ prompt/parse với CloudProvider → so sánh độ chính xác công bằng (KT-CX-03).
- Endpoint Ollama: POST /api/generate (trích xuất), POST /api/embeddings (RAG - GĐ3), GET /api/tags (health).
"""

import json
import time
import logging
import urllib.request
import urllib.error
from typing import List, Optional

from scripts.providers.base import (
    ModelProvider, ExtractionSchema, ExtractionResult, FieldValue, ProviderHealth,
)

logger = logging.getLogger("provider.local")


class LocalProvider(ModelProvider):
    """Trích xuất/embedding bằng mô hình mở chạy tại chỗ (Ollama)."""

    name = "local"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b",
        config=None,
        timeout: int = 120,
    ):
        from scripts.digitize import ProcessingConfig, AIMetadataExtractor
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.version = ""
        self.timeout = timeout
        self.config = config or ProcessingConfig()
        # Chỉ mượn logic prompt/parse/basic; LocalProvider tự gọi model nên api_key=None
        self._extractor = AIMetadataExtractor(self.config, api_key=None)

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
        })
        return out.get("response", "")

    # -- ModelProvider ----------------------------------------------------
    def extract_fields(self, text: str, schema: ExtractionSchema) -> ExtractionResult:
        self.config.document_type = schema.document_type

        # Lược đồ khác dublin_core (vd công văn) → generic schema-driven
        if schema.code != "dublin_core":
            return self._extract_generic(text, schema)

        t0 = time.perf_counter()
        used_ai = False
        try:
            prompt = self._extractor._get_unified_prompt(text)   # cùng prompt với cloud
            raw = self._call_generate(prompt)
            import re
            cleaned = re.sub(r"```json\s*|\s*```", "", raw.strip())
            extracted = json.loads(cleaned)
            result = self._extractor._build_metadata(extracted)  # cùng parser với cloud
            used_ai = True
        except Exception as e:  # noqa: BLE001 - không mất dữ liệu, fallback giống pipeline cũ (YC-MP-05)
            logger.warning("Local extraction lỗi, fallback basic: %s", e)
            result = self._extractor._basic_extraction(text)

        latency_ms = int((time.perf_counter() - t0) * 1000)
        metadata = result.get("metadata", [])
        logger.info(
            "model_call provider=%s model=%s ai=%s latency_ms=%d fields=%d",
            self.name, self.model, used_ai, latency_ms, len(metadata),
        )
        fields = [
            FieldValue(key=m["key"], value=m["value"], language=m.get("language"))
            for m in metadata
        ]
        return ExtractionResult(fields=fields, raw=result)

    def _complete(self, prompt: str) -> str:
        """Gọi Ollama với 1 prompt tự do → text (dùng cho generic schema-driven)."""
        return self._call_generate(prompt)

    def _extract_generic(self, text: str, schema: ExtractionSchema) -> ExtractionResult:
        """Trích xuất theo lược đồ bất kỳ (không phải dublin_core)."""
        from scripts.providers.prompt import extract_with_schema
        t0 = time.perf_counter()
        used_ai = False
        try:
            result = extract_with_schema(self._complete, text, schema)
            used_ai = True
        except Exception as e:  # noqa: BLE001 - không mất dữ liệu (YC-MP-05)
            logger.warning("Generic extraction (local) lỗi: %s", e)
            result = ExtractionResult(fields=[])
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "model_call provider=%s model=%s ai=%s latency_ms=%d fields=%d schema=%s",
            self.name, self.model, used_ai, latency_ms, len(result.fields), schema.code,
        )
        return result

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Tạo embedding tại chỗ (YC-RG-02) — dùng cho RAG ở GĐ3."""
        vectors: List[List[float]] = []
        for t in texts:
            out = self._post_json("/api/embeddings", {"model": self.model, "prompt": t})
            vectors.append(out.get("embedding", []))
        return vectors

    def health(self) -> ProviderHealth:
        """Kiểm tra Ollama sống (YC-MS-04) — GET /api/tags."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                ok = resp.status == 200
            return ProviderHealth(ready=ok, detail="Ollama sẵn sàng" if ok else "Ollama không phản hồi")
        except Exception as e:  # noqa: BLE001
            return ProviderHealth(ready=False, detail=f"Ollama không phản hồi: {e}")
