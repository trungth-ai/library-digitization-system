import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders } from '@/lib/api';

// Proxy tình trạng chi tiết từng thành phần (Redis, PostgreSQL, worker, công cụ mô hình).
export async function GET() {
  try {
    const res = await fetch(`${apiBase()}/api/v2/health/detailed`,
      { cache: 'no-store', headers: await forwardHeaders() });
    return new NextResponse(await res.text(), {
      status: res.status,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (err) {
    return NextResponse.json(
      { error: 'Không kết nối được backend', detail: err.message },
      { status: 502 }
    );
  }
}
