import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders } from '@/lib/api';

// Proxy same-origin cho nhóm bảng điều khiển: /api/v2/dashboard* (sprint V7).

export const dynamic = 'force-dynamic';

export async function GET(req, ctx) {
  const { path } = await ctx.params;
  const suffix = (path || []).join('/');
  const search = new URL(req.url).search;

  try {
    const upstream = await fetch(
      `${apiBase()}/api/v2/dashboard/${suffix}${search}`,
      { cache: 'no-store', headers: await forwardHeaders() }
    );
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
