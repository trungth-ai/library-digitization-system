#!/usr/bin/env python3
"""
Hàng đợi tin cậy — không mất job khi worker chết (ADR-011, sửa lỗi N-02).

LỖI ĐANG SỬA: `worker.py` dùng `redis.blpop`, lệnh này lấy job **ra khỏi** hàng đợi rồi job chỉ tồn
tại trong bộ nhớ tiến trình worker suốt thời gian xử lý — với OCR hai pha, đó là vài phút cho một tài
liệu vài trăm trang. Trong cửa sổ đó nếu worker bị kill/OOM/restart thì **job biến mất im lặng**:
không có trong hàng đợi, không worker nào xử lý, tài liệu treo mãi ở "Chờ xử lý".

CÁCH SỬA: `BLMOVE` chuyển job **nguyên tử** sang danh sách đang-xử-lý riêng của từng worker. Job
LUÔN nằm ở đúng một chỗ — hàng đợi hoặc danh sách đang-xử-lý — không bao giờ chỉ nằm trong RAM.

Module này KHÔNG import `redis`: client được truyền vào (duck typing), nên kiểm thử được trên máy
không cài redis — cùng lý do với `_redis_exception_classes()` ở `worker.py` (ADR-009).

Sơ đồ khóa (mức `normal` DÙNG LẠI chính khóa đang chạy hôm nay → tương thích ngược do cấu trúc):

    {base}:high   ┐
    {base}        ├── BLMOVE ──► worker:processing:{worker_id} ──► xử lý
    {base}:low    ┘                        │
                                           ├─ xong    → LREM (xóa khỏi processing)
    {base}:delayed  (ZSET, score = hạn)    ├─ lỗi HT  → attempts+1 → delayed → về hàng đợi
    {base}:dead     (LIST, có lý do)       └─ hết lượt/lỗi tài liệu → dead
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("core.queue")

# Ba mức ưu tiên. `normal` KHÔNG có hậu tố: nó là chính khóa `digitization_jobs` đang dùng, nên mọi
# thứ đang đẩy vào khóa cũ vẫn chạy đúng và được coi là mức normal (ADR-011 mục 2).
PRIORITY_HIGH = "high"
PRIORITY_NORMAL = "normal"
PRIORITY_LOW = "low"
PRIORITIES = (PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW)

PROCESSING_PREFIX = "worker:processing:"
# Phải khớp `WORKER_HEARTBEAT_PREFIX` của worker.py — nhịp tim là căn cứ duy nhất để biết worker còn sống
HEARTBEAT_PREFIX = "worker:heartbeat:"

# Lý do đưa job vào hàng đợi chết — dùng làm hằng để nhất quán khi hiển thị lên giao diện
REASON_MAX_ATTEMPTS = "max_attempts"
REASON_DOCUMENT_ERROR = "document_error"


@dataclass
class ClaimedJob:
    """Một job đã được nhận. `raw` là chuỗi JSON gốc — cần đúng nguyên văn để `LREM` khớp."""
    raw: str
    data: Dict[str, Any]
    priority: str

    @property
    def job_id(self) -> str:
        return self.data.get("job_id", "unknown")

    @property
    def attempts(self) -> int:
        """Số lần ĐÃ thử trước lần này (0 = lần đầu). Lưu trong payload để không cần bảng phụ."""
        return int(self.data.get("_attempts", 0))


@dataclass
class QueueDepth:
    """Độ sâu từng hàng đợi. Dùng cho `/api/v2/stats`, kiểm soát tải, và biểu đồ xu hướng."""
    high: int = 0
    normal: int = 0
    low: int = 0
    delayed: int = 0
    dead: int = 0
    processing: int = 0

    @property
    def ready(self) -> int:
        """Số job đang chờ được nhận NGAY (không tính delayed/dead/processing)."""
        return self.high + self.normal + self.low

    def as_dict(self) -> Dict[str, int]:
        return {
            "high": self.high, "normal": self.normal, "low": self.low,
            "delayed": self.delayed, "dead": self.dead,
            "processing": self.processing, "ready": self.ready,
        }


# ─────────────────────────────────────────────────────────────
# TÊN KHÓA
# ─────────────────────────────────────────────────────────────

def queue_key(base: str, priority: str = PRIORITY_NORMAL) -> str:
    """Khóa hàng đợi theo mức ưu tiên. `normal` trả về chính `base` (tương thích ngược)."""
    if priority == PRIORITY_NORMAL:
        return base
    if priority not in PRIORITIES:
        raise ValueError(f"Mức ưu tiên không hợp lệ: {priority!r} (hợp lệ: {', '.join(PRIORITIES)})")
    return f"{base}:{priority}"


def delayed_key(base: str) -> str:
    return f"{base}:delayed"


def dead_key(base: str) -> str:
    return f"{base}:dead"


def processing_key(worker_id: str) -> str:
    return f"{PROCESSING_PREFIX}{worker_id}"


def _priority_from_key(base: str, key: str) -> str:
    """Suy ra mức ưu tiên từ tên khóa — để biết job vừa nhận thuộc hàng đợi nào mà trả về đúng chỗ."""
    for priority in (PRIORITY_HIGH, PRIORITY_LOW):
        if key == f"{base}:{priority}":
            return priority
    return PRIORITY_NORMAL


# ─────────────────────────────────────────────────────────────
# ĐẨY VÀO
# ─────────────────────────────────────────────────────────────

def push(redis_client: Any, base: str, payload: Dict[str, Any],
         priority: str = PRIORITY_NORMAL) -> str:
    """
    Đẩy một job vào hàng đợi. Trả về chuỗi JSON đã đẩy.

    `LPUSH` (thêm bên trái) + nhận từ bên phải = FIFO đúng thứ tự tải lên.

    Mức ưu tiên được ghi VÀO payload (`_priority`), không chỉ nằm ở tên khóa. Lý do: khi job đã được
    chuyển sang danh sách đang-xử-lý thì tên khóa hàng đợi gốc không còn ở đâu cả — nếu không ghi vào
    payload thì lúc thu hồi việc mồ côi hay lúc thử lại, job `high` sẽ bị trả về hàng đợi `normal`.
    (Đúng lỗi mà `test_thu_hoi_giu_dung_muc_uu_tien` bắt được.)
    """
    key = queue_key(base, priority)          # kiểm tra mức ưu tiên hợp lệ trước khi ghi
    data = dict(payload)
    data["_priority"] = priority
    raw = json.dumps(data, ensure_ascii=False)
    redis_client.lpush(key, raw)
    return raw


# ─────────────────────────────────────────────────────────────
# NHẬN VIỆC
# ─────────────────────────────────────────────────────────────

def claim(redis_client: Any, base: str, worker_id: str,
          timeout: int = 5) -> Optional[ClaimedJob]:
    """
    Nhận một job, chuyển NGUYÊN TỬ sang danh sách đang-xử-lý của worker này.

    Chiến lược (ADR-011 mục 3): thăm dò `high` → `normal` → `low` không chặn; cả ba rỗng thì CHẶN
    trên khóa normal với `timeout`. Đánh đổi được ghi nhận rõ: job `high` đến trong lúc đang chặn có
    thể chờ tối đa `timeout` giây — **chỉ khi hệ thống đang rỗi**. Redis không có `BLMOVE` nhiều khóa,
    và thăm dò liên tục thì làm nóng Redis vô ích.

    Trả `None` khi hết giờ chờ mà không có việc — chuyện BÌNH THƯỜNG, không phải lỗi (ADR-009).
    """
    dst = processing_key(worker_id)

    # Thăm dò không chặn theo đúng thứ tự ưu tiên
    for priority in PRIORITIES:
        src = queue_key(base, priority)
        raw = redis_client.lmove(src, dst, "RIGHT", "LEFT")
        if raw:
            return _parse_claimed(raw, priority, redis_client, dst)

    # Cả ba rỗng → chặn trên mức normal để không quay vòng nóng
    src = queue_key(base, PRIORITY_NORMAL)
    raw = redis_client.blmove(src, dst, timeout, "RIGHT", "LEFT")
    if not raw:
        return None
    return _parse_claimed(raw, PRIORITY_NORMAL, redis_client, dst)


def _parse_claimed(raw: str, priority: str, redis_client: Any,
                   dst: str) -> Optional[ClaimedJob]:
    """
    Giải mã payload đã nhận. JSON hỏng thì BỎ khỏi danh sách đang-xử-lý và bỏ qua.

    Nếu không xử lý riêng: một bản ghi rác sẽ nằm mãi trong danh sách đang-xử-lý, và bộ thu hồi sẽ
    trả nó về hàng đợi vô hạn — một job rác làm tắc cả hàng đợi.
    """
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("payload không phải object JSON")
    except Exception as e:  # noqa: BLE001
        logger.error("Payload hàng đợi không đọc được, bỏ qua: %s — %.200s", e, raw)
        try:
            redis_client.lrem(dst, 1, raw)
        except Exception:  # noqa: BLE001
            pass
        return None

    return ClaimedJob(raw=raw, data=data, priority=priority)


def ack(redis_client: Any, worker_id: str, job: ClaimedJob) -> bool:
    """
    Báo đã xử lý xong: xóa khỏi danh sách đang-xử-lý.

    Chỉ gọi SAU KHI job thực sự hoàn tất (kể cả hoàn tất ở trạng thái thất bại đã ghi vào DB). Gọi
    sớm là mở lại đúng cửa sổ mất job mà ADR-011 đang đóng.
    """
    removed = redis_client.lrem(processing_key(worker_id), 1, job.raw)
    return bool(removed)


# ─────────────────────────────────────────────────────────────
# THẤT BẠI: THỬ LẠI HAY BỎ VÀO HÀNG ĐỢI CHẾT
# ─────────────────────────────────────────────────────────────

def fail(redis_client: Any, base: str, worker_id: str, job: ClaimedJob,
         reason: str, retryable: bool = True, max_attempts: int = 3,
         backoff_sec: int = 30, now: Optional[float] = None) -> Tuple[str, int]:
    """
    Xử lý job thất bại. Trả về `(hành_động, số_lần_đã_thử)` với hành động là `retry` hoặc `dead`.

    Phân biệt hai loại lỗi (ADR-011 mục 6):
      - `retryable=True`  — lỗi HẠ TẦNG (mất Redis/PostgreSQL/công cụ mô hình) → thử lại có khoảng lùi.
      - `retryable=False` — lỗi TÀI LIỆU (PDF hỏng, tệp không tồn tại, vi phạm độ nhạy cảm) → vào
        hàng đợi chết NGAY. Thử lại một tài liệu hỏng chỉ tốn thời gian và làm nhiễu nhật ký.

    Khoảng lùi dùng ZSET `delayed`, **không** cho worker ngủ: worker ngủ để chờ thử lại là biến một
    job lỗi thành một worker bị chiếm dụng.
    """
    now = time.time() if now is None else now
    attempts = job.attempts + 1

    # Luôn bỏ khỏi danh sách đang-xử-lý trước, để bộ thu hồi không nhặt lại bản cũ
    redis_client.lrem(processing_key(worker_id), 1, job.raw)

    if not retryable or attempts >= max_attempts:
        payload = dict(job.data)
        payload["_attempts"] = attempts
        payload["_dead_reason"] = REASON_DOCUMENT_ERROR if not retryable else REASON_MAX_ATTEMPTS
        payload["_error"] = reason
        payload["_dead_at"] = now
        payload["_priority"] = job.priority
        redis_client.lpush(dead_key(base), json.dumps(payload, ensure_ascii=False))
        logger.error("Job %s vào hàng đợi chết sau %d lần thử: %s", job.job_id, attempts, reason)
        return "dead", attempts

    payload = dict(job.data)
    payload["_attempts"] = attempts
    payload["_last_error"] = reason
    payload["_priority"] = job.priority
    # Khoảng lùi tăng dần: 30s, 60s, 120s... — lỗi hạ tầng thường cần thời gian để tự khỏi
    due_at = now + backoff_sec * (2 ** (attempts - 1))
    redis_client.zadd(delayed_key(base), {json.dumps(payload, ensure_ascii=False): due_at})
    logger.warning("Job %s sẽ thử lại lần %d sau %.0fs: %s",
                   job.job_id, attempts, due_at - now, reason)
    return "retry", attempts


def promote_delayed(redis_client: Any, base: str, now: Optional[float] = None,
                    limit: int = 100) -> int:
    """
    Chuyển các job đã đến hạn từ ZSET `delayed` về hàng đợi. Trả về số job đã chuyển.

    Gọi định kỳ (mỗi vòng lặp worker là đủ — rẻ: một lệnh `ZRANGEBYSCORE` có `LIMIT`).
    """
    now = time.time() if now is None else now
    zkey = delayed_key(base)

    due = redis_client.zrangebyscore(zkey, "-inf", now, start=0, num=limit)
    if not due:
        return 0

    moved = 0
    for raw in due:
        # Chỉ đẩy về hàng đợi khi ĐÃ xóa được khỏi ZSET: nếu một tiến trình khác xóa trước thì
        # `zrem` trả 0 và ta bỏ qua — tránh hai worker cùng đẩy một job về hàng đợi.
        if not redis_client.zrem(zkey, raw):
            continue
        try:
            priority = json.loads(raw).get("_priority", PRIORITY_NORMAL)
        except Exception:  # noqa: BLE001
            priority = PRIORITY_NORMAL
        # RPUSH (bên phải) = được nhận NGAY lượt sau, vì claim lấy từ bên phải. Job đã chờ hết
        # khoảng lùi thì không nên xếp lại cuối hàng.
        redis_client.rpush(queue_key(base, priority), raw)
        moved += 1

    if moved:
        logger.info("Đã chuyển %d job đến hạn thử lại về hàng đợi", moved)
    return moved


# ─────────────────────────────────────────────────────────────
# THU HỒI VIỆC MỒ CÔI
# ─────────────────────────────────────────────────────────────

def reclaim_orphans(redis_client: Any, base: str,
                    heartbeat_prefix: str = HEARTBEAT_PREFIX) -> List[Tuple[str, int]]:
    """
    Trả về hàng đợi những job của worker ĐÃ CHẾT. Trả về danh sách `(worker_id, số_job_thu_hồi)`.

    Căn cứ duy nhất để kết luận worker đã chết là **khóa nhịp tim biến mất** (TTL 60s, ADR-009). Đây
    là lý do phần khó của ADR-011 đã làm xong từ trước: cơ chế biết-worker-nào-còn-sống đã có sẵn.

    An toàn với worker đang chạy job dài: worker còn sống thì còn ghi nhịp tim mỗi vòng lặp, nên
    không bị thu hồi dù job mất 20 phút. Điều kiện để việc này không gây xử lý trùng là job phải
    **idempotent** — đã thỏa mãn: `save_metadata` dùng `ON CONFLICT DO NOTHING`, `_update_status` là
    ghi đè trạng thái.
    """
    reclaimed: List[Tuple[str, int]] = []

    for key in redis_client.scan_iter(f"{PROCESSING_PREFIX}*", count=100):
        worker_id = key[len(PROCESSING_PREFIX):]
        if redis_client.exists(f"{heartbeat_prefix}{worker_id}"):
            continue                      # worker còn sống — để nguyên

        count = 0
        while True:
            # Lấy từ bên trái (job cũ nhất trong processing), đẩy sang bên phải hàng đợi để được
            # nhận ngay lượt sau — job này đã mất một lượt xử lý, không nên xếp lại cuối hàng.
            raw = redis_client.lpop(key)
            if raw is None:
                break
            try:
                priority = json.loads(raw).get("_priority", PRIORITY_NORMAL)
            except Exception:  # noqa: BLE001
                priority = PRIORITY_NORMAL
            redis_client.rpush(queue_key(base, priority), raw)
            count += 1

        if count:
            logger.warning("Thu hồi %d job từ worker đã chết '%s' — trả về hàng đợi", count, worker_id)
            reclaimed.append((worker_id, count))

    return reclaimed


# ─────────────────────────────────────────────────────────────
# QUAN SÁT & HÀNG ĐỢI CHẾT
# ─────────────────────────────────────────────────────────────

def depth(redis_client: Any, base: str) -> QueueDepth:
    """Đếm độ sâu mọi hàng đợi, gồm cả tổng số job đang được xử lý trên các worker."""
    result = QueueDepth(
        high=redis_client.llen(queue_key(base, PRIORITY_HIGH)),
        normal=redis_client.llen(queue_key(base, PRIORITY_NORMAL)),
        low=redis_client.llen(queue_key(base, PRIORITY_LOW)),
        delayed=redis_client.zcard(delayed_key(base)),
        dead=redis_client.llen(dead_key(base)),
    )
    for key in redis_client.scan_iter(f"{PROCESSING_PREFIX}*", count=100):
        result.processing += redis_client.llen(key)
    return result


def list_dead(redis_client: Any, base: str, limit: int = 100,
              offset: int = 0) -> List[Dict[str, Any]]:
    """Liệt kê hàng đợi chết để hiển thị lên giao diện kèm LÝ DO đọc được."""
    rows = redis_client.lrange(dead_key(base), offset, offset + limit - 1)
    out: List[Dict[str, Any]] = []
    for raw in rows:
        try:
            out.append(json.loads(raw))
        except Exception:  # noqa: BLE001
            out.append({"job_id": None, "_error": "payload không đọc được", "_raw": raw[:200]})
    return out


def retry_dead(redis_client: Any, base: str, job_id: str) -> bool:
    """
    Đưa một job từ hàng đợi chết về hàng đợi, đặt lại số lần thử.

    GIỮ NGUYÊN `job_id` (KT-BU-22): tài liệu đã có bản ghi trong `documents`, tạo id mới sẽ sinh ra
    bản ghi trùng và làm mất lịch sử kiểm toán của lần xử lý trước.
    """
    dkey = dead_key(base)
    for raw in redis_client.lrange(dkey, 0, -1):
        try:
            data = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        if data.get("job_id") != job_id:
            continue

        if not redis_client.lrem(dkey, 1, raw):
            return False                  # ai đó vừa xử lý trước — không đẩy trùng

        priority = data.pop("_priority", PRIORITY_NORMAL)
        for meta in ("_attempts", "_dead_reason", "_error", "_dead_at", "_last_error"):
            data.pop(meta, None)
        push(redis_client, base, data, priority)
        logger.info("Chạy lại job %s từ hàng đợi chết", job_id)
        return True

    return False


def retry_all_dead(redis_client: Any, base: str, limit: int = 500) -> int:
    """Chạy lại toàn bộ hàng đợi chết. Trả về số job đã đưa về hàng đợi."""
    count = 0
    for _ in range(limit):
        raw = redis_client.rpop(dead_key(base))     # cũ nhất trước
        if raw is None:
            break
        try:
            data = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        priority = data.pop("_priority", PRIORITY_NORMAL)
        for meta in ("_attempts", "_dead_reason", "_error", "_dead_at", "_last_error"):
            data.pop(meta, None)
        push(redis_client, base, data, priority)
        count += 1
    return count
