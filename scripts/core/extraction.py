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

# Ghi chi tiết TỪNG TRƯỜNG vào `model_call_fields` (YC-AN-02, sprint V2). Van lùi `=0` khi bảng chưa
# được di trú hoặc muốn giảm khối lượng ghi — hệ thống chạy y như trước, chỉ mất số liệu phân tích.
ANALYTICS_DETAIL = os.getenv("AI_ANALYTICS_DETAIL", "1").strip() not in ("0", "false", "no")
# Cắt giá trị lưu để bảng nhật ký không thành bản sao thứ hai của nội dung tài liệu
FIELD_PREVIEW_CHARS = int(os.getenv("AI_FIELD_PREVIEW_CHARS", "200"))


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
        # Kết quả và ngữ cảnh của lần trích gần nhất — dùng để ghi chi tiết từng trường (YC-AN-02).
        # Giữ ở mức đối tượng thay vì truyền qua tham số vì `_persist` đã là bước cuối của luồng.
        self._last_result = None
        self._last_context: str = ""

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
        self._last_result = result
        self._last_context = text

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

    def _field_rows(self) -> List[Dict]:
        """
        Chuyển kết quả trích xuất thành các dòng cho `model_call_fields`.

        `grounded` = giá trị có xuất hiện trong văn bản gốc không (YC-CF-05). Tính lại ở đây thay vì
        lấy từ `quality` vì `quality` chỉ trả về điểm tin cậy tổng hợp; ta cần cờ nhị phân từng
        trường để đếm được tỉ lệ ảo giác.
        """
        from scripts.core.analytics import normalize_value

        context_text = normalize_value(self._last_context)
        rows: List[Dict] = []

        for field in getattr(self._last_result, "fields", []) or []:
            value = getattr(field, "value", None)
            normalized = normalize_value(str(value) if value is not None else "")
            rows.append({
                "key": getattr(field, "key", None),
                "value": value,
                "confidence": getattr(field, "confidence", None),
                # Giá trị rỗng thì không xét bám văn bản: "không tìm thấy" là câu trả lời hợp lệ,
                # không phải ảo giác.
                "grounded": (bool(normalized and normalized in context_text)
                             if normalized else None),
                "attempt": self.last_run.get("attempts", 1),
            })
        return rows

    def _build_analytics(self, run: Dict) -> Dict:
        """
        Gom các chỉ số phân tích cho một lượt gọi (YC-AN-01/04/11).

        Bọc try/except riêng cho phần tính chi phí: bảng đơn giá hỏng hoặc thiếu không được làm mất
        cả bản ghi `model_calls` — số liệu chi phí là thứ có thể thiếu, nhật ký gọi model thì không.
        """
        from scripts.core import context as ctx

        usage = getattr(self._last_result, "usage", None) or {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")

        fields = getattr(self._last_result, "fields", []) or []
        confidences = [f.confidence for f in fields
                       if getattr(f, "confidence", None) is not None]
        grounded_flags = [row["grounded"] for row in (self._field_rows() if fields else [])
                          if row["grounded"] is not None]

        analytics: Dict = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": ((prompt_tokens or 0) + (completion_tokens or 0)) or None,
            "context_chars": len(self._last_context) or None,
            "request_id": ctx.get_request_id(),
            "retry_reason": (run["errors"][0] if run.get("errors") else None),
            "confidence_avg": (round(sum(confidences) / len(confidences), 3)
                               if confidences else None),
            "confidence_min": (round(min(confidences), 3) if confidences else None),
            "grounded_ratio": (round(sum(grounded_flags) / len(grounded_flags), 3)
                               if grounded_flags else None),
        }

        try:
            from scripts.core import pricing
            cost = pricing.compute_cost(
                provider=run["provider"], deployment=run["deployment"], model=run["model"],
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            )
            if cost.known:
                analytics["cost_micro_usd"] = cost.micro_usd
                analytics["cost_vnd"] = cost.vnd
        except Exception as e:  # noqa: BLE001
            logger.debug("Không tính được chi phí lượt gọi: %s", e)

        return analytics

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
            model_call_id = db.log_model_call(
                provider=run["provider"], deployment=run["deployment"],
                document_id=self.document_id, model=run["model"],
                model_version=run["model_version"], schema_code=run["schema_code"],
                used_ai=not run["error"], attempts=run["attempts"],
                latency_ms=run["latency_ms"], rss_mb=run["rss_mb"], gpu_mem_mb=run["gpu_mem_mb"],
                n_fields=run["n_fields"], fallback_from=run["fallback_from"],
                error=run["error"], status=status,
                analytics=self._build_analytics(run),
            )

            # Chi tiết TỪNG TRƯỜNG (YC-AN-02) — dữ liệu để đo độ chính xác trên việc thật về sau.
            # Tắt được bằng AI_ANALYTICS_DETAIL=0 nếu bảng chưa di trú hoặc muốn giảm ghi.
            if ANALYTICS_DETAIL and self._last_result is not None:
                db.log_model_call_fields(
                    model_call_id=model_call_id, document_id=self.document_id,
                    fields=self._field_rows(), preview_chars=FIELD_PREVIEW_CHARS,
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
