#!/usr/bin/env python3
"""
Kiểm thử bảng điều khiển (sprint V7) — KT-DB-01/02/05/08.

TRỌNG TÂM: **số liệu không được vênh với `/api/v2/stats` và `/bao-cao`** (KT-DB-02). Hai màn hình
mâu thuẫn nhau còn tệ hơn một màn hình không có — người dùng mất niềm tin vào cả hai rồi quay lại
đếm tay. Sai lệch kiểu này không bao giờ báo lỗi, nên chỉ có test chốt được.

Kiểm bằng cách bắt câu SQL: máy dev không có PostgreSQL (xem `docs/PLAN.md`).
"""

from contextlib import contextmanager

import pytest

from scripts.core import dashboard


class DictCursor:
    """
    Con trỏ giả theo ngữ nghĩa `RealDictCursor`: `fetchone()` trả DICT, không phải tuple.

    Dùng bản riêng thay vì mượn của `test_user_log`: module đó dùng con trỏ thường (trả tuple), và
    dashboard đọc kết quả bằng `.get()` — mượn nhầm sẽ cho `AttributeError` che mất lỗi thật.
    """

    def __init__(self, store, rows=None):
        self.store = store
        self._rows = rows if rows is not None else []

    def execute(self, sql, params=None):
        self.store.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class DictConn:
    def __init__(self, store, rows=None):
        self.store = store
        self.rows = rows

    def cursor(self, cursor_factory=None):
        return DictCursor(self.store, self.rows)

    def rollback(self):
        pass


@pytest.fixture
def sql_store(monkeypatch):
    store = []

    @contextmanager
    def fake_get_conn():
        yield DictConn(store)

    import scripts.db as db
    monkeypatch.setattr(db, "get_conn", fake_get_conn)
    return store


def _sql_texts(store):
    return [sql for sql, _ in store]


# ─────────────────────────────────────────────────────────────
# KT-DB-02: SỐ LIỆU KHÔNG ĐƯỢC VÊNH 🔴
# ─────────────────────────────────────────────────────────────

def test_tong_quan_loai_tru_tai_lieu_da_xoa_mem(sql_store):
    """
    🔴 Phải dùng ĐÚNG bộ lọc của `get_stats()`: loại `status = 'deleted'`.

    Nếu bảng điều khiển đếm cả tài liệu đã xóa mềm thì nó sẽ hiện số lớn hơn `/bao-cao` — và không
    ai biết con số nào đúng.
    """
    dashboard.summary()

    sql = _sql_texts(sql_store)[0]
    assert "status <> 'deleted'" in sql


def test_viec_cua_toi_cung_loai_tru_da_xoa(sql_store):
    dashboard.my_work(user_id=7, username="canbo1")

    assert "status <> 'deleted'" in _sql_texts(sql_store)[0]


def test_sla_cung_loai_tru_da_xoa(sql_store):
    """Tài liệu đã xóa mềm không được xuất hiện trong danh sách quá hạn."""
    dashboard.sla_breaches()

    for sql in _sql_texts(sql_store):
        assert "status <> 'deleted'" in sql


def test_bo_loc_dung_chung_duoc_khai_bao_mot_cho():
    """
    Bộ lọc phải là một hằng dùng chung, không phải chuỗi lặp lại ở mỗi truy vấn.

    Lặp lại là cách chắc chắn để một ngày nào đó sửa một chỗ mà quên chỗ kia.
    """
    assert dashboard.NOT_DELETED == "status <> 'deleted'"


# ─────────────────────────────────────────────────────────────
# VIỆC CỦA TÔI (YC-DB-01)
# ─────────────────────────────────────────────────────────────

def test_loc_theo_dung_nguoi_dung(sql_store):
    dashboard.my_work(user_id=42, username="canbo1")

    sql, params = sql_store[0]
    assert "uploaded_by = %(uid)s" in sql
    assert params["uid"] == 42


def test_chua_dang_nhap_thi_tra_so_toan_he_thong(sql_store):
    """
    Chưa có danh tính (nấc `AUTH_MODE=off`) → trả số TOÀN HỆ THỐNG kèm cờ `theo_ca_nhan=False`.

    Trả rỗng sẽ khiến trang trông như hỏng; trả số toàn hệ thống thì trang vẫn có ích và nói rõ
    đây không phải số của riêng ai.
    """
    result = dashboard.my_work(user_id=None)

    assert result["theo_ca_nhan"] is False
    # Truy vấn KHÔNG được lọc theo người dùng — đó chính là điều làm nó thành "toàn hệ thống"
    sql, params = sql_store[0]
    assert "uploaded_by =" not in sql
    assert params is None


