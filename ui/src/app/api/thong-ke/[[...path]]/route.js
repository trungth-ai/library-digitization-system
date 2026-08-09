import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders } from '@/lib/api';

// Proxy same-origin cho thống kê: /api/v2/stats/* (YC-TT).
//
//   /api/thong-ke/me                 → của chính người đang đăng nhập
//   /api/thong-ke/users              → bảng theo từng cán bộ
//   /api/thong-ke/users/<tên>        → hồ sơ một người
//   /api/thong-ke/admin              → toàn hệ thống + số liệu an ninh
//   /api/thong-ke/classification     → độ chính xác đoán loại tài liệu
//
// ⚠️ `[[...path]]` hai cặp ngoặc — xem ghi chú trong `api/lo/[[...path]]/route.js`.

export const dynamic = 'force-dynamic';

export async function GET(req, ctx) {
  const { path } = await ctx.params;
  const suffix = (path || []).join('/');
  const search = new URL(req.url).search;
  const url = `${apiBase()}/api/v2/stats${suffix ? '/' + suffix : ''}${search}`;

  try {
    const upstream = await fetch(url, {
      headers: await forwardHeaders(),
      cache: 'no-store',
    });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { 'Content-Type': upstream.headers.get('content-type') || 'application/json' },
    });
  } catch (err) {
    return NextResponse.json(
      { status: 'error', message: 'Không kết nối được backend', detail: err.message },
      { status: 502 }
    );
  }
}
