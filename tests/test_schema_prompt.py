#!/usr/bin/env python3
"""
Test generic schema-driven prompt/parse + rẽ nhánh provider (công văn → generic; dublin_core → đường cũ).
Chạy: pytest tests/test_schema_prompt.py -v
"""

from scripts.providers.prompt import build_schema_prompt, parse_schema_response, extract_with_schema
from scripts.providers.cloud import CloudProvider
from scripts.providers.local import LocalProvider
from scripts.eval.schemas import cong_van_schema, get_schema

CV_JSON = (
    '{"so_hieu":"123/QĐ-ĐHQLCN","ngay_ban_hanh":"15/03/2024",'
    '"co_quan_ban_hanh":"Trường ĐHQLCN","loai_van_ban":"Quyết định",'
    '"trich_yeu":"Về việc thành lập hội đồng","do_khan":null,"do_mat":null,'
    '"noi_nhan":["Như Điều 2","Lưu VT"],"nguoi_ky":"Hiệu trưởng"}'
)

DUBLIN_JSON = '{"title":"Sách A","authors":["Nguyễn, A"],"subjects":["X"],"type":"Book","language":"vi"}'


# --- build/parse thuần ---
def test_build_prompt_liet_ke_field():
    p = build_schema_prompt("VB mẫu", cong_van_schema())
    assert "so_hieu" in p and "nguoi_ky" in p
    assert "null" in p                 # hướng dẫn để null khi không thấy
    assert "VB mẫu" in p               # có văn bản


def test_parse_skip_null_va_multivalue():
    res = parse_schema_response(CV_JSON, cong_van_schema())
    keys = [f.key for f in res.fields]
    # null bị bỏ (không bịa)
    assert "do_khan" not in keys and "do_mat" not in keys
    # multi-value noi_nhan → 2 giá trị
    assert sum(1 for f in res.fields if f.key == "noi_nhan") == 2
    assert any(f.key == "so_hieu" and f.value == "123/QĐ-ĐHQLCN" for f in res.fields)


def test_parse_bo_markdown_fence():
    raw = "```json\n" + CV_JSON + "\n```"
    res = parse_schema_response(raw, cong_van_schema())
    assert any(f.key == "nguoi_ky" for f in res.fields)


def test_extract_with_schema_dieu_phoi():
    calls = {}
    def fake_complete(prompt):
        calls["prompt"] = prompt
        return CV_JSON
    res = extract_with_schema(fake_complete, "VB", cong_van_schema())
    assert "so_hieu" in calls["prompt"]
    assert any(f.key == "trich_yeu" for f in res.fields)


# --- rẽ nhánh provider ---
def test_cloud_cong_van_generic(monkeypatch):
    prov = CloudProvider(api_key=None)
    prov._extractor.client = object()  # giả có client để qua nhánh AI
    monkeypatch.setattr(prov, "_complete", lambda p: CV_JSON)
    res = prov.extract_fields("VB", cong_van_schema())
    keys = [f.key for f in res.fields]
    assert "so_hieu" in keys and "co_quan_ban_hanh" in keys
    assert "do_mat" not in keys        # null → không bịa


def test_cloud_cong_van_khong_key_tra_rong():
    """Không có key + lược đồ generic → trả rỗng, KHÔNG bịa (YC-MP-05 an toàn)."""
    prov = CloudProvider(api_key=None)  # client None
    res = prov.extract_fields("VB", cong_van_schema())
    assert res.fields == []


def test_local_cong_van_generic(monkeypatch):
    prov = LocalProvider(model="m")
    monkeypatch.setattr(prov, "_complete", lambda p: CV_JSON)
    res = prov.extract_fields("VB", cong_van_schema())
    assert any(f.key == "so_hieu" for f in res.fields)


def test_dublin_core_van_di_duong_cu(monkeypatch):
    """Lược đồ dublin_core vẫn đi đường cũ (dùng _call_generate + _build_metadata → dc.*)."""
    prov = LocalProvider(model="m")
    monkeypatch.setattr(prov, "_call_generate", lambda p: DUBLIN_JSON)
    res = prov.extract_fields("VB", get_schema("book"))
    keys = [f.key for f in res.fields]
    assert "dc.title" in keys          # đường Dublin Core, không phải generic
