import { NextResponse } from 'next/server';
import { apiBase } from '@/lib/api';

// Proxy same-origin tới FastAPI. Client PHẢI gọi qua đây thay vì gọi trực tiếp bằng URL tuyệt đối:
// trình duyệt không nhất thiết tới được địa chỉ nội bộ của API, và mọi thay đổi tên miền sẽ bắt
// phải build lại UI (NEXT_PUBLIC_* nhúng lúc build). Đi qua proxy thì client không cần biết gì.

export async function PUT(req, ctx) {
  const { jobId } = await ctx.params;
    const payload = await req.json().catch(() => ({}));

  try {
    const res = await fetch(`${apiBase()}/api/v2/jobs/${jobId}/dspace-collection`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
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
