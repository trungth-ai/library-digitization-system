#!/usr/bin/env python3
"""
ProviderMetadataExtractor — nối pipeline số hóa vào lớp trừu tượng hóa mô hình (ADR-008).

ĐÂY LÀ MẢNH GHÉP CUỐI của GĐ1: trước đây `DigitizationPipeline` gọi thẳng `AIMetadataExtractor`
(bám cứng Claude), nên đổi `MODEL_PROVIDER` không đổi được hành vi của worker. Lớp này thay vào đó,
GIỮ NGUYÊN giao diện `extract(pdf_path) -> Dict` để pipeline không phải viết lại (ADR-004 đã cố ý
hoãn việc này tới khi lớp provider đủ chín).

Một lần trích xuất nay đi qua đủ 5 bước, thay vì chỉ gọi model:
  1. Lược đồ  — lấy từ DB (YC-SC-01), không có thì dùng lược đồ trong mã
  2. Ngữ cảnh — theo `context_strategy` của lược đồ (YC-SC-04), thay cho hằng số "10 trang đầu" cũ
  3. Định tuyến — theo độ nhạy cảm, ràng buộc cứng YC-DR-03 + dự phòng chéo công cụ cùng chế độ
  4. Chất lượng — kiểm hợp lệ, thử lại, điểm tin cậy theo mức bám văn bản gốc (YC-CF-01/02/03/05)
  5. Truy vết — đo tài nguyên (YC-MS-07), ghi `model_calls` (YC-MP-06) + `audit_log` (YC-AU-04)

KHÔNG MẤT TÀI LIỆU: mọi nhánh lỗi đều trả về metadata (dù ít) và đánh dấu `needs_review`, thay vì
ném lỗi làm job thất bại — trừ vi phạm ràng buộc cứng độ nhạy cảm, trường hợp đó PHẢI dừng.
"""

import logging
import os
from typing import Dict, List, Optional

from scripts.core import metrics
from scripts.core.exceptions import SensitivityViolation
from scripts.providers.base import ExtractionResult, ExtractionSchema

logger = logging.getLogger("core.extraction")

# Ngữ cảnh cho lược đồ Dublin Core — GIỮ ĐÚNG hằng số của hệ đang chạy để không hồi quy (KT-KH):
# `AIMetadataExtractor.extract` dùng max_pages=10 rồi cắt 6000 ký tự.
LEGACY_MAX_PAGES = 10
LEGACY_MAX_CHARS = 6000

# Ngữ cảnh cho lược đồ 'full' (vd công văn: ngắn, cần đọc trọn văn bản)
FULL_MAX_PAGES = int(os.getenv("CONTEXT_FULL_MAX_PAGES", "30"))
FULL_MAX_CHARS = int(os.getenv("CONTEXT_FULL_MAX_CHARS", "20000"))

