import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders } from '@/lib/api';

// Proxy tới /api/v2/stats của FastAPI. Client cần số liệu này để biết hàng đợi có việc mà
// KHÔNG có worker nào đang chạy — trường hợp trước đây hoàn toàn im lặng.
export async function GET() {
  try {
    const res = await fetch(`${apiBase()}/api/v2/stats`,
      { cache: 'no-store', headers: await forwardHeaders() });
    if (!res.ok) {
      return NextResponse.json({ error: `Backend trả về HTTP ${res.status}` }, { status: res.status });
    }
    return NextResponse.json(await res.json());
  } catch (err) {
    return NextResponse.json(
      { error: 'Không kết nối được backend', detail: err.message },
      { status: 502 }
    );
  }
}
