import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders } from '@/lib/api';

// Proxy same-origin cho nhóm quản trị người dùng: /api/v2/{users,roles,sessions} (ADR-012).
//
// Mọi endpoint phía sau đều đòi quyền `user:manage` ở FastAPI — proxy này KHÔNG tự kiểm quyền, chỉ
// chuyển tiếp cookie. Cưỡng chế phải nằm ở một chỗ duy nhất (máy chủ); kiểm hai nơi thì sớm muộn hai
// nơi sẽ lệch nhau, và nơi lỏng hơn mới là nơi có hiệu lực thật.

export const dynamic = 'force-dynamic';

const ALLOWED_ROOTS = new Set(['users', 'roles', 'sessions']);

async function proxy(req, ctx, method) {
  const { path } = await ctx.params;
  const segments = path || [];

  if (!ALLOWED_ROOTS.has(segments[0])) {
    return NextResponse.json(
      { status: 'error', message: 'Đường dẫn quản trị không hợp lệ' },
      { status: 404 }
    );
  }

  const search = new URL(req.url).search;
  const init = {
    method,
    cache: 'no-store',
    headers: await forwardHeaders({ 'Content-Type': 'application/json' }),
  };
  if (method !== 'GET' && method !== 'DELETE') {
    const body = await req.text();
    if (body) init.body = body;
  }

  try {
    const upstream = await fetch(`${apiBase()}/api/v2/${segments.join('/')}${search}`, init);
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

export async function DELETE(req, ctx) {
  return proxy(req, ctx, 'DELETE');
}
