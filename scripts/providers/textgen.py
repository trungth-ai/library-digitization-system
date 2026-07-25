#!/usr/bin/env python3
"""
TextGenProvider — lớp trung gian cho MỌI công cụ kiểu "gửi prompt → nhận text" (YC-MP-08).

VÌ SAO CÓ FILE NÀY:
Trước đây logic trích xuất (chọn nhánh dublin_core / generic, dự phòng khi lỗi, ghi nhật ký gọi model)
bị lặp trong từng provider. Mỗi lần thêm một công cụ mới (vLLM, llama.cpp, OpenAI, Gemini...) là một lần
sao chép → nguy cơ hai chế độ diễn giải prompt khác nhau, so sánh độ chính xác mất công bằng (KT-CX-03).

Nay: lớp con CHỈ cần hiện thực `_complete(prompt) -> str` (+ `embed`/`health`) là có đầy đủ hành vi
trích xuất giống hệt các provider khác. Đây chính là phép thử YC-MP-08 / KT-CN-06c: thêm công cụ mới =
viết một lớp nhỏ, KHÔNG sửa giao diện, KHÔNG sửa phần còn lại của hệ thống.

NGUYÊN TẮC được bảo toàn:
- YC-MP-05 dự phòng: model lỗi → KHÔNG mất dữ liệu (dublin_core rơi về `_basic_extraction`).
- YC-MP-06 nhật ký: mỗi lần gọi model ghi provider/model/chế độ/thời gian.
- Dùng CHUNG một lược đồ prompt/parse với CloudProvider để so sánh công bằng giữa các chế độ.
"""

import re
import json
import time
import logging
from typing import List

from scripts.providers.base import (
    ModelProvider, ExtractionSchema, ExtractionResult, FieldValue, ProviderHealth,
)

logger = logging.getLogger("provider.textgen")


class TextGenProvider(ModelProvider):
    """Provider sinh văn bản tổng quát. Lớp con hiện thực `_complete()`."""

    def __init__(self, config=None, api_key=None):
        # Lazy import: cho phép import module này ở môi trường thiếu pypdf/anthropic (ADR-005)
        from scripts.digitize import ProcessingConfig, AIMetadataExtractor
        self.config = config or ProcessingConfig()
        # MƯỢN logic prompt/parse/basic của hệ thống đang chạy để dùng chung một lược đồ prompt.
        # `api_key=None` với provider tự gọi model (Ollama/vLLM/Gemini...); chỉ CloudProvider truyền khóa
        # vì nó tái dùng luôn cả đường gọi Claude cũ (bảo đảm không hồi quy — KT-KH).
        self._extractor = AIMetadataExtractor(self.config, api_key)

    # -- Điểm mở rộng duy nhất mà lớp con BẮT BUỘC hiện thực ----------------
    def _complete(self, prompt: str) -> str:
        """Gửi một prompt tự do tới model, trả về text thô. Ném ngoại lệ nếu gọi thất bại."""
        raise NotImplementedError

    # -- Hành vi dùng chung -------------------------------------------------
    def extract_fields(self, text: str, schema: ExtractionSchema) -> ExtractionResult:
        self.config.document_type = schema.document_type
        if schema.code != "dublin_core":
            return self._extract_generic(text, schema)
        return self._extract_dublin_core(text)

    def _extract_dublin_core(self, text: str) -> ExtractionResult:
        """Đường trích xuất Dublin Core — dùng đúng prompt/parser của hệ thống đang chạy."""
        t0 = time.perf_counter()
        used_ai = False
        try:
            raw = self._complete(self._extractor._get_unified_prompt(text))
            cleaned = re.sub(r"```json\s*|\s*```", "", (raw or "").strip())
            result = self._extractor._build_metadata(json.loads(cleaned))
            used_ai = True
        except Exception as e:  # noqa: BLE001 - YC-MP-05: không mất dữ liệu, rơi về basic như pipeline cũ
            logger.warning("[%s] Trích xuất lỗi, dự phòng basic: %s", self.name, e)
            result = self._extractor._basic_extraction(text)

        metadata = result.get("metadata", [])
        self._log_call(used_ai, t0, len(metadata), "dublin_core")
        fields = [
            FieldValue(key=m["key"], value=m["value"], language=m.get("language"))
            for m in metadata
        ]
        return ExtractionResult(fields=fields, raw=result)

    def _extract_generic(self, text: str, schema: ExtractionSchema) -> ExtractionResult:
        """Trích xuất theo lược đồ bất kỳ (vd công văn) — YC-SC."""
        from scripts.providers.prompt import extract_with_schema
        t0 = time.perf_counter()
        used_ai = False
        try:
            result = extract_with_schema(self._complete, text, schema)
            used_ai = True
        except Exception as e:  # noqa: BLE001 - YC-MP-05: trả rỗng, KHÔNG bịa giá trị
            logger.warning("[%s] Trích xuất theo lược đồ '%s' lỗi: %s", self.name, schema.code, e)
            result = ExtractionResult(fields=[])
        self._log_call(used_ai, t0, len(result.fields), schema.code)
        return result

    def _log_call(self, used_ai: bool, t0: float, n_fields: int, schema_code: str) -> None:
        """YC-MP-06: nhật ký mỗi lần gọi model (không bao giờ ghi khóa API — YC-BM-03)."""
        logger.info(
            "model_call provider=%s deployment=%s model=%s ai=%s latency_ms=%d fields=%d schema=%s",
            self.name, self.deployment, self.model, used_ai,
            int((time.perf_counter() - t0) * 1000), n_fields, schema_code,
        )

    # -- Mặc định cho hai năng lực còn lại ---------------------------------
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Lớp con hỗ trợ embedding thì ghi đè. Mặc định: nói rõ là không hỗ trợ."""
        raise NotImplementedError(
            f"Provider '{self.name}' chưa hỗ trợ embedding; dùng provider tại chỗ có embedding (YC-RG-02)"
        )

    def health(self) -> ProviderHealth:
        raise NotImplementedError
