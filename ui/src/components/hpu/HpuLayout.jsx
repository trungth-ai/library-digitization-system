// Khung layout HPU: sidebar trái 240px (#1e3a5f) + vùng nội dung; StatCard.

import { formatNumber } from "@/lib/format";

// Điều hướng: `href` chỉ đặt cho trang ĐÃ CÓ. Mục chưa làm để href=null và hiện mờ — thà nói rõ
// "chưa có" còn hơn để người dùng bấm vào một liên kết không đi đâu cả.
const NAV = [
  { key: "upload", label: "Tải tài liệu", icon: "⬆️", href: "/" },
  { key: "jobs", label: "Hàng đợi OCR", icon: "⏳", href: "/" },
  { key: "dspace", label: "Đẩy DSpace", icon: "📤", href: null },
  { key: "schemas", label: "Lược đồ", icon: "🧩", href: "/luoc-do" },
  { key: "reports", label: "Báo cáo", icon: "📊", href: "/bao-cao" },
  { key: "tools", label: "Công cụ mô hình", icon: "🧠", href: "/cong-cu" },
  { key: "audit", label: "Nhật ký kiểm toán", icon: "🔒", href: null },
];

export function HpuSidebar({ appName = "DocuFlow HP", activeKey = null }) {
  return (
    <aside className="fixed left-0 top-0 h-screen w-60 bg-hpu-primary text-white flex flex-col">
      <div className="px-5 py-4 border-b border-white/10">
        <div className="text-lg font-bold">HPU · {appName}</div>
        <div className="text-xs text-white/60 mt-0.5">Số hóa & trích xuất tài liệu</div>
      </div>
      <nav className="flex-1 py-3">
        {NAV.map((item) => {
          const active = item.key === activeKey;
          const base = "flex items-center gap-3 px-5 py-2.5 text-sm transition-colors";
          if (!item.href) {
            return (
              <span key={item.key}
                className={`${base} text-white/35 cursor-not-allowed`}
                title="Chức năng chưa có trong bản này">
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </span>
            );
          }
          return (
            <a key={item.key} href={item.href}
              className={`${base} ${
                active
                  ? "bg-white/10 border-r-2 border-white font-medium"
                  : "text-white/80 hover:bg-white/5"
              }`}>
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </a>
          );
        })}
      </nav>
      <div className="px-5 py-3 border-t border-white/10 text-xs text-white/60">
        © Trung tâm Thông tin Thư viện
      </div>
    </aside>
  );
}

export function PageShell({ title, action, activeKey = null, children }) {
  return (
    <div className="min-h-screen bg-[#f8fafc]">
      <HpuSidebar activeKey={activeKey} />
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

/** Hộp thông báo lỗi — dùng khi backend chưa chạy, để trang không trắng mà nói rõ nguyên nhân. */
export function ErrorBox({ title = "Không tải được dữ liệu", message }) {
  return (
    <div className="bg-hpu-danger-light border border-hpu-danger/30 rounded-xl p-4 mb-5">
      <div className="text-sm font-semibold text-hpu-danger">{title}</div>
      {message && <div className="text-sm text-gray-700 mt-1">{message}</div>}
      <div className="text-xs text-gray-500 mt-2">
        Kiểm tra backend đang chạy và biến <code>NEXT_PUBLIC_OCR_API_URL</code> trỏ đúng địa chỉ.
      </div>
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
