#!/usr/bin/env python3
"""
Kiểm thử đoán loại tài liệu (YC-SC-09) — KT-SC-09→17.

Trọng tâm KHÔNG phải "đoán đúng mọi lúc" (không thể), mà là bốn tính chất phải giữ:
  1. Bản quét MẤT DẤU vẫn nhận ra được — OCR tiếng Việt hỏng dấu là chuyện thường ngày.
  2. Nội dung THẮNG tên tệp khi hai nguồn mâu thuẫn.
  3. Bằng chứng mỏng → độ tin cậy THẤP (chứ không phải đoán bừa với vẻ tự tin).
  4. Không bao giờ ném lỗi ra ngoài: đoán loại hỏng thì tài liệu vẫn phải được số hóa.

Chạy: pytest tests/test_doc_classifier.py -v
"""

import pytest

from scripts.core import doc_classifier as dc


# =====================================================================
# CHUẨN HÓA
# =====================================================================

def test_bo_dau_ke_ca_chu_d():
    assert dc.strip_accents("Luận văn Thạc sỹ") == "luan van thac sy"
    # 'đ' không tách được bằng NFD — phải thay tay, nếu không "đề cương" sẽ thành "ề cương"
    assert dc.strip_accents("Đề cương môn học") == "de cuong mon hoc"
    assert dc.strip_accents("") == ""


# =====================================================================
# TẦNG 1 — TÊN TỆP
# =====================================================================

@pytest.mark.parametrize("filename,expected", [
    ("KL_NguyenVanA_2024.pdf", "khoa_luan"),
    ("DATN_TranThiB.pdf", "khoa_luan"),
    ("Luan van thac si - Le Van C.pdf", "luan_van"),
    ("CV_123-QD-HPU.pdf", "cong_van"),
    ("De cuong chi tiet - Toan cao cap.pdf", "de_cuong"),
    ("Ky yeu hoi thao 2025.pdf", "hoi_thao"),
    ("Tap chi NCKH so 12.pdf", "bao_nckh"),
    ("Giao trinh Vat ly dai cuong.pdf", "sach"),
])
def test_doan_tu_ten_tep(filename, expected):
    assert dc.suggest_from_filename(filename).document_type == expected


def test_ten_tep_vo_nghia_khong_doan_bua():
    goi_y = dc.suggest_from_filename("scan_0001.pdf")
    assert goi_y.document_type == dc.FALLBACK_TYPE
    assert goi_y.confidence == 0.0
    assert goi_y.source == "none"


def test_ten_tep_rong():
    assert dc.suggest_from_filename("").source == "none"


# =====================================================================
# TẦNG 2 — NỘI DUNG
# =====================================================================

CONG_VAN = """
CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
Số: 123/TB-DHDL      V/v thông báo lịch nghỉ lễ
Kính gửi: Các đơn vị trực thuộc
Nơi nhận: Như trên, lưu VT.
"""

LUAN_VAN = """
TRƯỜNG ĐẠI HỌC QUẢN LÝ VÀ CÔNG NGHỆ HẢI PHÒNG
LUẬN VĂN THẠC SĨ
Chuyên ngành: Quản trị kinh doanh    Mã số: 8340101
Người hướng dẫn khoa học: PGS.TS. Nguyễn Văn A
"""

KHOA_LUAN = """
KHÓA LUẬN TỐT NGHIỆP ĐẠI HỌC
Sinh viên thực hiện: Trần Thị B      Lớp: QT2301N
Giảng viên hướng dẫn: ThS. Lê Văn C
"""

DE_CUONG = """
ĐỀ CƯƠNG CHI TIẾT HỌC PHẦN
Mã học phần: MAT101      Số tín chỉ: 3
Điều kiện tiên quyết: Không
Chuẩn đầu ra của học phần: sau khi học xong sinh viên có thể...
"""


