// Khung layout HPU: sidebar trái 240px (#1e3a5f) + vùng nội dung; StatCard.

import { formatNumber } from "@/lib/format";

const NAV = [
  { key: "upload", label: "Tải tài liệu", icon: "⬆️" },
  { key: "jobs", label: "Hàng đợi OCR", icon: "⏳" },
  { key: "dspace", label: "Đẩy DSpace", icon: "📤" },
  { key: "schemas", label: "Lược đồ", icon: "🧩" },
  { key: "reports", label: "Báo cáo", icon: "📊", active: true },
  { key: "audit", label: "Nhật ký kiểm toán", icon: "🔒" },
];

export function HpuSidebar({ appName = "DocuFlow HP" }) {
  return (
    <aside className="fixed left-0 top-0 h-screen w-60 bg-hpu-primary text-white flex flex-col">
      <div className="px-5 py-4 border-b border-white/10">
        <div className="text-lg font-bold">HPU · {appName}</div>
        <div className="text-xs text-white/60 mt-0.5">Số hóa & trích xuất tài liệu</div>
      </div>
      <nav className="flex-1 py-3">
        {NAV.map((item) => (
          <a key={item.key} href="#"
            className={`flex items-center gap-3 px-5 py-2.5 text-sm transition-colors ${
              item.active
                ? "bg-white/10 border-r-2 border-white font-medium"
                : "text-white/80 hover:bg-white/5"
            }`}>
            <span>{item.icon}</span>
            <span>{item.label}</span>
          </a>
        ))}
      </nav>
      <div className="px-5 py-3 border-t border-white/10 text-xs text-white/60">
        © Trung tâm Thông tin Thư viện
      </div>
    </aside>
  );
}

export function PageShell({ title, action, children }) {
  return (
    <div className="min-h-screen bg-[#f8fafc]">
      <HpuSidebar />
      <main className="ml-60 p-6">
        <div className="flex items-center justify-between mb-5">
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          {action}
        </div>
        {children}
      </main>
    </div>
  );
}

export function StatCard({ label, value, tone = "primary" }) {
  const toneCls = {
    primary: "text-hpu-primary",
    success: "text-hpu-success",
    warning: "text-hpu-warning",
    danger: "text-hpu-danger",
  }[tone];
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="text-xs font-medium text-gray-500">{label}</div>
      <div className={`text-2xl font-bold mt-1 tabular-nums ${toneCls}`}>
        {typeof value === "number" ? formatNumber(value) : value}
      </div>
    </div>
  );
}
