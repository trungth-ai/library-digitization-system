#!/usr/bin/env python3
"""
Kiểm thử hàng đợi tin cậy (ADR-011, sửa lỗi N-02) — KT-BU-15 → KT-BU-23.

Test quan trọng nhất: `test_worker_bi_kill_khong_mat_job` — tái hiện đúng ca production. Với `BLPOP`
cũ, job nằm trong RAM của worker suốt lúc xử lý nên `kill -9` là mất trắng; test đó sẽ hỏng.

Dùng `FakeRedis` tự viết thay vì `fakeredis`: máy dev không cài `redis` (xem `docs/PLAN.md`), và
`scripts.core.queue` cố ý KHÔNG import redis — client được truyền vào. Lớp giả dưới đây chỉ hiện thực
đúng những lệnh module dùng tới, và hiện thực chúng theo đúng ngữ nghĩa Redis thật.
"""

import json

import pytest

from scripts.core import queue as q


# ─────────────────────────────────────────────────────────────
# REDIS GIẢ — chỉ các lệnh module dùng, ngữ nghĩa khớp Redis thật
# ─────────────────────────────────────────────────────────────

class FakeRedis:
    """
    Lists: `self.lists[key]` — index 0 là phía TRÁI (LPUSH thêm vào đây).
    ZSet:  `self.zsets[key]` — dict {member: score}.
    Keys:  `self.plain[key]`  — cho nhịp tim (setex).
    """

    def __init__(self):
        self.lists = {}
        self.zsets = {}
        self.plain = {}

    # --- LIST ---
    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)
        return len(self.lists[key])

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)
        return len(self.lists[key])

    def lpop(self, key):
        items = self.lists.get(key) or []
        return items.pop(0) if items else None

    def rpop(self, key):
        items = self.lists.get(key) or []
        return items.pop() if items else None

    def llen(self, key):
        return len(self.lists.get(key) or [])

    def lrange(self, key, start, end):
        items = self.lists.get(key) or []
        if end == -1:
            return items[start:]
        return items[start:end + 1]

    def lrem(self, key, count, value):
        items = self.lists.get(key) or []
        removed = 0
        limit = count or len(items)
        i = 0
        while i < len(items) and removed < limit:
            if items[i] == value:
                items.pop(i)
                removed += 1
            else:
                i += 1
        return removed

    def lmove(self, src, dst, from_side, to_side):
        """LMOVE nguyên tử: đây chính là lệnh làm nên tính tin cậy của hàng đợi."""
        items = self.lists.get(src) or []
        if not items:
            return None
        value = items.pop() if from_side.upper() == "RIGHT" else items.pop(0)
        if to_side.upper() == "LEFT":
            self.lists.setdefault(dst, []).insert(0, value)
        else:
            self.lists.setdefault(dst, []).append(value)
        return value

    def blmove(self, src, dst, timeout, from_side, to_side):
        """Trong test không có tiến trình khác đẩy vào → hết giờ ngay, không chờ thật."""
        return self.lmove(src, dst, from_side, to_side)

    # --- ZSET ---
    def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update(mapping)
        return len(mapping)

    def zrem(self, key, member):
        return 1 if self.zsets.get(key, {}).pop(member, None) is not None else 0

    def zcard(self, key):
        return len(self.zsets.get(key) or {})

    def zrangebyscore(self, key, mini, maxi, start=0, num=None):
        items = sorted((self.zsets.get(key) or {}).items(), key=lambda kv: kv[1])
        lo = float("-inf") if mini == "-inf" else float(mini)
        hi = float("inf") if maxi == "+inf" else float(maxi)
        picked = [m for m, s in items if lo <= s <= hi]
        return picked[start:start + num] if num else picked[start:]

    # --- KEYS ---
    def setex(self, key, ttl, value):
        self.plain[key] = value

    def exists(self, key):
        return 1 if key in self.plain else 0

    def delete(self, key):
        self.plain.pop(key, None)

    def scan_iter(self, match, count=None):
        prefix = match.rstrip("*")
        return [k for k in list(self.lists.keys()) if k.startswith(prefix)]


BASE = "digitization_jobs"


@pytest.fixture
def r():
    return FakeRedis()


