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
from typing import Dict, Optional

from scripts.digitize import DigitizationPipeline, ProcessingConfig
import scripts.db as db
from scripts.core import audit
from scripts.core import queue as jobqueue
from scripts.core.exceptions import SensitivityViolation
from scripts.sse import publish_job_event


# =========================
# LOGGING
# =========================

# Log JSON có cấu trúc + che bí mật (sprint V1). Van lùi: `LOG_FORMAT=text`.
from scripts.core import context, logging_setup   # noqa: E402

logger = logging_setup.configure("worker")


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
# Thời gian chờ mỗi lượt BLPOP. Hết giờ mà hàng đợi rỗng là chuyện BÌNH THƯỜNG,
# KHÔNG phải lỗi — xem cách xử lý RedisTimeoutError trong run().
BLPOP_TIMEOUT = int(os.getenv("BLPOP_TIMEOUT", "5"))

# Hàng đợi TIN CẬY (ADR-011) — mặc định BẬT. `QUEUE_MODE=blpop` là van lùi về vòng lặp cũ mà không
# cần build lại image. Chế độ cũ MẤT job nếu worker chết giữa lúc xử lý (lỗi N-02) nên chỉ dùng để
# đối chứng khi gỡ lỗi, không dùng lâu dài.
QUEUE_MODE = os.getenv("QUEUE_MODE", "reliable").strip().lower()
RELIABLE_QUEUE = QUEUE_MODE != "blpop"
# Số lần thử TỐI ĐA cho lỗi hạ tầng (tính cả lần đầu). Lỗi tài liệu không thử lại — xem _classify_failure.
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))
RETRY_BACKOFF_SEC = int(os.getenv("RETRY_BACKOFF_SEC", "30"))
# Quét thu hồi việc mồ côi mỗi N giây (không quét mỗi vòng lặp: `scan_iter` rẻ nhưng không miễn phí)
RECLAIM_INTERVAL_SEC = int(os.getenv("RECLAIM_INTERVAL_SEC", "60"))

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

# Đo chất lượng OCR sau mỗi tài liệu (YC-AN-03). Van lùi `=0` khi chưa chạy migration 005 hoặc khi
# việc mở lại PDF để đếm trang làm chậm đáng kể trên phần cứng yếu.
OCR_METRICS_ENABLED = os.getenv("OCR_METRICS_ENABLED", "1").strip() not in ("0", "false", "no")

# Bao lâu thì thử lại một job thuộc lô đang tạm dừng. Không nên quá ngắn (quay vòng nóng trên Redis)
# cũng không nên quá dài (bấm "tiếp tục" xong phải đợi lâu mới thấy chạy lại).
BATCH_PAUSE_RECHECK_SEC = int(os.getenv("BATCH_PAUSE_RECHECK_SEC", "30"))

# Chu kỳ lấy mẫu độ sâu hàng đợi (YC-BU-18). Ngắn hơn chu kỳ thu hồi: mẫu thưa quá thì biểu đồ
# xu hướng không thấy được đỉnh cao điểm — mà cao điểm mới là thứ cần biết.
QUEUE_SAMPLE_INTERVAL_SEC = int(os.getenv("QUEUE_SAMPLE_INTERVAL_SEC", "60"))

# ── Kết quả xử lý một job (ADR-011 mục 6) ────────────────────────────
JOB_OK = "ok"
JOB_FAILED_DOCUMENT = "document"   # lỗi của TÀI LIỆU → không thử lại, vào hàng đợi chết ngay
JOB_FAILED_INFRA = "infra"         # lỗi HẠ TẦNG → thử lại có khoảng lùi

# Nhận diện lỗi hạ tầng theo TÊN LỚP thay vì `isinstance`, để không phải import psycopg2/redis ở mức
# module — máy dev không cài hai gói đó vẫn kiểm thử được phần phân loại này. Cùng lý do với
# `_redis_exception_classes()` (ADR-009).
_INFRA_EXCEPTION_NAMES = frozenset({
    "OperationalError",     # psycopg2: mất kết nối / DB không nhận kết nối
    "InterfaceError",       # psycopg2: kết nối đã đóng
    "PoolError",            # psycopg2 pool cạn
    "ConnectionError",      # redis-py + builtin
    "TimeoutError",         # redis-py + builtin
    "BrokenPipeError",
    "OSError",              # đĩa đầy, lỗi I/O — FileNotFoundError đã được loại trước đó
})


