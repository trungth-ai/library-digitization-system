#!/usr/bin/env python3
"""
Test 7 lược đồ biên mục theo bộ mẫu + quy tắc nguồn trường (source).
Trọng tâm: mã HPU (dc.identifier.other) và trường hệ thống KHÔNG lọt vào prompt AI (chống bịa).
Chạy: pytest tests/test_catalog_schemas.py -v
"""

import pytest

from scripts.eval.schemas import get_schema, all_catalog_schemas
from scripts.providers.base import SOURCE_AI, SOURCE_SYSTEM, SOURCE_MANUAL
from scripts.providers.prompt import build_schema_prompt


def _keys(schema):
    return [f.key for f in schema.fields]


# --- Đủ 7 loại ---
def test_du_7_luoc_do():
    assert len(all_catalog_schemas()) == 7
    for code in ("sach", "de_cuong", "khoa_luan", "luan_van", "hoi_thao", "bao_nckh", "cong_van"):
        assert get_schema(code).code == code


# --- Trường đặc trưng theo nhóm ---
def test_nhom_sach_co_editor_isbn_alternative():
    for code in ("sach", "de_cuong"):
        keys = _keys(get_schema(code))
        assert "dc.contributor.editor" in keys
        assert "dc.identifier.isbn" in keys
        assert "dc.title.alternative" in keys
        assert "dc.contributor.advisor" not in keys  # sách không có người hướng dẫn


def test_nhom_luan_co_advisor_degree_khong_isbn():
    for code in ("khoa_luan", "luan_van"):
        keys = _keys(get_schema(code))
        assert "dc.contributor.advisor" in keys
        assert "dc.description.degree" in keys
        assert "dc.identifier.isbn" not in keys
        assert "dc.contributor.editor" not in keys


def test_nhom_bai_viet_co_degree_department():
    for code in ("hoi_thao", "bao_nckh"):
        keys = _keys(get_schema(code))
        assert "dc.description.degree" in keys
        assert "dc.department" in keys


def test_cong_van_co_truong_moi_theo_mau():
    keys = _keys(get_schema("cong_van"))
    for k in ("so_hieu", "co_quan_ban_hanh", "nguoi_ky", "chuc_vu_nguoi_ky",
              "don_vi_ban_hanh", "noi_ban_hanh", "nhan_de", "trich_yeu"):
        assert k in keys


# --- Nguồn trường ---
def test_ma_hpu_la_manual():
    for code in ("sach", "khoa_luan", "bao_nckh"):
        f = next(x for x in get_schema(code).fields if x.key == "dc.identifier.other")
        assert f.source == SOURCE_MANUAL


def test_truong_he_thong():
    f = next(x for x in get_schema("sach").fields if x.key == "dc.format.extent")
    assert f.source == SOURCE_SYSTEM


# --- Prompt AI KHÔNG chứa trường manual/system (chống bịa mã HPU) ---
def test_prompt_khong_hoi_ma_hpu_va_truong_he_thong():
    schema = get_schema("khoa_luan")
    prompt = build_schema_prompt("nội dung tài liệu mẫu", schema)
    # Mã HPU (người điền) — TUYỆT ĐỐI không xuất hiện trong prompt để AI không thể bịa
    assert "dc.identifier.other" not in prompt
    # Trường hệ thống cũng không nằm trong prompt AI
    assert "dc.format.extent" not in prompt
    assert "dc.size" not in prompt
    assert "dc.format.mimetype" not in prompt
    # Trường AI thì có
    assert "dc.title" in prompt
    assert "dc.contributor.advisor" in prompt


def test_prompt_co_truong_ai_cong_van():
    prompt = build_schema_prompt("công văn mẫu", get_schema("cong_van"))
    assert "so_hieu" in prompt and "trich_yeu" in prompt
    # so_trang/dung_luong là hệ thống → không hỏi AI
    assert "so_trang" not in prompt and "dung_luong" not in prompt
