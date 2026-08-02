import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders } from '@/lib/api';

// Proxy xác nhận tài liệu (YC-RV-04, sprint V8).
//
// Xác nhận là hành vi CHỊU TRÁCH NHIỆM: nó ghi tên cán bộ vào `audit_log` và mở khóa cho việc đẩy
// lên DSpace. Vì vậy phải đi qua proxy có chuyển tiếp cookie phiên — gọi thẳng FastAPI từ trình
// duyệt sẽ mất phiên và tên người thực hiện.

export async function POST(req, ctx) {
  const { jobId } = await ctx.params;

  try {
    const upstream = await fetch(`${apiBase()}/api/v2/jobs/${jobId}/confirm`, {
      method: 'POST',
      cache: 'no-store',
      headers: await forwardHeaders({ 'Content-Type': 'application/json' }),
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
