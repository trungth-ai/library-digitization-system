#!/usr/bin/env python3
"""
Test chuyển đổi lược đồ (YC-SC): rows↔schema, export/import dict. Thuần, không cần DB.
Chạy: pytest tests/test_schema_store.py -v
"""

from scripts.core.schema_store import rows_to_schema, schema_to_dict, dict_to_schema
from scripts.providers.base import ExtractionSchema, SchemaField


def test_rows_to_schema_sap_xep_va_kieu():
    srow = {"code": "cong_van", "name": "Công văn", "document_type": "cong_van",
            "context_strategy": "full", "sensitivity": "internal"}
    frows = [
        {"key": "trich_yeu", "label": "Trích yếu", "required": True, "data_type": "text", "sort_order": 3},
        {"key": "so_hieu", "label": "Số hiệu", "required": True, "data_type": "text", "sort_order": 1},
        {"key": "ngay_ban_hanh", "label": "Ngày", "required": False, "data_type": "date", "sort_order": 2},
    ]
    schema = rows_to_schema(srow, frows)
    assert schema.code == "cong_van" and schema.sensitivity == "internal"
    # sắp theo sort_order
    assert [f.key for f in schema.fields] == ["so_hieu", "ngay_ban_hanh", "trich_yeu"]
    assert schema.fields[0].required is True
    assert schema.fields[1].data_type == "date"


def test_schema_to_dict():
    s = ExtractionSchema(code="x", name="X", document_type="book", sensitivity="public",
                         fields=[SchemaField("dc.title", "Tiêu đề", required=True)])
    d = schema_to_dict(s)
    assert d["code"] == "x" and d["sensitivity"] == "public"
    assert d["fields"][0]["key"] == "dc.title" and d["fields"][0]["sort_order"] == 1


def test_export_import_round_trip():
    """YC-SC-07: xuất rồi nhập lại cho lược đồ tương đương."""
    s = ExtractionSchema(
        code="cv2", name="Công văn biến thể", document_type="cong_van",
        context_strategy="full", sensitivity="internal",
        fields=[
            SchemaField("so_hieu", "Số hiệu", required=True),
            SchemaField("noi_nhan", "Nơi nhận", data_type="list"),
        ],
    )
    s2 = dict_to_schema(schema_to_dict(s))
    assert s2.code == s.code and s2.name == s.name
    assert s2.sensitivity == s.sensitivity and s2.context_strategy == s.context_strategy
    assert [(f.key, f.data_type, f.required) for f in s2.fields] == \
           [(f.key, f.data_type, f.required) for f in s.fields]
