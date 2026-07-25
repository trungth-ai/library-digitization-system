#!/usr/bin/env python3
"""
ClaudeProvider — nhà cung cấp mô hình đám mây Anthropic Claude. YC-MP-02.

Mục tiêu BẤT BIẾN: GIỮ NGUYÊN hành vi trích xuất hiện tại. Provider này TÁI SỬ DỤNG trực tiếp
`scripts.digitize.AIMetadataExtractor._ai_extraction` (không sao chép logic prompt/parse) để kết quả
giống hệt hệ thống đang chạy trên cùng đầu vào — tiêu chí không hồi quy (KT-KH / KT-CN-04).

Vì lý do đó, đây là provider DUY NHẤT ghi đè `_extract_dublin_core`: nó đi đúng đường gọi Claude cũ,
không đi qua `_complete()` dùng chung. Các nhánh còn lại (lược đồ tổng quát, nhật ký, dự phòng) thừa
hưởng từ `TextGenProvider` như mọi provider khác.

Ranh giới: provider nhận VĂN BẢN đã trích (ngữ cảnh) + lược đồ, trả về các trường. Việc tách text từ
PDF và chọn ngữ cảnh (YC-SC-04) do pipeline đảm nhiệm — đúng như `extract()` cũ vẫn làm.

Tên lớp `CloudProvider` được giữ làm bí danh để không phá mã/kiểm thử đang dùng.
"""

import logging
import time
from typing import Optional

from scripts.providers.base import (
    DEPLOY_CLOUD, ExtractionResult, FieldValue, ProviderHealth,
)
from scripts.providers.textgen import TextGenProvider

logger = logging.getLogger("provider.claude")


class ClaudeProvider(TextGenProvider):
    """Trích xuất metadata bằng Claude, bọc AIMetadataExtractor hiện có."""

    name = "claude"
    deployment = DEPLOY_CLOUD

    def __init__(self, api_key: Optional[str] = None, config=None, model: Optional[str] = None):
        super().__init__(config=config, api_key=api_key)
        if model:
            self.config.claude_model = model
        self.model = self.config.claude_model
        self.version = ""
        self.endpoint = "https://api.anthropic.com"

    def _extract_dublin_core(self, text: str) -> ExtractionResult:
        """
        Sao ĐÚNG nhánh của `AIMetadataExtractor.extract()`:
          có client → `_ai_extraction` (lỗi thì rơi về basic); không có client → basic.
        KHÔNG đổi đường này nếu chưa chạy lại kiểm thử không hồi quy.
        """
        t0 = time.perf_counter()
        used_ai = False
        if self._extractor.client:
            try:
                result = self._extractor._ai_extraction(text)
                used_ai = True
            except Exception as e:  # noqa: BLE001 - giữ đúng fallback cũ
                logger.warning("AI extraction lỗi, chuyển basic: %s", e)
                result = self._extractor._basic_extraction(text)
        else:
            result = self._extractor._basic_extraction(text)

        metadata = result.get("metadata", [])
        self._log_call(used_ai, t0, len(metadata), "dublin_core")   # YC-MP-06
        fields = [
            FieldValue(key=m["key"], value=m["value"], language=m.get("language"))
            for m in metadata
        ]
        return ExtractionResult(fields=fields, raw=result)

    def _complete(self, prompt: str) -> str:
        """Gọi Claude với 1 prompt tự do → trả text (dùng cho lược đồ tổng quát)."""
        if not self._extractor.client:
            raise RuntimeError("Thiếu CLAUDE_API_KEY → không gọi được Claude")
        resp = self._extractor.client.messages.create(
            model=self.config.claude_model,
            max_tokens=self.config.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text

    # `embed()` thừa hưởng từ TextGenProvider → ném NotImplementedError.
    # SRS YC-RG-02: embedding chạy TẠI CHỖ, provider đám mây không đảm nhiệm.

    def health(self) -> ProviderHealth:
        ok = self._extractor.client is not None
        return ProviderHealth(
            ready=ok,
            detail="có Claude client" if ok else "thiếu CLAUDE_API_KEY → chạy basic extraction",
        )


#: Bí danh tương thích ngược — mã/kiểm thử cũ import `CloudProvider`.
CloudProvider = ClaudeProvider
