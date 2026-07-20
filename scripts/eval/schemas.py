#!/usr/bin/env python3
"""
Lược đồ trích xuất định nghĩa dạng DỮ LIỆU (mầm mống YC-SC-01). GĐ0: định nghĩa trong mã là chấp nhận
được (YC-SC-03 "bản thô"); GĐ2 sẽ nạp từ DB + giao diện quản trị.

- dublin_core (book/thesis): khớp hành vi hiện tại → dùng cho KT-KH (không hồi quy) + KT-CX trên sách.
- cong_van: lược đồ công văn hành chính (YC-SC-03). Cần generic schema-driven prompt (bước kế) để
  provider trích xuất theo lược đồ này — hiện định nghĩa sẵn để harness/đáp án chuẩn tham chiếu.
"""

from scripts.providers.base import (
    ExtractionSchema, SchemaField,
    SENSITIVITY_PUBLIC, SENSITIVITY_INTERNAL,
)


def dublin_core_schema(document_type: str = "book") -> ExtractionSchema:
    """Lược đồ Dublin Core hiện hành (16 trường) — provider dùng prompt book/thesis sẵn có."""
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
    return ExtractionSchema(
        code="dublin_core",
        document_type=document_type,      # book | thesis
        fields=fields,
        context_strategy="first8_last2",  # đúng hành vi hiện tại
        sensitivity=SENSITIVITY_PUBLIC,   # tài liệu thư viện: công khai
    )


def cong_van_schema() -> ExtractionSchema:
    """Lược đồ công văn hành chính (YC-SC-03). Độ nhạy cảm mặc định: Nội bộ (mặc định an toàn)."""
    fields = [
        SchemaField("so_hieu", "Số hiệu", required=True),
        SchemaField("ngay_ban_hanh", "Ngày ban hành", data_type="date"),
        SchemaField("co_quan_ban_hanh", "Cơ quan ban hành", required=True),
        SchemaField("loai_van_ban", "Loại văn bản"),
        SchemaField("trich_yeu", "Trích yếu", required=True),
        SchemaField("do_khan", "Độ khẩn"),
        SchemaField("do_mat", "Độ mật"),
        SchemaField("noi_nhan", "Nơi nhận", data_type="list"),
        SchemaField("nguoi_ky", "Người ký"),
    ]
    return ExtractionSchema(
        code="cong_van",
        document_type="cong_van",
        fields=fields,
        context_strategy="full",          # công văn ngắn: đọc toàn văn (sửa lỗ hổng 8 trang đầu/2 cuối)
        sensitivity=SENSITIVITY_INTERNAL, # mặc định an toàn (YC-DR-02)
    )


_REGISTRY = {
    "dublin_core": lambda: dublin_core_schema("book"),
    "book": lambda: dublin_core_schema("book"),
    "thesis": lambda: dublin_core_schema("thesis"),
    "cong_van": cong_van_schema,
}


def get_schema(name: str) -> ExtractionSchema:
    """Lấy lược đồ theo tên. Ném KeyError nếu không có."""
    key = name.lower().strip()
    if key not in _REGISTRY:
        raise KeyError(f"Không có lược đồ '{name}'. Có: {', '.join(_REGISTRY)}")
    return _REGISTRY[key]()
