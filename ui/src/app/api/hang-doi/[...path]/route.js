import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders } from '@/lib/api';

// Proxy same-origin cho nhóm hàng đợi: /api/v2/queue* (ADR-011, sprint V6).

export const dynamic = 'force-dynamic';

async function proxy(req, ctx, method) {
  const { path } = await ctx.params;
  const suffix = (path || []).join('/');
  const search = new URL(req.url).search;
  const url = `${apiBase()}/api/v2/queue${suffix ? '/' + suffix : ''}${search}`;

  const init = {
    method,
    cache: 'no-store',
    headers: await forwardHeaders({ 'Content-Type': 'application/json' }),
  };
  if (method === 'POST') {
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
