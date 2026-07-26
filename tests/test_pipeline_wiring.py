#!/usr/bin/env python3
"""
Kiểm thử việc NỐI pipeline vào lớp provider (ADR-008) — phần rủi ro nhất của lần nâng cấp này, vì nó
chạm vào đường xử lý tài liệu thật.

Nguyên tắc kiểm: mọi thứ mock, không cần DB/mạng/pypdf → chạy được ở máy dev và khi ngắt mạng.
Ba nhóm câu hỏi:
  1. Trích xuất qua lớp provider có trả đúng ĐỊNH DẠNG mà pipeline/worker đang chờ không?
  2. Các nhánh XẤU (model lỗi, không hợp lệ, điểm thấp, vi phạm độ nhạy cảm) có xử lý đúng không?
  3. Dự phòng chéo công cụ có TUYỆT ĐỐI không đổi chế độ triển khai không?

Chạy: pytest tests/test_pipeline_wiring.py -v
"""

import pytest

from scripts.core import metrics
from scripts.core.exceptions import SensitivityViolation
from scripts.core.extraction import (
    FULL_MAX_CHARS, LEGACY_MAX_CHARS, LEGACY_MAX_PAGES,
    ProviderMetadataExtractor, resolve_schema, select_context,
)
from scripts.providers import fallback
from scripts.providers.base import (
    DEPLOY_CLOUD, DEPLOY_LOCAL, ExtractionResult, ExtractionSchema, FieldValue,
    ProviderHealth, SchemaField, SENSITIVITY_PUBLIC, SENSITIVITY_SENSITIVE,
)


class _Config:
    """ProcessingConfig tối giản — tránh phụ thuộc digitize khi chỉ cần vài thuộc tính."""
    document_type = "book"
    claude_model = "test-model"
    max_tokens = 1000


class _FakeProvider:
    """Provider giả: trả đúng những gì test cần, không gọi mạng."""

    def __init__(self, name="ollama", deployment=DEPLOY_LOCAL, fields=None,
                 ready=True, raise_on_extract=False):
        self.name = name
        self.deployment = deployment
        self.model = "model-gia-lap"
        self.version = ""
        self.endpoint = "http://ollama:11434"
        self._fields = fields
        self._ready = ready
        self._raise = raise_on_extract
        self.health_calls = 0

    def extract_fields(self, text, schema):
        if self._raise:
            raise RuntimeError("máy chủ model chết")
        if self._fields is not None:
            return ExtractionResult(fields=list(self._fields))
        return ExtractionResult(fields=[
            FieldValue(key="dc.title", value="Giáo trình cơ sở dữ liệu", language="vi_VN"),
            FieldValue(key="dc.type", value="Book", language="en_US"),
        ])

    def health(self):
        self.health_calls += 1
        return ProviderHealth(ready=self._ready, detail="ok" if self._ready else "chưa sẵn sàng")


def _patch_extraction(monkeypatch, provider, mode=DEPLOY_LOCAL, schema=None, text="Giáo trình cơ sở dữ liệu"):
    """Chặn 3 chỗ đi ra ngoài: lược đồ (DB), ngữ cảnh (pypdf), chọn provider (mạng)."""
    schema = schema or ExtractionSchema(
        code="dublin_core", document_type="book", sensitivity=SENSITIVITY_PUBLIC,
        fields=[SchemaField(key="dc.title", label="Tiêu đề", required=True)],
    )
    monkeypatch.setattr("scripts.core.extraction.resolve_schema", lambda dt: schema)
    monkeypatch.setattr("scripts.core.extraction.select_context", lambda p, s: text)
    monkeypatch.setattr("scripts.providers.router.resolve_mode", lambda s, r=None: mode)
    monkeypatch.setattr("scripts.providers.fallback.select_provider",
                        lambda m, config=None: (provider, None))
    # DB chưa có pool trong test → _persist tự bắt lỗi; chặn luôn cho log gọn
    monkeypatch.setattr("scripts.core.extraction.ProviderMetadataExtractor._persist",
                        lambda self, schema: None)
    return schema


# =====================================================================
# 1. ĐỊNH DẠNG TRẢ VỀ — pipeline và worker đang phụ thuộc vào nó
# =====================================================================

def test_tra_ve_dung_dinh_dang_cua_extractor_cu(monkeypatch):
    """Phải giữ khóa 'metadata' dạng [{key,value,language}] — JSONExporter và worker đọc đúng khóa này."""
    _patch_extraction(monkeypatch, _FakeProvider())
    out = ProviderMetadataExtractor(config=_Config()).extract("khong-doc-file.pdf")

    assert "metadata" in out
    assert isinstance(out["metadata"], list)
    first = out["metadata"][0]
    assert set(("key", "value", "language")).issubset(first.keys())
    assert first["key"] == "dc.title"