def _payload(job_id="job-1", filename="a.pdf"):
    return {"job_id": job_id, "filename": filename, "input_file": "/x/a.pdf",
            "output_dir": "/x/out"}


# ─────────────────────────────────────────────────────────────
# TƯƠNG THÍCH NGƯỢC
# ─────────────────────────────────────────────────────────────

def test_muc_normal_dung_chinh_khoa_cu():
    """
    Mức `normal` PHẢI là chính khóa `digitization_jobs` đang chạy (ADR-011 mục 2).

    Đây là điều kiện để tương thích ngược: mọi thứ đang đẩy vào khóa cũ vẫn được worker nhận. Nếu
    ai đó đổi thành `digitization_jobs:normal` thì job cũ sẽ nằm im trong khóa không ai đọc.
    """
    assert q.queue_key(BASE) == BASE
    assert q.queue_key(BASE, q.PRIORITY_NORMAL) == BASE
    assert q.queue_key(BASE, q.PRIORITY_HIGH) == f"{BASE}:high"
    assert q.queue_key(BASE, q.PRIORITY_LOW) == f"{BASE}:low"


def test_muc_uu_tien_khong_hop_le_bi_tu_choi():
    with pytest.raises(ValueError):
        q.queue_key(BASE, "urgent")


def test_nhan_duoc_job_day_boi_client_cu(r):
    """Job do phiên bản API cũ đẩy trực tiếp vào khóa cũ vẫn nhận được bình thường."""
    r.rpush(BASE, json.dumps(_payload()))          # đúng cách bản cũ đẩy (RPUSH)

    claimed = q.claim(r, BASE, "w1")

    assert claimed is not None
    assert claimed.job_id == "job-1"
    assert claimed.priority == q.PRIORITY_NORMAL


# ─────────────────────────────────────────────────────────────
# NHẬN VIỆC & FIFO
# ─────────────────────────────────────────────────────────────

def test_job_nam_trong_processing_sau_khi_nhan(r):
    """
    Sau khi nhận, job phải nằm trong danh sách đang-xử-lý — KHÔNG chỉ nằm trong RAM.

    Đây là bản chất của bản vá N-02.
    """
    q.push(r, BASE, _payload())

    claimed = q.claim(r, BASE, "w1")

    assert r.llen(BASE) == 0
    assert r.llen(q.processing_key("w1")) == 1
    assert json.loads(r.lrange(q.processing_key("w1"), 0, -1)[0])["job_id"] == claimed.job_id


def test_fifo_dung_thu_tu_tai_len(r):
    """Đẩy vào bên trái + nhận từ bên phải = FIFO. Tài liệu tải lên trước được xử lý trước."""
    for i in range(3):
        q.push(r, BASE, _payload(job_id=f"job-{i}"))

    thu_tu = [q.claim(r, BASE, "w1").job_id for _ in range(3)]

    assert thu_tu == ["job-0", "job-1", "job-2"]


def test_uu_tien_cao_duoc_xu_ly_truoc(r):
    """KT-BU-23: tài liệu lẻ cán bộ đang chờ không bị kẹt sau lô 500 tệp chạy đêm."""
    for i in range(5):
        q.push(r, BASE, _payload(job_id=f"lo-{i}"), priority=q.PRIORITY_LOW)
    q.push(r, BASE, _payload(job_id="le-gap"), priority=q.PRIORITY_HIGH)

    assert q.claim(r, BASE, "w1").job_id == "le-gap"


def test_hang_doi_rong_tra_none(r):
    """Hàng đợi rỗng là chuyện BÌNH THƯỜNG, không phải lỗi (ADR-009)."""
    assert q.claim(r, BASE, "w1") is None


def test_payload_rac_khong_lam_tac_hang_doi(r):
    """
    JSON hỏng phải bị BỎ khỏi danh sách đang-xử-lý, không để lại.

    Nếu để lại: bộ thu hồi sẽ trả bản rác về hàng đợi vô hạn — một job rác làm tắc cả hàng đợi.
    """
    r.lpush(BASE, "{khong-phai-json")

    assert q.claim(r, BASE, "w1") is None
    assert r.llen(q.processing_key("w1")) == 0