class JobResult:
    """
    Kết quả xử lý một job. `process_job` trước đây trả `None`; nay trả về đối tượng này để vòng lặp
    biết nên thử lại hay bỏ vào hàng đợi chết. Nơi gọi cũ không dùng giá trị trả về nên không bị ảnh hưởng.
    """

    __slots__ = ("status", "error")

    def __init__(self, status: str, error: str = None):
        self.status = status
        self.error = error

    @property
    def ok(self) -> bool:
        return self.status == JOB_OK

    def __repr__(self) -> str:
        return f"JobResult(status={self.status!r}, error={self.error!r})"


def _classify_failure(exc: BaseException) -> str:
    """
    Lỗi này nên THỬ LẠI (hạ tầng) hay BỎ VÀO HÀNG ĐỢI CHẾT (tài liệu)?

    Mặc định là lỗi TÀI LIỆU (không thử lại) — chọn có chủ đích: giữ đúng hành vi hiện tại cho mọi
    tình huống thất bại đã biết, chỉ thêm việc thử lại cho những lỗi hạ tầng nhận diện được chắc chắn.
    Mặc định ngược lại (cứ thử lại) sẽ làm một tài liệu hỏng tốn 3 lượt OCR để rồi kết cục y như cũ.
    """
    # Tệp không có / không đọc được là lỗi TÀI LIỆU, dù FileNotFoundError là con của OSError
    if isinstance(exc, (FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError)):
        return JOB_FAILED_DOCUMENT
    for cls in type(exc).__mro__:
        if cls.__name__ in _INFRA_EXCEPTION_NAMES:
            return JOB_FAILED_INFRA
    return JOB_FAILED_DOCUMENT

# Trích metadata qua lớp trừu tượng hóa mô hình (ADR-008) — mặc định BẬT.
# Đặt USE_PROVIDER_LAYER=0 để lùi ngay về đường cũ bám Claude mà không cần build lại image:
# đây là van an toàn cho vận hành, không phải cờ tính năng dài hạn.
USE_PROVIDER_LAYER = os.getenv("USE_PROVIDER_LAYER", "1").strip() not in ("0", "false", "no")


