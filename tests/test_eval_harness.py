#!/usr/bin/env python3
"""
Test logic đo đạc (KT-CX) — thuần, dùng mock provider (không cần mạng/model thật).
Chạy: pytest tests/test_eval_harness.py -v
"""

from scripts.eval.harness import (
    normalize_value, compare_field, group_fields_by_key, run_provider_eval,
    CORRECT, CORRECT_EMPTY, INCORRECT, HALLUCINATED,
)
from scripts.eval.schemas import get_schema, cong_van_schema
from scripts.providers.base import ExtractionResult, FieldValue, ExtractionSchema


# --- normalize ---
def test_normalize_whitespace():
    assert normalize_value("  Hà   Nội \n") == "Hà Nội"
    assert normalize_value(None) == ""


def test_normalize_date_ve_iso():
    assert normalize_value("15/03/2024") == "2024-03-15"
    assert normalize_value("2024-03-15") == "2024-03-15"
    assert normalize_value("15-03-2024") == "2024-03-15"
    assert normalize_value("không phải ngày") == "không phải ngày"


# --- compare_field: 4 trạng thái ---
def test_compare_correct():
    assert compare_field("Sách A", "Sách A") == CORRECT
    assert compare_field("Sách  A", " Sách A ") == CORRECT  # sau chuẩn hóa whitespace


def test_compare_incorrect():
    assert compare_field("Sách A", "Sách B") == INCORRECT


def test_compare_empty_va_hallucinated():
    # kỳ vọng rỗng + trả rỗng = ĐÚNG (không bịa)
    assert compare_field(None, None) == CORRECT_EMPTY
    assert compare_field("", "") == CORRECT_EMPTY
    # kỳ vọng rỗng + model bịa ra giá trị = SAI (ảo giác) — KT-CX-05
    assert compare_field(None, "123/QĐ-BC") == HALLUCINATED


def test_compare_multivalue_set():
    assert compare_field(["Nguyễn, A", "Trần, B"], ["Trần, B", "Nguyễn, A"]) == CORRECT
    assert compare_field(["Nguyễn, A", "Trần, B"], ["Nguyễn, A"]) == INCORRECT


# --- group ---
def test_group_fields_by_key_multivalue():
    md = [{"key": "dc.contributor.author", "value": "A"},
          {"key": "dc.contributor.author", "value": "B"},
          {"key": "dc.title", "value": "T"}]
    g = group_fields_by_key(md)
    assert g["dc.contributor.author"] == ["A", "B"]
    assert g["dc.title"] == ["T"]


# --- run_provider_eval với mock provider ---
class _MockProvider:
    name = "mock"
    model = "mock-1"
    version = "0"

    def __init__(self, mapping):
        self._mapping = mapping  # {doc_id_text: ExtractionResult}

    def extract_fields(self, text, schema):
        return self._mapping[text]


def test_run_provider_eval_tinh_dung():
    schema = get_schema("cong_van")
    docs = {"cv1": "vb1", "cv2": "vb2"}
    truth = {
        "cv1": {"so_hieu": "123/QĐ", "co_quan_ban_hanh": "UBND", "do_mat": ""},
        "cv2": {"so_hieu": "456/TB", "co_quan_ban_hanh": "Sở GD", "do_mat": ""},
    }
    mapping = {
        # cv1: so_hieu đúng, co_quan sai, do_mat rỗng đúng
        "vb1": ExtractionResult(fields=[
            FieldValue("so_hieu", "123/QĐ"),
            FieldValue("co_quan_ban_hanh", "Sai cơ quan"),
        ]),
        # cv2: so_hieu đúng, co_quan đúng, do_mat BỊA (ảo giác)
        "vb2": ExtractionResult(fields=[
            FieldValue("so_hieu", "456/TB"),
            FieldValue("co_quan_ban_hanh", "Sở GD"),
            FieldValue("do_mat", "MẬT"),
        ]),
    }
    rep = run_provider_eval(_MockProvider(mapping), docs, truth, schema)

    assert rep.n_docs == 2
    # 6 trường tổng (3 field × 2 doc): đúng = so_hieu×2 + co_quan cv2 + do_mat cv1 rỗng = 4; sai=1; bịa=1
    assert rep.per_field["so_hieu"].correct == 2
    assert rep.per_field["co_quan_ban_hanh"].correct == 1
    assert rep.per_field["co_quan_ban_hanh"].incorrect == 1
    assert rep.per_field["do_mat"].correct_empty == 1
    assert rep.per_field["do_mat"].hallucinated == 1
    # tổng đúng 4/6
    assert abs(rep.overall_accuracy - 4/6) < 1e-9
    # tỉ lệ bịa: 1 bịa / 2 trường-lẽ-ra-rỗng = 0.5
    assert abs(rep.hallucination_rate - 0.5) < 1e-9


def test_schemas_co_san():
    assert get_schema("book").document_type == "book"
    assert get_schema("cong_van").document_type == "cong_van"
    assert cong_van_schema().sensitivity == "internal"  # mặc định an toàn


# --- CLI đo đạc: hỗ trợ nhiều công cụ (ADR-007) ---

def test_report_ghi_ca_che_do_trien_khai():
    """Bảng so sánh trong hồ sơ phải nói rõ dữ liệu chạy Ở ĐÂU, không chỉ tên công cụ."""
    class _MockProvider:
        name, deployment, model, version = "vllm", "local", "Qwen2.5-7B", ""

        def extract_fields(self, text, schema):
            return ExtractionResult(fields=[FieldValue(key="so_hieu", value="01/QĐ")])

    rep = run_provider_eval(_MockProvider(), {"d1": "x"}, {"d1": {"so_hieu": "01/QĐ"}},
                            get_schema("cong_van"))
    assert rep.provider == "vllm" and rep.deployment == "local"

    from scripts.eval.run_eval import report_to_dict
    assert report_to_dict(rep)["deployment"] == "local"


def test_list_providers_liet_ke_ca_hai_che_do(capsys):
    """`--list-providers` phải chạy được và nêu cả công cụ tại chỗ lẫn đám mây."""
    from scripts.eval.run_eval import main
    assert main(["--list-providers"]) == 0
    out = capsys.readouterr().out
    for name in ("ollama", "vllm", "llamacpp", "claude", "gemini"):
        assert name in out
    assert "TẠI CHỖ" in out and "ĐÁM MÂY" in out


def test_thieu_tham_so_bat_buoc_thi_bao_loi():
    """Không có --data/--truth và cũng không --list-providers → lỗi rõ, không chạy nửa vời."""
    import pytest
    from scripts.eval.run_eval import main
    with pytest.raises(SystemExit):
        main([])
