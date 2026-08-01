#!/usr/bin/env python3
"""
Kiểm thử vòng lặp worker: phân loại lỗi Redis + theo dõi vận hành.

BỐI CẢNH: trên máy chủ, log worker ngập traceback
`redis.exceptions.TimeoutError: Timeout reading from socket`. Đó KHÔNG phải lỗi — `BLPOP` hết giờ chờ
khi hàng đợi rỗng là chuyện bình thường, nhưng redis-py áp thời hạn đọc socket theo chính `timeout`
của lệnh nên phản hồi về chậm một nhịp là ném TimeoutError. Nhánh đó rơi vào `except Exception`
chung → ghi cả traceback rồi ngủ 2 giây MỖI VÒNG, vừa ngập log vừa làm nhận job chậm.

Chạy: pytest tests/test_worker_monitoring.py -v
"""

import logging
import pytest


class _FakeTimeout(Exception):
    """Đóng vai redis.exceptions.TimeoutError (máy dev không cài redis)."""


class _FakeConnError(Exception):
    """Đóng vai redis.exceptions.ConnectionError."""


class _StopLoop(BaseException):
    """Thoát vòng lặp vô hạn của worker. Là BaseException nên `except Exception` KHÔNG bắt được."""


class _ScriptedRedis:
    """
    Redis giả diễn theo kịch bản: mỗi lượt lấy việc làm một việc đã định trước.

    Hỗ trợ CẢ HAI chế độ hàng đợi để cùng một kịch bản kiểm chứng được cả đường cũ (`blpop`) và
    đường tin cậy mặc định (`blmove`, ADR-011). Nếu chỉ hỗ trợ `blpop` thì các bảo đảm của ADR-009
    (hết giờ chờ không phải lỗi, ghi nhận mất kết nối, nhịp tim) sẽ không còn được kiểm trên đường
    đang chạy thật — mất độ phủ ở đúng chỗ quan trọng.
    """

    def __init__(self, script):
        self.script = list(script)
        self.hashes = {}
        self.calls = 0
        self.lists = {}

    def _next_action(self):
        self.calls += 1
        if not self.script:
            raise _StopLoop()
        action = self.script.pop(0)
        if isinstance(action, BaseException):
            raise action
        return action           # None = hàng đợi rỗng; tuple = có việc

    def blpop(self, key, timeout=0):
        return self._next_action()

    # ── Hàng đợi tin cậy (ADR-011) ──────────────────────────────
    def lmove(self, src, dst, from_side, to_side):
        """Thăm dò không chặn: luôn rỗng, để kịch bản được điều khiển qua `blmove`."""
        return None

    def blmove(self, src, dst, timeout, from_side, to_side):
        action = self._next_action()
        if action is None:
            return None
        # Kịch bản dùng dạng tuple của blpop `(key, raw)`; blmove trả về chính chuỗi raw
        raw = action[1] if isinstance(action, tuple) else action
        self.lists.setdefault(dst, []).insert(0, raw)
        return raw

    def lrem(self, key, count, value):
        items = self.lists.get(key) or []
        if value in items:
            items.remove(value)
            return 1
        return 0

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def llen(self, key):
        return len(self.lists.get(key) or [])

    def lpop(self, key):
        items = self.lists.get(key) or []
        return items.pop(0) if items else None

    def zadd(self, key, mapping):
        self.hashes.setdefault("_delayed", {}).update(mapping)

    def zrangebyscore(self, key, mini, maxi, start=0, num=None):
        return []

    def zrem(self, key, member):
        return 0

    def zcard(self, key):
        return len(self.hashes.get("_delayed") or {})

    def exists(self, key):
        return 1

    def scan_iter(self, match, count=None):
        return []

    def hset(self, name, mapping=None, **kw):
        self.hashes.setdefault(name, {}).update(mapping or {})

    def setex(self, key, ttl, value):
        self.hashes.setdefault("_heartbeat", {})[key] = (ttl, value)

    def publish(self, ch, msg):
        pass


@pytest.fixture
def worker(monkeypatch):
    """Worker với Redis giả, không DB, và mọi lời gọi DB/sleep được ghi lại."""
    import scripts.worker as w

    monkeypatch.setattr(w, "_redis_exception_classes", lambda: (_FakeTimeout, _FakeConnError))

    events, sleeps = [], []
    monkeypatch.setattr(w.db, "log_system_event",
                        lambda **kw: events.append(kw))
    monkeypatch.setattr(w.db, "resolve_system_events", lambda kind, instance=None: 0)
    monkeypatch.setattr(w.db, "close_pool", lambda: None)
    monkeypatch.setattr(w.time, "sleep", lambda s: sleeps.append(s))

    inst = w.DigitizationWorker(redis_client=_ScriptedRedis([]), init_db=False)
    inst._test_events, inst._test_sleeps = events, sleeps
    return inst


