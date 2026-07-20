#!/usr/bin/env python3
"""
CloudProvider — nhà cung cấp mô hình đám mây (Claude). YC-MP-02.

Mục tiêu: GIỮ NGUYÊN hành vi trích xuất hiện tại. Provider này TÁI SỬ DỤNG trực tiếp
`scripts.digitize.AIMetadataExtractor` (không sao chép logic prompt/parse) để kết quả giống hệt hệ
thống cũ trên cùng đầu vào — tiêu chí không hồi quy (KT-KH / KT-CN-04).

Ranh giới: provider nhận VĂN BẢN đã trích (ngữ cảnh) + lược đồ, trả về các trường. Việc tách text từ
PDF và chọn ngữ cảnh (YC-SC-04) do pipeline đảm nhiệm — đúng như `extract()` cũ vẫn làm.
"""

import time
import logging
from typing import List, Optional

from scripts.providers.base import (
    ModelProvider, ExtractionSchema, ExtractionResult, FieldValue, ProviderHealth,
)

logger = logging.getLogger("provider.cloud")


class CloudProvider(ModelProvider):
    """Trích xuất metadata bằng Claude, bọc AIMetadataExtractor hiện có."""

    name = "cloud"

    def __init__(self, api_key: Optional[str] = None, config=None, model: Optional[str] = None):
        # Lazy import để cloud.py import được ở môi trường thiếu pypdf/anthropic
        from scripts.digitize import AIMetadataExtractor, ProcessingConfig
        self.config = config or ProcessingConfig()
        if model:
            self.config.claude_model = model
        self.model = self.config.claude_model
        self.version = ""
        self._extractor = AIMetadataExtractor(self.config, api_key)

    def extract_fields(self, text: str, schema: ExtractionSchema) -> ExtractionResult:
        # Đồng bộ loại tài liệu để prompt giữ nguyên như hệ thống cũ
        self.config.document_type = schema.document_type

        # Lược đồ khác dublin_core (vd công văn) → đường generic schema-driven (giữ nguyên đường cũ cho dublin_core)
        if schema.code != "dublin_core":
            return self._extract_generic(text, schema)

        t0 = time.perf_counter()
        used_ai = False
        # Sao đúng nhánh của AIMetadataExtractor.extract():
        #   có client -> _ai_extraction (lỗi thì fallback basic); không có client -> basic
        if self._extractor.client:
            try:
                result = self._extractor._ai_extraction(text)
                used_ai = True
            except Exception as e:  # noqa: BLE001 - giữ đúng fallback cũ
                logger.warning("AI extraction lỗi, chuyển basic: %s", e)
                result = self._extractor._basic_extraction(text)
        else:
            result = self._extractor._basic_extraction(text)

        latency_ms = int((time.perf_counter() - t0) * 1000)
        metadata = result.get("metadata", [])

        # YC-MP-06: ghi nhật ký mỗi lần gọi model (provider/model/chế độ/thời gian)
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
        """Gọi Claude với 1 prompt tự do → trả text (dùng cho generic schema-driven)."""
        resp = self._extractor.client.messages.create(
            model=self.config.claude_model,
            max_tokens=self.config.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text

    def _extract_generic(self, text: str, schema: ExtractionSchema) -> ExtractionResult:
        """Trích xuất theo lược đồ bất kỳ (không phải dublin_core)."""
        from scripts.providers.prompt import extract_with_schema
        t0 = time.perf_counter()
        used_ai = False
        if not self._extractor.client:
            logger.warning("CloudProvider thiếu key cho lược đồ '%s' → trả rỗng (không bịa)", schema.code)
            result = ExtractionResult(fields=[])
        else:
            try:
                result = extract_with_schema(self._complete, text, schema)
                used_ai = True
            except Exception as e:  # noqa: BLE001 - không mất dữ liệu (YC-MP-05)
                logger.warning("Generic extraction lỗi: %s", e)
                result = ExtractionResult(fields=[])
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "model_call provider=%s model=%s ai=%s latency_ms=%d fields=%d schema=%s",
            self.name, self.model, used_ai, latency_ms, len(result.fields), schema.code,
        )
        return result

    def embed(self, texts: List[str]) -> List[List[float]]:
        # SRS YC-RG-02: embedding chạy tại chỗ → CloudProvider không đảm nhiệm
        raise NotImplementedError(
            "CloudProvider không hỗ trợ embedding; dùng LocalProvider (YC-RG-02)"
        )

    def health(self) -> ProviderHealth:
        ok = self._extractor.client is not None
        return ProviderHealth(
            ready=ok,
            detail="có Claude client" if ok else "thiếu CLAUDE_API_KEY → chạy basic extraction",
        )
