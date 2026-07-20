// Badge theo design system HPU: trạng thái + điểm tin cậy (YC-CF-04).

import { formatPercent } from "@/lib/format";

const STATUS_VARIANTS = {
  completed: "bg-hpu-success-light text-hpu-success",
  done:      "bg-hpu-success-light text-hpu-success",
  uploaded:  "bg-hpu-success-light text-hpu-success",
  failed:    "bg-hpu-danger-light text-hpu-danger",
  upload_failed: "bg-hpu-danger-light text-hpu-danger",
  ocr:       "bg-hpu-warning-light text-hpu-warning",
  extracting:"bg-hpu-warning-light text-hpu-warning",
  exporting: "bg-hpu-warning-light text-hpu-warning",
  processing:"bg-hpu-warning-light text-hpu-warning",
  queued:    "bg-gray-100 text-gray-600",
  pending:   "bg-gray-100 text-gray-600",
};

export function StatusBadge({ code, label }) {
  const cls = STATUS_VARIANTS[code] || "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {label || code}
    </span>
  );
}

/**
 * ConfidenceBadge (YC-CF-04): tô màu điểm tin cậy để cán bộ tập trung kiểm tra.
 * >=0.7 xanh (tin cậy) · 0.5–0.7 vàng (cần xem) · <0.5 đỏ (nghi bịa/ảo giác).
 */
export function ConfidenceBadge({ value }) {
  const v = value ?? 0;
  const cls =
    v >= 0.7 ? "bg-hpu-success-light text-hpu-success"
    : v >= 0.5 ? "bg-hpu-warning-light text-hpu-warning"
    : "bg-hpu-danger-light text-hpu-danger";
  const title =
    v >= 0.7 ? "Tin cậy" : v >= 0.5 ? "Cần kiểm tra" : "Nghi ngờ (có thể bịa)";
  return (
    <span title={title}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${cls}`}>
      {formatPercent(v)}
    </span>
  );
}