def _run(worker, script):
    worker.redis.script = list(script)
    with pytest.raises(_StopLoop):
        worker.run()


# =====================================================================
# 1. BLPOP hết giờ chờ KHÔNG phải lỗi (đúng lỗi trên máy chủ)
# =====================================================================

def test_blpop_het_gio_khong_bi_coi_la_loi(worker, caplog):
    """Ba lượt hết giờ liên tiếp: không ERROR nào, không ngủ 2s, không ghi sự kiện."""
    with caplog.at_level(logging.DEBUG):
        _run(worker, [_FakeTimeout("Timeout reading from socket")] * 3)

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors == [], f"hết giờ chờ bị coi là lỗi: {[r.message for r in errors]}"
    assert worker._test_sleeps == [], "không được ngủ sau mỗi lượt hết giờ (làm nhận job chậm)"
    assert worker._test_events == [], "không được ghi sự kiện hệ thống cho việc bình thường"


def test_hang_doi_rong_tra_None_cung_khong_sao(worker, caplog):
    with caplog.at_level(logging.DEBUG):
        _run(worker, [None, None])
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_van_nhan_duoc_viec_sau_khi_het_gio(worker, monkeypatch):
    """Quan trọng nhất: hết giờ chờ xong thì lượt sau vẫn phải lấy được job."""
    import json
    processed = []
    monkeypatch.setattr(type(worker), "process_job", lambda self, data: processed.append(data))

    job = ("digitization_jobs", json.dumps({"job_id": "j-1", "filename": "a.pdf"}))
    _run(worker, [_FakeTimeout(), None, job, _FakeTimeout()])

    assert len(processed) == 1 and processed[0]["job_id"] == "j-1"


# =====================================================================
# 2. Mất kết nối Redis THẬT thì phải ghi nhận
# =====================================================================

def test_mat_ket_noi_redis_duoc_ghi_nhan(worker):
    _run(worker, [_FakeConnError("Connection refused")])

    kinds = [e["kind"] for e in worker._test_events]
    assert "redis_down" in kinds
    down = next(e for e in worker._test_events if e["kind"] == "redis_down")
    assert down["level"] == "error"
    assert "Connection refused" in down["message"]
    assert worker._test_sleeps == [2], "mất kết nối thì nên chờ chút rồi thử lại"


def test_chi_ghi_MOT_lan_du_mat_ket_noi_nhieu_vong(worker):
    """Ghi mỗi vòng sẽ ngập bảng sự kiện (mỗi 5 giây một dòng)."""
    _run(worker, [_FakeConnError("refused")] * 5)
    downs = [e for e in worker._test_events if e["kind"] == "redis_down"]
    assert len(downs) == 1, f"ghi {len(downs)} lần, đáng ra chỉ 1 lần khi trạng thái ĐỔI"


def test_noi_lai_duoc_thi_ghi_redis_up(worker):
    """Mất rồi nối lại: phải có cả hai mốc để biết gián đoạn từ lúc nào đến lúc nào."""
    _run(worker, [_FakeConnError("refused"), None, None])
    kinds = [e["kind"] for e in worker._test_events]
    assert kinds == ["redis_down", "redis_up"], str(kinds)


def test_loi_khac_van_ghi_nhat_ky_va_khong_lam_chet_worker(worker):
    _run(worker, [ValueError("lỗi lạ")])
    kinds = [e["kind"] for e in worker._test_events]
    assert "worker_error" in kinds
    ev = next(e for e in worker._test_events if e["kind"] == "worker_error")
    assert "lỗi lạ" in ev["message"] and ev["detail"], "phải kèm traceback để chẩn đoán"


# =====================================================================
# 3. Nhịp tim + tham số kết nối
# =====================================================================

def test_moi_vong_deu_ghi_nhip_tim(worker):
    _run(worker, [None, None, None])
    beats = worker.redis.hashes.get("_heartbeat", {})
    assert len(beats) == 1, "một worker → một khóa nhịp tim"
    key, (ttl, _) = next(iter(beats.items()))
    assert key.startswith("worker:heartbeat:")
    assert ttl == 60, "TTL phải có để worker đã tắt tự biến mất khỏi danh sách"


