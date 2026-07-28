import { apiBase } from '@/lib/api';

// Proxy SSE (tiến độ OCR) qua same-origin.
//
// Vì sao không cho client gọi thẳng FastAPI: EventSource tới URL tuyệt đối đòi trình duyệt phải tới
// được địa chỉ đó, và trên HTTPS thì URL http:// sẽ bị chặn vì mixed content. Đi qua đây thì luôn
// cùng origin với trang.
//
// `runtime = nodejs` + trả nguyên `res.body`: giữ luồng chảy liên tục, không đệm lại.
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(req) {
  const { searchParams } = new URL(req.url);
  const jobId = searchParams.get('job_id');
  const upstream = jobId
    ? `${apiBase()}/api/v2/jobs/${jobId}/stream`
    : `${apiBase()}/api/v2/jobs/stream`;

  try {
    const res = await fetch(upstream, {
      headers: { Accept: 'text/event-stream' },
      cache: 'no-store',
    });

    if (!res.ok || !res.body) {
      return new Response(`event: error
data: {"error":"backend HTTP ${res.status}"}

`, {
        status: 200,   // giữ 200 để EventSource nhận được thông báo lỗi thay vì tự thử lại vô hạn
        headers: { 'Content-Type': 'text/event-stream' },
      });
    }

    return new Response(res.body, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-transform',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no',   // chặn đệm ở tầng proxy phía trước
      },
    });
  } catch (err) {
    return new Response(
      `event: error
data: ${JSON.stringify({ error: 'Không kết nối được backend', detail: err.message })}

`,
      { status: 200, headers: { 'Content-Type': 'text/event-stream' } }
    );
  }
}
