#!/usr/bin/env python3
"""
Kiểm thử thống kê người dùng & quản trị (YC-TT) — KT-TT-01→12.

Phần lớn module này là SQL, chỉ kiểm được thật trên PostgreSQL (đã có job `migrations` trong CI làm
việc đó). Ở đây kiểm phần LOGIC THUẦN — chính là phần dễ sai âm thầm nhất:

  • Ngưỡng cảnh báo: báo động giả sẽ khiến bảng cảnh báo bị bỏ qua, kể cả lúc nó nói thật.
  • Phân biệt "chưa đo được" (None) với "bằng 0" — hai chuyện dẫn tới hai hành động khác nhau.
  • Ghi chú cách đọc theo QĐ-06 phải LUÔN đi kèm số liệu theo người.

Chạy: pytest tests/test_user_stats.py -v
"""

import pytest

from scripts.core import user_stats


# =====================================================================
# GHI CHÚ CÁCH ĐỌC (QĐ-06)
# =====================================================================

def test_ghi_chu_noi_ro_khong_phai_bang_xep_hang():
    """
    Số liệu theo người mà không kèm cách đọc sẽ bị dùng làm bảng thi đua — đúng thứ QĐ-06 cấm.
    Ghi chú nằm TRONG dữ liệu backend trả về để giao diện không thể quên hiển thị.
    """
    ghi_chu = user_stats.GHI_CHU_CACH_DOC
    assert "KHÔNG phải bảng xếp hạng" in ghi_chu
    assert "số trang" in ghi_chu.lower()


# =====================================================================
# CẢNH BÁO
# =====================================================================

def _du_lieu(**kwargs):
    """Bộ dữ liệu 'mọi thứ bình thường', ghi đè từng phần cho mỗi bài kiểm."""
    base = {
        "an_ninh": {"so_dang_nhap": 100, "so_dang_nhap_hong": 2, "so_bi_tu_choi": 0},
        "khoi_luong": {"so_tai_lieu": 100, "so_hoan_thanh": 95, "so_that_bai": 2,
                       "so_can_xem_lai": 5},
        "ip_dang_nhap_hong": [],
    }
    for key, value in kwargs.items():
        if isinstance(value, dict) and key in base:
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def test_binh_thuong_thi_KHONG_canh_bao_gi():
    """
    Một bảng cảnh báo lúc nào cũng có gì đó sẽ nhanh chóng bị bỏ qua. Im lặng khi mọi thứ ổn là
    một tính năng, không phải thiếu sót.
    """
    assert user_stats._canh_bao(_du_lieu()) == []


def test_dang_nhap_hong_nhieu_thi_canh_bao():
    data = _du_lieu(an_ninh={"so_dang_nhap": 50, "so_dang_nhap_hong": 40})
    canh_bao = user_stats._canh_bao(data)
    assert any("đăng nhập thất bại" in c["noi_dung"] for c in canh_bao)


def test_he_thong_moi_it_du_lieu_KHONG_bao_dong_gia():
    """
    Ngưỡng kép (số tuyệt đối VÀ tỉ lệ) là để tránh đúng tình huống này: hệ thống vừa dựng, 1 lần gõ
    sai mật khẩu trên 2 lần thử = 50% — chỉ dùng tỉ lệ thì báo động ngay ngày đầu.
    """
    data = _du_lieu(an_ninh={"so_dang_nhap": 1, "so_dang_nhap_hong": 1})
    assert user_stats._canh_bao(data) == []


def test_he_thong_lon_van_bao_duoc_khi_ty_le_cao():
    """Ngược lại: chỉ dùng số tuyệt đối thì hệ thống lớn không bao giờ báo. Cả hai điều kiện đều cần."""
    data = _du_lieu(an_ninh={"so_dang_nhap": 100, "so_dang_nhap_hong": 60})
    assert any("đăng nhập thất bại" in c["noi_dung"] for c in user_stats._canh_bao(data))


def test_mot_ip_thu_nhieu_tai_khoan_la_muc_nguy_hiem():
    """Dò mật khẩu là tín hiệu an ninh nghiêm trọng nhất bảng này bắt được — phải ở mức cao nhất."""
    data = _du_lieu(ip_dang_nhap_hong=[
        {"ip": "10.0.0.9", "so_lan": 30, "so_tai_khoan_bi_thu": 8},
    ])
    canh_bao = user_stats._canh_bao(data)
    do_mat_khau = [c for c in canh_bao if "dò mật khẩu" in c["noi_dung"]]
    assert len(do_mat_khau) == 1
    assert do_mat_khau[0]["muc"] == "nguy_hiem"
    assert "10.0.0.9" in do_mat_khau[0]["noi_dung"]


