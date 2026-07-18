import { NextResponse } from 'next/server';

export async function GET(req) {
  try {
    const { searchParams } = new URL(req.url);
    const status = searchParams.get('status');
    const includeMetadata = searchParams.get('include_metadata');
    
    const ocrApiUrl = process.env.NEXT_PUBLIC_OCR_API_URL;
    
    // Build query params
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (includeMetadata) params.append('include_metadata', includeMetadata);
    
    const url = params.toString() 
      ? `${ocrApiUrl}/api/v2/jobs?${params.toString()}`
      : `${ocrApiUrl}/api/v2/jobs`;

    console.log('Fetching OCR jobs:', url);

    const res = await fetch(url);
    
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