#!/usr/bin/env python3
"""
Kiểm thử phần worker của hàng đợi tin cậy (ADR-011) — KT-BU-16, KT-BU-19, KT-BU-20.

Hai nhóm:
1. `_classify_failure` — quyết định thử lại hay không. Phân loại sai ở đây là hoặc mất cơ hội tự khỏi
   sau sự cố hạ tầng, hoặc tốn 3 lượt OCR cho một tài liệu hỏng.
2. `_handle_claimed` — ghép `process_job` với hàng đợi: ack khi xong, thử lại/bỏ vào hàng đợi chết khi lỗi.

Không cần redis/PostgreSQL: worker nhận `redis_client` giả và `init_db=False` (đã có sẵn từ ADR-008).
"""

import pytest

from scripts.core import queue as q
from scripts.core.exceptions import SensitivityViolation
from scripts.worker import (
    JOB_FAILED_DOCUMENT,
    JOB_FAILED_INFRA,
    JOB_OK,
    DigitizationWorker,
    JobResult,
    _classify_failure,
)
from tests.test_queue_reliable import FakeRedis

BASE = "digitization_jobs"


# ─────────────────────────────────────────────────────────────
# PHÂN LOẠI LỖI
# ─────────────────────────────────────────────────────────────

# Giả lập ngoại lệ của psycopg2/redis mà KHÔNG cần cài hai gói đó — phân loại theo tên lớp nên
# lớp giả cùng tên là đủ để kiểm chứng đúng đường đi của mã production.
class OperationalError(Exception):
    """Giống psycopg2.OperationalError."""


class InterfaceError(Exception):
    """Giống psycopg2.InterfaceError."""


class RedisConnectionErrorFake(ConnectionError):
    """redis.exceptions.ConnectionError kế thừa từ ConnectionError của Python."""


@pytest.mark.parametrize("exc", [
    OperationalError("server closed the connection unexpectedly"),
    InterfaceError("connection already closed"),
    ConnectionError("Redis không nối được"),
    RedisConnectionErrorFake("mất kết nối"),
    TimeoutError("hết giờ đọc socket"),
    BrokenPipeError("đường ống đứt"),
    OSError(28, "No space left on device"),
])
def test_loi_ha_tang_thi_thu_lai(exc):
    """Những lỗi này thường TỰ KHỎI sau vài chục giây → phải thử lại, không được bỏ tài liệu."""
    assert _classify_failure(exc) == JOB_FAILED_INFRA


@pytest.mark.parametrize("exc", [
    FileNotFoundError("/data/jobs/x/input/a.pdf"),
    PermissionError("không đọc được tệp"),
    IsADirectoryError("là thư mục"),
    ValueError("PDF hỏng: không đọc được trang 1"),
    RuntimeError("Processing failed"),
    SensitivityViolation("tài liệu nhạy cảm không được ra đám mây"),
])
def test_loi_tai_lieu_thi_khong_thu_lai(exc):
    """Thử lại những lỗi này chỉ tốn thời gian: lần sau cũng hỏng y như vậy."""
    assert _classify_failure(exc) == JOB_FAILED_DOCUMENT


def test_file_not_found_khong_bi_coi_la_loi_ha_tang():
    """
    Chốt riêng một ca dễ sai: `FileNotFoundError` LÀ con của `OSError`, mà `OSError` nằm trong danh
    sách lỗi hạ tầng. Thứ tự kiểm tra trong `_classify_failure` phải loại nó ra TRƯỚC.
    """
    assert issubclass(FileNotFoundError, OSError)
    assert _classify_failure(FileNotFoundError("thiếu tệp")) == JOB_FAILED_DOCUMENT


