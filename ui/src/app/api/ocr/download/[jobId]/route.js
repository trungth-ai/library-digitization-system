// =============================================================================
// src/app/api/ocr/download/[jobId]/route.js
// Proxy tải file ZIP (PDF đã OCR + metadata) từ FastAPI về trình duyệt.
// =============================================================================

import { NextResponse } from 'next/server';
import { apiBase } from '@/lib/api';

/**
 * Dựng header trả về cho tệp tải xuống.
 *
 * ⚠️ CHỖ TỪNG GÂY LỖI: trước đây luôn đặt
 *     'Content-Length': res.headers.get('content-length') || ''
 * FastAPI dùng `StreamingResponse` nên KHÔNG gửi `content-length` (nó dùng chunked encoding), khiến
 * header này thành CHUỖI RỖNG — một giá trị Content-Length không hợp lệ. Hệ quả: Node bỏ luôn thân
 * phản hồi (tải về 0 byte), và Caddy đứng trước coi đó là phản hồi hỏng nên trả **502** cho trình
 * duyệt. Triệu chứng ở giao diện là "Không tải được file đã xử lý từ backend (HTTP 502)" — mà FastAPI
 * thì vẫn ghi log 200 OK, nên rất dễ đi tìm sai chỗ.
 *
 * Nguyên tắc: CHỈ đặt Content-Length khi upstream thực sự có, và giữ nguyên Content-Disposition của
 * FastAPI (nó đã mã hóa UTF-8 đúng cho tên tệp tiếng Việt).
 */
function downloadHeaders(res, fallbackName) {
  const headers = {
    'Content-Type': res.headers.get('content-type') || 'application/zip',
    'Content-Disposition':
      res.headers.get('content-disposition') || `attachment; filename="${fallbackName}"`,
    'Cache-Control': 'no-store',
  };

  const length = res.headers.get('content-length');
  if (length) headers['Content-Length'] = length;   // không có thì để chunked, KHÔNG đặt rỗng

  return headers;
}

export async function GET(req, ctx) {
  const { jobId } = await ctx.params;
  try {
    // Route handler chạy PHÍA SERVER → gọi qua mạng nội bộ Docker (OCR_API_INTERNAL_URL).
    // Không dùng NEXT_PUBLIC_* ở đây: biến đó là URL cho TRÌNH DUYỆT và bị nhúng lúc build.
    const res = await fetch(`${apiBase()}/api/v2/download/${jobId}`, { cache: 'no-store' });

    if (!res.ok) {
      let detail = '';
      try {
        detail = (await res.text()).slice(0, 300);
      } catch {
        /* thân rỗng */
      }
      return NextResponse.json(
        { error: 'Không tải được file từ backend', status: res.status, detail },
        { status: res.status }
      );
    }

    // Truyền thẳng luồng (stream) — không đệm cả tệp vào bộ nhớ, tài liệu scan có thể rất lớn
    return new NextResponse(res.body, { headers: downloadHeaders(res, `${jobId}.zip`) });
  } catch (err) {
    return NextResponse.json(
      { error: 'Không kết nối được backend khi tải file', detail: err.message },
      { status: 502 }
    );
  }
}
