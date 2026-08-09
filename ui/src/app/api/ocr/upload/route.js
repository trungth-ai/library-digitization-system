import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders } from '@/lib/api';

export const runtime = 'nodejs';

export async function POST(req) {
  try {
    const formData = await req.formData();
    const file = formData.get('file');
    const collection = formData.get('collection') || 'default';
    const language = formData.get('language') || 'vie';
    // Loại tài liệu (YC-SC-09). Route này TRƯỚC ĐÂY bỏ rơi trường này, nên mọi tệp tải qua trang
    // chính đều vào backend với loại mặc định 'book' dù cán bộ chọn gì — dựng lại nguyên vẹn.
    // Mặc định 'book' (KHÔNG phải 'auto') để giữ đúng hành vi cũ cho client chưa gửi trường này.
    const docType = formData.get('doc_type') || 'book';

    if (!file) {
      return NextResponse.json({ error: 'No file provided' }, { status: 400 });
    }

    // Forward to FastAPI
    // Route handler chạy PHÍA SERVER → gọi qua mạng nội bộ Docker (OCR_API_INTERNAL_URL).
    // Không dùng NEXT_PUBLIC_* ở đây: biến đó là URL cho TRÌNH DUYỆT và bị nhúng lúc build.
    const ocrApiUrl = apiBase();
    const uploadFormData = new FormData();
    uploadFormData.append('file', file);
    uploadFormData.append('collection', collection);
    uploadFormData.append('language', language);
    uploadFormData.append('doc_type', docType);

    const res = await fetch(`${ocrApiUrl}/api/v1/process`, {
      method: 'POST',
      body: uploadFormData,
      headers: await forwardHeaders(),
    });

    if (!res.ok) {
      const error = await res.json();
      return NextResponse.json(error, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);

  } catch (err) {
    return NextResponse.json(
      { error: 'Upload failed', message: err.message },
      { status: 500 }
    );
  }
}