# ─────────────────────────────────────────────────────────────
# GHÉP VỚI HÀNG ĐỢI
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def worker(monkeypatch):
    """Worker dùng Redis giả, không nối DB, không khởi tạo lớp provider."""
    monkeypatch.setenv("USE_PROVIDER_LAYER", "0")
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    w = DigitizationWorker(redis_client=FakeRedis(), init_db=False)
    w.worker_id = "w-test"
    # Không ghi DB/audit trong test: chỉ ghi lại lời gọi để kiểm chứng
    w.trang_thai = []
    w.su_kien = []
    w._update_status = lambda *a, **k: w.trang_thai.append((a, k))
    w._log_event = lambda *a, **k: w.su_kien.append((a, k))
    return w


def test_xong_thi_ack(worker):
    """Job xong → bỏ khỏi danh sách đang-xử-lý. Đây là điều kiện để không xử lý lại lần nữa."""
    q.push(worker.redis, BASE, {"job_id": "j1", "filename": "a.pdf"})
    claimed = q.claim(worker.redis, BASE, worker.worker_id)
    worker.process_job = lambda data: JobResult(JOB_OK)

    worker._handle_claimed(claimed)

    assert worker.redis.llen(q.processing_key(worker.worker_id)) == 0
    assert worker.redis.llen(BASE) == 0


def test_chua_xong_thi_khong_ack(worker):
    """
    Job thất bại KHÔNG được ack lặng lẽ — phải đi vào nhánh thử lại hoặc hàng đợi chết.

    Ack sớm là mở lại đúng cửa sổ mất job mà ADR-011 đóng.
    """
    q.push(worker.redis, BASE, {"job_id": "j1", "filename": "a.pdf"})
    claimed = q.claim(worker.redis, BASE, worker.worker_id)
    worker.process_job = lambda data: JobResult(JOB_FAILED_INFRA, "PostgreSQL down")

    worker._handle_claimed(claimed)

    assert worker.redis.llen(q.processing_key(worker.worker_id)) == 0   # đã rời processing
    assert worker.redis.zcard(q.delayed_key(BASE)) == 1                 # nhưng nằm ở chỗ thử lại


def test_loi_ha_tang_tra_tai_lieu_ve_cho_xu_ly(worker):
    """
    Khi sẽ thử lại, tài liệu phải quay về "Chờ xử lý" kèm lý do — không để nguyên "Thất bại".

    Người dùng cần phân biệt "đang được thử lại" với "đã bỏ".
    """
    q.push(worker.redis, BASE, {"job_id": "j1", "filename": "a.pdf"})
    claimed = q.claim(worker.redis, BASE, worker.worker_id)
    worker.process_job = lambda data: JobResult(JOB_FAILED_INFRA, "mất kết nối PostgreSQL")

    worker._handle_claimed(claimed)

    assert worker.trang_thai, "phải cập nhật lại trạng thái tài liệu"
    args, kwargs = worker.trang_thai[-1]
    assert args[1] == "queued"
    assert "Thử lại" in kwargs["error_message"]
    assert "PostgreSQL" in kwargs["error_message"]


def test_loi_tai_lieu_ghi_su_kien_he_thong(worker):
    """Job vào hàng đợi chết phải để lại dấu vết tra được, không chỉ nằm im trong Redis."""
    q.push(worker.redis, BASE, {"job_id": "j1", "filename": "a.pdf"})
    claimed = q.claim(worker.redis, BASE, worker.worker_id)
    worker.process_job = lambda data: JobResult(JOB_FAILED_DOCUMENT, "PDF hỏng")

    worker._handle_claimed(claimed)

    assert worker.redis.llen(q.dead_key(BASE)) == 1
    kinds = [a[0] for a, _ in worker.su_kien]
    assert "job_dead" in kinds


