#!/usr/bin/env python3
"""
Test kiểm soát chất lượng (YC-CF). Chạy: pytest tests/test_quality.py -v
"""

from scripts.core.quality import (
    grounding_confidence, apply_grounding_confidence, low_confidence_fields,
    validate_extraction, extract_with_quality,
)
from scripts.providers.base import (
    ExtractionResult, FieldValue, ExtractionSchema, SchemaField,
)

SOURCE = "Quyết định số 123/QĐ-ĐHQLCN của Trường Đại học Quản lý và Công nghệ Hải Phòng."

SCHEMA = ExtractionSchema(code="cong_van", document_type="cong_van", fields=[
    SchemaField("so_hieu", "Số hiệu", required=True),
    SchemaField("co_quan_ban_hanh", "Cơ quan", required=True),
    SchemaField("ngay_ban_hanh", "Ngày", data_type="date"),
])


# --- grounding / chống ảo giác (YC-CF-05) ---
def test_grounding_nguyen_van_cao():
    assert grounding_confidence("123/QĐ-ĐHQLCN", SOURCE) == 0.95

def test_grounding_gia_tri_bia_thap():
    # số hiệu bịa hoàn toàn không có trong văn bản → điểm thấp
    assert grounding_confidence("999/XX-ZZZ", SOURCE) <= 0.5

def test_grounding_rong():
    assert grounding_confidence("", SOURCE) == 0.0


def test_apply_va_low_confidence():
    res = ExtractionResult(fields=[
        FieldValue("so_hieu", "123/QĐ-ĐHQLCN"),
        FieldValue("so_hieu_bia", "999/XX-ZZZ"),
    ])
    apply_grounding_confidence(res, SOURCE)
    assert res.fields[0].confidence == 0.95
    assert res.fields[1].confidence <= 0.5
    low = low_confidence_fields(res, threshold=0.5)
    assert "so_hieu_bia" in low and "so_hieu" not in low


# --- validate (YC-CF-02) ---
def test_validate_thieu_required():
    res = ExtractionResult(fields=[FieldValue("so_hieu", "123/QĐ")])
    errs = validate_extraction(res, SCHEMA)
    assert any("co_quan_ban_hanh" in e for e in errs)

def test_validate_sai_kieu_ngay():
    res = ExtractionResult(fields=[
        FieldValue("so_hieu", "123"), FieldValue("co_quan_ban_hanh", "X"),
        FieldValue("ngay_ban_hanh", "không phải ngày"),
    ])
    errs = validate_extraction(res, SCHEMA)
    assert any("ngày" in e.lower() for e in errs)

def test_validate_hop_le():
    res = ExtractionResult(fields=[
        FieldValue("so_hieu", "123"), FieldValue("co_quan_ban_hanh", "X"),
        FieldValue("ngay_ban_hanh", "15/03/2024"),
    ])
    assert validate_extraction(res, SCHEMA) == []


# --- extract_with_quality: retry + needs_manual (YC-CF-03) ---
class _FixedProvider:
    name = "fixed"; model = "m"
    def __init__(self, result): self._r = result
    def extract_fields(self, text, schema): return self._r

class _SeqProvider:
    name = "seq"; model = "m"
    def __init__(self, results): self._r = list(results); self._i = 0
    def extract_fields(self, text, schema):
        r = self._r[min(self._i, len(self._r)-1)]; self._i += 1; return r


def test_extract_quality_hop_le_ngay_lan_dau():
    good = ExtractionResult(fields=[
        FieldValue("so_hieu", "123/QĐ-ĐHQLCN"), FieldValue("co_quan_ban_hanh", "Trường Đại học"),
    ])
    result, errors, attempts, needs_manual = extract_with_quality(
        _FixedProvider(good), SOURCE, SCHEMA, max_retries=2)
    assert errors == [] and needs_manual is False and attempts == 1
    # confidence đã được gán
    assert all(f.confidence is not None for f in result.fields)


def test_extract_quality_het_retry_can_thu_cong():
    bad = ExtractionResult(fields=[FieldValue("so_hieu", "123")])  # thiếu co_quan (required)
    result, errors, attempts, needs_manual = extract_with_quality(
        _FixedProvider(bad), SOURCE, SCHEMA, max_retries=2)
    assert needs_manual is True
    assert attempts == 3  # 1 + 2 retry
    assert any("co_quan_ban_hanh" in e for e in errors)


def test_extract_quality_retry_thanh_cong_lan_2():
    bad = ExtractionResult(fields=[FieldValue("so_hieu", "123")])
    good = ExtractionResult(fields=[
        FieldValue("so_hieu", "123"), FieldValue("co_quan_ban_hanh", "Trường X"),
    ])
    result, errors, attempts, needs_manual = extract_with_quality(
        _SeqProvider([bad, good]), SOURCE, SCHEMA, max_retries=2)
    assert needs_manual is False and attempts == 2 and errors == []
