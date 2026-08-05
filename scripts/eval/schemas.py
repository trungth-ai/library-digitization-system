#!/usr/bin/env python3
"""
Lược đồ trích xuất theo BỘ MẪU BIÊN MỤC HPU (docs/CATALOG_SCHEMAS.md).

7 loại tài liệu → 3 nhóm cấu trúc Dublin Core + công văn hành chính:
- Nhóm SÁCH   (sach, de_cuong):        + editor, title.alternative, isbn
- Nhóm LUẬN   (khoa_luan, luan_van):   + advisor, degree
- Nhóm BÀI VIẾT (hoi_thao, bao_nckh):  + advisor (tùy), degree, department
- Công văn    (cong_van):              trường hành chính riêng

Mỗi trường có `source`:
  ai     — model trích từ nội dung (có điểm tin cậy, cán bộ duyệt)
  system — hệ thống sinh từ file/PDF (số trang, dung lượng, mimetype, dc.type)
  manual — người biên mục nhập (dc.identifier.other = mã HPU; AI KHÔNG được đoán)

Giữ `dublin_core`/`book`/`thesis` (đường cũ, không hồi quy KT-KH); 6 lược đồ mới dùng generic prompt.
"""

from scripts.providers.base import (
    ExtractionSchema, SchemaField,
    SENSITIVITY_PUBLIC, SENSITIVITY_INTERNAL,
    SOURCE_AI, SOURCE_SYSTEM, SOURCE_MANUAL,
)


# ---------------------------------------------------------------------
# Trường dùng chung
# ---------------------------------------------------------------------

def _f_ma_hpu():
    return SchemaField("dc.identifier.other", "Mã tài liệu (HPU)", required=True,
                       source=SOURCE_MANUAL, description="Mã kho thư viện gán khi nhập — người biên mục điền, AI không đoán")


def _f_system(dc_type: str):
    """Trường hệ thống tự sinh: dc.type (cố định theo loại), số trang, dung lượng, định dạng."""
    return [
        SchemaField("dc.type", "Loại tài liệu", required=True, language="en_US",
                    source=SOURCE_SYSTEM, description=f"Cố định = {dc_type}"),
        SchemaField("dc.format.extent", "Số trang", source=SOURCE_SYSTEM, description="Đếm từ PDF"),
        SchemaField("dc.size", "Dung lượng", language="en_US", source=SOURCE_SYSTEM, description="Từ kích thước file"),
        SchemaField("dc.format.mimetype", "Định dạng", source=SOURCE_SYSTEM, description="application/pdf"),
    ]


def _schema_sach(code: str, name: str, document_type: str, dc_type: str) -> ExtractionSchema:
    """Nhóm SÁCH: có editor, title.alternative, isbn."""
    fields = [
        _f_ma_hpu(),
        SchemaField("dc.title", "Nhan đề", required=True, language="vi_VN"),
        SchemaField("dc.title.alternative", "Nhan đề khác", language="vi_VN"),
        SchemaField("dc.contributor.author", "Tác giả", required=True, data_type="list", language="vi_VN"),
        SchemaField("dc.contributor.editor", "Biên tập / Chủ biên", data_type="list", language="vi_VN"),
        SchemaField("dc.publisher", "Nhà xuất bản", language="vi_VN"),
        SchemaField("dc.date.issued", "Năm xuất bản", data_type="number"),
        SchemaField("dc.subject", "Từ khóa", required=True, data_type="list", language="vi_VN"),
        SchemaField("dc.description.abstract", "Tóm tắt", language="vi_VN"),
        SchemaField("dc.identifier.isbn", "ISBN"),
        SchemaField("dc.language.iso", "Ngôn ngữ"),
        SchemaField("dc.department", "Bộ sưu tập / Khoa", language="en_US"),
        *_f_system(dc_type),
    ]
    return ExtractionSchema(code=code, name=name, document_type=document_type, fields=fields,
                            context_strategy="first8_last2", sensitivity=SENSITIVITY_PUBLIC)


