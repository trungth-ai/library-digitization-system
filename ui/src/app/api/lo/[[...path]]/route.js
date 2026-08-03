import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders } from '@/lib/api';

// Proxy same-origin cho nhóm lô nạp tài liệu: /api/v2/batches* (sprint V5).
//
// ⚠️ HAI CẶP NGOẶC `[[...path]]` LÀ CÓ CHỦ ĐÍCH — ĐỪNG rút về `[...path]`.
//
// Next.js: `[...path]` là catch-all BẮT BUỘC, cần ít nhất một đoạn đường dẫn nên nó KHÔNG khớp
// `/api/lo` trần. `[[...path]]` là catch-all TÙY CHỌN, khớp cả đường dẫn cha.
//
// Trang `/lo` gọi `fetch("/api/lo")` để lấy danh sách lô (backend: `GET /api/v2/batches`). Với
// `[...path]`, lời gọi đó không khớp route nào → Next trả về trang 404 dạng HTML → `res.json()` chết
// với "Unexpected token '<', "<!DOCTYPE"...". Triệu chứng trông như backend sập, thực chất là request
// chưa bao giờ ra khỏi Next.
//
// Tách riêng khỏi proxy quản trị vì đường này phải chuyển tiếp được **thân multipart** của tệp tải
// lên: một lô có thể là 500 tệp, không được đọc hết vào RAM rồi mới gửi đi. `duplex: 'half'` cho
// phép chuyển tiếp thân request dạng luồng — thiếu nó thì Node đọc trọn tệp vào bộ nhớ trước.

export const dynamic = 'force-dynamic';

// Tệp lớn: không giới hạn thời gian mặc định của route
export const maxDuration = 600;

async function proxy(req, ctx, method) {
  const { path } = await ctx.params;
  const suffix = (path || []).join('/');
  const search = new URL(req.url).search;
  const url = `${apiBase()}/api/v2/batches${suffix ? '/' + suffix : ''}${search}`;

  const contentType = req.headers.get('content-type') || '';
  const isMultipart = contentType.startsWith('multipart/form-data');

  const headers = await forwardHeaders(
    isMultipart ? { 'content-type': contentType } : { 'Content-Type': 'application/json' }
  );

  const init = { method, headers, cache: 'no-store' };

  if (method !== 'GET') {
    if (isMultipart) {
      // Chuyển tiếp dạng luồng — KHÔNG đọc trọn tệp vào RAM
      init.body = req.body;
      init.duplex = 'half';
    } else {
      const body = await req.text();
      if (body) init.body = body;
    }
  }

  try {
    const upstream = await fetch(url, init);
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

export async function GET(req, ctx) {
  return proxy(req, ctx, 'GET');
}

export async function POST(req, ctx) {
  return proxy(req, ctx, 'POST');
}

export async function PUT(req, ctx) {
  return proxy(req, ctx, 'PUT');
}