def test_ack_xoa_khoi_processing(r):
    q.push(r, BASE, _payload())
    claimed = q.claim(r, BASE, "w1")

    assert q.ack(r, "w1", claimed) is True
    assert r.llen(q.processing_key("w1")) == 0


# ─────────────────────────────────────────────────────────────
# KT-BU-15: WORKER BỊ KILL KHÔNG MẤT JOB  🔴
# ─────────────────────────────────────────────────────────────

def test_worker_bi_kill_khong_mat_job(r):
    """
    KT-BU-15 — trường hợp kiểm thử quan trọng nhất của ADR-011.

    Kịch bản đúng như production: worker nhận job, đang OCR (chưa ack), rồi bị `kill -9` → nhịp tim
    hết hạn. Bộ thu hồi phải trả job về hàng đợi để worker khác làm.

    Với `BLPOP` cũ, job chỉ tồn tại trong RAM của tiến trình đã chết → mất trắng, tài liệu treo mãi
    ở "Chờ xử lý" và không ai biết vì sao.
    """
    q.push(r, BASE, _payload(job_id="job-dang-ocr"))
    r.setex(q.HEARTBEAT_PREFIX + "w1", 60, "alive")

    claimed = q.claim(r, BASE, "w1")
    assert claimed.job_id == "job-dang-ocr"
    assert r.llen(BASE) == 0                       # không còn trong hàng đợi

    # ── worker w1 bị kill -9: nhịp tim hết hạn, job vẫn nằm trong processing ──
    r.delete(q.HEARTBEAT_PREFIX + "w1")

    reclaimed = q.reclaim_orphans(r, BASE)

    assert reclaimed == [("w1", 1)]
    assert r.llen(BASE) == 1, "job PHẢI quay lại hàng đợi — đây là lỗi mất dữ liệu N-02"
    assert r.llen(q.processing_key("w1")) == 0

    # Worker khác nhận lại được và xử lý tiếp
    lai = q.claim(r, BASE, "w2")
    assert lai.job_id == "job-dang-ocr"


def test_khong_thu_hoi_worker_con_song(r):
    """
    KT-BU-17: worker đang OCR một tài liệu 300 trang (20 phút) KHÔNG được bị thu hồi.

    Nếu thu hồi nhầm thì hai worker cùng xử lý một tài liệu — tốn gấp đôi và sinh dữ liệu lạ.
    Căn cứ duy nhất là nhịp tim (ADR-009).
    """
    q.push(r, BASE, _payload())
    r.setex(q.HEARTBEAT_PREFIX + "w1", 60, "alive")
    q.claim(r, BASE, "w1")

    assert q.reclaim_orphans(r, BASE) == []
    assert r.llen(BASE) == 0
    assert r.llen(q.processing_key("w1")) == 1


def test_thu_hoi_giu_dung_muc_uu_tien(r):
    """Job `high` bị thu hồi phải về lại hàng đợi `high`, không bị hạ xuống normal."""
    q.push(r, BASE, _payload(job_id="gap"), priority=q.PRIORITY_HIGH)
    r.setex(q.HEARTBEAT_PREFIX + "w1", 60, "alive")
    q.claim(r, BASE, "w1")
    r.delete(q.HEARTBEAT_PREFIX + "w1")

    q.reclaim_orphans(r, BASE)

    assert r.llen(q.queue_key(BASE, q.PRIORITY_HIGH)) == 1
    assert r.llen(BASE) == 0


def test_thu_hoi_nhieu_job_cua_mot_worker(r):
    """Worker có thể đang giữ nhiều job (prefetch trong tương lai) — phải thu hồi hết."""
    for i in range(3):
        q.push(r, BASE, _payload(job_id=f"j{i}"))
    r.setex(q.HEARTBEAT_PREFIX + "w1", 60, "alive")
    for _ in range(3):
        q.claim(r, BASE, "w1")
    r.delete(q.HEARTBEAT_PREFIX + "w1")

    assert q.reclaim_orphans(r, BASE) == [("w1", 3)]
    assert r.llen(BASE) == 3


# ─────────────────────────────────────────────────────────────
# THỬ LẠI / HÀNG ĐỢI CHẾT
# ─────────────────────────────────────────────────────────────