def test_co_danh_tinh_thi_danh_dau_la_so_ca_nhan(sql_store):
    result = dashboard.my_work(user_id=7, username="canbo1")
    assert result["theo_ca_nhan"] is True


def test_tai_lieu_chua_giao_van_hien_trong_cho_toi_duyet(sql_store):
    """
    Tài liệu chưa giao cho ai (`assigned_to IS NULL`) phải hiện với mọi người có quyền duyệt.

    Nếu chỉ hiện tài liệu đã được giao thì ở một Trung tâm chưa dùng tính năng phân công, danh sách
    "chờ tôi duyệt" sẽ luôn rỗng và cả thẻ này thành vô dụng.
    """
    dashboard.my_work(user_id=7, username="canbo1")

    sql = _sql_texts(sql_store)[0]
    assert "assigned_to IS NULL" in sql


# ─────────────────────────────────────────────────────────────
# SLA (YC-DB-04)
# ─────────────────────────────────────────────────────────────

def test_sla_do_theo_updated_at_khong_phai_created_at(sql_store):
    """
    🔴 Đo bằng `updated_at`: câu hỏi là "nằm ở TRẠNG THÁI NÀY bao lâu rồi".

    Dùng `created_at` sẽ báo quá hạn cho một tài liệu tạo từ tháng trước nhưng vừa chuyển sang chờ
    duyệt sáng nay — cảnh báo giả, và cảnh báo giả làm người ta bỏ qua cả cảnh báo thật.
    """
    dashboard.sla_breaches()

    sql = _sql_texts(sql_store)[0]
    assert "updated_at <" in sql
    assert "created_at <" not in sql


def test_moi_trang_thai_co_nguong_rieng(sql_store):
    """Chờ hàng đợi vài giờ là bình thường; chờ duyệt vài ngày thì không — không dùng chung một ngưỡng."""
    result = dashboard.sla_breaches()

    nguong = result["nguong_gio"]
    assert nguong["queued"] != nguong["needs_review"]
    assert nguong["needs_review"] > nguong["queued"]


def test_sla_bao_gom_tai_lieu_cho_duyet(sql_store):
    """
    Chờ duyệt là chỗ tồn đọng nhiều nhất trong thực tế — không được bỏ sót khỏi cảnh báo.

    Tài liệu đã `completed` nhưng `needs_review` thì mọi thước đo trạng thái đều coi là "xong".
    """
    dashboard.sla_breaches()

    sql = _sql_texts(sql_store)[0]
    assert "needs_review" in sql


# ─────────────────────────────────────────────────────────────
# NĂNG SUẤT (YC-DB-05 / QĐ-06)
# ─────────────────────────────────────────────────────────────

def test_nang_suat_luon_kem_ghi_chu_muc_dich(sql_store):
    """
    🔴 QĐ-06: số liệu năng suất công khai PHẢI kèm ghi chú "không phải bảng xếp hạng".

    Ghi chú nằm TRONG dữ liệu trả về chứ không chỉ trong mã giao diện, để một lần sửa giao diện
    không thể vô tình bỏ mất nó.
    """
    result = dashboard.staff_workload()

    assert "ghi_chu" in result
    assert "không so sánh trực tiếp" in result["ghi_chu"]
    assert "xếp hạng" in result["ghi_chu"]


def test_nang_suat_kem_boi_canh_khong_chi_so_dem(sql_store):
    """
    QĐ-06 ràng buộc 2: phải có số trang và số trường đã sửa, không chỉ số tài liệu.

    Một công văn 2 trang và một khóa luận 200 trang đều là "1 tài liệu" nếu chỉ đếm đầu mục.
    """
    dashboard.staff_workload()

    sql = " ".join(_sql_texts(sql_store))
    assert "pages" in sql, "phải lấy số trang làm bối cảnh"
    assert "edit_field" in sql, "phải lấy số trường đã sửa làm bối cảnh"


def test_nang_suat_chi_tinh_thao_tac_duyet(sql_store):
    """Đếm `confirm`, không đếm mọi thao tác — mở xem tài liệu không phải là duyệt."""
    dashboard.staff_workload()

    assert "action = 'confirm'" in _sql_texts(sql_store)[0]


def test_lo_chua_di_tru_khong_lam_gay_bang_dieu_khien(monkeypatch):
    """
    Chưa chạy migration 006 thì thẻ lô trả rỗng, KHÔNG ném lỗi.

    Bảng điều khiển gồm nhiều nguồn dữ liệu; một nguồn chưa sẵn sàng không được làm trắng cả trang.
    """
    @contextmanager
    def hong():
        raise RuntimeError("bảng batches chưa tồn tại")
        yield

    import scripts.db as db
    monkeypatch.setattr(db, "get_conn", hong)

    assert dashboard.active_batches() == []