def _redis_exception_classes():
    """
    Trả về (TimeoutError, ConnectionError) của redis-py.

    Tách thành hàm module-level để KIỂM THỬ ĐƯỢC: máy dev không cài `redis`, nên nếu lấy lớp ngoại lệ
    ngay trong `run()` thì không cách nào dựng được tình huống "BLPOP hết giờ" trong test — đúng cái
    lỗi vừa gặp ở production. Test thay hàm này bằng lớp giả của nó.
    """
    try:
        from redis.exceptions import ConnectionError as RedisConnectionError
        from redis.exceptions import TimeoutError as RedisTimeoutError
        return RedisTimeoutError, RedisConnectionError
    except ImportError:
        class _NoRedisTimeout(Exception): ...
        class _NoRedisConnError(Exception): ...
        return _NoRedisTimeout, _NoRedisConnError


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
        # Trạng thái kết nối Redis; None = chưa biết, để lần đầu xác định được cũng ghi nhận
        self._redis_ok = None
        # Lần cuối quét thu hồi việc mồ côi (0 = chưa quét → quét ngay vòng đầu, đúng lúc cần nhất:
        # worker vừa khởi động lại thường là sau khi worker trước đã chết)
        self._last_reclaim = 0.0
        self._last_sample = 0.0
        # Chế độ hàng đợi đặt ở MỨC ĐỐI TƯỢNG, không đọc trực tiếp hằng module trong `run()`:
        # để kiểm thử bật/tắt được từng worker mà không phải nạp lại module (van lùi vẫn là QUEUE_MODE).
        self.reliable_queue = RELIABLE_QUEUE

        if redis_client is not None:
            self.redis = redis_client
        else:
            import redis  # lazy: máy dev không cài redis vẫn import được module này để test
            self.redis = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True,
                # ---- Tham số kết nối cho hàng đợi CHẶN (blocking) ----
                # socket_timeout=None: BẮT BUỘC. redis-py áp thời hạn đọc socket cho lệnh chặn theo
                # chính `timeout` của lệnh, nên nếu đặt thời hạn socket thì phản hồi "hết giờ, không
                # có việc" của BLPOP về CHẬM một nhịp là client ném TimeoutError — đúng lỗi đang gặp.
                socket_timeout=None,
                socket_connect_timeout=5,      # nối không được thì báo nhanh, không treo
                socket_keepalive=True,         # phát hiện kết nối đứt (NAT/firewall cắt lặng lẽ)
                retry_on_timeout=True,
                health_check_interval=30,      # tự PING để kết nối rỗi không bị coi là chết
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

    def _log_event(self, kind: str, level: str, message: str, detail: str = None,
                   document_id: str = None) -> None:
        """Ghi một sự kiện hạ tầng vào DB để còn tra được sau (log container bị cắt vòng)."""
        db.log_system_event(source="worker", kind=kind, level=level, message=message,
                            detail=detail, instance=self.worker_id, document_id=document_id)

    def _set_redis_state(self, ok: bool, detail: str = None) -> None:
        """
        Theo dõi trạng thái kết nối Redis, CHỈ ghi khi trạng thái ĐỔI.

        Ghi mỗi vòng lặp sẽ làm ngập bảng sự kiện (mỗi 5 giây một dòng); ghi theo lần đổi thì đúng
        cái người vận hành cần biết: mất lúc nào, nối lại lúc nào.
        """
        if ok == self._redis_ok:
            return

        # Lần quan sát ĐẦU TIÊN mà kết nối bình thường: chỉ ghi nhận trạng thái, KHÔNG báo
        # "đã nối lại được" — chưa từng mất thì không có gì để nối lại. Nếu không phân biệt, mỗi lần
        # khởi động worker sẽ sinh một sự kiện giả và làm loãng bảng sự kiện thật.
        first_observation = self._redis_ok is None
        self._redis_ok = ok
        if ok and first_observation:
            return

        if ok:
            logger.info("Redis đã nối lại được")
            self._log_event("redis_up", "info", "Redis đã nối lại được")
            try:
                db.resolve_system_events("redis_down", self.worker_id)
            except Exception:  # noqa: BLE001
                pass
        else:
            logger.error("MẤT kết nối Redis: %s", detail)
            self._log_event("redis_down", "error", f"Mất kết nối Redis: {detail}")

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

    def _maintenance(self) -> None:
        """
        Việc nền của hàng đợi tin cậy: đưa job đến hạn thử lại về hàng đợi + thu hồi việc mồ côi.

        Chạy trong worker khi rỗi, KHÔNG thêm container. `promote_delayed` rẻ (một lệnh có LIMIT) nên
        chạy mỗi vòng; `reclaim_orphans` phải quét khóa nên giãn ra theo `RECLAIM_INTERVAL_SEC`.
        """
        try:
            jobqueue.promote_delayed(self.redis, REDIS_QUEUE)
        except Exception as e:  # noqa: BLE001 - việc nền hỏng không được làm dừng xử lý tài liệu
            logger.debug("Không chuyển được job đến hạn thử lại: %s", e)

        now = time.time()

        # Lấy mẫu độ sâu hàng đợi (YC-BU-18) — nguồn dữ liệu cho biểu đồ xu hướng.
        # Chu kỳ riêng, ngắn hơn chu kỳ thu hồi: mẫu thưa quá thì không thấy được đỉnh cao điểm.
        if now - self._last_sample >= QUEUE_SAMPLE_INTERVAL_SEC:
            self._last_sample = now
            self._sample_queue_depth()

        if now - self._last_reclaim < RECLAIM_INTERVAL_SEC:
            return
        self._last_reclaim = now

        try:
            for worker_id, count in jobqueue.reclaim_orphans(self.redis, REDIS_QUEUE):
                # Đây là sự kiện vận hành QUAN TRỌNG: nó nghĩa là một worker đã chết giữa lúc làm việc.
                # Trước ADR-011 thì những job này biến mất không dấu vết.
                self._log_event(
                    "job_reclaimed", "warning",
                    f"Thu hồi {count} job từ worker đã chết '{worker_id}' — đã trả về hàng đợi",
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("Không thu hồi được việc mồ côi: %s", e)

    def _handle_claimed(self, job: "jobqueue.ClaimedJob") -> None:
        """
        Xử lý một job đã nhận, rồi báo kết quả cho hàng đợi.

        Thứ tự QUAN TRỌNG: chỉ `ack` (xóa khỏi danh sách đang-xử-lý) SAU KHI job thực sự xong. Ack
        sớm là mở lại đúng cửa sổ mất job mà ADR-011 đang đóng.
        """
        logger.info("Processing job: %s (ưu tiên=%s, lần thử %d)",
                    job.job_id, job.priority, job.attempts + 1)

        # Lô bị tạm dừng/hủy: trả job về hàng đợi và KHÔNG xử lý (YC-BU-16). Trả về chứ không bỏ đi —
        # "tạm dừng" phải nghĩa là hoãn lại, không phải mất tài liệu.
        batch_id = job.data.get("batch_id")
        if batch_id and self._batch_paused(batch_id):
            logger.info("Lô %s đang tạm dừng — hoãn job %s", batch_id[:8], job.job_id)
            jobqueue.fail(self.redis, REDIS_QUEUE, self.worker_id, job,
                          reason="Lô đang tạm dừng", retryable=True,
                          max_attempts=10 ** 6,       # tạm dừng không tính là lần thử thất bại
                          backoff_sec=BATCH_PAUSE_RECHECK_SEC)
            return

        # `process_job` trước ADR-011 trả `None`. Nơi nào còn theo hợp đồng cũ (lớp con, mã kiểm thử)
        # thì hiểu là "đã tự xử lý xong" → ack. Không normalize ở đây sẽ ném AttributeError trên None.
        result = self.process_job(job.data) or JobResult(JOB_OK)

        if result.status == JOB_OK:
            jobqueue.ack(self.redis, self.worker_id, job)
            self._bump_batch(batch_id, done=1)
            return

        retryable = result.status == JOB_FAILED_INFRA
        action, attempts = jobqueue.fail(
            self.redis, REDIS_QUEUE, self.worker_id, job,
            reason=result.error or "không rõ nguyên nhân",
            retryable=retryable, max_attempts=MAX_ATTEMPTS, backoff_sec=RETRY_BACKOFF_SEC,
        )

        if action == "retry":
            # Trả tài liệu về "Chờ xử lý" với lý do đọc được: người dùng thấy nó đang được thử lại,
            # không phải đã thất bại hẳn. `process_job` vừa đặt trạng thái 'failed' cho lần thử này.
            self._update_status(
                job.job_id, "queued", 10, job.data.get("filename", ""),
                error_message=f"Thử lại lần {attempts}/{MAX_ATTEMPTS} (lỗi hạ tầng): {result.error}",
            )
        else:
            self._log_event(
                "job_dead", "error",
                f"Job {job.job_id} vào hàng đợi chết sau {attempts} lần thử: {result.error}",
                document_id=job.job_id,
            )
            # Chỉ đếm là thất bại khi ĐÃ HẾT đường thử lại — đếm ở mỗi lần thử sẽ làm tiến độ lô
            # vượt quá tổng số tệp và tự đánh dấu "hoàn thành" quá sớm.
            self._bump_batch(batch_id, failed=1)

    def run(self):
        logger.info("Worker started (id=%s). Waiting for jobs on queue '%s'...",
                    self.worker_id, REDIS_QUEUE)

        if self.reliable_queue:
            logger.info("Hàng đợi TIN CẬY BẬT (BLMOVE + thu hồi việc mồ côi, ADR-011) — "
                        "job không mất khi worker chết. Tối đa %d lần thử, khoảng lùi %ds.",
                        MAX_ATTEMPTS, RETRY_BACKOFF_SEC)
        else:
            logger.warning("Hàng đợi chế độ CŨ (QUEUE_MODE=blpop) — ⚠️ job sẽ MẤT nếu worker chết "
                           "giữa lúc xử lý (lỗi N-02). Chỉ dùng để đối chứng khi gỡ lỗi.")

        RedisTimeoutError, RedisConnectionError = _redis_exception_classes()

        try:
            while True:
                try:
                    self._beat()

                    if self.reliable_queue:
                        self._maintenance()
                        claimed = jobqueue.claim(self.redis, REDIS_QUEUE, self.worker_id,
                                                 timeout=BLPOP_TIMEOUT)
                        self._set_redis_state(True)
                        if claimed is None:
                            continue    # hết giờ chờ, hàng đợi rỗng — chuyện bình thường
                        self._handle_claimed(claimed)
                        continue

                    # ── Đường CŨ (van lùi QUEUE_MODE=blpop) — giữ nguyên từng dòng ──
                    job = self.redis.blpop(REDIS_QUEUE, timeout=BLPOP_TIMEOUT)

                    self._set_redis_state(True)

                    if not job:
                        continue        # hết giờ chờ, hàng đợi rỗng — chuyện bình thường

                    _, raw_data = job
                    job_data = json.loads(raw_data)

                    job_id = job_data.get("job_id", "unknown")
                    logger.info(f"Processing job: {job_id}")

                    self.process_job(job_data)

                except RedisTimeoutError:
                    # KHÔNG phải lỗi: BLPOP hết giờ chờ mà phản hồi về chậm một nhịp so với thời hạn
                    # đọc socket. Trước đây nhánh này rơi vào `except Exception` → log cả traceback
                    # rồi ngủ 2s mỗi vòng, làm log ngập lỗi giả và job bị nhận chậm hơn.
                    logger.debug("BLPOP hết giờ chờ (hàng đợi rỗng) — bỏ qua, không phải lỗi")
                    self._set_redis_state(True)
                    continue

                except RedisConnectionError as e:
                    # Redis THẬT SỰ mất kết nối — ghi lại một lần khi đổi trạng thái, không spam
                    self._set_redis_state(False, str(e))
                    time.sleep(2)

                except Exception as e:
                    logger.error(f"Worker loop error: {e}")
                    logger.error(traceback.format_exc())
                    self._log_event("worker_error", "error",
                                    f"Lỗi vòng lặp worker: {e}", traceback.format_exc())
                    time.sleep(2)
        finally:
            db.close_pool()

    # ─────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────

    def _update_status(self, job_id: str, status: str, progress: int,
                       filename: str = "", pdf_path: str = None,
                       error_message: str = None, clear_error: bool = False):
        """
        Ghi trạng thái đồng thời vào 3 nơi:
        1. Redis hash  — API polling cũ vẫn hoạt động
        2. PostgreSQL  — nguồn dữ liệu chính
        3. Redis Pub/Sub — SSE push xuống frontend ngay lập tức

        `clear_error=True` xóa thông báo lỗi cũ — cần khi một tài liệu thất bại rồi thành công ở lần
        thử lại, nếu không nó sẽ hiện "Hoàn thành" kèm lỗi của lần trước (xem `db.update_document_status`).
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
                clear_error=clear_error,
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

    def _sample_queue_depth(self) -> None:
        """
        Ghi một mẫu độ sâu hàng đợi. Không ném lỗi ra ngoài.

        ⚠️ NHIỀU WORKER cùng lấy mẫu sẽ ghi trùng thời điểm. Chấp nhận được: truy vấn lịch sử dùng
        `MAX` theo khoảng thời gian nên các mẫu trùng cho cùng kết quả. Bầu chọn một worker "chủ" để
        lấy mẫu sẽ phức tạp hơn nhiều so với giá trị nhận được.
        """
        try:
            depth = jobqueue.depth(self.redis, REDIS_QUEUE)

            try:
                workers_alive = sum(
                    1 for _ in self.redis.scan_iter(f"{WORKER_HEARTBEAT_PREFIX}*", count=100))
            except Exception:  # noqa: BLE001
                workers_alive = None      # None = KHÔNG BIẾT, khác hẳn 0 = không có worker nào

            db.log_queue_sample(depth.as_dict(), workers_alive=workers_alive)
        except Exception as e:  # noqa: BLE001
            logger.debug("Không lấy được mẫu độ sâu hàng đợi: %s", e)

    def _batch_paused(self, batch_id: str) -> bool:
        """Lô có đang tạm dừng không? Lỗi truy vấn → coi như không, để tài liệu vẫn được xử lý."""
        try:
            from scripts.core import batches
            return batches.is_paused(batch_id)
        except Exception as e:  # noqa: BLE001 - chưa chạy migration 006 thì cứ xử lý bình thường
            logger.debug("Không đọc được trạng thái lô %s: %s", batch_id, e)
            return False

    def _bump_batch(self, batch_id: Optional[str], done: int = 0, failed: int = 0) -> None:
        """Cập nhật tiến độ lô. Số liệu tiến độ không bao giờ được chặn việc xử lý tài liệu."""
        if not batch_id:
            return
        try:
            from scripts.core import batches
            batches.bump_counters(batch_id, done=done, failed=failed)
        except Exception as e:  # noqa: BLE001
            logger.debug("Không cập nhật được tiến độ lô %s: %s", batch_id, e)

    def _record_ocr_metrics(self, job_id: str, input_file: str, summary: dict,
                            config, language: Optional[str], stage_timings: dict) -> None:
        """
        Ghi chỉ số chất lượng OCR (YC-AN-03). Không bao giờ ném lỗi ra ngoài.

        Đo trên PDF ĐẦU RA, không phải đầu vào: câu hỏi là "sau khi OCR, tài liệu này có tra cứu được
        không", mà chỉ bản đầu ra mới trả lời được.
        """
        if not OCR_METRICS_ENABLED:
            return

        try:
            from scripts.core import ocr_metrics

            metrics_row = ocr_metrics.collect(
                document_id=job_id,
                input_pdf=input_file,
                output_pdf=summary.get("output_pdf"),
                duration_ms=stage_timings.get("ocr_and_extract"),
                language=language,
                dpi_pre=getattr(config, "pre_compress_dpi", None),
                dpi_post=getattr(config, "post_compress_dpi", None),
            )
            db.log_ocr_run(job_id, **metrics_row)

            # Cảnh báo ngay trong log worker: cán bộ thấy sớm thì còn kịp lấy lại bản giấy để quét lại
            without_text = metrics_row.get("pages_without_text") or 0
            if without_text:
                logger.warning(
                    "Job %s: %d/%s trang KHÔNG có lớp text sau OCR — bản scan có thể cần quét lại",
                    job_id, without_text, metrics_row.get("pages"),
                )
        except Exception as e:  # noqa: BLE001 - số liệu không được làm hỏng tài liệu đã xử lý xong
            logger.warning("Không ghi được chỉ số OCR cho %s: %s", job_id, e)

    def _save_timing(self, job_id: str, duration_ms: int, stage_timings: dict) -> None:
        """Lưu thời gian xử lý. Không được làm gãy job nếu ghi thất bại — đây chỉ là số liệu."""
        try:
            db.set_job_timing(job_id, duration_ms, stage_timings)
        except Exception as e:  # noqa: BLE001
            logger.warning("Không lưu được thời gian xử lý cho %s: %s", job_id, e)

    # ─────────────────────────────────────────────────────────────
    # MAIN JOB PROCESSOR
    # ─────────────────────────────────────────────────────────────

    def process_job(self, job_data: Dict) -> JobResult:
        """
        Xử lý trọn một tài liệu. Trả về `JobResult` để vòng lặp quyết định thử lại hay không (ADR-011).

        MỌI hiệu ứng phụ giữ nguyên như trước: cập nhật trạng thái, ghi audit, ghi sự kiện, lưu thời
        gian. Chỉ thêm giá trị trả về.
        """
        # Đặt `job_id` vào ngữ cảnh cho TOÀN BỘ vòng đời xử lý (YC-LG-03): mọi dòng log sinh ra từ
        # đây trở xuống — kể cả từ digitize.py, extraction.py, quality.py — đều mang mã này, nên
        # grep một job_id ra được đủ chuỗi thay vì phải lần theo dấu thời gian giữa nhiều tài liệu
        # đang chạy song song trên nhiều worker.
        with context.job_context(job_data.get("job_id", "unknown"), actor="worker"):
            return self._process_job_inner(job_data)

    def _process_job_inner(self, job_data: Dict) -> JobResult:
        job_id        = job_data.get("job_id", "unknown")
        filename      = job_data.get("filename", "")
        input_file    = job_data["input_file"]
        output_dir    = job_data["output_dir"]
        collection_id = job_data.get("collection_id", "")
        document_type = job_data.get("document_type", "book")

        extractor = None
        # Đo thời gian THỰC SỰ xử lý (không tính thời gian nằm chờ hàng đợi) — theo dõi hiệu năng.
        t_start = time.perf_counter()
        stage_timings = {}

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
            t_ocr = time.perf_counter()
            results = pipeline.process(
                input_pdf=input_file,
                output_dir=output_dir
            )
            # Chặng này gồm OCR + trích metadata (pipeline gọi extractor bên trong); tách được phần
            # gọi model nhờ `latency_ms` trong last_run, phần còn lại là OCR/nén PDF.
            stage_timings["ocr_and_extract"] = int((time.perf_counter() - t_ocr) * 1000)

            summary = results.get("summary", {})
            if summary.get("status") == "failed":
                raise RuntimeError(summary.get("error", "Processing failed"))

            # Chỉ số chất lượng OCR (YC-AN-03). Đặt SAU khi biết pipeline thành công, và bọc riêng:
            # đo đạc hỏng không được làm hỏng một tài liệu đã OCR xong.
            self._record_ocr_metrics(job_id, input_file, summary, config,
                                     job_data.get("language"), stage_timings)

            # ── extracting (60%) ─────────────────────────────────
            self._update_status(job_id, "extracting", 60, filename)

            t_save = time.perf_counter()
            metadata_list = self._read_metadata(output_dir)
            if metadata_list:
                db.save_metadata(job_id, metadata_list)
                logger.info(f"Saved {len(metadata_list)} metadata fields for job {job_id}")
            stage_timings["save_metadata"] = int((time.perf_counter() - t_save) * 1000)

            # ── exporting (80%) ───────────────────────────────────
            self._update_status(job_id, "exporting", 80, filename)

            # ── completed ────────────────────────────────────────
            pdf_path     = summary.get("output_pdf", "")
            finished_at  = datetime.now(timezone.utc).isoformat()

            # `clear_error=True`: tài liệu thành công ở lần thử lại không được mang lỗi của lần trước
            self._update_status(job_id, "completed", 100, filename, pdf_path=pdf_path,
                                clear_error=True)

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
                # Tách riêng phần gọi model để biết OCR chậm hay model chậm
                if run.get("latency_ms") is not None:
                    stage_timings["model_call"] = run["latency_ms"]
                logger.info(
                    "Job %s trích bằng %s (%s) model=%s, %d trường, %s ms",
                    job_id, run.get("provider"), run.get("mode"), run.get("model"),
                    run.get("n_fields", 0), run.get("latency_ms"),
                )

            duration_ms = int((time.perf_counter() - t_start) * 1000)
            self._save_timing(job_id, duration_ms, stage_timings)
            logger.info("Job %s completed successfully trong %.1fs %s",
                        job_id, duration_ms / 1000, stage_timings)

            return JobResult(JOB_OK)

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
            # Ghi cả vào sự kiện hệ thống: đây là từ chối CÓ CHỦ ĐÍCH nên mức 'warning', không phải lỗi
            self._log_event("route_denied", "warning",
                            f"Từ chối xử lý '{filename}' theo ràng buộc độ nhạy cảm", str(e), job_id)
            self._save_timing(job_id, int((time.perf_counter() - t_start) * 1000), stage_timings)
            self.redis.hset(f"job:{job_id}", mapping={
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })

            # Ràng buộc cứng bị vi phạm là lỗi CẤU HÌNH/TÀI LIỆU, không phải sự cố tạm thời:
            # thử lại sẽ bị từ chối y như vậy. Vào hàng đợi chết ngay để người phụ trách sửa lược đồ.
            return JobResult(JOB_FAILED_DOCUMENT, error_msg)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Job {job_id} failed: {e}")
            logger.error(traceback.format_exc())

            self._update_status(job_id, "failed", 0, filename, error_message=error_msg)
            audit.log_action(
                action=audit.ACTION_PROCESS, document_id=job_id, actor="worker",
                detail={"status": "failed", "error": error_msg},
            )
            self._log_event("job_failed", "error", f"Xử lý '{filename}' thất bại: {error_msg}",
                            traceback.format_exc(), job_id)
            # Vẫn lưu thời gian: biết job thất bại sau bao lâu giúp phân biệt lỗi tức thời với treo lâu
            self._save_timing(job_id, int((time.perf_counter() - t_start) * 1000), stage_timings)

            self.redis.hset(f"job:{job_id}", mapping={
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })

            kind = _classify_failure(e)
            if kind == JOB_FAILED_INFRA:
                logger.warning("Job %s thất bại vì LỖI HẠ TẦNG (%s) — sẽ thử lại",
                               job_id, type(e).__name__)
            return JobResult(kind, error_msg)

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