@pytest.mark.parametrize("text,expected", [
    (CONG_VAN, "cong_van"),
    (LUAN_VAN, "luan_van"),
    (KHOA_LUAN, "khoa_luan"),
    (DE_CUONG, "de_cuong"),
])
def test_doan_tu_noi_dung(text, expected):
    goi_y = dc.suggest_from_text(text)
    assert goi_y.document_type == expected
    assert goi_y.confidence > 0


def test_ban_quet_mat_dau_van_nhan_ra():
    """OCR tiếng Việt rất hay mất dấu — đây là điều kiện sống còn của bộ đoán loại."""
    khong_dau = dc.strip_accents(LUAN_VAN)
    assert "ậ" not in khong_dau                       # chắc chắn đã mất dấu thật
    assert dc.suggest_from_text(khong_dau).document_type == "luan_van"


def test_noi_dung_thang_ten_tep_khi_mau_thuan():
    """
    Tệp đặt tên nhầm "sach_..." nhưng nội dung rõ ràng là công văn → phải theo NỘI DUNG.
    Tên tệp chỉ là ý định của người đặt tên; nội dung là sự thật của tài liệu.
    """
    goi_y = dc.suggest_from_text(CONG_VAN, filename="sach_giao_trinh_2024.pdf")
    assert goi_y.document_type == "cong_van"


def test_ten_tep_keo_lai_khi_noi_dung_mo():
    """Bản quét hỏng, OCR gần như không ra chữ → tên tệp vẫn phải cứu được."""
    goi_y = dc.suggest_from_text("...", filename="Luan van thac si Nguyen Van A.pdf")
    assert goi_y.document_type == "luan_van"


def test_bang_chung_mong_thi_tin_cay_thap():
    """Một từ khóa yếu lẻ loi không được cho ra một gợi ý trông đầy tự tin."""
    goi_y = dc.suggest_from_text("Tài liệu này có phần mục lục ở trang 3.")
    assert goi_y.confidence < dc.MODEL_CONFIDENCE_THRESHOLD
    assert not goi_y.confident


def test_do_dai_tai_lieu_khong_lam_lech_diem():
    """
    Lặp một từ khóa 50 lần không được làm tài liệu "thuộc loại đó hơn". Nếu đếm số lần khớp thay vì
    khớp một lần, điểm số sẽ phụ thuộc độ dài tài liệu chứ không phải loại tài liệu.
    """
    mot_lan = dc.suggest_from_text(CONG_VAN)
    lap_lai = dc.suggest_from_text(CONG_VAN + ("\nNơi nhận: Như trên." * 50))
    assert mot_lan.scores["cong_van"] == lap_lai.scores["cong_van"]


def test_van_ban_rong():
    assert dc.suggest_from_text("").source == "none"
    assert dc.suggest_from_text(None).document_type == dc.FALLBACK_TYPE


# =====================================================================
# GIẢI THÍCH ĐƯỢC
# =====================================================================

def test_co_bang_chung_de_can_bo_kiem_tra():
    """Điểm số trần trụi thì không ai dám tin — phải nói rõ đã thấy dấu hiệu gì."""
    goi_y = dc.suggest_from_text(LUAN_VAN)
    assert goi_y.evidence, "phải liệt kê được dấu hiệu đã khớp"
    assert "luan van thac si" in goi_y.evidence[0]
    ly_do = goi_y.reason_vi()
    assert "nội dung tài liệu" in ly_do and "luan van thac si" in ly_do


def test_to_dict_du_khoa_cho_giao_dien():
    d = dc.suggest_from_filename("KL_A.pdf").to_dict()
    assert set(d) == {"document_type", "label", "confidence", "source", "evidence", "reason"}
    assert d["label"] == "Khóa luận / Đồ án"


# =====================================================================
# CỜ 'TỰ ĐOÁN'
# =====================================================================

@pytest.mark.parametrize("value", ["auto", "AUTO", " auto ", "", None, "tu_dong"])
def test_nhan_dien_che_do_tu_doan(value):
    assert dc.is_auto(value)


@pytest.mark.parametrize("value", ["book", "sach", "cong_van"])
def test_loai_chon_tay_khong_bi_coi_la_tu_doan(value):
    assert not dc.is_auto(value)


