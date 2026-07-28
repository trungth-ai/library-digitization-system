"use client";

import React, { useState } from "react";
import { LogIn } from "lucide-react";
import { useRouter } from "next/navigation";

export default function LoginForm({ dspaceUrl }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [errorDetail, setErrorDetail] = useState("");
  const [success, setSuccess] = useState("");

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setErrorDetail("");
    setSuccess("");

    if (!email || !password) {
      setError("Vui lòng nhập email và mật khẩu");
      return;
    }

    setIsLoading(true);

    try {
      const res = await fetch("/api/dspace/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password, dspaceUrl }),
      });

      if (!res.ok) {
        const payload = await res.json();
        setError(payload.error ?? "Đăng nhập thất bại");
        // Giữ lại phản hồi gốc của DSpace: đây là thứ phân biệt "sai mật khẩu" với "REST API chết"
        setErrorDetail(payload.detail || "");
        setIsLoading(false);
        return;
      }

      // Check session
      const statusRes = await fetch("/api/dspace/status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ dspaceUrl }),
      });

      const statusData = await statusRes.json();

      if (statusData.authenticated) {
        setSuccess(`Xin chào, ${statusData.fullname}!`);

        // Bỏ trạng thái "đang tải" NGAY: trước đây thiếu dòng này nên nút kẹt ở "Đang đăng nhập..."
        // vĩnh viễn, và nếu bước dựng lại trang phía server thất bại thì người dùng không bấm lại được.
        setIsLoading(false);

        // Dựng lại trang phía server để nó thấy cookie phiên và hiện giao diện làm việc
        setTimeout(() => {
          router.refresh();
        }, 300);
      } else {
        setError("DSpace nhận đăng nhập nhưng phiên không hợp lệ — thử lại hoặc xóa cookie.");
        setIsLoading(false);
      }
    } catch (err) {
      setError(`Lỗi khi đăng nhập: ${err.message}`);
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-lg p-6 mb-8">
      <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <LogIn className="w-5 h-5" />
        Đăng nhập DSpace
      </h2>

      {/* Success Message */}
      {success && (
        <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
          {success} — đang chuyển trang...
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
          {errorDetail && (
            <div className="mt-2 pt-2 border-t border-red-200 text-xs text-red-600 font-mono break-all">
              Phản hồi từ DSpace: {errorDetail}
            </div>
          )}
        </div>
      )}

      <form onSubmit={handleLogin} className="space-y-4">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <p className="text-sm text-blue-800">
            <span className="font-semibold">Máy chủ:</span> {dspaceUrl}
          </p>
          <p className="text-xs text-blue-700 mt-1">
            Dùng tài khoản DSpace của bạn trên máy chủ thư viện — hệ thống này không có tài khoản riêng.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Email
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="ten.ban@hpu.edu.vn"
            disabled={isLoading}
            className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Mật khẩu
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            disabled={isLoading}
            className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            required
          />
        </div>

        <button
          type="submit"
          disabled={isLoading}
          className="w-full bg-blue-600 text-white py-3 rounded-lg hover:bg-blue-700 font-medium disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
        >
          {isLoading ? (
            <>
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
              Đang đăng nhập...
            </>
          ) : (
            "Đăng nhập"
          )}
        </button>
      </form>
    </div>
  );
}