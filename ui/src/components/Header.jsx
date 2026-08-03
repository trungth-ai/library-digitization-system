import React from 'react';

// Đường vào các trang bổ sung (sprint V2–V9).
//
// VÌ SAO CẦN: trang `/` là ứng dụng gốc, dùng `Header` chứ KHÔNG dùng `PageShell` — nên nó không có
// sidebar. Mọi trang mới đều bọc trong `PageShell` và liên kết được với nhau qua sidebar, nhưng
// không có đường nào từ `/` đi vào chúng, nên cách duy nhất vào là gõ URL. Hàng liên kết dưới đây
// chính là đường vào đó.
//
// CHỈ ĐỂ NHỮNG TRANG DÙNG HẰNG NGÀY. Đổ cả 10 trang vào đây sẽ biến một dải liên kết hữu ích thành
// một hàng chữ không ai đọc. Các trang dùng thưa hơn (Phân tích AI, Báo cáo, Công cụ mô hình, Thùng
// rác, Lược đồ, Quản trị người dùng) vẫn tới được qua sidebar ngay khi đã vào một trang ở đây.
//
// TODO(trungth): thêm/bớt theo thực tế công việc của Trung tâm — bạn biết cán bộ mở gì mỗi ngày.
const QUICK_LINKS = [
  { label: 'Bảng điều khiển', href: '/bang-dieu-khien', hint: 'Việc hôm nay, tồn đọng, hàng đợi' },
  { label: 'Duyệt tài liệu',  href: '/duyet',           hint: 'Đối chiếu PDF với metadata rồi xác nhận' },
  { label: 'Lô tài liệu',     href: '/lo',              hint: 'Nạp nhiều tệp hoặc một tệp .zip thành một lô' },
  { label: 'Hàng đợi',        href: '/hang-doi',        hint: 'Tài liệu đang chờ và tài liệu lỗi' },
];

export default function Header({ session }) {
  return (
    <header className="bg-white shadow-md border-b border-gray-200 sticky top-0 z-40">
      <div className="max-w-450 mx-auto px-8 py-4">
        <div className="flex items-center justify-between">
          {/* Left - Title */}
          <div className="flex items-center gap-3">
            <span className="text-3xl">🤖</span>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                Document Processing System
              </h1>
              <p className="text-sm text-gray-500">Upload → OCR → AI Analysis → DSpace</p>
            </div>
          </div>

          {/* Right - User Info */}
          {session?.authenticated && (
            <div className="flex items-center gap-3 bg-green-50 border-2 border-green-200 rounded-lg px-4 py-2">
              <span className="text-green-600 font-bold text-lg">✓</span>
              <span className="text-green-800 font-semibold">
                Logged in as {session.fullname}
              </span>
            </div>
          )}
        </div>

        {/* Hàng liên kết — CHỈ hiện khi đã đăng nhập: chưa đăng nhập thì mọi trang này đều đưa về
            form đăng nhập, nên hiện chúng chỉ làm người dùng bấm vào rồi quay lại đúng chỗ cũ. */}
        {session?.authenticated && (
          <nav className="mt-3 pt-3 border-t border-gray-100 flex flex-wrap items-center gap-x-1 gap-y-2">
            {QUICK_LINKS.map((link, i) => (
              <React.Fragment key={link.href}>
                {i > 0 && <span className="text-gray-300 px-1">·</span>}
                <a
                  href={link.href}
                  title={link.hint}
                  className="text-sm font-medium text-gray-700 hover:text-hpu-primary
                             hover:bg-gray-50 rounded px-2 py-1 transition-colors"
                >
                  {link.label}
                </a>
              </React.Fragment>
            ))}

            {/* Nói rõ còn trang khác, để cán bộ không tưởng hệ thống chỉ có mấy trang này */}
            <span className="ml-auto text-xs text-gray-400">
              Các trang khác nằm trong thanh bên
            </span>
          </nav>
        )}
      </div>
    </header>
  );
}