# Ngưỡng điểm tin cậy dưới mức này thì coi là cần cán bộ kiểm tra (YC-CF-04)
LOW_CONFIDENCE_THRESHOLD = float(os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.5"))


def resolve_schema(document_type: str) -> ExtractionSchema:
    """
    Lấy lược đồ cho loại tài liệu: ưu tiên DB (cấu hình được — YC-SC-01), không có thì dùng lược đồ
    trong mã. Lược đồ trong DB mang cả độ nhạy cảm và chiến lược ngữ cảnh, nên đây cũng là nơi
    quyết định tài liệu này được xử lý ở chế độ nào.
    """
    # Đường 1: DB
    try:
        from scripts.core.schema_store import load_schema_for_document_type
        schema = load_schema_for_document_type(document_type)
        if schema:
            logger.info("Dùng lược đồ '%s' từ DB cho loại tài liệu '%s'", schema.code, document_type)
            return schema
    except Exception as e:  # noqa: BLE001 - DB chưa có bảng/chưa seed thì vẫn phải chạy được
        logger.warning("Không lấy được lược đồ từ DB (%s) → dùng lược đồ trong mã", e)

    # Đường 2: lược đồ trong mã
    from scripts.eval.schemas import get_schema
    code = "cong_van" if document_type == "cong_van" else "book"
    schema = get_schema(code)
    logger.info("Dùng lược đồ trong mã '%s' cho loại tài liệu '%s'", schema.code, document_type)
    return schema


def select_context(pdf_path: str, schema: ExtractionSchema) -> str:
    """
    Chọn ngữ cảnh đưa vào model theo `schema.context_strategy` (YC-SC-04).

    Lược đồ Dublin Core đi đúng tham số của hệ đang chạy (10 trang / 6000 ký tự) — đây là điều kiện
    để kết quả không hồi quy so với trước (KT-KH). Lược đồ 'full' đọc nhiều hơn vì công văn ngắn
    nhưng thông tin (nơi nhận, người ký) nằm ở cuối văn bản.
    """
    from scripts.digitize import PDFTextExtractor   # lazy: pypdf chỉ cần khi chạy thật

    strategy = (schema.context_strategy or "first8_last2").lower()
    if strategy == "full":
        max_pages, max_chars = FULL_MAX_PAGES, FULL_MAX_CHARS
    else:
        max_pages, max_chars = LEGACY_MAX_PAGES, LEGACY_MAX_CHARS

    text = PDFTextExtractor().extract(pdf_path, max_pages=max_pages)
    return text[:max_chars]


class ProviderMetadataExtractor:
    """
    Trích metadata qua lớp provider. Thay thế `AIMetadataExtractor` trong pipeline bằng cách
    **tiêm vào**, không sửa pipeline (`DigitizationPipeline(metadata_extractor=...)`).

    Sau khi `extract()` chạy, `self.last_run` chứa thông tin để worker cập nhật DB + audit.
    """

    def __init__(self, config, document_id: Optional[str] = None,
                 actor: str = "worker", requested_mode: Optional[str] = None,
                 max_retries: int = 2):
        self.config = config
        self.document_id = document_id
        self.actor = actor
        self.requested_mode = requested_mode
        self.max_retries = max_retries
        self.last_run: Dict = {}
        self._sample: Optional[metrics.ResourceSample] = None

    # -- Giao diện giống AIMetadataExtractor -------------------------------
    def extract(self, pdf_path: str) -> Dict:
        """Trả về {"metadata": [...], "extraction": {...}} — tương thích JSONExporter + worker."""
        from scripts.core import quality
        from scripts.providers import fallback, router

        schema = resolve_schema(getattr(self.config, "document_type", "book"))

        # Ràng buộc cứng YC-DR-03: vi phạm thì PHẢI dừng, không được "cứ xử lý tạm".
        # SensitivityViolation cố ý bay ra ngoài để worker cho job thất bại có mô tả.
        mode = router.resolve_mode(schema, self.requested_mode)

        # Chọn công cụ: lỗi CẤU HÌNH (thiếu gói, thiếu điểm cuối, tên công cụ lạ) KHÔNG được làm job
        # thất bại. Tài liệu đã OCR xong rồi; cứ lưu phần trích được (dù rỗng) và đánh dấu cần xem lại
        # để cán bộ xử lý tay — mất chất lượng còn hơn mất tài liệu (YC-MP-05).
        try:
            provider, fallback_from = fallback.select_provider(mode, config=self.config)
            router.assert_mode_matches(provider, mode, schema.code)
        except SensitivityViolation:
            raise                      # ràng buộc cứng: phải dừng
        except Exception as e:         # noqa: BLE001
            logger.error("Không chọn được công cụ mô hình cho chế độ '%s': %s", mode, e)
            return self._degraded_result(schema, mode, f"Không dùng được công cụ mô hình: {e}")

        text = select_context(pdf_path, schema)

        result, errors, attempts, needs_manual, error_msg = self._run_extraction(
            provider, text, schema, quality,
        )

        metadata = result.to_metadata_list()
        low_conf = quality.low_confidence_fields(result, LOW_CONFIDENCE_THRESHOLD)

        # Cần cán bộ xem lại khi: không hợp lệ sau khi thử lại, HOẶC có trường điểm tin cậy thấp,
        # HOẶC không trích được gì. Thà báo cần xem lại còn hơn để dữ liệu sai đi tiếp vào DSpace.
        needs_review = bool(needs_manual or low_conf or not metadata)
        review_note = self._build_review_note(errors, low_conf, metadata, error_msg)

        self.last_run = {
            "provider": provider.name,
            "deployment": provider.deployment,
            "mode": mode,
            "model": provider.model,
            "model_version": provider.version,
            "schema_code": schema.code,
            "sensitivity": schema.sensitivity,
            "attempts": attempts,
            "errors": errors,
            "low_confidence_fields": low_conf,
            "needs_review": needs_review,
            "review_note": review_note,
            "fallback_from": fallback_from,
            "n_fields": len(metadata),
            "error": error_msg,
            "latency_ms": self._sample.latency_ms if self._sample else None,
            "rss_mb": self._sample.rss_mb if self._sample else None,
            "gpu_mem_mb": self._sample.gpu_mem_mb if self._sample else None,
        }

        self._persist(schema)

        return {"metadata": metadata, "extraction": dict(self.last_run)}

    def _degraded_result(self, schema: ExtractionSchema, mode: str, reason: str) -> Dict:
        """
        Kết quả khi KHÔNG gọi được model: rỗng nhưng hợp lệ, có đánh dấu cần xem lại và ghi truy vết.
        Dùng cho lỗi cấu hình — tài liệu vẫn đi tiếp trong quy trình, cán bộ nhập tay phần metadata.
        """
        self.last_run = {
            "provider": "(không dùng được)", "deployment": mode, "mode": mode,
            "model": "", "model_version": "", "schema_code": schema.code,
            "sensitivity": schema.sensitivity, "attempts": 0, "errors": [reason],
            "low_confidence_fields": [], "needs_review": True, "review_note": reason,
            "fallback_from": None, "n_fields": 0, "error": reason,
            "latency_ms": None, "rss_mb": None, "gpu_mem_mb": None,
        }
        self._persist(schema)
        return {"metadata": [], "extraction": dict(self.last_run)}

    # -- Các bước con -----------------------------------------------------
    def _run_extraction(self, provider, text: str, schema: ExtractionSchema, quality):
        """Gọi model qua lớp chất lượng, có đo tài nguyên. Không để ngoại lệ làm mất tài liệu."""
        self._sample = None
        try:
            with metrics.measure() as m:
                result, errors, attempts, needs_manual = quality.extract_with_quality(
                    provider, text, schema, max_retries=self.max_retries, source_text=text,
                )
            self._sample = m.sample
            return result, errors, attempts, needs_manual, None
        except Exception as e:  # noqa: BLE001 - YC-MP-05: tài liệu vẫn phải đi tiếp
            logger.error("Trích xuất qua provider '%s' lỗi: %s", provider.name, e)
            self._sample = metrics.ResourceSample()
            return ExtractionResult(fields=[]), [f"Lỗi gọi model: {e}"], 1, True, str(e)

    @staticmethod
    def _build_review_note(errors: List[str], low_conf: List[str],
                           metadata: List[Dict], error_msg: Optional[str]) -> Optional[str]:
        """Ghi lý do cần xem lại bằng tiếng Việt, đủ cụ thể để cán bộ biết phải kiểm gì."""
        parts = []
        if error_msg:
            parts.append(f"Lỗi gọi model: {error_msg}")
        if errors:
            parts.append("Không hợp lệ: " + "; ".join(errors))
        if low_conf:
            parts.append("Trường điểm tin cậy thấp: " + ", ".join(low_conf))
        if not metadata:
            parts.append("Không trích được trường nào")
        return " | ".join(parts) if parts else None

    def _persist(self, schema: ExtractionSchema) -> None:
        """
        Ghi nhật ký gọi model + audit + thông tin trích xuất vào DB.
        Bọc try/except: đây là truy vết, không được làm gãy việc số hóa (cùng nguyên tắc audit).
        """
        run = self.last_run
        try:
            import scripts.db as db
            from scripts.core import audit

            status = "failed" if run["error"] else ("fallback" if run["fallback_from"] else "success")
            db.log_model_call(
                provider=run["provider"], deployment=run["deployment"],
                document_id=self.document_id, model=run["model"],
                model_version=run["model_version"], schema_code=run["schema_code"],
                used_ai=not run["error"], attempts=run["attempts"],
                latency_ms=run["latency_ms"], rss_mb=run["rss_mb"], gpu_mem_mb=run["gpu_mem_mb"],
                n_fields=run["n_fields"], fallback_from=run["fallback_from"],
                error=run["error"], status=status,
            )

            if self.document_id:
                db.set_extraction_info(
                    self.document_id, provider=run["provider"], mode=run["mode"],
                    model=run["model"], needs_review=run["needs_review"],
                    review_note=run["review_note"],
                )
                audit.log_action(
                    action=audit.ACTION_PROCESS, document_id=self.document_id, actor=self.actor,
                    mode=run["mode"], model=f"{run['provider']}/{run['model']}",
                    detail={
                        "schema": run["schema_code"], "sensitivity": run["sensitivity"],
                        "n_fields": run["n_fields"], "attempts": run["attempts"],
                        "latency_ms": run["latency_ms"], "needs_review": run["needs_review"],
                        "fallback_from": run["fallback_from"],
                        "low_confidence_fields": run["low_confidence_fields"],
                    },
                )
        except Exception as e:  # noqa: BLE001
            logger.error("Ghi truy vết trích xuất thất bại (doc=%s): %s", self.document_id, e)
