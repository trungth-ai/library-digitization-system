import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders } from '@/lib/api';

// Proxy same-origin tới FastAPI. Client PHẢI gọi qua đây thay vì gọi trực tiếp bằng URL tuyệt đối:
// trình duyệt không nhất thiết tới được địa chỉ nội bộ của API, và mọi thay đổi tên miền sẽ bắt
// phải build lại UI (NEXT_PUBLIC_* nhúng lúc build). Đi qua proxy thì client không cần biết gì.

export async function POST(req, ctx) {
  const { jobId } = await ctx.params;
  try {
    const res = await fetch(`${apiBase()}/api/v2/jobs/${jobId}/dspace-reset`, {
      method: 'POST',
      headers: await forwardHeaders({ 'Content-Type': 'application/json' }),
      cache: 'no-store',
    });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: { 'Content-Type': res.headers.get('content-type') || 'application/json' },
    });
  } catch (err) {
    return NextResponse.json(
      { error: 'Không kết nối được backend', detail: err.message },
      { status: 502 }
    );
  }
}
