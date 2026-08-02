#!/usr/bin/env python3
"""
Kiểm thử phân tích chi tiết kết quả AI (sprint V2) — KT-AN-02/03/06/07/08/09/10.

Hai nhóm rủi ro được nhắm tới:

1. **Số liệu sai lặng lẽ.** Một công thức so sánh sai không làm hỏng gì cả — nó chỉ cho ra con số
   đẹp hơn hoặc xấu hơn thực tế, và không ai phát hiện. Nhóm `test_so_sanh_*` chốt đúng công thức
   của kế hoạch kiểm thử mục 1.3.
2. **Tiền tính bằng dấu phẩy động.** Quy ước dự án cấm; nhóm `test_chi_phi_*` chốt mọi giá trị tiền
   là số nguyên.
"""

import pytest

from scripts.core import analytics, pricing


# ─────────────────────────────────────────────────────────────
# SO SÁNH GIÁ TRỊ — công thức mục 1.3 kế hoạch kiểm thử
# ─────────────────────────────────────────────────────────────

def test_so_sanh_khop_hoan_toan():
    assert analytics.values_match("Báo cáo tổng kết", "Báo cáo tổng kết") is True


def test_so_sanh_bo_qua_khoang_trang_thua():
    """KT-AN-07: chuẩn hóa khoảng trắng trước khi so — hai khoảng trắng không phải là một lỗi trích xuất."""
    assert analytics.values_match("Báo cáo  tổng kết", "Báo cáo tổng kết") is True
    assert analytics.values_match("  Báo cáo tổng kết  ", "Báo cáo tổng kết") is True


def test_so_sanh_bo_qua_hoa_thuong():
    assert analytics.values_match("BÁO CÁO TỔNG KẾT", "Báo cáo tổng kết") is True


def test_so_sanh_ngay_thang_khac_dinh_dang():
    """KT-AN-08: `01/03/2026` và `2026-03-01` là CÙNG một ngày, không phải hai giá trị khác nhau."""
    assert analytics.values_match("01/03/2026", "2026-03-01") is True
    assert analytics.values_match("2026-03-01", "01.03.2026") is True


def test_so_sanh_ngay_khac_nhau_van_la_sai():
    assert analytics.values_match("01/03/2026", "02/03/2026") is False


def test_ca_hai_rong_la_dung():
    """
    KT-AN-09: trường không có trong tài liệu, AI trả rỗng, cán bộ cũng để rỗng → ĐÚNG.

    Đây là hành vi chống ảo giác đúng (YC-CF-05): "không tìm thấy" là câu trả lời hợp lệ.
    """
    assert analytics.values_match("", "") is True
    assert analytics.values_match(None, None) is True
    assert analytics.values_match(None, "") is True


def test_ai_biat_gia_tri_khi_khong_co_la_sai():
    """AI trả về giá trị trong khi cán bộ để rỗng = bịa. Phải tính là SAI."""
    assert analytics.values_match("Nhà xuất bản Giáo dục", "") is False


def test_ai_bo_sot_la_sai():
    assert analytics.values_match("", "Nhà xuất bản Giáo dục") is False


def test_khong_bo_dau_khi_so_sanh():
    """
    🔴 KHÔNG được bỏ dấu khi so sánh.

    "Bao cao tong ket" (AI trả về, mất dấu) và "Báo cáo tổng kết" (cán bộ sửa lại) là hai giá trị
    KHÁC nhau — và chính việc AI trả bản không dấu là lỗi cần đếm. Bỏ dấu khi so sánh sẽ che mất
    đúng loại lỗi phổ biến nhất với tài liệu tiếng Việt.
    """
    assert analytics.values_match("Bao cao tong ket", "Báo cáo tổng kết") is False


def test_chuan_hoa_unicode_hai_dang_to_hop():
    """Tiếng Việt có hai dạng tổ hợp (NFC/NFD) — cùng một chuỗi hiển thị phải khớp nhau."""
    import unicodedata
    nfc = unicodedata.normalize("NFC", "Tiếng Việt")
    nfd = unicodedata.normalize("NFD", "Tiếng Việt")
    assert nfc != nfd
    assert analytics.values_match(nfc, nfd) is True


