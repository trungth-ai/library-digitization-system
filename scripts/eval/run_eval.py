#!/usr/bin/env python3
"""
CLI đo đạc GĐ0 (KT-CX / KT-HN): chạy tập tài liệu qua các chế độ (cloud/local), so khớp với đáp án
chuẩn, xuất bảng độ chính xác theo TỪNG trường + thời gian — theo mẫu ghi kết quả (test plan 6.1).

Cách dùng:
    # Chuẩn bị: thư mục chứa <doc_id>.txt (văn bản đã trích) + ground_truth.json {doc_id: {field: value}}
    python -m scripts.eval.run_eval --data ./eval_data --truth ./eval_data/ground_truth.json \\
        --schema book --providers cloud,local --out ./eval_out

Lưu ý: cần cấu hình provider (CLAUDE_API_KEY cho cloud; Ollama chạy cho local). Số liệu phải ĐO THẬT
(nguyên tắc SRS "đo được mới tuyên bố") — không điền con số chưa chạy.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict

from scripts.eval.harness import run_provider_eval, EvalReport
from scripts.eval.schemas import get_schema


def load_documents(data_dir: str) -> Dict[str, str]:
    """Đọc tài liệu: .txt đọc thẳng; .pdf trích văn bản (lazy pypdf)."""
    docs: Dict[str, str] = {}
    for p in sorted(Path(data_dir).iterdir()):
        if p.suffix.lower() == ".txt":
            docs[p.stem] = p.read_text(encoding="utf-8")
        elif p.suffix.lower() == ".pdf":
            from scripts.digitize import PDFTextExtractor  # lazy
            docs[p.stem] = PDFTextExtractor().extract(str(p))
    return docs


def load_ground_truth(path: str) -> Dict[str, Dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def render_table(report: EvalReport) -> str:
    """Bảng độ chính xác theo từng trường (KT-CX yêu cầu báo cáo per-field)."""
    lines = []
    lines.append(f"  Provider: {report.provider}  |  Model: {report.model or '(n/a)'}  |  Cỡ mẫu: {report.n_docs} tài liệu")
    lines.append(f"  Độ chính xác tổng: {report.overall_accuracy*100:.1f}%  |  "
                 f"Tỉ lệ bịa (ảo giác): {report.hallucination_rate*100:.1f}%  |  "
                 f"Thời gian TB: {report.avg_latency_ms:.0f} ms/tài liệu")
    lines.append("  " + "-" * 74)
    lines.append(f"  {'Trường':<34}{'Đúng':>6}{'Sai':>6}{'Bịa':>6}{'Rỗng✓':>7}{'ĐộCX':>8}")
    lines.append("  " + "-" * 74)
    for key, st in sorted(report.per_field.items()):
        lines.append(f"  {key:<34}{st.correct:>6}{st.incorrect:>6}"
                     f"{st.hallucinated:>6}{st.correct_empty:>7}{st.accuracy*100:>7.1f}%")
    return "\n".join(lines)


def report_to_dict(report: EvalReport) -> dict:
    return {
        "provider": report.provider,
        "model": report.model,
        "version": report.version,
        "n_docs": report.n_docs,
        "overall_accuracy": round(report.overall_accuracy, 4),
        "hallucination_rate": round(report.hallucination_rate, 4),
        "avg_latency_ms": round(report.avg_latency_ms, 1),
        "per_field": {
            k: {"correct": s.correct, "incorrect": s.incorrect,
                "hallucinated": s.hallucinated, "correct_empty": s.correct_empty,
                "accuracy": round(s.accuracy, 4)}
            for k, s in report.per_field.items()
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Harness đo đạc DocuFlow HP (KT-CX/KT-HN)")
    ap.add_argument("--data", required=True, help="Thư mục tài liệu (.txt/.pdf)")
    ap.add_argument("--truth", required=True, help="File ground_truth.json")
    ap.add_argument("--schema", default="book", help="Lược đồ: book | thesis | cong_van")
    ap.add_argument("--providers", default="cloud", help="Danh sách provider, phẩy: cloud,local")
    ap.add_argument("--out", default="./eval_out", help="Thư mục xuất kết quả JSON")
    args = ap.parse_args(argv)

    docs = load_documents(args.data)
    truth = load_ground_truth(args.truth)
    schema = get_schema(args.schema)
    provider_kinds = [p.strip() for p in args.providers.split(",") if p.strip()]

    from scripts.providers.factory import get_provider  # lazy (tránh cần deps khi chỉ test harness)

    os.makedirs(args.out, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_reports = []

    print("=" * 78)
    print(f"BÁO CÁO ĐO ĐẠC — {datetime.now():%Y-%m-%d %H:%M} — lược đồ: {args.schema} — cỡ mẫu: {len(truth)}")
    print("=" * 78)

    for kind in provider_kinds:
        provider = get_provider(kind=kind, config=None)
        report = run_provider_eval(provider, docs, truth, schema)
        print("\n" + render_table(report))
        all_reports.append(report_to_dict(report))

    out_file = Path(args.out) / f"eval_{args.schema}_{ts}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({"schema": args.schema, "n_docs": len(truth),
                   "generated_at": ts, "reports": all_reports},
                  f, ensure_ascii=False, indent=2)
    print(f"\nĐã ghi kết quả: {out_file}")
    print("⚠️  Ghi kèm cỡ mẫu + phương pháp khi đưa vào hồ sơ (nguyên tắc: đo được mới tuyên bố).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
