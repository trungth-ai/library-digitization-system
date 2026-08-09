import { NextResponse } from 'next/server';
import { apiBase, forwardHeaders } from '@/lib/api';

// Proxy same-origin cho LOẠI TÀI LIỆU (YC-SC-09).
//
//   GET  /api/loai-tai-lieu  → danh sách loại tài liệu đang dùng (đổ vào dropdown)
//   POST /api/loai-tai-lieu  → gợi ý loại từ danh sách TÊN TỆP, trước khi tải lên
//
// Gộp hai việc vào một route vì chúng luôn đi cùng nhau: mở form nạp tài liệu là cần cả danh sách
// loại lẫn gợi ý cho các tệp vừa chọn.
//
// Gợi ý nhận CẢ DANH SÁCH trong một lượt, không phải mỗi tệp một request: chọn một thư mục 500 tệp
// mà bắn 500 request thì trình duyệt tự bóp cổ mình.

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const upstream = await fetch(`${apiBase()}/api/v2/lookup/document-types`, {
      headers: await forwardHeaders(),
      cache: 'no-store',
    });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (err) {
    return NextResponse.json(
      { status: 'error', message: 'Không tải được danh sách loại tài liệu', detail: err.message },
      { status: 502 }
    );
  }
}

export async function POST(req) {
  try {
    const upstream = await fetch(`${apiBase()}/api/v2/classify/filenames`, {
      method: 'POST',
      headers: await forwardHeaders({ 'Content-Type': 'application/json' }),
      body: await req.text(),
      cache: 'no-store',
    });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (err) {
    return NextResponse.json(
      { status: 'error', message: 'Không lấy được gợi ý loại tài liệu', detail: err.message },
      { status: 502 }
    );
  }
}
