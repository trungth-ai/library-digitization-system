// =============================================================================
// src/app/api/ocr/download/[jobId]/route.js
// =============================================================================

import { NextResponse } from 'next/server';
import { apiBase } from '@/lib/api';

export async function GET(req, { params }) {
  try {
    const { jobId } = await params;
    // Route handler chạy PHÍA SERVER → gọi qua mạng nội bộ Docker (OCR_API_INTERNAL_URL).
    // Không dùng NEXT_PUBLIC_* ở đây: biến đó là URL cho TRÌNH DUYỆT và bị nhúng lúc build.
    const ocrApiUrl = apiBase();

    const res = await fetch(`${ocrApiUrl}/api/v2/download/${jobId}`);
    
    if (!res.ok) {
      return NextResponse.json(
        { error: 'Download failed' },
        { status: res.status }
      );
    }

    // ✅ THAY ĐỔI: Dùng res.body (stream) thay vì res.blob()
    // Không đợi tải xong → Browser nhận ngay và hiện dialog
    const body = res.body;

    return new NextResponse(body, {
      headers: {
        'Content-Type': 'application/zip',
        'Content-Disposition': `attachment; filename="${jobId}.zip"`,
        'Content-Length': res.headers.get('content-length') || '',
      },
    });

  } catch (err) {
    return NextResponse.json(
      { error: 'Download error', message: err.message },
      { status: 500 }
    );
  }
}