def test_co_khoi_extraction_de_truy_vet(monkeypatch):
    """Khối 'extraction' đi vào metadata.json → hồ sơ có bằng chứng tài liệu nào do công cụ nào trích."""
    _patch_extraction(monkeypatch, _FakeProvider(name="vllm"))
    info = ProviderMetadataExtractor(config=_Config()).extract("x.pdf")["extraction"]

    assert info["provider"] == "vllm"
    assert info["deployment"] == DEPLOY_LOCAL
    assert info["schema_code"] == "dublin_core"
    assert info["n_fields"] == 2
    assert info["latency_ms"] is not None


def test_gan_diem_tin_cay_theo_muc_bam_van_ban(monkeypatch):
    """YC-CF-01: giá trị có trong văn bản gốc → điểm cao; giá trị bịa → điểm thấp."""
    provider = _FakeProvider(fields=[
        FieldValue(key="dc.title", value="Giáo trình cơ sở dữ liệu"),   # có trong text
        FieldValue(key="dc.publisher", value="NXB Không Tồn Tại"),      # bịa
    ])
    _patch_extraction(monkeypatch, provider, text="Giáo trình cơ sở dữ liệu — tài liệu nội bộ")
    out = ProviderMetadataExtractor(config=_Config()).extract("x.pdf")

    by_key = {m["key"]: m for m in out["metadata"]}
    assert by_key["dc.title"]["confidence"] > 0.9
    assert by_key["dc.publisher"]["confidence"] < 0.6
    # Có trường điểm thấp → phải báo cần xem lại (YC-CF-04)
    assert out["extraction"]["needs_review"] is True
    assert "dc.publisher" in out["extraction"]["low_confidence_fields"]


# =====================================================================
# 2. NHÁNH XẤU — nơi lỗi thật hay nằm
# =====================================================================

def test_model_chet_thi_khong_mat_tai_lieu(monkeypatch):
    """YC-MP-05: provider ném lỗi → vẫn trả về kết quả (rỗng) + cần xem lại, KHÔNG làm job chết."""
    _patch_extraction(monkeypatch, _FakeProvider(raise_on_extract=True))
    out = ProviderMetadataExtractor(config=_Config()).extract("x.pdf")

    assert out["metadata"] == []
    assert out["extraction"]["needs_review"] is True
    assert "máy chủ model chết" in out["extraction"]["review_note"]
    assert out["extraction"]["error"] is not None


def test_thieu_truong_bat_buoc_thi_bao_can_xem_lai(monkeypatch):
    """YC-CF-02/03: thiếu trường bắt buộc, thử lại vẫn thiếu → cần cán bộ xử lý tay."""
    schema = ExtractionSchema(
        code="cong_van", document_type="cong_van", context_strategy="full",
        sensitivity=SENSITIVITY_PUBLIC,
        fields=[SchemaField(key="so_hieu", label="Số hiệu", required=True)],
    )
    provider = _FakeProvider(fields=[FieldValue(key="trich_yeu", value="Về việc ...")])
    _patch_extraction(monkeypatch, provider, schema=schema)

    out = ProviderMetadataExtractor(config=_Config(), max_retries=1).extract("x.pdf")
    assert out["extraction"]["needs_review"] is True
    assert any("so_hieu" in e for e in out["extraction"]["errors"])
    assert out["extraction"]["attempts"] == 2      # đã thử lại đúng số lần


def test_khong_trich_duoc_gi_thi_bao_can_xem_lai(monkeypatch):
    _patch_extraction(monkeypatch, _FakeProvider(fields=[]))
    out = ProviderMetadataExtractor(config=_Config()).extract("x.pdf")
    assert out["extraction"]["needs_review"] is True
    assert "Không trích được trường nào" in out["extraction"]["review_note"]


def test_ket_qua_tot_thi_khong_bat_xem_lai(monkeypatch):
    """Đối chứng: tài liệu sạch KHÔNG được đánh dấu cần xem lại, nếu không cờ này thành vô nghĩa."""
    provider = _FakeProvider(fields=[
        FieldValue(key="dc.title", value="Giáo trình cơ sở dữ liệu"),
    ])
    _patch_extraction(monkeypatch, provider, text="Giáo trình cơ sở dữ liệu")
    out = ProviderMetadataExtractor(config=_Config()).extract("x.pdf")

    assert out["extraction"]["needs_review"] is False
    assert out["extraction"]["review_note"] is None