def test_maintenance_thu_hoi_va_ghi_su_kien(worker):
    """
    KT-BU-16: bộ thu hồi phải trả job của worker đã chết về hàng đợi VÀ ghi sự kiện.

    Sự kiện này quan trọng: nó là dấu hiệu duy nhất cho biết một worker đã chết giữa lúc làm việc.
    """
    q.push(worker.redis, BASE, {"job_id": "mo-coi", "filename": "a.pdf"})
    worker.redis.setex(q.HEARTBEAT_PREFIX + "w-chet", 60, "alive")
    q.claim(worker.redis, BASE, "w-chet")
    worker.redis.delete(q.HEARTBEAT_PREFIX + "w-chet")

    worker._last_reclaim = 0.0            # buộc quét ngay
    worker._maintenance()

    assert worker.redis.llen(BASE) == 1
    kinds = [a[0] for a, _ in worker.su_kien]
    assert "job_reclaimed" in kinds


def test_maintenance_gian_theo_chu_ky(worker, monkeypatch):
    """Không quét thu hồi mỗi vòng lặp (5s): `scan_iter` rẻ nhưng không miễn phí."""
    import time as _time
    worker._last_reclaim = _time.time()   # vừa quét xong

    q.push(worker.redis, BASE, {"job_id": "mo-coi"})
    worker.redis.setex(q.HEARTBEAT_PREFIX + "w-chet", 60, "alive")
    q.claim(worker.redis, BASE, "w-chet")
    worker.redis.delete(q.HEARTBEAT_PREFIX + "w-chet")

    worker._maintenance()

    assert worker.redis.llen(BASE) == 0, "chưa tới chu kỳ thì không được quét"


def test_van_lui_ve_duong_blpop_cu(monkeypatch):
    """
    Van lùi `QUEUE_MODE=blpop` phải chạy ĐÚNG vòng lặp cũ (ADR-011 mục 7).

    Kiểm bằng cách đếm: đường cũ gọi `blpop`, đường mới gọi `blmove`. Nếu van lùi không thật thì
    lúc có sự cố sẽ không có gì để lùi về.
    """
    import scripts.worker as w

    class _Dem:
        def __init__(self):
            self.blpop_calls = 0
            self.blmove_calls = 0

        def blpop(self, key, timeout=0):
            self.blpop_calls += 1
            raise KeyboardInterrupt()          # thoát vòng lặp: `except Exception` không bắt được

        def blmove(self, *a, **k):
            self.blmove_calls += 1
            raise KeyboardInterrupt()

        def lmove(self, *a, **k):
            return None

        def setex(self, *a, **k):
            pass

        def zrangebyscore(self, *a, **k):
            return []

        def scan_iter(self, *a, **k):
            return []

    monkeypatch.setattr(w.db, "close_pool", lambda: None)
    monkeypatch.setenv("USE_PROVIDER_LAYER", "0")

    dem = _Dem()
    inst = w.DigitizationWorker(redis_client=dem, init_db=False)
    inst.reliable_queue = False
    with pytest.raises(KeyboardInterrupt):
        inst.run()

    assert dem.blpop_calls == 1
    assert dem.blmove_calls == 0


def test_che_do_mac_dinh_la_hang_doi_tin_cay():
    """
    Mặc định PHẢI là hàng đợi tin cậy.

    Nếu ai đó đổi mặc định về `blpop` thì lỗi mất dữ liệu N-02 quay lại im lặng — test này chặn việc đó.
    """
    import scripts.worker as w

    assert w.RELIABLE_QUEUE is True, "mặc định phải là hàng đợi tin cậy (QUEUE_MODE=reliable)"


def test_maintenance_khong_gay_loi_khi_redis_hong(worker):
    """Việc nền hỏng KHÔNG được làm dừng việc xử lý tài liệu (cùng nguyên tắc với audit)."""
    class RedisHong:
        def zrangebyscore(self, *a, **k):
            raise ConnectionError("Redis chết")

        def scan_iter(self, *a, **k):
            raise ConnectionError("Redis chết")

    worker.redis = RedisHong()
    worker._last_reclaim = 0.0

    worker._maintenance()        # không được ném ngoại lệ ra ngoài