# ─────────────────────────────────────────────────────────────
# CỠ MẪU TỐI THIỂU — KT-AN-06 🔴
# ─────────────────────────────────────────────────────────────

def test_duoi_nguong_mau_khong_tra_ty_le():
    """
    🔴 Dưới cỡ mẫu tối thiểu phải trả `None`, KHÔNG trả %.

    Một trường có 3 quan sát mà báo "100% chính xác" là con số gây hiểu nhầm nguy hiểm hơn là không
    có con số nào — và nó sẽ đi thẳng vào hồ sơ dự thi nếu không chặn ở đây.
    """
    assert analytics.accuracy_percent(3, 3) is None
    assert analytics.accuracy_percent(0, 5) is None


def test_du_mau_thi_tra_ty_le():
    assert analytics.accuracy_percent(45, 50) == 90.0


def test_nguong_mau_doi_duoc_bang_bien_moi_truong(monkeypatch):
    monkeypatch.setattr(analytics, "ACCURACY_MIN_SAMPLE", 5)
    assert analytics.accuracy_percent(4, 5) == 80.0


def test_gop_ket_qua_luon_kem_co_mau():
    """Mọi dòng kết quả PHẢI có `sample_size` — % không kèm cỡ mẫu là số liệu không dùng được."""
    rows = [
        {"field_key": "dc.title", "ai_value": "A", "approved_value": "A"},
        {"field_key": "dc.title", "ai_value": "B", "approved_value": "C"},
    ]
    ket_qua = analytics._aggregate_accuracy(rows, key="field_key")

    assert ket_qua[0]["sample_size"] == 2
    assert ket_qua[0]["so_dung"] == 1


def test_truong_it_mau_van_xuat_hien_kem_ghi_chu():
    """
    Trường ít mẫu vẫn hiện trong bảng, với ghi chú "chưa đủ dữ liệu".

    Ẩn hẳn chúng đi sẽ tạo ấn tượng sai rằng mọi trường đều đã đo được.
    """
    rows = [{"field_key": "dc.isbn", "ai_value": "X", "approved_value": "X"}]
    ket_qua = analytics._aggregate_accuracy(rows, key="field_key")

    assert ket_qua[0]["do_chinh_xac"] is None
    assert ket_qua[0]["ghi_chu"] == analytics.INSUFFICIENT


def test_sap_theo_co_mau_giam_dan():
    """Trường đo được nhiều nhất là trường đáng tin nhất → đưa lên trước."""
    rows = ([{"field_key": "it", "ai_value": "a", "approved_value": "a"}]
            + [{"field_key": "nhieu", "ai_value": "a", "approved_value": "a"}] * 5)
    ket_qua = analytics._aggregate_accuracy(rows, key="field_key")

    assert ket_qua[0]["field_key"] == "nhieu"


def test_ghi_chu_phuong_phap_noi_ro_gioi_han():
    """
    Ghi chú phương pháp phải nói rõ đây KHÔNG phải đáp án chuẩn độc lập.

    Thiếu câu này thì số liệu dễ bị trích vào hồ sơ như thể đã đối chiếu BD-01.
    """
    assert "cán bộ đã duyệt" in analytics.METHOD_NOTE
    assert "BD-01" in analytics.METHOD_NOTE
    assert str(analytics.ACCURACY_MIN_SAMPLE) in analytics.METHOD_NOTE


# ─────────────────────────────────────────────────────────────
# CHI PHÍ — tiền là SỐ NGUYÊN
# ─────────────────────────────────────────────────────────────

def test_che_do_tai_cho_khong_ton_tien():
    """Model chạy trên máy chủ Nhà trường không phát sinh chi phí theo lượt gọi."""
    cost = pricing.compute_cost("ollama", "local", "qwen2.5", 10000, 500)

    assert cost.vnd == 0
    assert cost.micro_usd == 0
    assert cost.known is True, "0 đồng vì chạy tại chỗ là điều CHẮC CHẮN, không phải 'chưa biết'"