def test_loi_ha_tang_duoc_thu_lai_co_khoang_lui(r):
    """KT-BU-19: lỗi hạ tầng → vào ZSET chờ thử lại, KHÔNG cho worker ngủ."""
    q.push(r, BASE, _payload())
    claimed = q.claim(r, BASE, "w1")

    action, attempts = q.fail(r, BASE, "w1", claimed, reason="mất kết nối PostgreSQL",
                              retryable=True, max_attempts=3, backoff_sec=30, now=1000.0)

    assert (action, attempts) == ("retry", 1)
    assert r.zcard(q.delayed_key(BASE)) == 1
    assert r.llen(q.processing_key("w1")) == 0, "phải bỏ khỏi processing để không bị thu hồi lại"
    # Khoảng lùi lần 1 = 30s
    member = list(r.zsets[q.delayed_key(BASE)].keys())[0]
    assert r.zsets[q.delayed_key(BASE)][member] == 1030.0


def test_khoang_lui_tang_dan(r):
    """Lỗi hạ tầng thường cần thời gian tự khỏi → 30s, 60s, ... chứ không thử lại dồn dập."""
    q.push(r, BASE, _payload())
    claimed = q.claim(r, BASE, "w1")
    claimed.data["_attempts"] = 1                  # đã thử 1 lần

    q.fail(r, BASE, "w1", claimed, reason="Redis chớp mạng", retryable=True,
           max_attempts=5, backoff_sec=30, now=1000.0)

    member = list(r.zsets[q.delayed_key(BASE)].keys())[0]
    assert r.zsets[q.delayed_key(BASE)][member] == 1060.0     # 30 * 2^1


def test_loi_tai_lieu_vao_hang_doi_chet_ngay(r):
    """
    KT-BU-20: PDF hỏng thì KHÔNG thử lại 3 lần vô ích — vào hàng đợi chết ngay, có lý do.
    """
    q.push(r, BASE, _payload())
    claimed = q.claim(r, BASE, "w1")

    action, attempts = q.fail(r, BASE, "w1", claimed, reason="PDF hỏng: không đọc được trang 1",
                              retryable=False, max_attempts=3)

    assert (action, attempts) == ("dead", 1)
    assert r.zcard(q.delayed_key(BASE)) == 0
    dead = q.list_dead(r, BASE)
    assert len(dead) == 1
    assert dead[0]["_dead_reason"] == q.REASON_DOCUMENT_ERROR
    assert "PDF hỏng" in dead[0]["_error"]


def test_het_luot_thu_thi_vao_hang_doi_chet(r):
    """Lỗi hạ tầng dai dẳng cũng phải có điểm dừng, và điểm dừng đó phải NHÌN THẤY được."""
    q.push(r, BASE, _payload())
    claimed = q.claim(r, BASE, "w1")
    claimed.data["_attempts"] = 2                  # lần này là lần thứ 3

    action, attempts = q.fail(r, BASE, "w1", claimed, reason="PostgreSQL vẫn chưa lên",
                              retryable=True, max_attempts=3)

    assert (action, attempts) == ("dead", 3)
    assert q.list_dead(r, BASE)[0]["_dead_reason"] == q.REASON_MAX_ATTEMPTS


def test_job_den_han_duoc_dua_ve_hang_doi(r):
    """Đến hạn thì về hàng đợi; chưa đến hạn thì nằm yên."""
    q.push(r, BASE, _payload(job_id="chua-han"))
    c1 = q.claim(r, BASE, "w1")
    q.fail(r, BASE, "w1", c1, reason="x", retryable=True, backoff_sec=30, now=1000.0)

    assert q.promote_delayed(r, BASE, now=1010.0) == 0      # chưa tới 1030
    assert q.promote_delayed(r, BASE, now=1031.0) == 1
    assert r.llen(BASE) == 1
    assert r.zcard(q.delayed_key(BASE)) == 0


