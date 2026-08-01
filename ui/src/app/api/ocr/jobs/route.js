import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders } from '@/lib/api';

export async function GET(req) {
  try {
    const { searchParams } = new URL(req.url);
    const status = searchParams.get('status');
    const includeMetadata = searchParams.get('include_metadata');
    
    // Route handler chạy PHÍA SERVER → gọi qua mạng nội bộ Docker (OCR_API_INTERNAL_URL).
    // Không dùng NEXT_PUBLIC_* ở đây: biến đó là URL cho TRÌNH DUYỆT và bị nhúng lúc build.
    const ocrApiUrl = apiBase();
    
    // Build query params
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (includeMetadata) params.append('include_metadata', includeMetadata);
    
    const url = params.toString() 
      ? `${ocrApiUrl}/api/v2/jobs?${params.toString()}`
      : `${ocrApiUrl}/api/v2/jobs`;

    console.log('Fetching OCR jobs:', url);

    const res = await fetch(url, { cache: 'no-store', headers: await forwardHeaders() });
    
    if (!res.ok) {
      const errorText = await res.text();
      console.error('FastAPI error:', errorText);
      return NextResponse.json(
        { error: 'Failed to fetch jobs', detail: errorText },
        { status: res.status }
      );
    }

    const data = await res.json();
    
    console.log(`Fetched ${data.jobs?.length || 0} jobs`);
    
    return NextResponse.json(data);

  } catch (err) {
    console.error('OCR jobs fetch error:', err);
    return NextResponse.json(
      { error: 'Failed to fetch jobs', message: err.message },
      { status: 500 }
    );
  }
}