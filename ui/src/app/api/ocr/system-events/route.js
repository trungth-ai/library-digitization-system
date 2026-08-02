import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders } from '@/lib/api';

// Proxy danh sách sự kiện hạ tầng (mất kết nối, lỗi worker, job thất bại).
export async function GET(req) {
  const { searchParams } = new URL(req.url);
  try {
    const res = await fetch(`${apiBase()}/api/v2/system-events?${searchParams.toString()}`,
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
