#!/usr/bin/env python3
"""
Giao diện chung cho nhà cung cấp mô hình (YC-MP-01, YC-MP-08).

NGUYÊN TẮC (SRS mục 2.1):
- Toàn hệ thống chỉ gọi model QUA `ModelProvider`, KHÔNG gọi trực tiếp Anthropic/Ollama/... ở nơi khác.
- Giao diện phải đủ tổng quát để thêm công cụ mới = viết THÊM một lớp hiện thực (một file), KHÔNG sửa
  giao diện này, KHÔNG sửa phần còn lại của hệ thống (phép thử YC-MP-08 / KT-CN-06c).
- Ba năng lực: trích xuất trường theo lược đồ, tạo embedding (cho RAG - GĐ3), kiểm tra sẵn sàng (YC-MS-04).

Thứ tự phát triển (SRS): viết giao diện này TRƯỚC, chọn công cụ SAU.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


# =====================================================================
# LƯỢC ĐỒ TRÍCH XUẤT (schema) — bản tối thiểu cho GĐ0.
# GĐ2 (YC-SC) sẽ nạp schema từ DB; ở GĐ0 dựng schema trong mã là chấp nhận được.
# =====================================================================

@dataclass
class SchemaField:
    """Một trường trong lược đồ trích xuất."""
    key: str                       # vd "dc.title", "so_hieu"
    label: str = ""                # nhãn hiển thị tiếng Việt
    required: bool = False
    data_type: str = "text"        # text | date | number | list
    language: Optional[str] = None # vd "vi_VN", "en_US"
    description: str = ""


# Độ nhạy cảm (YC-DR-01) — dùng cho định tuyến ở GĐ1
SENSITIVITY_PUBLIC = "public"       # Công khai
SENSITIVITY_INTERNAL = "internal"   # Nội bộ
SENSITIVITY_SENSITIVE = "sensitive" # Nhạy cảm


@dataclass
class ExtractionSchema:
    """
    Định nghĩa cách trích xuất một loại tài liệu.
    `context_strategy` là thuộc tính của lược đồ (YC-SC-04) — thay cho hằng số cứng "8 trang đầu/2 cuối".
    """
    code: str                              # vd "dublin_core", "cong_van"
    name: str = ""                         # nhãn hiển thị lược đồ
    document_type: str = "book"            # book | thesis | cong_van | ...
    fields: List[SchemaField] = field(default_factory=list)
    context_strategy: str = "first8_last2" # chiến lược chọn ngữ cảnh
    sensitivity: str = SENSITIVITY_PUBLIC  # mặc định; "không rõ" sẽ do tầng định tuyến xử lý (YC-DR-02)


# =====================================================================
# KẾT QUẢ TRÍCH XUẤT
# =====================================================================

@dataclass
class FieldValue:
    """Một giá trị trường được trích xuất, giữ tương thích cấu trúc metadata cũ (key/value/language)."""
    key: str
    value: str
    language: Optional[str] = None
    confidence: Optional[float] = None  # YC-CF-01 — chưa dùng ở GĐ0, để sẵn cho GĐ1


@dataclass
class ExtractionResult:
    """Kết quả trích xuất từ một provider."""
    fields: List[FieldValue] = field(default_factory=list)
    raw: Optional[dict] = None          # dữ liệu thô của model (debug)

    def to_metadata_list(self) -> List[dict]:
        """Chuyển về định dạng metadata cũ [{key, value, language}] — giữ tương thích db.save_metadata."""
        out = []
        for f in self.fields:
            item = {"key": f.key, "value": f.value, "language": f.language}
            if f.confidence is not None:
                item["confidence"] = f.confidence
            out.append(item)
        return out


@dataclass
class ProviderHealth:
    """Kết quả kiểm tra sẵn sàng (YC-MS-04)."""
    ready: bool
    detail: str = ""


# =====================================================================
# GIAO DIỆN NHÀ CUNG CẤP MÔ HÌNH
# =====================================================================

class ModelProvider(ABC):
    """
    Giao diện chung. Mỗi công cụ (Claude đám mây, Ollama tại chỗ, ...) là một lớp con.

    Thuộc tính `name`/`model`/`version` phục vụ ghi nhật ký mỗi lần gọi model (YC-MP-06).
    """

    #: định danh nhà cung cấp, vd "cloud", "local"
    name: str = "base"
    #: tên model đang dùng, vd "claude-sonnet-4", "qwen2.5:7b"
    model: str = ""
    #: phiên bản model nếu có
    version: str = ""

    @abstractmethod
    def extract_fields(self, text: str, schema: ExtractionSchema) -> ExtractionResult:
        """Trích xuất các trường theo lược đồ từ văn bản. Ném ProviderUnavailable nếu không gọi được."""
        raise NotImplementedError

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Tạo embedding cho danh sách văn bản (phục vụ RAG - GĐ3)."""
        raise NotImplementedError

    @abstractmethod
    def health(self) -> ProviderHealth:
        """Kiểm tra provider có sẵn sàng nhận việc không (YC-MS-04)."""
        raise NotImplementedError

    def describe(self) -> dict:
        """Thông tin nhận dạng provider — nhúng vào log/audit (YC-MP-06, YC-AU-04)."""
        return {"provider": self.name, "model": self.model, "version": self.version}