def _schema_luan(code: str, name: str, document_type: str, dc_type: str = "Thesis") -> ExtractionSchema:
    """Nhóm LUẬN: có advisor, degree."""
    fields = [
        _f_ma_hpu(),
        SchemaField("dc.title", "Nhan đề", required=True, language="vi_VN"),
        SchemaField("dc.contributor.author", "Tác giả", required=True, data_type="list", language="vi_VN"),
        SchemaField("dc.contributor.advisor", "Người hướng dẫn", required=True, data_type="list", language="vi_VN"),
        SchemaField("dc.publisher", "Đơn vị đào tạo", language="vi_VN"),
        SchemaField("dc.date.issued", "Năm bảo vệ", data_type="number"),
        SchemaField("dc.subject", "Từ khóa", required=True, data_type="list", language="vi_VN"),
        SchemaField("dc.description.abstract", "Tóm tắt", language="vi_VN"),
        SchemaField("dc.description.degree", "Học vị / Loại", language="en_US",
                    description="vd Đồ án, Khóa luận, Thạc sỹ"),
        SchemaField("dc.language.iso", "Ngôn ngữ"),
        SchemaField("dc.department", "Khoa / Bộ môn", language="en_US"),
        *_f_system(dc_type),
    ]
    return ExtractionSchema(code=code, name=name, document_type=document_type, fields=fields,
                            context_strategy="first8_last2", sensitivity=SENSITIVITY_PUBLIC)


def _schema_baiviet(code: str, name: str, document_type: str, dc_type: str) -> ExtractionSchema:
    """Nhóm BÀI VIẾT (hội thảo, báo NCKH): advisor tùy chọn, degree = loại bài, có department (lĩnh vực)."""
    fields = [
        _f_ma_hpu(),
        SchemaField("dc.title", "Nhan đề", required=True, language="vi_VN"),
        SchemaField("dc.contributor.author", "Tác giả", required=True, data_type="list", language="vi_VN"),
        SchemaField("dc.contributor.advisor", "Người hướng dẫn", data_type="list", language="vi_VN"),
        SchemaField("dc.publisher", "Nơi công bố / Tạp chí", language="vi_VN"),
        SchemaField("dc.date.issued", "Năm công bố", data_type="number"),
        SchemaField("dc.subject", "Từ khóa", required=True, data_type="list", language="vi_VN"),
        SchemaField("dc.description.abstract", "Tóm tắt", language="vi_VN"),
        SchemaField("dc.description.degree", "Loại bài", language="en_US", description="vd Bài báo khoa học"),
        SchemaField("dc.language.iso", "Ngôn ngữ"),
        SchemaField("dc.department", "Lĩnh vực / Khoa", language="en_US"),
        *_f_system(dc_type),
    ]
    return ExtractionSchema(code=code, name=name, document_type=document_type, fields=fields,
                            context_strategy="first8_last2", sensitivity=SENSITIVITY_PUBLIC)


# ---------------------------------------------------------------------
# Lược đồ CŨ (giữ nguyên cho tương thích + không hồi quy KT-KH đường Claude)
# ---------------------------------------------------------------------

def dublin_core_schema(document_type: str = "book") -> ExtractionSchema:
    """Lược đồ Dublin Core generic cũ (book/thesis dùng prompt _get_unified_prompt sẵn có)."""
    fields = [
        SchemaField("dc.title", "Tiêu đề", required=True, language="vi_VN"),
        SchemaField("dc.title.alternative", "Tiêu đề phụ", language="en_US"),
        SchemaField("dc.contributor.author", "Tác giả", required=True, data_type="list", language="vi_VN"),
        SchemaField("dc.contributor.advisor", "Giảng viên hướng dẫn", data_type="list", language="vi_VN"),
        SchemaField("dc.publisher", "Nhà xuất bản", language="vi_VN"),
        SchemaField("dc.date.issued", "Năm xuất bản", data_type="number"),
        SchemaField("dc.subject", "Từ khóa", data_type="list", language="vi_VN"),
        SchemaField("dc.description.abstract", "Tóm tắt", language="vi_VN"),
        SchemaField("dc.type", "Loại", required=True, language="en_US"),
        SchemaField("dc.language.iso", "Ngôn ngữ"),
        SchemaField("dc.identifier.isbn", "ISBN"),
    ]
    return ExtractionSchema(code="dublin_core", document_type=document_type, fields=fields,
                            context_strategy="first8_last2", sensitivity=SENSITIVITY_PUBLIC)


