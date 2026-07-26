// File: src/app/api/dspace/login/route.js
//
// Đăng nhập DSpace 6.x REST API (POST /rest/login, form-urlencoded) và chuyển JSESSIONID về trình duyệt.
// LƯU Ý: hệ thống này KHÔNG có tài khoản riêng — người dùng đăng nhập bằng chính tài khoản DSpace của
// mình trên máy chủ thư viện. Mật khẩu chỉ đi qua đây một lần để lấy phiên, không được lưu lại.
import { NextResponse } from "next/server";

export const runtime = "nodejs";

/**
 * Chuyển mã lỗi HTTP của DSpace thành thông báo tiếng Việt NÊU ĐƯỢC VIỆC CẦN LÀM.
 *
 * Vì sao cần: trước đây mọi lỗi đều hiện "Login failed", nên "sai mật khẩu" và "REST API của DSpace
 * đang chết" trông giống nhau — người dùng đổi mật khẩu mãi không được trong khi lỗi nằm ở máy chủ.
 */
function messageForStatus(status, dspaceUrl) {
  if (status === 401 || status === 403) {
    return "Sai email hoặc mật khẩu DSpace. Đây là tài khoản trên máy chủ thư viện, không phải tài khoản riêng của hệ thống này.";
  }
  if (status === 404) {
    return `Không tìm thấy REST API tại ${dspaceUrl}/rest/login. Kiểm tra đường dẫn và phiên bản DSpace (bản 7.x dùng /server/api/authn/login).`;
  }
  if (status === 502 || status === 503 || status === 504) {
    return `DSpace có chạy nhưng REST API không phản hồi (HTTP ${status}). Module /rest chưa được bật hoặc reverse proxy chưa trỏ tới nó — không mật khẩu nào đăng nhập được cho tới khi sửa xong.`;
  }
  return `DSpace từ chối đăng nhập (HTTP ${status}).`;
}

export async function POST(req) {
  let dspaceUrl = "";
  try {
    const body_ = await req.json();
    const { email, password } = body_;
    dspaceUrl = (body_.dspaceUrl || "").replace(/\/+$/, "");

    if (!dspaceUrl) {
      return NextResponse.json(
        { error: "Thiếu địa chỉ DSpace. Kiểm tra biến NEXT_PUBLIC_DSPACE_URL khi build UI." },
        { status: 400 }
      );
    }

    // Build form-urlencoded body as per DSpace 6.3 REST API spec
    const body = new URLSearchParams();
    body.append("email", email);
    body.append("password", password);

    const res = await fetch(`${dspaceUrl}/rest/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });

    if (!res.ok) {
      // Giữ lại thân phản hồi để chẩn đoán, nhưng CẮT NGẮN: thân lỗi của Tomcat là cả trang HTML.
      let detail = "";
      try {
        detail = (await res.text()).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().slice(0, 300);
      } catch {
        detail = "";
      }
      return NextResponse.json(
        { error: messageForStatus(res.status, dspaceUrl), status: res.status, detail },
        { status: res.status }
      );
    }

    const rawCookie = res.headers.get("set-cookie");

    if (!rawCookie) {
      return NextResponse.json(
        { error: "DSpace đăng nhập được nhưng không trả về cookie phiên (JSESSIONID)." },
        { status: 500 }
      );
    }

    // 👉 CẮT CHỈ LẤY JSESSIONID
    const jsession = rawCookie.split(";")[0];

    const response = NextResponse.json({ success: true, message: "Đăng nhập thành công" });

    // 👉 SET COOKIE LẠI CHO BROWSER
    response.headers.set("Set-Cookie", `${jsession}; Path=/; HttpOnly; SameSite=Lax`);

    return response;
  } catch (err) {
    // Tới đây nghĩa là KHÔNG gọi được DSpace (DNS, TLS, firewall) — khác hẳn với "DSpace trả lỗi".
    // Lời gọi này đi từ CONTAINER, nên container phải ra được Internet/mạng nội bộ tới máy chủ thư viện.
    return NextResponse.json(
      {
        error: `Không kết nối được tới DSpace tại ${dspaceUrl || "(chưa rõ)"}. `
             + `Kiểm tra container UI có ra được địa chỉ này không (DNS, firewall, chứng chỉ TLS).`,
        detail: err.message,
      },
      { status: 502 }
    );
  }
}
