// Tiện ích định dạng theo chuẩn HPU (ngày DD/MM/YYYY, số có phân cách).

/** YYYY-MM-DD (hoặc ISO) -> DD/MM/YYYY */
export function formatDateVN(value) {
  if (!value) return "";
  const d = new Date(value);
  if (isNaN(d)) return String(value);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}/${d.getFullYear()}`;
}

/** Số nguyên có dấu phân cách nghìn kiểu VN (1.234) */
export function formatNumber(n) {
  return new Intl.NumberFormat("vi-VN").format(n ?? 0);
}

/** Phần trăm từ tỉ lệ 0..1 */
export function formatPercent(ratio) {
  return `${((ratio ?? 0) * 100).toFixed(1)}%`;
}
