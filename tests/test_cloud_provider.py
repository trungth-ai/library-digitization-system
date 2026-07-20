#!/usr/bin/env python3
"""
Regression test CloudProvider (YC-MP-02 / KT-KH): CloudProvider phải cho kết quả GIỐNG HỆT
AIMetadataExtractor cũ trên cùng đầu vào — cả nhánh basic (không key) lẫn nhánh AI (mock client).

Chạy: pytest tests/test_cloud_provider.py -v
"""

from scripts.digitize import AIMetadataExtractor, ProcessingConfig
from scripts.providers.cloud import CloudProvider
from scripts.providers.base import ExtractionSchema


BOOK_SCHEMA = ExtractionSchema(code="dublin_core", document_type="book")


# --- Fake Anthropic client trả JSON cố định (không gọi API thật) ---
class _FakeContent:
    def __init__(self, text): self.text = text

class _FakeResp:
    def __init__(self, text): self.content = [_FakeContent(text)]

class _FakeMessages:
    def __init__(self, canned): self._canned = canned
    def create(self, **kwargs): return _FakeResp(self._canned)

class _FakeClient:
    def __init__(self, canned): self.messages = _FakeMessages(canned)


def test_regression_basic_khong_key():
    """client=None → basic extraction: CloudProvider giống hệt AIMetadataExtractor._basic_extraction."""
    text = "Nhập môn Trí tuệ nhân tạo\nTác giả X\nNhà xuất bản Y"

    cfg_old = ProcessingConfig(); cfg_old.document_type = "book"
    old = AIMetadataExtractor(cfg_old, api_key=None)._basic_extraction(text)["metadata"]

    prov = CloudProvider(api_key=None, config=ProcessingConfig())
    new = prov.extract_fields(text, BOOK_SCHEMA).to_metadata_list()

    assert new == old
    assert prov.health().ready is False  # không key → không sẵn sàng AI


def test_regression_ai_path_mock():
    """Nhánh AI (mock client): CloudProvider giống hệt AIMetadataExtractor._ai_extraction."""
    canned = (
        '{"title":"Sách Thử Nghiệm","title_alternative":null,'
        '"authors":["Nguyễn, Văn A","Trần, Thị B"],"advisors":null,"editor":null,'
        '"publisher":"NXB Giáo dục","year":"2024","subjects":["AI","Máy học","Dữ liệu"],'
        '"abstract":"Một cuốn sách thử nghiệm.","pages":"200 tr.","size":null,'
        '"language":"vi","isbn":"978-604-1-00000-0","department":null,"degree":null,"type":"Book"}'
    )
    text = "Nội dung mẫu để trích xuất"

    # Đường cũ
    cfg_old = ProcessingConfig(); cfg_old.document_type = "book"
    ext = AIMetadataExtractor(cfg_old, api_key=None)
    ext.client = _FakeClient(canned)
    old = ext._ai_extraction(text)["metadata"]

    # Đường mới qua provider
    prov = CloudProvider(api_key=None, config=ProcessingConfig())
    prov._extractor.client = _FakeClient(canned)
    new = prov.extract_fields(text, BOOK_SCHEMA).to_metadata_list()

    assert new == old
    # kiểm tra vài trường chắc chắn có
    keys = [f["key"] for f in new]
    assert "dc.title" in keys and "dc.contributor.author" in keys
    # multi-value: 2 tác giả
    assert sum(1 for f in new if f["key"] == "dc.contributor.author") == 2


def test_regression_thesis_document_type():
    """document_type='thesis' đổi prompt/nhánh degree — vẫn khớp giữa cũ và mới."""
    canned = (
        '{"title":"Đồ án tốt nghiệp","authors":["Lê, C"],"advisors":["TS. Phạm, D"],'
        '"subjects":["CNTT"],"abstract":"tóm tắt","type":"Thesis","language":"vi",'
        '"degree":"Đồ án","department":"Khoa CNTT"}'
    )
    text = "noi dung do an"
    schema = ExtractionSchema(code="dublin_core", document_type="thesis")

    cfg_old = ProcessingConfig(); cfg_old.document_type = "thesis"
    ext = AIMetadataExtractor(cfg_old, api_key=None); ext.client = _FakeClient(canned)
    old = ext._ai_extraction(text)["metadata"]

    prov = CloudProvider(api_key=None, config=ProcessingConfig())
    prov._extractor.client = _FakeClient(canned)
    new = prov.extract_fields(text, schema).to_metadata_list()

    assert new == old
    assert any(f["key"] == "dc.contributor.advisor" for f in new)
