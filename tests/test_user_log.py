#!/usr/bin/env python3
"""
Kiểm thử nhật ký hành vi người dùng (sprint V4) — KT-NK-02/03/04/07, và cơ chế dọn theo tuổi.

Không có PostgreSQL trên máy dev, nên phần chạm DB được kiểm bằng cách bắt câu SQL và tham số gửi
xuống driver: đủ để bắt lỗi cột sai tên, lọc sai, hay nuốt lỗi không đúng chỗ. Việc chạy thật trên
PostgreSQL nằm ở phần kiểm chứng môi trường thật (xem docs/PLAN.md).
"""

import json
from contextlib import contextmanager

import pytest

from scripts.core import context, retention, user_log


# ─────────────────────────────────────────────────────────────
# HỖ TRỢ: bắt câu SQL thay vì cần PostgreSQL thật
# ─────────────────────────────────────────────────────────────

class FakeCursor:
    def __init__(self, store, rows=None):
        self.store = store
        self._rows = rows if rows is not None else []

    def execute(self, sql, params=None):
        self.store.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else (0,)

    @property
    def rowcount(self):
        return len(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    def __init__(self, store, rows=None):
        self.store = store
        self.rows = rows

    def cursor(self, cursor_factory=None):
        return FakeCursor(self.store, self.rows)

    def rollback(self):
        pass


@pytest.fixture
def sql_store(monkeypatch):
    """Bắt mọi câu SQL mà module gửi xuống driver."""
    store = []

    @contextmanager
    def fake_get_conn():
        yield FakeConn(store)

    import scripts.db as db
    monkeypatch.setattr(db, "get_conn", fake_get_conn)
    context.clear()
    return store


# ─────────────────────────────────────────────────────────────
# GHI NHẬT KÝ
# ─────────────────────────────────────────────────────────────

def test_ghi_dang_nhap_thanh_cong(sql_store):
    user_log.log_activity(action=user_log.ACTION_LOGIN, username="nguyenvanan",
                          user_id=7, ip="10.1.1.50")

    sql, params = sql_store[0]
    assert "INSERT INTO user_activity" in sql
    assert params[0] == 7
    assert params[1] == "nguyenvanan"
    assert params[2] == "login"
    assert params[5] == "10.1.1.50"


def test_ghi_tu_choi_quyen_du_thong_tin(sql_store):
    """
    KT-NK-03: bị từ chối quyền là tín hiệu an ninh quan trọng nhất — phải ghi đủ ai/gì/ở đâu.
    """
    user_log.log_denied(username="nguoixem", method="DELETE", path="/api/v2/jobs/abc",
                        role="viewer", missing=["document:delete"], ip="10.1.1.9")

    _, params = sql_store[0]
    assert params[2] == user_log.ACTION_PERMISSION_DENIED
    assert params[4] == "DELETE /api/v2/jobs/abc"
    assert params[8] == user_log.RESULT_DENIED
    detail = json.loads(params[9])
    assert detail["missing"] == ["document:delete"]
    assert detail["role"] == "viewer"


def test_tu_lay_actor_va_request_id_tu_ngu_canh(sql_store):
    """
    Nơi gọi chỉ cần nói *việc gì xảy ra*; danh tính và mã request tự lấy từ ngữ cảnh.

    Không có cơ chế này thì mỗi nơi gọi phải mang theo hai giá trị đó, và mỗi nơi mới là một cơ hội quên.
    """
    with context.request_context(request_id="req-abc", actor="canbo1"):
        user_log.log_activity(action=user_log.ACTION_DOWNLOAD, resource_id="job-1")

    _, params = sql_store[0]
    assert params[1] == "canbo1"        # username lấy từ ngữ cảnh
    assert params[7] == "req-abc"       # request_id lấy từ ngữ cảnh


def test_user_agent_bi_cat_ngan(sql_store):
    """User-agent có thể rất dài; cắt để một dòng nhật ký không phình bất thường."""
    user_log.log_activity(action=user_log.ACTION_LOGIN, username="a", user_agent="x" * 2000)

    _, params = sql_store[0]
    assert len(params[6]) == 500


def test_ghi_nhat_ky_hong_khong_lam_gay_nghiep_vu(monkeypatch):
    """
    Nhật ký hỏng KHÔNG được chặn nghiệp vụ chính — cùng nguyên tắc với `audit.py`.

    Nếu ghi nhật ký ném lỗi ra ngoài thì một bảng chưa di trú sẽ làm **không ai đăng nhập được**.
    """
    @contextmanager
    def hong():
        raise RuntimeError("bảng user_activity chưa tồn tại")
        yield

    import scripts.db as db
    monkeypatch.setattr(db, "get_conn", hong)

    user_log.log_activity(action=user_log.ACTION_LOGIN, username="a")   # không được ném ra ngoài


# ─────────────────────────────────────────────────────────────
# TRA CỨU
# ─────────────────────────────────────────────────────────────

def test_loc_theo_nhieu_dieu_kien(sql_store):
    user_log.list_activity(username="canbo1", action="login_failed",
                           date_from="2026-08-01", limit=50)

    sql, params = sql_store[0]
    assert "WHERE username = %s AND action = %s AND created_at >= %s" in sql
    assert params[:3] == ["canbo1", "login_failed", "2026-08-01"]
    assert params[-2:] == [50, 0]


def test_khong_co_bo_loc_thi_khong_co_menh_de_where(sql_store):
    user_log.list_activity()

    sql, _ = sql_store[0]
    assert "WHERE" not in sql


def test_sap_xep_moi_nhat_truoc(sql_store):
    """Người tra nhật ký hầu như luôn quan tâm việc vừa xảy ra."""
    user_log.list_activity()

    sql, _ = sql_store[0]
    assert "ORDER BY created_at DESC" in sql


def test_dong_thoi_gian_gop_du_bon_nguon(sql_store):
    """KT-NK-09: một tài liệu, bốn nguồn, một danh sách theo thời gian."""
    user_log.document_timeline("job-1")

    sql, _ = sql_store[0]
    for bang in ("audit_log", "user_activity", "model_calls", "ocr_runs"):
        assert bang in sql, f"thiếu nguồn {bang} trong dòng thời gian"
    assert "ORDER BY created_at ASC" in sql


# ─────────────────────────────────────────────────────────────
# DỌN THEO TUỔI (YC-LG-07)
# ─────────────────────────────────────────────────────────────

def test_chi_don_bang_trong_danh_sach_trang():
    """
    Tên bảng không tham số hóa được trong SQL nên phải nội suy chuỗi — chỉ an toàn khi giá trị đến
    từ danh sách trắng. Test này chốt rằng đầu vào tùy ý bị từ chối.
    """
    with pytest.raises(ValueError):
        retention.cleanup_table("documents")
    with pytest.raises(ValueError):
        retention.cleanup_table("users; DROP TABLE documents")


def test_audit_log_khong_nam_trong_danh_sach_don():
    """
    🔴 `audit_log` phải VĨNH VIỄN (YC-AU-06) — không được có đường nào dọn nó từ module này.
    """
    assert "audit_log" not in retention.CLEANABLE_TABLES


def test_thoi_han_luu_mac_dinh_dung_quy_dinh():
    """QĐ-08: hành vi người dùng 365 ngày, sự cố hạ tầng 90 ngày."""
    assert retention.retention_days("user_activity") == 365
    assert retention.retention_days("system_events") == 90


def test_thoi_han_luu_doi_duoc_bang_bien_moi_truong(monkeypatch):
    monkeypatch.setenv("SYSTEM_EVENTS_RETENTION_DAYS", "30")
    assert retention.retention_days("system_events") == 30


def test_don_tep_log_chi_dung_ban_da_luan_chuyen(tmp_path):
    """
    CHỈ xóa tệp `.jsonl.N` (đã luân chuyển), KHÔNG đụng tệp đang được ghi.

    Xóa tệp đang mở trên Windows sẽ lỗi; trên Linux thì tiến trình vẫn ghi vào một tệp đã bị gỡ khỏi
    thư mục và dung lượng không thực sự được giải phóng.
    """
    import os
    import time

    dang_ghi = tmp_path / "api.jsonl"
    da_luan_chuyen = tmp_path / "api.jsonl.1"
    con_moi = tmp_path / "api.jsonl.2"
    for tep in (dang_ghi, da_luan_chuyen, con_moi):
        tep.write_text("{}", encoding="utf-8")

    cu = time.time() - 30 * 86400
    os.utime(dang_ghi, (cu, cu))
    os.utime(da_luan_chuyen, (cu, cu))

    da_xoa = retention.cleanup_log_files(str(tmp_path), days=14)

    assert da_xoa == ["api.jsonl.1"]
    assert dang_ghi.exists(), "KHÔNG được xóa tệp đang được ghi"
    assert con_moi.exists(), "tệp còn trong hạn phải giữ lại"


def test_khong_co_thu_muc_log_thi_khong_lam_gi():
    assert retention.cleanup_log_files("", days=14) == []
    assert retention.cleanup_log_files("/khong/ton/tai/o/dau", days=14) == []


def test_bao_cao_don_dep_tom_tat_doc_duoc():
    report = retention.CleanupReport(
        rows_deleted={"system_events": 120, "user_activity": 0},
        files_deleted=["api.jsonl.3"],
    )
    tom_tat = report.summary()

    assert "system_events: 120 dòng" in tom_tat
    assert "user_activity" not in tom_tat, "không liệt kê bảng không xóa dòng nào"
    assert "1 tệp log" in tom_tat


def test_bao_cao_rong_noi_ro_khong_co_gi():
    """Nói rõ "không có gì quá hạn" thay vì im lặng — im lặng dễ bị hiểu là tác vụ chưa chạy."""
    assert retention.CleanupReport().summary() == "không có gì quá hạn"


# ─────────────────────────────────────────────────────────────
# DỌN TỆP TRUNG GIAN (YC-VH-09, sprint V9)
# ─────────────────────────────────────────────────────────────

def test_chi_don_thu_muc_dung_dang_uuid(tmp_path, monkeypatch):
    """
    🔴 CHỈ đụng thư mục tên đúng dạng uuid4 (id job).

    Thư mục lạ — `_zip_staging`, tệp người dùng để nhầm, thư mục cấu hình — tuyệt đối không xóa.
    Đây là hàm xóa dữ liệu; một mẫu khớp quá rộng ở đây là mất dữ liệu không lấy lại được.
    """
    from contextlib import contextmanager

    uuid_hop_le = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
    (tmp_path / uuid_hop_le).mkdir()
    (tmp_path / "_zip_staging").mkdir()
    (tmp_path / "cau-hinh").mkdir()

    @contextmanager
    def fake_conn():
        yield FakeConn([], rows=[(uuid_hop_le,)])

    import scripts.db as db
    monkeypatch.setattr(db, "get_conn", fake_conn)

    da_xoa = retention.cleanup_job_files(str(tmp_path), days=90, dry_run=True)

    assert da_xoa == [uuid_hop_le]
    assert (tmp_path / "_zip_staging").exists()
    assert (tmp_path / "cau-hinh").exists()


def test_khong_doc_duoc_db_thi_khong_xoa_gi(tmp_path, monkeypatch):
    """
    🔴 Không tra được tài liệu nào quá hạn → KHÔNG xóa gì cả.

    Xóa theo phỏng đoán (vd theo tuổi tệp) sẽ xóa nhầm tài liệu tải lên tháng trước mà vẫn đang chờ
    duyệt — tệp của nó vẫn cần thiết.
    """
    from contextlib import contextmanager

    (tmp_path / "3f2504e0-4f89-41d3-9a0c-0305e82c3301").mkdir()

    @contextmanager
    def hong():
        raise RuntimeError("DB không đọc được")
        yield

    import scripts.db as db
    monkeypatch.setattr(db, "get_conn", hong)

    assert retention.cleanup_job_files(str(tmp_path), days=90) == []
    assert (tmp_path / "3f2504e0-4f89-41d3-9a0c-0305e82c3301").exists()


def test_dry_run_khong_xoa_that(tmp_path, monkeypatch):
    """Xem trước danh sách sẽ xóa mà không đụng đĩa — bắt buộc có cho một hàm xóa dữ liệu."""
    from contextlib import contextmanager

    uuid_hop_le = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
    (tmp_path / uuid_hop_le).mkdir()

    @contextmanager
    def fake_conn():
        yield FakeConn([], rows=[(uuid_hop_le,)])

    import scripts.db as db
    monkeypatch.setattr(db, "get_conn", fake_conn)

    retention.cleanup_job_files(str(tmp_path), dry_run=True)

    assert (tmp_path / uuid_hop_le).exists(), "dry_run KHÔNG được xóa thật"


def test_thu_muc_khong_ton_tai_khong_gay_loi():
    assert retention.cleanup_job_files("/khong/co/o/dau") == []
