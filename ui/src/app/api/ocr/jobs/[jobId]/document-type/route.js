import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders } from '@/lib/api';

// Proxy same-origin cho việc CÁN BỘ SỬA LẠI loại tài liệu máy đã đoán (YC-SC-09).
//
// Backend giữ nguyên `detected_type` (ý kiến của máy) và chỉ đổi `document_type` (kết luận của
// người) — hai cột đó so với nhau chính là số liệu đo độ chính xác của bộ đoán loại.

export async function PUT(req, ctx) {
  const { jobId } = await ctx.params;
  const payload = await req.json().catch(() => ({}));

  try {
    const res = await fetch(`${apiBase()}/api/v2/jobs/${jobId}/document-type`, {
      method: 'PUT',
      headers: await forwardHeaders({ 'Content-Type': 'application/json' }),
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
      { status: 'error', message: 'Không kết nối được backend', detail: err.message },
      { status: 502 }
    );
  }
}
