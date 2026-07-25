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

# Chế độ triển khai của một provider (YC-DR-03).
# LƯU Ý QUAN TRỌNG: đây là thuộc tính KHÁC với `name`.
#   - `name`       = danh tính công cụ ("claude", "ollama", "vllm", "gemini"...) → ghi vào log (YC-MP-06)
#   - `deployment` = dữ liệu chạy Ở ĐÂU ("cloud" = ra ngoài tổ chức | "local" = trong hạ tầng của trường)
# Ràng buộc cứng YC-DR-03 chỉ dựa vào `deployment`, KHÔNG dựa vào `name`.
DEPLOY_CLOUD = "cloud"
DEPLOY_LOCAL = "local"


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

    #: định danh CÔNG CỤ, vd "claude", "ollama", "vllm", "gemini", "openai"
    name: str = "base"
    #: chế độ triển khai: DEPLOY_CLOUD | DEPLOY_LOCAL — quyết định ràng buộc cứng YC-DR-03.
    #: Mặc định là CLOUD (mặc định an toàn: lớp con chưa khai báo thì bị coi là "ra ngoài",
    #: nên KHÔNG được nhận tài liệu Nội bộ/Nhạy cảm — thà từ chối oan hơn để lộ dữ liệu).
    deployment: str = DEPLOY_CLOUD
    #: tên model đang dùng cho trích xuất, vd "claude-sonnet-4", "qwen2.5:7b"
    model: str = ""
    #: model dùng cho embedding (YC-MS-05: tác vụ khác nhau có thể dùng model khác nhau)
    embed_model: str = ""
    #: phiên bản model nếu có
    version: str = ""
    #: điểm cuối đang gọi (chỉ host/đường dẫn — TUYỆT ĐỐI không chứa khóa API, YC-BM-03)
    endpoint: str = ""

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
        info = {
            "provider": self.name,
            "deployment": self.deployment,
            "model": self.model,
            "version": self.version,
        }
        if self.embed_model:
            info["embed_model"] = self.embed_model
        if self.endpoint:
            info["endpoint"] = self.endpoint
        return info
