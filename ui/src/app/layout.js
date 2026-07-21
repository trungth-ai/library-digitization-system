import "./globals.css";

export const metadata = {
  title: "DocuFlow HP — Số hóa tài liệu",
  description: "HPU — Số hóa & trích xuất dữ liệu tự động từ hồ sơ giấy",
};

// Dùng font hệ thống (system-ui) theo design system HPU — KHÔNG phụ thuộc Google Fonts,
// để docker build chạy được cả khi air-gapped / không có ca-certificates.
export default function RootLayout({ children }) {
  return (
    <html lang="vi">
      <body className="antialiased">{children}</body>
    </html>
  );
}