# =====================================================================
# TẦNG 3 — MODEL (dùng lớp giả, không cần dịch vụ ngoài)
# =====================================================================

class _ProviderGia:
    """Provider giả trả về đúng một trường `loai_tai_lieu`."""

    def __init__(self, answer, raise_error=False):
        self.answer = answer
        self.raise_error = raise_error
        self.called_with = None

    def extract_fields(self, text, schema):
        from scripts.providers.base import ExtractionResult, FieldValue
        if self.raise_error:
            raise RuntimeError("model chết")
        self.called_with = (text, schema)
        return ExtractionResult(fields=[FieldValue(key="loai_tai_lieu", value=self.answer)])


def test_model_tra_ma_hop_le():
    goi_y = dc.classify_with_model("nội dung mơ hồ", _ProviderGia("hoi_thao"))
    assert goi_y.document_type == "hoi_thao"
    assert goi_y.source == "model"


def test_model_tra_kem_nhan_van_doc_duoc():
    """Model hay trả 'sach (Sách)' thay vì đúng mã — vẫn phải dò ra mã hợp lệ."""
    assert dc.classify_with_model("x", _ProviderGia("sach (Sách)")).document_type == "sach"


def test_model_tra_ma_la_thi_bo_qua():
    assert dc.classify_with_model("x", _ProviderGia("ban_do_dia_ly")) is None


def test_model_chet_khong_lam_hong_gi():
    """Đoán loại là việc PHỤ — model chết thì trả None, tuyệt đối không ném lỗi lên trên."""
    assert dc.classify_with_model("x", _ProviderGia("sach", raise_error=True)) is None


def test_luoc_do_hoi_model_chi_co_mot_truong():
    """Dùng lược đồ một trường để tái dùng `extract_fields` — không thêm phương thức vào giao diện."""
    provider = _ProviderGia("sach")
    dc.classify_with_model("nội dung", provider)
    _, schema = provider.called_with
    assert len(schema.fields) == 1
    assert schema.fields[0].key == "loai_tai_lieu"
    # Nhãn phải liệt kê đủ 7 mã hợp lệ, nếu không model không biết được phép trả gì
    for code in dc.KNOWN_TYPES:
        assert code in schema.fields[0].label


# =====================================================================
# ĐIỀU PHỐI — leo thang rẻ trước đắt sau
# =====================================================================

def test_tu_khoa_du_tu_tin_thi_khong_goi_model():
    """Lô hàng nghìn tệp đặt tên đúng quy ước không được tốn lượt gọi model nào."""
    provider = _ProviderGia("sach")
    ket_qua = dc.classify(CONG_VAN, filename="CV_123.pdf", provider=provider)
    assert ket_qua.document_type == "cong_van"
    assert provider.called_with is None, "đã đủ tự tin mà vẫn gọi model"


def test_khong_tu_tin_thi_hoi_model():
    provider = _ProviderGia("bao_nckh")
    ket_qua = dc.classify("một đoạn văn không có dấu hiệu gì", provider=provider)
    assert provider.called_with is not None
    assert ket_qua.document_type == "bao_nckh"


def test_khong_co_provider_thi_dung_ket_qua_tu_khoa():
    ket_qua = dc.classify("văn bản mơ hồ", provider=None)
    assert ket_qua.source in ("none", "text")


def test_model_va_tu_khoa_cung_ket_luan_thi_tin_hon():
    """Hai nguồn độc lập cùng chỉ về một loại thì đáng tin hơn từng nguồn riêng lẻ."""
    text = "Tài liệu có mục lục và lời nói đầu."          # dấu hiệu 'sach' yếu
    chi_tu_khoa = dc.suggest_from_text(text)
    assert not chi_tu_khoa.confident                       # đúng là chưa đủ tự tin

    ket_qua = dc.classify(text, provider=_ProviderGia("sach"))
    assert ket_qua.document_type == "sach"
    assert ket_qua.confidence > chi_tu_khoa.confidence