def test_job_thu_lai_duoc_nhan_ngay_luot_sau(r):
    """
    Job đã chờ hết khoảng lùi thì được nhận NGAY lượt sau, không xếp lại cuối hàng.

    `RPUSH` vào bên phải + claim lấy từ bên phải = được ưu tiên. Job này đã mất một lượt xử lý rồi.
    """
    q.push(r, BASE, _payload(job_id="moi"))
    q.push(r, BASE, _payload(job_id="cho-thu-lai"))
    c = q.claim(r, BASE, "w1")                     # nhận "moi" (FIFO)
    assert c.job_id == "moi"
    q.fail(r, BASE, "w1", c, reason="x", retryable=True, backoff_sec=1, now=1000.0)
    q.promote_delayed(r, BASE, now=2000.0)

    assert q.claim(r, BASE, "w1").job_id == "moi"


def test_chay_lai_tu_hang_doi_chet_giu_nguyen_job_id(r):
    """
    KT-BU-22: chạy lại phải GIỮ NGUYÊN `job_id`.

    Tạo id mới sẽ sinh bản ghi tài liệu trùng trong `documents` và làm mất lịch sử kiểm toán của
    lần xử lý trước.
    """
    q.push(r, BASE, _payload(job_id="job-hong"))
    c = q.claim(r, BASE, "w1")
    q.fail(r, BASE, "w1", c, reason="PDF hỏng", retryable=False)

    assert q.retry_dead(r, BASE, "job-hong") is True

    assert r.llen(q.dead_key(BASE)) == 0
    lai = q.claim(r, BASE, "w2")
    assert lai.job_id == "job-hong"
    # Siêu dữ liệu của lần chết phải được dọn, và số lần thử đặt lại về 0
    assert lai.attempts == 0
    assert "_dead_reason" not in lai.data
    assert "_error" not in lai.data


def test_chay_lai_job_khong_ton_tai(r):
    assert q.retry_dead(r, BASE, "khong-co") is False


def test_chay_lai_toan_bo_hang_doi_chet(r):
    """Dùng sau khi sửa nguyên nhân chung (vd PostgreSQL đã lên lại)."""
    for i in range(3):
        q.push(r, BASE, _payload(job_id=f"j{i}"))
        c = q.claim(r, BASE, "w1")
        q.fail(r, BASE, "w1", c, reason="DB down", retryable=False)

    assert q.retry_all_dead(r, BASE) == 3
    assert r.llen(q.dead_key(BASE)) == 0
    assert r.llen(BASE) == 3


def test_chay_lai_giu_muc_uu_tien(r):
    q.push(r, BASE, _payload(job_id="gap"), priority=q.PRIORITY_HIGH)
    c = q.claim(r, BASE, "w1")
    q.fail(r, BASE, "w1", c, reason="x", retryable=False)

    q.retry_dead(r, BASE, "gap")

    assert r.llen(q.queue_key(BASE, q.PRIORITY_HIGH)) == 1


# ─────────────────────────────────────────────────────────────
# QUAN SÁT
# ─────────────────────────────────────────────────────────────

def test_do_sau_hang_doi_dem_du_moi_loai(r):
    """
    Độ sâu phải gồm cả job đang thử lại / đã chết / đang xử lý.

    Trước đây giao diện chỉ thấy `llen(digitization_jobs)` nên những job này "vô hình" — người dùng
    không hiểu tại sao tài liệu không chạy mà hàng đợi lại rỗng.
    """
    q.push(r, BASE, _payload(job_id="a"))
    q.push(r, BASE, _payload(job_id="b"), priority=q.PRIORITY_HIGH)
    q.push(r, BASE, _payload(job_id="c"), priority=q.PRIORITY_LOW)
    dang_lam = q.claim(r, BASE, "w1")              # lấy "b" (high)
    q.push(r, BASE, _payload(job_id="d"))
    c2 = q.claim(r, BASE, "w2")
    q.fail(r, BASE, "w2", c2, reason="x", retryable=True, backoff_sec=30)
    c3 = q.claim(r, BASE, "w2")
    q.fail(r, BASE, "w2", c3, reason="y", retryable=False)

    d = q.depth(r, BASE)

    assert dang_lam.job_id == "b"
    assert d.processing == 1
    assert d.delayed == 1
    assert d.dead == 1
    assert d.as_dict()["ready"] == d.high + d.normal + d.low
