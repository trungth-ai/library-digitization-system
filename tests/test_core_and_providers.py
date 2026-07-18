#!/usr/bin/env python3
"""
Test nền tảng Sprint 0A: response envelope + interface ModelProvider.
Chạy: pytest tests/test_core_and_providers.py -v
"""

import pytest

from scripts.core.responses import success, error, paginated
from scripts.core.exceptions import ResourceNotFound, ProviderUnavailable, AppError
from scripts.providers.base import (
    ModelProvider, ExtractionSchema, SchemaField,
    ExtractionResult, FieldValue, ProviderHealth,
)


# ---------------------------------------------------------------------
# Response envelope (chuẩn HPU)
# ---------------------------------------------------------------------

def test_success_co_dung_cau_truc():
    r = success({"id": 1}, "OK")
    assert r == {"status": "success", "data": {"id": 1}, "message": "OK"}
    assert "meta" not in r  # không có meta khi không truyền


def test_success_kem_meta():
    r = success([1, 2], meta={"page": 1})
    assert r["meta"] == {"page": 1}


def test_error_co_code_va_errors():
    r = error("Không hợp lệ", code="VALIDATION_ERROR",
              errors=[{"field": "email", "message": "sai"}])
    assert r["status"] == "error"
    assert r["code"] == "VALIDATION_ERROR"
    assert r["errors"][0]["field"] == "email"


def test_paginated_tinh_total_pages():
    r = paginated(data=[], page=1, per_page=10, total=98)
    assert r["meta"]["total_pages"] == 10  # ceil(98/10)
    r2 = paginated(data=[], page=1, per_page=10, total=100)
    assert r2["meta"]["total_pages"] == 10
    r3 = paginated(data=[], page=1, per_page=10, total=0)
    assert r3["meta"]["total_pages"] == 0


# ---------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------

def test_exception_mapping_http():
    assert ResourceNotFound("x").http_status == 404
    assert ResourceNotFound("x").code == "NOT_FOUND"
    assert ProviderUnavailable("x").http_status == 503
    assert isinstance(ResourceNotFound("x"), AppError)


# ---------------------------------------------------------------------
# Interface ModelProvider
# ---------------------------------------------------------------------

def test_model_provider_la_abstract():
    # Không được phép khởi tạo trực tiếp giao diện trừu tượng
    with pytest.raises(TypeError):
        ModelProvider()


def test_them_provider_moi_chi_can_1_lop(monkeypatch):
    """Phép thử YC-MP-08: thêm provider = 1 lớp con, không sửa giao diện."""

    class DummyProvider(ModelProvider):
        name = "dummy"
        model = "dummy-1"
        version = "0"

        def extract_fields(self, text, schema):
            return ExtractionResult(fields=[FieldValue(key="dc.title", value=text[:5])])

        def embed(self, texts):
            return [[0.0] * 3 for _ in texts]

        def health(self):
            return ProviderHealth(ready=True, detail="ok")

    p = DummyProvider()
    schema = ExtractionSchema(code="dublin_core", document_type="book",
                              fields=[SchemaField(key="dc.title", required=True)])
    res = p.extract_fields("Hello world", schema)
    assert res.fields[0].value == "Hello"
    assert p.health().ready is True
    assert p.embed(["a", "b"]) == [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    assert p.describe() == {"provider": "dummy", "model": "dummy-1", "version": "0"}


def test_to_metadata_list_giu_tuong_thich():
    """Kết quả chuyển đúng định dạng metadata cũ [{key, value, language}]."""
    res = ExtractionResult(fields=[
        FieldValue(key="dc.title", value="Sách A", language="vi_VN"),
        FieldValue(key="dc.type", value="Book", language="en_US", confidence=0.9),
    ])
    ml = res.to_metadata_list()
    assert ml[0] == {"key": "dc.title", "value": "Sách A", "language": "vi_VN"}
    assert ml[1]["confidence"] == 0.9
