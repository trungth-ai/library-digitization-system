#!/usr/bin/env python3
"""
Logic đo độ chính xác trích xuất (KT-CX) — THUẦN, không phụ thuộc provider/mạng → unit-test được.

Công thức (theo Kế hoạch kiểm thử, mục 1.3):
  Độ chính xác = (số trường đúng) / (tổng số trường cần trích) × 100%
  - "Đúng" = trùng khớp hoàn toàn sau chuẩn hóa khoảng trắng + định dạng ngày tháng.
  - Trường KHÔNG có trong tài liệu: trả rỗng là ĐÚNG; bịa ra giá trị là SAI (ảo giác).
  - Báo cáo theo TỪNG trường, kèm cỡ mẫu (số tổng che giấu một trường luôn sai).
"""

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Union

# Trạng thái so khớp một trường
CORRECT = "correct"            # có kỳ vọng, khớp
CORRECT_EMPTY = "correct_empty"  # kỳ vọng rỗng, trả rỗng (không bịa) → đúng
INCORRECT = "incorrect"        # có kỳ vọng, không khớp
HALLUCINATED = "hallucinated"  # kỳ vọng rỗng nhưng model bịa ra giá trị → sai

_DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d")


def normalize_value(value: Optional[str]) -> str:
    """Chuẩn hóa 1 giá trị để so khớp: gộp khoảng trắng + chuẩn hóa ngày về YYYY-MM-DD nếu là ngày.
    KHÔNG đổi hoa/thường (giữ trung thực theo test plan)."""
    if value is None:
        return ""
    s = re.sub(r"\s+", " ", str(value)).strip()
    if not s:
        return ""
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def _to_norm_set(v: Union[str, List[str], None]) -> set:
    """Chuyển giá trị (đơn hoặc nhiều) thành tập giá trị đã chuẩn hóa, loại rỗng."""
    if v is None:
        return set()
    items = v if isinstance(v, list) else [v]
    return {normalize_value(x) for x in items if normalize_value(x)}


def compare_field(expected: Union[str, List[str], None],
                  extracted: Union[str, List[str], None]) -> str:
    """So khớp một trường, trả về một trong 4 trạng thái."""
    exp = _to_norm_set(expected)
    ext = _to_norm_set(extracted)
    if not exp:
        return CORRECT_EMPTY if not ext else HALLUCINATED
    return CORRECT if exp == ext else INCORRECT


@dataclass
class FieldStat:
    correct: int = 0
    correct_empty: int = 0
    incorrect: int = 0
    hallucinated: int = 0

    @property
    def total(self) -> int:
        return self.correct + self.correct_empty + self.incorrect + self.hallucinated

    @property
    def accuracy(self) -> float:
        """Tỉ lệ đúng (gồm cả trả-rỗng-đúng) trên tổng."""
        return (self.correct + self.correct_empty) / self.total if self.total else 0.0

    def add(self, status: str) -> None:
        setattr(self, status, getattr(self, status) + 1)


@dataclass
class EvalReport:
    provider: str = ""
    deployment: str = ""   # cloud | local — để bảng so sánh trong hồ sơ nói rõ dữ liệu chạy ở đâu
    model: str = ""
    version: str = ""
    n_docs: int = 0
    per_field: Dict[str, FieldStat] = field(default_factory=dict)
    total_latency_ms: int = 0

    def _overall(self) -> FieldStat:
        agg = FieldStat()
        for st in self.per_field.values():
            agg.correct += st.correct
            agg.correct_empty += st.correct_empty
            agg.incorrect += st.incorrect
            agg.hallucinated += st.hallucinated
        return agg

    @property
    def overall_accuracy(self) -> float:
        return self._overall().accuracy

    @property
    def hallucination_rate(self) -> float:
        """Tỉ lệ bịa trên số trường lẽ ra phải rỗng (KT-CX-05). 0 nếu không có trường rỗng."""
        agg = self._overall()
        empty_expected = agg.correct_empty + agg.hallucinated
        return agg.hallucinated / empty_expected if empty_expected else 0.0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.n_docs if self.n_docs else 0.0


def evaluate_document(report: EvalReport,
                      extracted_by_key: Dict[str, List[str]],
                      ground_truth: Dict[str, Union[str, List[str]]]) -> None:
    """Cập nhật report cho 1 tài liệu. So khớp theo tập trường trong ground_truth."""
    for key, expected in ground_truth.items():
        status = compare_field(expected, extracted_by_key.get(key))
        report.per_field.setdefault(key, FieldStat()).add(status)


def group_fields_by_key(metadata_list: List[dict]) -> Dict[str, List[str]]:
    """Gom metadata [{key,value,...}] thành {key: [value,...]} (hỗ trợ multi-value)."""
    out: Dict[str, List[str]] = {}
    for m in metadata_list:
        out.setdefault(m["key"], []).append(m.get("value", ""))
    return out


def run_provider_eval(provider, docs: Dict[str, str],
                      ground_truths: Dict[str, Dict], schema) -> EvalReport:
    """
    Chạy 1 provider trên tập tài liệu, so khớp với đáp án chuẩn, đo thời gian.
    `provider` chỉ cần có .name/.model/.extract_fields → test được bằng mock (không cần mạng).
    `docs`: {doc_id: text}; `ground_truths`: {doc_id: {field_key: expected}}.
    """
    report = EvalReport(
        provider=getattr(provider, "name", "?"),
        deployment=getattr(provider, "deployment", ""),
        model=getattr(provider, "model", ""),
        version=getattr(provider, "version", ""),
    )
    for doc_id, text in docs.items():
        gt = ground_truths.get(doc_id)
        if not gt:
            continue  # chỉ đo tài liệu có đáp án chuẩn
        t0 = time.perf_counter()
        result = provider.extract_fields(text, schema)
        report.total_latency_ms += int((time.perf_counter() - t0) * 1000)
        report.n_docs += 1
        grouped = group_fields_by_key(result.to_metadata_list())
        evaluate_document(report, grouped, gt)
    return report
