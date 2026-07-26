// Gọi backend FastAPI từ phía SERVER (server component / route handler).
//
// VÌ SAO CÓ FILE NÀY: `NEXT_PUBLIC_OCR_API_URL` là URL mà TRÌNH DUYỆT truy cập được (IP/domain
// công khai). Khi Next.js chạy trong Docker, lời gọi từ phía server nên đi qua mạng nội bộ
// (`http://api:8000`) — nhanh hơn và không phụ thuộc DNS/IP công khai. Vì vậy ưu tiên `OCR_API_INTERNAL_URL`
// nếu có, rồi mới đến biến công khai.

const DEFAULT_BASE = "http://localhost:8000";

export function apiBase() {
  return (
    process.env.OCR_API_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_OCR_API_URL ||
    DEFAULT_BASE
  ).replace(/\/+$/, "");
}

/**
 * Gọi API, luôn lấy dữ liệu mới (trang quản trị không được cache trạng thái cũ).
 * Trả về { ok, data, error } — KHÔNG ném lỗi, để trang còn dựng được và hiện thông báo
 * tiếng Việt thay vì trắng màn hình khi backend chưa chạy.
 */
export async function fetchApi(path) {
  const url = `${apiBase()}${path}`;
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) {
      return { ok: false, data: null, error: `Backend trả về HTTP ${res.status}` };
    }
    const body = await res.json();
    // Endpoint mới dùng envelope HPU {status, data, message}; endpoint cũ trả JSON thô (ADR-003)
    const data = body && typeof body === "object" && "data" in body ? body.data : body;
    return { ok: true, data, error: null };
  } catch (err) {
    return {
      ok: false,
      data: null,
      error: `Không kết nối được backend tại ${url} (${err.message})`,
    };
  }
}