def cong_van_schema() -> ExtractionSchema:
    """Lược đồ công văn hành chính (YC-SC-03) — mở rộng theo bộ mẫu biên mục."""
    fields = [
        SchemaField("so_hieu", "Số, ký hiệu văn bản", required=True),
        SchemaField("loai_van_ban", "Loại văn bản"),
        SchemaField("ngay_ban_hanh", "Ngày ban hành", data_type="date"),
        SchemaField("don_vi_ban_hanh", "Đơn vị/bộ phận ban hành"),
        SchemaField("co_quan_ban_hanh", "Cơ quan ban hành", required=True),
        SchemaField("noi_ban_hanh", "Nơi ban hành"),
        SchemaField("nguoi_ky", "Người ký"),
        SchemaField("chuc_vu_nguoi_ky", "Chức vụ người ký"),
        SchemaField("nhan_de", "Nhan đề văn bản"),
        SchemaField("trich_yeu", "Trích yếu nội dung", required=True),
        SchemaField("tu_khoa", "Từ khóa", data_type="list"),
        SchemaField("noi_nhan", "Nơi nhận", data_type="list"),
        SchemaField("do_khan", "Độ khẩn"),
        SchemaField("do_mat", "Độ mật"),
        SchemaField("so_trang", "Số trang", source=SOURCE_SYSTEM, description="Đếm từ PDF"),
        SchemaField("dung_luong", "Dung lượng tệp", source=SOURCE_SYSTEM, description="Từ kích thước file"),
    ]
    return ExtractionSchema(code="cong_van", name="Công văn hành chính", document_type="cong_van",
                            fields=fields, context_strategy="full", sensitivity=SENSITIVITY_INTERNAL)


# ---------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------

_REGISTRY = {
    # 7 loại theo bộ mẫu biên mục — document_type RIÊNG cho từng loại (không trùng 'book' của
    # lược đồ dublin_core cũ → resolve_schema('book') vẫn ra Claude cũ, không hồi quy KT-KH).
    "sach":      lambda: _schema_sach("sach", "Sách", "sach", "Book"),
    "de_cuong":  lambda: _schema_sach("de_cuong", "Đề cương môn học", "de_cuong", "Presentation"),
    "khoa_luan": lambda: _schema_luan("khoa_luan", "Khóa luận / Đồ án", "khoa_luan", "Thesis"),
    "luan_van":  lambda: _schema_luan("luan_van", "Luận văn thạc sỹ", "luan_van", "Thesis"),
    "hoi_thao":  lambda: _schema_baiviet("hoi_thao", "Kỷ yếu hội thảo", "hoi_thao", "Presentation"),
    "bao_nckh":  lambda: _schema_baiviet("bao_nckh", "Báo / Tạp chí NCKH", "bao_nckh", "Article"),
    "cong_van":  cong_van_schema,
    # Tương thích cũ (đường Claude unified prompt — KT-KH)
    "dublin_core": lambda: dublin_core_schema("book"),
    "book":        lambda: dublin_core_schema("book"),
    "thesis":      lambda: dublin_core_schema("thesis"),
}


def get_schema(name: str) -> ExtractionSchema:
    """Lấy lược đồ theo tên. Ném KeyError nếu không có."""
    key = name.lower().strip()
    if key not in _REGISTRY:
        raise KeyError(f"Không có lược đồ '{name}'. Có: {', '.join(_REGISTRY)}")
    return _REGISTRY[key]()


def all_catalog_schemas():
    """7 lược đồ biên mục chính thức (để seed DB / hiển thị) — không gồm alias tương thích."""
    return [_REGISTRY[c]() for c in
            ("sach", "de_cuong", "khoa_luan", "luan_van", "hoi_thao", "bao_nckh", "cong_van")]