def test_vi_pham_do_nhay_cam_thi_NEM_LOI_khong_xu_ly_tam(monkeypatch):
    """
    YC-DR-03: đây là trường hợp DUY NHẤT được phép làm job thất bại thay vì xử lý tạm.
    Nếu lớp này "cứ trích cho xong" thì ràng buộc cứng mất tác dụng.
    """
    schema = ExtractionSchema(code="cong_van", document_type="cong_van",
                              sensitivity=SENSITIVITY_SENSITIVE)
    monkeypatch.setattr("scripts.core.extraction.resolve_schema", lambda dt: schema)
    monkeypatch.setattr("scripts.core.extraction.select_context", lambda p, s: "text")

    extractor = ProviderMetadataExtractor(config=_Config(), requested_mode="cloud")
    with pytest.raises(SensitivityViolation):
        extractor.extract("x.pdf")


def test_cong_cu_dam_may_o_slot_tai_cho_bi_chan(monkeypatch):
    """Cấu hình sai (LOCAL_PROVIDER=groq) phải bị chặn ngay trong đường pipeline, không chỉ ở router."""
    provider = _FakeProvider(name="groq", deployment=DEPLOY_CLOUD)
    _patch_extraction(monkeypatch, provider, mode=DEPLOY_LOCAL)

    with pytest.raises(SensitivityViolation, match="đám mây"):
        ProviderMetadataExtractor(config=_Config()).extract("x.pdf")


# =====================================================================
# 3. NGỮ CẢNH theo lược đồ (YC-SC-04) — điều kiện KHÔNG HỒI QUY
# =====================================================================

class _FakePDFExtractor:
    last_call = {}

    def extract(self, pdf_path, max_pages=10):
        _FakePDFExtractor.last_call = {"path": pdf_path, "max_pages": max_pages}
        return "X" * 100_000    # dài hơn mọi ngưỡng để kiểm việc cắt


def test_dublin_core_giu_dung_tham_so_cu(monkeypatch):
    """
    KT-KH: lược đồ Dublin Core phải đọc ĐÚNG 10 trang và cắt ĐÚNG 6000 ký tự như hệ đang chạy.
    Lệch tham số này là thay đổi ngữ cảnh đưa vào model → kết quả khác → hồi quy âm thầm.
    """
    monkeypatch.setattr("scripts.digitize.PDFTextExtractor", _FakePDFExtractor)
    schema = ExtractionSchema(code="dublin_core", document_type="book",
                              context_strategy="first8_last2")

    text = select_context("a.pdf", schema)
    assert _FakePDFExtractor.last_call["max_pages"] == LEGACY_MAX_PAGES == 10
    assert len(text) == LEGACY_MAX_CHARS == 6000


def test_luoc_do_full_doc_nhieu_hon(monkeypatch):
    """Công văn ngắn nhưng nơi nhận/người ký nằm ở cuối → phải đọc rộng hơn Dublin Core."""
    monkeypatch.setattr("scripts.digitize.PDFTextExtractor", _FakePDFExtractor)
    schema = ExtractionSchema(code="cong_van", document_type="cong_van", context_strategy="full")

    text = select_context("a.pdf", schema)
    assert _FakePDFExtractor.last_call["max_pages"] > LEGACY_MAX_PAGES
    assert len(text) == FULL_MAX_CHARS > LEGACY_MAX_CHARS


def test_resolve_schema_khong_co_db_van_chay(monkeypatch):
    """DB chưa dựng (chưa init_pool) → phải rơi về lược đồ trong mã, không được ném lỗi."""
    schema = resolve_schema("book")
    assert schema.code == "dublin_core"
    assert resolve_schema("cong_van").code == "cong_van"


# =====================================================================
# 4. DỰ PHÒNG CHÉO CÔNG CỤ — không được đổi chế độ (ADR-008)
# =====================================================================

def test_khong_cau_hinh_du_phong_thi_khong_goi_health(monkeypatch):
    """Chuỗi rỗng thì kiểm tra sẵn sàng để làm gì — không được tốn thêm một lần gọi mạng nào."""
    primary = _FakeProvider(name="ollama")
    monkeypatch.delenv("LOCAL_FALLBACK_PROVIDERS", raising=False)
    monkeypatch.setattr("scripts.providers.factory.get_provider",
                        lambda kind=None, config=None: primary)

    provider, fallback_from = fallback.select_provider(DEPLOY_LOCAL)
    assert provider is primary and fallback_from is None
    assert primary.health_calls == 0


def test_chuyen_sang_du_phong_cung_che_do(monkeypatch):
    primary = _FakeProvider(name="vllm", ready=False)
    backup = _FakeProvider(name="ollama", ready=True)
    monkeypatch.setenv("LOCAL_FALLBACK_PROVIDERS", "ollama")

    def _get(kind=None, config=None):
        return backup if kind == "ollama" else primary

    monkeypatch.setattr("scripts.providers.factory.get_provider", _get)
    provider, fallback_from = fallback.select_provider(DEPLOY_LOCAL)

    assert provider is backup
    assert fallback_from == "vllm"