def test_tham_so_ket_noi_redis_dung_cho_hang_doi_chan(monkeypatch):
    """
    Chốt nguyên nhân gốc: socket_timeout PHẢI là None cho lệnh chặn.
    Nếu ai đó đặt lại giá trị này thì lỗi TimeoutError sẽ quay lại — test sẽ chặn.
    """
    import sys, types
    captured = {}

    fake = types.ModuleType("redis")
    fake.Redis = lambda **kw: (captured.update(kw), _ScriptedRedis([]))[1]
    monkeypatch.setitem(sys.modules, "redis", fake)

    import scripts.worker as w
    monkeypatch.setattr(w, "USE_PROVIDER_LAYER", False)
    w.DigitizationWorker(init_db=False)

    assert captured["socket_timeout"] is None, "đặt thời hạn đọc socket sẽ làm BLPOP ném TimeoutError"
    assert captured["socket_keepalive"] is True
    assert captured["health_check_interval"] == 30
    assert captured["socket_connect_timeout"] == 5


# =====================================================================
# 4. Đo thời gian xử lý
# =====================================================================

def test_luu_thoi_gian_xu_ly_va_tung_chang(monkeypatch):
    """Thời gian phải đo phần worker THỰC SỰ làm, và tách được chặng nào tốn bao lâu."""
    import scripts.worker as w

    timings = {}
    monkeypatch.setattr(w.db, "set_job_timing",
                        lambda job_id, duration_ms, stage_timings=None:
                            timings.update(job_id=job_id, duration_ms=duration_ms,
                                           stages=stage_timings))
    monkeypatch.setattr(w.db, "update_document_status", lambda *a, **kw: None)
    monkeypatch.setattr(w.db, "save_metadata", lambda *a, **kw: None)
    monkeypatch.setattr(w.audit, "log_action", lambda **kw: None)
    monkeypatch.setattr(w, "publish_job_event", lambda **kw: None)
    monkeypatch.setattr(w, "USE_PROVIDER_LAYER", False)

    class _Pipeline:
        def __init__(self, **kw): pass
        def process(self, input_pdf, output_dir):
            return {"summary": {"status": "completed", "output_pdf": "/o/x.pdf"}}

    monkeypatch.setattr(w, "DigitizationPipeline", _Pipeline)
    monkeypatch.setattr(w.DigitizationWorker, "_read_metadata", lambda self, d: [])

    inst = w.DigitizationWorker(redis_client=_ScriptedRedis([]), init_db=False)
    inst.process_job({"job_id": "j-t", "filename": "a.pdf", "input_file": "/i/a.pdf",
                      "output_dir": "/o", "document_type": "book"})

    assert timings["job_id"] == "j-t"
    assert timings["duration_ms"] >= 0
    assert "ocr_and_extract" in timings["stages"], str(timings["stages"])
    assert "save_metadata" in timings["stages"]


def test_job_that_bai_van_luu_thoi_gian(monkeypatch):
    """Biết job thất bại sau bao lâu giúp phân biệt lỗi tức thời với treo lâu rồi mới chết."""
    import scripts.worker as w

    saved = {}
    monkeypatch.setattr(w.db, "set_job_timing",
                        lambda job_id, duration_ms, stage_timings=None:
                            saved.update(job_id=job_id, duration_ms=duration_ms))
    monkeypatch.setattr(w.db, "update_document_status", lambda *a, **kw: None)
    monkeypatch.setattr(w.db, "log_system_event", lambda **kw: None)
    monkeypatch.setattr(w.audit, "log_action", lambda **kw: None)
    monkeypatch.setattr(w, "publish_job_event", lambda **kw: None)
    monkeypatch.setattr(w, "USE_PROVIDER_LAYER", False)

    class _Failing:
        def __init__(self, **kw): pass
        def process(self, input_pdf, output_dir):
            return {"summary": {"status": "failed", "error": "Ghostscript lỗi"}}

    monkeypatch.setattr(w, "DigitizationPipeline", _Failing)

    inst = w.DigitizationWorker(redis_client=_ScriptedRedis([]), init_db=False)
    inst.process_job({"job_id": "j-f", "filename": "a.pdf", "input_file": "/i/a.pdf",
                      "output_dir": "/o", "document_type": "book"})

    assert saved.get("job_id") == "j-f"
