#!/usr/bin/env python3
"""
Library Digitization Worker
Async worker consuming jobs from Redis and running DigitizationPipeline
"""

import os
import json
import time
from datetime import datetime, timezone
import logging
import traceback
from typing import Dict

from scripts.digitize import DigitizationPipeline, ProcessingConfig
import scripts.db as db
from scripts.core import audit
from scripts.core.exceptions import SensitivityViolation
from scripts.sse import publish_job_event


# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("worker")


# =========================
# REDIS CONFIG
# =========================
DIGITIZE_DATA_DIR = os.getenv("DIGITIZE_DATA_DIR", "/data/digitization/jobs")
REDIS_HOST  = os.getenv("REDIS_HOST", "redis")
REDIS_PORT  = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB    = int(os.getenv("REDIS_DB", "0"))
REDIS_QUEUE = os.getenv("REDIS_QUEUE", "digitization_jobs")
# Tiền tố khóa nhịp tim; API đếm số khóa này để biết có worker nào sống không
WORKER_HEARTBEAT_PREFIX = "worker:heartbeat:"

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

# Trích metadata qua lớp trừu tượng hóa mô hình (ADR-008) — mặc định BẬT.
# Đặt USE_PROVIDER_LAYER=0 để lùi ngay về đường cũ bám Claude mà không cần build lại image:
# đây là van an toàn cho vận hành, không phải cờ tính năng dài hạn.
USE_PROVIDER_LAYER = os.getenv("USE_PROVIDER_LAYER", "1").strip() not in ("0", "false", "no")


# =========================
# WORKER CLASS
# =========================