def test_mot_nguoi_go_sai_mat_khau_cua_chinh_minh_khong_bi_bao_do_mat_khau():
    """Gõ sai mật khẩu của chính mình 10 lần là chuyện đãng trí, không phải tấn công."""
    data = _du_lieu(ip_dang_nhap_hong=[
        {"ip": "10.0.0.5", "so_lan": 10, "so_tai_khoan_bi_thu": 1},
    ])
    assert not any("dò mật khẩu" in c["noi_dung"] for c in user_stats._canh_bao(data))


def test_ty_le_can_xem_lai_cao_thi_canh_bao_chat_luong():
    data = _du_lieu(khoi_luong={"so_hoan_thanh": 100, "so_can_xem_lai": 50})
    assert any("cần xem lại" in c["noi_dung"] for c in user_stats._canh_bao(data))


def test_ty_le_that_bai_cao_thi_canh_bao_van_hanh():
    data = _du_lieu(khoi_luong={"so_tai_lieu": 100, "so_that_bai": 25})
    canh_bao = user_stats._canh_bao(data)
    that_bai = [c for c in canh_bao if "thất bại" in c["noi_dung"] and "worker" in c["noi_dung"]]
    assert len(that_bai) == 1
    assert that_bai[0]["muc"] == "nguy_hiem"


def test_bi_tu_choi_quyen_nhieu_thi_goi_y_xem_lai_phan_vai():
    """
    Bị từ chối quyền nhiều thường KHÔNG phải tấn công mà là phân vai thiếu — nên để mức 'thông tin'
    và nói thẳng hướng xử lý, thay vì làm quản trị viên hoảng.
    """
    data = _du_lieu(an_ninh={"so_bi_tu_choi": 25})
    canh_bao = user_stats._canh_bao(data)
    tu_choi = [c for c in canh_bao if "từ chối quyền" in c["noi_dung"]]
    assert len(tu_choi) == 1
    assert tu_choi[0]["muc"] == "thong_tin"
    assert "phân vai" in tu_choi[0]["noi_dung"]


def test_khong_chia_cho_khong_khi_chua_co_du_lieu():
    """Hệ thống vừa dựng, mọi bảng đều rỗng — không được ném ZeroDivisionError."""
    trong = {"an_ninh": {}, "khoi_luong": {}, "ip_dang_nhap_hong": []}
    assert user_stats._canh_bao(trong) == []


def test_moi_canh_bao_deu_co_muc_hop_le():
    """Giao diện tô màu theo `muc` — một mức lạ sẽ rơi về màu mặc định và mất ý nghĩa cảnh báo."""
    data = _du_lieu(
        an_ninh={"so_dang_nhap": 10, "so_dang_nhap_hong": 50, "so_bi_tu_choi": 30},
        khoi_luong={"so_tai_lieu": 100, "so_that_bai": 40, "so_hoan_thanh": 60,
                    "so_can_xem_lai": 40},
        ip_dang_nhap_hong=[{"ip": "1.2.3.4", "so_lan": 40, "so_tai_khoan_bi_thu": 5}],
    )
    canh_bao = user_stats._canh_bao(data)
    assert len(canh_bao) >= 4
    for c in canh_bao:
        assert c["muc"] in ("nguy_hiem", "canh_bao", "thong_tin")
        assert c["noi_dung"].strip()


# =====================================================================
# CHUẨN HÓA THỜI GIAN
# =====================================================================

def test_doi_thoi_gian_sang_chuoi_iso():
    from datetime import datetime

    rows = [{"lan_cuoi": datetime(2026, 8, 9, 10, 30), "ten": "a"}]
    ket_qua = user_stats._iso(rows, "lan_cuoi")
    assert ket_qua[0]["lan_cuoi"] == "2026-08-09T10:30:00"
    assert ket_qua[0]["ten"] == "a"


def test_gia_tri_none_giu_nguyen_khong_thanh_chuoi():
    """None phải ở lại là None — đổi thành chuỗi rỗng sẽ khiến giao diện hiện 'Invalid Date'."""
    rows = [{"lan_cuoi": None}]
    assert user_stats._iso(rows, "lan_cuoi")[0]["lan_cuoi"] is None


def test_cot_khong_ton_tai_khong_gay_loi():
    assert user_stats._iso([{"a": 1}], "khong_co_cot_nay") == [{"a": 1}]
