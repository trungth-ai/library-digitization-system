// =============================================================================
// src/app/api/ocr/download/batch/route.js
// =============================================================================

import { NextResponse } from 'next/server';
import { apiBase } from '@/lib/api';

export async function GET(req) {
  try {
    const { searchParams } = new URL(req.url);
    const ids = searchParams.getAll('ids');

    if (!ids || ids.length === 0) {
      return NextResponse.json({ error: 'No job IDs provided' }, { status: 400 });
    }

    // Route handler chạy PHÍA SERVER → gọi qua mạng nội bộ Docker (OCR_API_INTERNAL_URL).
    // Không dùng NEXT_PUBLIC_* ở đây: biến đó là URL cho TRÌNH DUYỆT và bị nhúng lúc build.
    const ocrApiUrl = apiBase();

    // Forward sang FastAPI GET /api/v2/download/batch?ids=x&ids=y
    const params = new URLSearchParams();
    ids.forEach(id => params.append('ids', id));

    const res = await fetch(`${ocrApiUrl}/api/v2/download/batch?${params.toString()}`);

    if (!res.ok) {
      return NextResponse.json(
        { error: 'Batch download failed' },
        { status: res.status }
      );
    }

    const timestamp = new Date().toISOString().slice(0, 10);

    return new NextResponse(res.body, {
      headers: {
        'Content-Type': 'application/zip',
        'Content-Disposition': `attachment; filename="batch_${timestamp}.zip"`,
        'Content-Length': res.headers.get('content-length') || '',
      },
    });

  } catch (err) {
    return NextResponse.json(
      { error: 'Batch download error', message: err.message },
      { status: 500 }
    );
  }
}