class DigitizationWorker:
    def __init__(self, redis_client=None, init_db: bool = True):
        """
        `redis_client`/`init_db`: cho phép kiểm thử `process_job` bằng client giả, không cần Redis và
        PostgreSQL thật — cùng lý do với ADR-005 (lazy import để test được tầng logic). Vận hành
        thật gọi `DigitizationWorker()` như trước, hành vi không đổi.
        """
        # Mỗi replica một id riêng để đếm được số worker đang sống
        self.worker_id = os.getenv("HOSTNAME") or f"pid-{os.getpid()}"

        if redis_client is not None:
            self.redis = redis_client
        else:
            import redis  # lazy: máy dev không cài redis vẫn import được module này để test
            self.redis = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True
            )
        logger.info(f"Worker initialized. Redis: {REDIS_HOST}:{REDIS_PORT}, queue={REDIS_QUEUE}")

        if init_db:
            self._init_db_with_retry()

        if USE_PROVIDER_LAYER:
            try:
                # Import BÊN TRONG try: nếu lớp provider có vấn đề (thiếu gói, cấu hình lạ) thì worker
                # vẫn phải khởi động và tiêu thụ hàng đợi — job sẽ lỗi có mô tả, còn hơn cả worker
                # chết khiến MỌI tài liệu treo ở trạng thái "Chờ xử lý" mà không ai biết vì sao.
                from scripts.providers.factory import get_provider
                provider = get_provider()
                health = provider.health()
                logger.info(
                    "Lớp provider BẬT — công cụ %s (%s), model=%s, sẵn sàng=%s: %s",
                    provider.name, provider.deployment, provider.model, health.ready, health.detail,
                )
                if not health.ready:
                    # Không dừng worker: tài liệu vẫn vào hàng đợi được, và mỗi job sẽ tự thử lại.
                    # Dừng ở đây sẽ làm mất cả những job mà công cụ dự phòng xử lý được.
                    logger.warning("Công cụ mô hình CHƯA sẵn sàng — job sẽ dùng dự phòng hoặc bị đánh "
                                   "dấu cần xem lại. Kiểm bằng: python -m scripts.eval.run_eval --health")
            except Exception as e:  # noqa: BLE001 - cấu hình sai không được làm worker không khởi động
                logger.error("Không khởi tạo được provider (%s) — job sẽ lỗi có mô tả cho từng tài liệu", e)
        elif CLAUDE_API_KEY:
            logger.info("Lớp provider TẮT (USE_PROVIDER_LAYER=0) — dùng đường cũ với Claude API key")
        else:
            logger.warning("Lớp provider TẮT và không có Claude API key — chỉ có basic extraction")

    def _init_db_with_retry(self, max_wait: int = 30) -> None:
        """
        Mở connection pool, THỬ LẠI cho tới khi được.

        VÌ SAO: `docker compose` không đợi PostgreSQL sẵn sàng mới chạy worker. Trước đây
        `init_pool` lỗi là worker chết ngay, `restart: unless-stopped` cho nó chết lại vòng vòng —
        và triệu chứng ở giao diện chỉ là tài liệu treo mãi ở "Chờ xử lý", không hề nói vì sao.
        Thử lại thì container còn sống, log nêu rõ đang đợi cái gì.
        """
        delay, attempt = 1, 0
        while True:
            attempt += 1
            try:
                # Worker là single process → pool nhỏ là đủ
                db.init_pool(min_conn=1, max_conn=3)
                logger.info("DB pool initialized (lần thử %d)", attempt)
                return
            except Exception as e:  # noqa: BLE001
                logger.error(
                    "Chưa nối được PostgreSQL (lần %d): %s — thử lại sau %ds. "
                    "Kiểm tra service postgres đã chạy và POSTGRES_* có đúng chưa.",
                    attempt, e, delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, max_wait)

    def _beat(self):
        """
        Ghi nhịp tim vào Redis (TTL 60s) để API/giao diện biết CÓ worker đang sống.

        VÌ SAO CẦN: khi không có worker nào chạy, tài liệu chỉ nằm im ở "Chờ xử lý" và giao diện
        không nói gì cả — người dùng đợi mãi mà không biết là đang đợi vô ích. Có nhịp tim thì
        giao diện báo được "không có worker nào đang chạy" thay vì im lặng.
        Khóa hết hạn tự động nên worker đã tắt sẽ tự biến mất, không cần dọn.
        """
        try:
            self.redis.setex(f"{WORKER_HEARTBEAT_PREFIX}{self.worker_id}", 60,
                             datetime.now(timezone.utc).isoformat())
        except Exception as e:  # noqa: BLE001 - nhịp tim hỏng không được làm dừng việc xử lý
            logger.debug("Không ghi được nhịp tim: %s", e)

    def run(self):
        logger.info("Worker started (id=%s). Waiting for jobs on queue '%s'...",
                    self.worker_id, REDIS_QUEUE)

        try:
            while True:
                try:
                    self._beat()
                    job = self.redis.blpop(REDIS_QUEUE, timeout=5)

                    if not job:
                        continue

                    _, raw_data = job
                    job_data = json.loads(raw_data)

                    job_id = job_data.get("job_id", "unknown")
                    logger.info(f"Processing job: {job_id}")

                    self.process_job(job_data)

                except Exception as e:
                    logger.error(f"Worker loop error: {e}")
                    logger.error(traceback.format_exc())
                    time.sleep(2)
        finally:
            db.close_pool()

    # ─────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────

    def _update_status(self, job_id: str, status: str, progress: int,
                       filename: str = "", pdf_path: str = None,
                       error_message: str = None):
        """
        Ghi trạng thái đồng thời vào 3 nơi:
        1. Redis hash  — API polling cũ vẫn hoạt động
        2. PostgreSQL  — nguồn dữ liệu chính
        3. Redis Pub/Sub — SSE push xuống frontend ngay lập tức
        """
        # 1. Redis hash (backward compat)
        mapping = {"status": status, "progress": str(progress)}
        if error_message:
            mapping["error"] = error_message
        self.redis.hset(f"job:{job_id}", mapping=mapping)

        # 2. PostgreSQL
        try:
            db.update_document_status(
                job_id,
                status,
                progress=progress,
                pdf_path=pdf_path,
                error_message=error_message,
            )
        except Exception as e:
            logger.error(f"DB update failed for {job_id}: {e}")

        # 3. Pub/Sub → SSE clients
        publish_job_event(
            redis_client=self.redis,
            job_id=job_id,
            status=status,
            progress=progress,
            filename=filename,
            error=error_message,
        )

    # ─────────────────────────────────────────────────────────────
    # MAIN JOB PROCESSOR
    # ─────────────────────────────────────────────────────────────

    def process_job(self, job_data: Dict):
        job_id        = job_data.get("job_id", "unknown")
        filename      = job_data.get("filename", "")
        input_file    = job_data["input_file"]
        output_dir    = job_data["output_dir"]
        collection_id = job_data.get("collection_id", "")
        document_type = job_data.get("document_type", "book")

        extractor = None
        try:
            # ── Cấu hình pipeline ────────────────────────────────
            config = ProcessingConfig()
            config.document_type = document_type
            if collection_id:
                config.collection_id = collection_id

            # Lớp provider: định tuyến theo độ nhạy cảm + điểm tin cậy + nhật ký gọi model.
            # Tạo mới cho TỪNG job vì nó giữ `last_run` của riêng tài liệu đó.
            if USE_PROVIDER_LAYER:
                from scripts.core.extraction import ProviderMetadataExtractor
                extractor = ProviderMetadataExtractor(
                    config=config, document_id=job_id, actor="worker",
                )

            pipeline = DigitizationPipeline(
                config=config,
                claude_api_key=CLAUDE_API_KEY,
                metadata_extractor=extractor,
            )

            # ── ocr (20%) ─────────────────────────────────────────
            # Progress tang dan: 20 → 60 → 80 → 100, khong bao gio giat lui
            self._update_status(job_id, "ocr", 20, filename)

            # Chạy pipeline — không chỉnh sửa logic bên trong
            results = pipeline.process(
                input_pdf=input_file,
                output_dir=output_dir
            )

            summary = results.get("summary", {})
            if summary.get("status") == "failed":
                raise RuntimeError(summary.get("error", "Processing failed"))

            # ── extracting (60%) ─────────────────────────────────
            self._update_status(job_id, "extracting", 60, filename)

            metadata_list = self._read_metadata(output_dir)
            if metadata_list:
                db.save_metadata(job_id, metadata_list)
                logger.info(f"Saved {len(metadata_list)} metadata fields for job {job_id}")

            # ── exporting (80%) ───────────────────────────────────
            self._update_status(job_id, "exporting", 80, filename)

            # ── completed ────────────────────────────────────────
            pdf_path     = summary.get("output_pdf", "")
            finished_at  = datetime.now(timezone.utc).isoformat()

            self._update_status(job_id, "completed", 100, filename, pdf_path=pdf_path)

            # Ghi thêm finished_at vào Redis (không có trong _update_status)
            self.redis.hset(f"job:{job_id}", mapping={
                "finished_at":  finished_at,
                "results_path": os.path.join(output_dir, "processing_results.json"),
            })

            # Tài liệu cần cán bộ xem lại (YC-CF-03/04): status vẫn 'completed' vì OCR đã xong,
            # nhưng đẩy cờ ra Redis + SSE để UI hiện ngay, không phải chờ cán bộ mở từng tài liệu.
            run = getattr(extractor, "last_run", None) or {}
            if run.get("needs_review"):
                self.redis.hset(f"job:{job_id}", mapping={
                    "needs_review": "1",
                    "review_note": run.get("review_note") or "",
                })
                logger.warning("Job %s HOÀN THÀNH nhưng cần xem lại: %s", job_id, run.get("review_note"))

            if run:
                logger.info(
                    "Job %s trích bằng %s (%s) model=%s, %d trường, %s ms",
                    job_id, run.get("provider"), run.get("mode"), run.get("model"),
                    run.get("n_fields", 0), run.get("latency_ms"),
                )

            logger.info(f"Job {job_id} completed successfully")

        except SensitivityViolation as e:
            # YC-DR-03: ràng buộc cứng — KHÔNG xử lý tạm, KHÔNG âm thầm đổi chế độ.
            # Job thất bại có mô tả tiếng Việt để cán bộ biết phải sửa cấu hình, và audit giữ
            # bằng chứng từ chối cho kiểm toán (KT-BM-06).
            error_msg = f"Từ chối theo ràng buộc độ nhạy cảm: {e}"
            logger.error("Job %s bị từ chối (YC-DR-03): %s", job_id, e)

            self._update_status(job_id, "failed", 0, filename, error_message=error_msg)
            audit.log_action(
                action=audit.ACTION_ROUTE_DENIED, document_id=job_id, actor="worker",
                detail={"reason": str(e), "document_type": document_type},
            )
            self.redis.hset(f"job:{job_id}", mapping={
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Job {job_id} failed: {e}")
            logger.error(traceback.format_exc())

            self._update_status(job_id, "failed", 0, filename, error_message=error_msg)
            audit.log_action(
                action=audit.ACTION_PROCESS, document_id=job_id, actor="worker",
                detail={"status": "failed", "error": error_msg},
            )

            self.redis.hset(f"job:{job_id}", mapping={
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })

    def _read_metadata(self, output_dir: str) -> list:
        """
        Đọc metadata.json mà digitize.py đã ghi ra disk.
        File này vẫn cần cho download ZIP nên không xóa.
        """
        import json as _json
        from pathlib import Path

        metadata_path = Path(output_dir) / "metadata.json"
        if metadata_path.exists():
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    return _json.load(f).get("metadata", [])
            except Exception as e:
                logger.warning(f"Could not read metadata.json: {e}")
        return []


# =========================
# ENTRYPOINT
# =========================

def main():
    worker = DigitizationWorker()
    worker.run()


if __name__ == "__main__":
    main()