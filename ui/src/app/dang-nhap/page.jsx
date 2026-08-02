"use client";

// Trang ĐĂNG NHẬP DOCUFLOW (ADR-012).
//
// ⚠️ KHÁC HOÀN TOÀN với `LoginForm.jsx` — thành phần đó đăng nhập vào **DSpace** (hệ đích), dùng bộ
// tài khoản khác. Hai thứ phải giữ tách bạch và gọi tên rõ ràng trên giao diện, nếu không cán bộ sẽ
// nhầm mật khẩu nào dùng ở đâu và mất thời gian của cả hai phía.

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { LogIn, KeyRound, AlertCircle } from "lucide-react";

export default function DangNhapPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Bước đổi mật khẩu bắt buộc (YC-QT-05): tài khoản mới hoặc vừa được đặt lại mật khẩu
  const [mustChange, setMustChange] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  async function handleLogin(e) {
    e.preventDefault();
    setError("");

    if (!username || !password) {
      setError("Vui lòng nhập tên đăng nhập và mật khẩu");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username, password }),
      });
      const payload = await res.json();

      if (!res.ok) {
        // Giữ nguyên thông báo tiếng Việt của backend: nó phân biệt "sai mật khẩu" với
        // "tài khoản bị khóa còn N phút" — hai tình huống cần hai hành động khác nhau
        setError(payload.message || "Đăng nhập thất bại");
        return;
      }

      if (payload.data?.user?.must_change_password) {
        setMustChange(true);
        return;
      }

      router.push("/");
      router.refresh();
    } catch (err) {
      setError(`Không kết nối được máy chủ (${err.message})`);
    } finally {
      setLoading(false);
    }
  }

  async function handleChangePassword(e) {
    e.preventDefault();
    setError("");

    if (newPassword !== confirmPassword) {
      setError("Hai lần nhập mật khẩu mới không khớp nhau");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("/api/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ current_password: password, new_password: newPassword }),
      });
      const payload = await res.json();

      if (!res.ok) {
        setError(payload.message || "Không đổi được mật khẩu");
        return;
      }

      // Đổi mật khẩu thu hồi mọi phiên (kể cả phiên hiện tại) → phải đăng nhập lại
      setMustChange(false);
      setPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setError("Đã đổi mật khẩu. Vui lòng đăng nhập lại bằng mật khẩu mới.");
    } catch (err) {
      setError(`Không kết nối được máy chủ (${err.message})`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold" style={{ color: "#1e3a5f" }}>
            DocuFlow HP
          </h1>
          <p className="text-sm text-gray-600 mt-1">
            Hệ thống số hóa tài liệu — Trung tâm Thông tin Thư viện
          </p>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          {mustChange ? (
            <>
              <div className="flex items-center gap-2 mb-1">
                <KeyRound className="w-5 h-5" style={{ color: "#1e3a5f" }} />
                <h2 className="text-lg font-semibold text-gray-800">Đổi mật khẩu</h2>
              </div>
              <p className="text-sm text-gray-600 mb-4">
                Đây là lần đăng nhập đầu tiên. Bạn cần đặt mật khẩu mới mà chỉ mình bạn biết.
              </p>

              <form onSubmit={handleChangePassword} className="space-y-4">
                <Field
                  label="Mật khẩu mới"
                  type="password"
                  value={newPassword}
                  onChange={setNewPassword}
                  hint="Tối thiểu 10 ký tự. Không dùng tên của bạn hoặc mật khẩu dễ đoán."
                />
                <Field
                  label="Nhập lại mật khẩu mới"
                  type="password"
                  value={confirmPassword}
                  onChange={setConfirmPassword}
                />
                {error && <ErrorBox message={error} />}
                <SubmitButton loading={loading} label="Đổi mật khẩu" />
              </form>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2 mb-1">
                <LogIn className="w-5 h-5" style={{ color: "#1e3a5f" }} />
                <h2 className="text-lg font-semibold text-gray-800">Đăng nhập DocuFlow</h2>
              </div>
              {/* Nói rõ ngay đây để cán bộ không thử mật khẩu DSpace */}
              <p className="text-sm text-gray-600 mb-4">
                Tài khoản do quản trị viên cấp. Đây <strong>không phải</strong> tài khoản DSpace —
                kết nối DSpace được cấu hình riêng trong phần đẩy tài liệu.
              </p>

              <form onSubmit={handleLogin} className="space-y-4">
                <Field
                  label="Tên đăng nhập"
                  value={username}
                  onChange={setUsername}
                  autoFocus
                />
                <Field
                  label="Mật khẩu"
                  type="password"
                  value={password}
                  onChange={setPassword}
                />
                {error && <ErrorBox message={error} />}
                <SubmitButton loading={loading} label="Đăng nhập" />
              </form>
            </>
          )}
        </div>

        <p className="text-xs text-gray-500 text-center mt-4">
          Quên mật khẩu? Liên hệ quản trị viên để được đặt lại.
        </p>
      </div>
    </main>
  );
}

function Field({ label, value, onChange, type = "text", hint, autoFocus }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <input
        type={type}
        value={value}
        autoFocus={autoFocus}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
                   focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      {hint && <p className="text-xs text-gray-500 mt-1">{hint}</p>}
    </div>
  );
}

function ErrorBox({ message }) {
  return (
    <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 px-3 py-2">
      <AlertCircle className="w-4 h-4 text-red-600 mt-0.5 shrink-0" />
      <p className="text-sm text-red-700">{message}</p>
    </div>
  );
}

function SubmitButton({ loading, label }) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="w-full rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
      style={{ backgroundColor: "#1e3a5f" }}
    >
      {loading ? "Đang xử lý…" : label}
    </button>
  );
}
