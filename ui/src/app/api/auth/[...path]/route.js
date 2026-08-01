import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders, passThroughSetCookie } from '@/lib/api';

// Proxy same-origin cho toàn bộ nhóm /api/v2/auth/* của FastAPI (ADR-012).
//
// VÌ SAO GOM MỘT ROUTE: bốn endpoint xác thực (login/logout/me/change-password) có cùng một yêu cầu
// đặc biệt — phải chuyển tiếp cookie theo CẢ HAI CHIỀU:
//   • lên   : cookie phiên của trình duyệt → FastAPI, nếu không thì mọi request là "chưa đăng nhập";
//   • xuống : `Set-Cookie` của FastAPI → trình duyệt, nếu không thì đăng nhập xong vẫn như chưa.
// Viết bốn lần cùng một logic là bốn cơ hội quên một chiều.
//
// Cookie đặt bởi route này là same-origin với giao diện nên trình duyệt luôn gửi kèm — đây là lý do
// giao diện KHÔNG gọi thẳng FastAPI (xem commit 440f550).

export const dynamic = 'force-dynamic';

// Chỉ cho phép đúng những đường dẫn đã biết. Không có danh sách này thì đây thành proxy mở tới mọi
// endpoint bắt đầu bằng /api/v2/auth/ mà backend có thể thêm sau, kể cả endpoint không định lộ ra.
const ALLOWED = new Set(['login', 'logout', 'me', 'change-password']);

async function proxy(req, ctx, method) {
  const { path } = await ctx.params;
  const segment = (path || []).join('/');

  if (!ALLOWED.has(segment)) {
    return NextResponse.json(
      { status: 'error', message: 'Đường dẫn xác thực không hợp lệ' },
      { status: 404 }
    );
  }

  const init = {
    method,
    cache: 'no-store',
    headers: await forwardHeaders({ 'Content-Type': 'application/json' }),
  };
  if (method !== 'GET') {
    // Đọc thân dạng text rồi chuyển nguyên vẹn: không parse lại JSON để khỏi đổi dữ liệu người dùng gửi
    const body = await req.text();
    if (body) init.body = body;
  }

  try {
    const upstream = await fetch(`${apiBase()}/api/v2/auth/${segment}`, init);
    const text = await upstream.text();

    const response = new NextResponse(text, {
      status: upstream.status,
      headers: { 'Content-Type': upstream.headers.get('content-type') || 'application/json' },
    });
    return passThroughSetCookie(upstream, response);
  } catch (err) {
    return NextResponse.json(
      { status: 'error', message: 'Không kết nối được máy chủ xác thực', detail: err.message },
      { status: 502 }
    );
  }
}

export async function GET(req, ctx) {
  return proxy(req, ctx, 'GET');
}

export async function POST(req, ctx) {
  return proxy(req, ctx, 'POST');
}
