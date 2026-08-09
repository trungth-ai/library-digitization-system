import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders } from '@/lib/api';

// Proxy same-origin cho nguồn Google Drive: /api/v2/drive/* (YC-BU-21).
//
// ⚠️ HAI CẶP NGOẶC `[[...path]]` LÀ CÓ CHỦ ĐÍCH — xem ghi chú dài trong `api/lo/[[...path]]`:
// `[...path]` là catch-all BẮT BUỘC nên KHÔNG khớp `/api/nguon-drive` trần, và trang sẽ nhận về
// một trang 404 dạng HTML mà `res.json()` không đọc nổi — trông hệt như backend sập.
//
// `maxDuration` cao: quét tay có thể tải hàng chục tệp từ Drive trong một request.

export const dynamic = 'force-dynamic';
export const maxDuration = 600;

// `health` là endpoint NGANG HÀNG với `sources` ở backend, không phải con của nó — ghép thẳng
// `sources/health` sẽ thành lời gọi tới một nguồn có mã "health" và trả 404 khó hiểu.
function backendPath(suffix) {
  if (!suffix) return 'sources';
  if (suffix === 'health') return 'health';
  return `sources/${suffix}`;
}

async function proxy(req, ctx, method) {
  const { path } = await ctx.params;
  const suffix = (path || []).join('/');
  const target = backendPath(suffix);
  const search = new URL(req.url).search;
  const url = `${apiBase()}/api/v2/drive/${target}${search}`;

  const init = {
    method,
    headers: await forwardHeaders({ 'Content-Type': 'application/json' }),
    cache: 'no-store',
  };
  if (method !== 'GET') {
    const body = await req.text();
    if (body) init.body = body;
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
