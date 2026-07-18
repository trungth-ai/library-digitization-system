#!/usr/bin/env python3
"""
Library Digitization Worker
Async worker consuming jobs from Redis and running DigitizationPipeline
"""

import os
import json
import time
from datetime import datetime
import logging
import traceback
from typing import Dict

import redis

from scripts.digitize import DigitizationPipeline, ProcessingConfig
import scripts.db as db
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

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")


# =========================
# WORKER CLASS
# =========================

class DigitizationWorker:
    def __init__(self):
        self.redis = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True
        )
        logger.info(f"Worker initialized. Redis: {REDIS_HOST}:{REDIS_PORT}")

        # Worker là single process → pool nhỏ là đủ
        db.init_pool(min_conn=1, max_conn=3)
        logger.info("DB pool initialized")

        if CLAUDE_API_KEY:
            logger.info("Claude API key detected - AI metadata extraction enabled")
        else:
            logger.warning("No Claude API key - using basic metadata extraction")

    def run(self):
        logger.info("Worker started. Waiting for jobs...")

        try:
            while True:
                try:
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

        try:
            # ── Cấu hình pipeline ────────────────────────────────
            config = ProcessingConfig()
            config.document_type = document_type
            if collection_id:
                config.collection_id = collection_id

            pipeline = DigitizationPipeline(
                config=config,
                claude_api_key=CLAUDE_API_KEY
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
            finished_at  = datetime.utcnow().isoformat()

            self._update_status(job_id, "completed", 100, filename, pdf_path=pdf_path)

            # Ghi thêm finished_at vào Redis (không có trong _update_status)
            self.redis.hset(f"job:{job_id}", mapping={
                "finished_at":  finished_at,
                "results_path": os.path.join(output_dir, "processing_results.json"),
            })

            logger.info(f"Job {job_id} completed successfully")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Job {job_id} failed: {e}")
            logger.error(traceback.format_exc())

            self._update_status(job_id, "failed", 0, filename, error_message=error_msg)

            self.redis.hset(f"job:{job_id}", mapping={
                "finished_at": datetime.utcnow().isoformat(),
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