def test_du_phong_TU_CHOI_cong_cu_khac_che_do(monkeypatch):
    """
    Kịch bản nguy hiểm: vLLM tại chỗ chết, dự phòng lại cấu hình sang Groq (đám mây).
    Nếu chấp nhận, một container chết sẽ âm thầm đẩy tài liệu nhạy cảm ra ngoài.
    """
    primary = _FakeProvider(name="vllm", ready=False)
    cloud_backup = _FakeProvider(name="groq", deployment=DEPLOY_CLOUD, ready=True)
    monkeypatch.setenv("LOCAL_FALLBACK_PROVIDERS", "groq")

    def _get(kind=None, config=None):
        return cloud_backup if kind == "groq" else primary

    monkeypatch.setattr("scripts.providers.factory.get_provider", _get)
    provider, fallback_from = fallback.select_provider(DEPLOY_LOCAL)

    # Không dùng công cụ đám mây; quay về công cụ chính dù nó chưa sẵn sàng
    assert provider is primary
    assert fallback_from is None


def test_khong_cong_cu_nao_san_sang_thi_van_xu_ly(monkeypatch):
    """Thà kết quả kém + đánh dấu cần xem lại, còn hơn mất tài liệu."""
    primary = _FakeProvider(name="vllm", ready=False)
    backup = _FakeProvider(name="ollama", ready=False)
    monkeypatch.setenv("LOCAL_FALLBACK_PROVIDERS", "ollama")

    def _get(kind=None, config=None):
        return backup if kind == "ollama" else primary

    monkeypatch.setattr("scripts.providers.factory.get_provider", _get)
    provider, fallback_from = fallback.select_provider(DEPLOY_LOCAL)
    assert provider is primary and fallback_from is None


def test_bo_qua_cong_cu_cau_hinh_sai_va_thu_tiep(monkeypatch):
    """Một tên công cụ sai trong chuỗi không được làm sập cả chuỗi dự phòng."""
    primary = _FakeProvider(name="vllm", ready=False)
    backup = _FakeProvider(name="llamacpp", ready=True)
    monkeypatch.setenv("LOCAL_FALLBACK_PROVIDERS", "cong-cu-sai,llamacpp")

    def _get(kind=None, config=None):
        if kind == "cong-cu-sai":
            raise ValueError("MODEL_PROVIDER không hợp lệ")
        return backup if kind == "llamacpp" else primary

    monkeypatch.setattr("scripts.providers.factory.get_provider", _get)
    provider, fallback_from = fallback.select_provider(DEPLOY_LOCAL)
    assert provider is backup and fallback_from == "vllm"


def test_describe_chain_cho_giao_dien_quan_tri(monkeypatch):
    monkeypatch.setenv("LOCAL_FALLBACK_PROVIDERS", "ollama, llamacpp")
    assert fallback.describe_chain()["local"] == ["ollama", "llamacpp"]


# =====================================================================
# 5. ĐO TÀI NGUYÊN (YC-MS-07)
# =====================================================================

def test_measure_do_duoc_thoi_gian():
    with metrics.measure(with_gpu=False) as m:
        sum(range(10_000))
    assert m.sample.latency_ms >= 0
    # rss_mb: Linux/macOS có số, Windows trả None — cả hai đều hợp lệ, KHÔNG được bịa 0
    assert m.sample.rss_mb is None or m.sample.rss_mb > 0
    assert m.sample.gpu_mem_mb is None


def test_gpu_mac_dinh_tat(monkeypatch):
    """Không bật METRICS_GPU thì tuyệt đối không gọi nvidia-smi (máy không GPU vẫn phải nhanh)."""
    monkeypatch.delenv("METRICS_GPU", raising=False)
    called = []
    monkeypatch.setattr("subprocess.run", lambda *a, **k: called.append(a))
    assert metrics.read_gpu_mem_mb() is None
    assert called == []


def test_measure_khong_nuot_ngoai_le():
    with pytest.raises(RuntimeError):
        with metrics.measure(with_gpu=False):
            raise RuntimeError("lỗi phải bay ra")


# =====================================================================
# 6. TIÊM VÀO PIPELINE — không phá đường cũ
# =====================================================================

def test_pipeline_dung_extractor_duoc_tiem():
    from scripts.digitize import DigitizationPipeline

    sentinel = object()
    pipeline = DigitizationPipeline(metadata_extractor=sentinel)
    assert pipeline.metadata_extractor is sentinel


def test_pipeline_khong_tiem_thi_giu_duong_cu():
    """Không truyền extractor → vẫn là AIMetadataExtractor như trước (CLI, và van lùi USE_PROVIDER_LAYER=0)."""
    from scripts.digitize import AIMetadataExtractor, DigitizationPipeline

    pipeline = DigitizationPipeline()
    assert isinstance(pipeline.metadata_extractor, AIMetadataExtractor)