def test_khong_bao_token_thi_khong_biet_chi_phi():
    """
    Không có số token → `known=False`, KHÔNG phải 0 đồng.

    Giao diện phải phân biệt "0 đồng vì chạy tại chỗ" với "chưa biết vì công cụ không báo token" —
    hai điều đó dẫn tới hai hành động khác nhau.
    """
    cost = pricing.compute_cost("claude", "cloud", "claude-sonnet-4", None, None)
    assert cost.known is False


def test_chua_co_don_gia_thi_khong_bia_so():
    cost = pricing.compute_cost("cong-cu-la", "cloud", "model-la", 1000, 100)
    assert cost.known is False


def test_moi_gia_tri_tien_deu_la_so_nguyen():
    """🔴 Quy ước dự án: tiền KHÔNG BAO GIỜ dùng dấu phẩy động."""
    cost = pricing.compute_cost("claude", "cloud", "claude-sonnet-4", 123457, 7891)

    assert isinstance(cost.micro_usd, int)
    assert isinstance(cost.vnd, int)


def test_tinh_chi_phi_dung_don_gia(monkeypatch):
    """1 triệu token vào của claude-sonnet-4 = 3 USD = 3.000.000 micro-USD."""
    monkeypatch.setenv("USD_VND_RATE", "25000")
    cost = pricing.compute_cost("claude", "cloud", "claude-sonnet-4",
                                prompt_tokens=1_000_000, completion_tokens=0)

    assert cost.micro_usd == 3_000_000
    assert cost.vnd == 75_000            # 3 USD × 25.000


def test_khop_don_gia_theo_tien_to_ten_model():
    """
    Tên model có hậu tố ngày (`claude-sonnet-4-20250514`) phải khớp đơn giá của họ model.

    Không lùi dần thì mỗi lần nhà cung cấp đổi hậu tố là mất đơn giá và báo cáo chi phí thành trống.
    """
    cost = pricing.compute_cost("claude", "cloud", "claude-sonnet-4-20250514",
                                prompt_tokens=1_000_000, completion_tokens=0)
    assert cost.known is True
    assert cost.micro_usd == 3_000_000


def test_ty_gia_sai_lui_ve_mac_dinh(monkeypatch):
    """Tỉ giá hỏng trong `.env` không được làm gãy việc ghi nhật ký gọi model."""
    monkeypatch.setenv("USD_VND_RATE", "khong-phai-so")
    assert pricing.usd_vnd_rate() == pricing.DEFAULT_USD_VND_RATE

    monkeypatch.setenv("USD_VND_RATE", "-100")
    assert pricing.usd_vnd_rate() == pricing.DEFAULT_USD_VND_RATE


def test_dinh_dang_tien_theo_quy_uoc_du_an():
    """Quy ước: `N.NNN.NNN đ`."""
    assert pricing.format_vnd(1234567) == "1.234.567 đ"
    assert pricing.format_vnd(0) == "0 đ"


def test_khong_hien_0_dong_khi_chua_co_so_lieu():
    """Hiển thị "0 đ" cho dữ liệu chưa biết là nói sai — phải nói rõ là chưa có."""
    assert pricing.format_vnd(None) == "chưa có số liệu"


def test_doc_de_don_gia_tu_tep(tmp_path, monkeypatch):
    """
    Đơn giá nhà cung cấp thay đổi theo thời gian — phải đổi được mà không sửa mã và build lại image.
    """
    import json
    tep = tmp_path / "gia.json"
    tep.write_text(json.dumps({"claude:claude-sonnet-4": {"in": 1, "out": 2}}), encoding="utf-8")
    monkeypatch.setenv("MODEL_PRICING_FILE", str(tep))

    bang = pricing.load_pricing()

    assert bang["claude:claude-sonnet-4"] == {"in": 1, "out": 2}
    assert "openai:gpt-4o" in bang, "đọc đè phải GIỮ các model khác, không thay thế cả bảng"


def test_tep_don_gia_hong_khong_lam_gay(tmp_path, monkeypatch):
    tep = tmp_path / "hong.json"
    tep.write_text("{khong phai json", encoding="utf-8")
    monkeypatch.setenv("MODEL_PRICING_FILE", str(tep))

    bang = pricing.load_pricing()
    assert "claude:claude-sonnet-4" in bang, "phải lùi về bảng trong mã"
