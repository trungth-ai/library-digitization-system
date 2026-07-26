import { NextResponse } from 'next/server';
import { apiBase } from '@/lib/api';

export async function DELETE(req, { params }) {
  try {
    const { jobId } = await params;
    // Route handler chạy PHÍA SERVER → gọi qua mạng nội bộ Docker (OCR_API_INTERNAL_URL).
    // Không dùng NEXT_PUBLIC_* ở đây: biến đó là URL cho TRÌNH DUYỆT và bị nhúng lúc build.
    const ocrApiUrl = apiBase();

    console.log(`Deleting job: ${jobId}`);

    const res = await fetch(`${ocrApiUrl}/api/v2/jobs/${jobId}`, {
      method: 'DELETE',
    });

    if (!res.ok) {
      const errorText = await res.text();
      console.error('FastAPI delete error:', errorText);
      return NextResponse.json(
        { error: 'Failed to delete job', detail: errorText },
        { status: res.status }
      );
    }

    const data = await res.json();
    console.log(`Job ${jobId} deleted successfully`);

    return NextResponse.json(data);

  } catch (err) {
    console.error('Delete job error:', err);
    return NextResponse.json(
      { error: 'Failed to delete job', message: err.message },
      { status: 500 }
    );
  }
}