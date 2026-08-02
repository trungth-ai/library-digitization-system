"use client";

// Trang QUẢN TRỊ NGƯỜI DÙNG (YC-QT-07 — ADR-012).
//
// Nguyên tắc hiển thị kế thừa từ /bao-cao: không vẽ bảng rỗng trông như đã có dữ liệu; backend chưa
// chạy thì hiện LÝ DO. Ẩn/hiện nút chỉ là tiện ích — quyền được cưỡng chế ở máy chủ, nên trang này
// vẫn an toàn kể cả khi ai đó sửa JavaScript trong trình duyệt.

import React, { useCallback, useEffect, useState } from "react";
import { PageShell, ErrorBox } from "@/components/hpu/HpuLayout";

const ROLE_LABELS = {
  admin: "Quản trị hệ thống",
  approver: "Cán bộ duyệt",
  librarian: "Cán bộ nghiệp vụ",
  viewer: "Người xem",
  service: "Tài khoản dịch vụ",
};

const STATUS_STYLE = {
  active: { label: "Đang dùng", cls: "bg-green-50 text-green-700 border-green-200" },
  disabled: { label: "Đã vô hiệu hóa", cls: "bg-gray-100 text-gray-600 border-gray-300" },
};

export default function QuanTriNguoiDungPage() {
  const [users, setUsers] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  // Mật khẩu tạm chỉ hiện MỘT LẦN sau khi đặt lại — quản trị viên đọc cho người dùng rồi nó biến mất
  const [tempPassword, setTempPassword] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/quan-tri/users", { credentials: "include" });
      const payload = await res.json();
      if (!res.ok) {
        setError(payload.message || `Không tải được danh sách (HTTP ${res.status})`);
        setUsers([]);
        return;
      }
      setUsers(payload.data || []);
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function call(path, options, successMessage) {
    setError("");
    setNotice("");
    try {
      const res = await fetch(path, { credentials: "include", ...options });
      const payload = await res.json();
      if (!res.ok) {
        setError(payload.message || `Thao tác thất bại (HTTP ${res.status})`);
        return null;
      }
      setNotice(successMessage || payload.message || "Đã thực hiện");
      await load();
      return payload.data;
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
      return null;
    }
  }

  async function handleResetPassword(user) {
    // Xác nhận trước thao tác nguy hiểm (chuẩn HPU): đặt lại mật khẩu sẽ đăng xuất người đó ngay
    if (!confirm(`Đặt lại mật khẩu cho "${user.full_name}"?\n\n` +
                 `Người dùng sẽ bị đăng xuất khỏi mọi thiết bị và phải đổi mật khẩu khi đăng nhập lại.`)) {
      return;
    }
    const data = await call(`/api/quan-tri/users/${user.id}/reset-password`, { method: "POST" });
    if (data?.temp_password) setTempPassword({ username: data.username, password: data.temp_password });
  }

  async function handleToggleStatus(user) {
    const disabling = user.status === "active";
    if (disabling && !confirm(
      `Vô hiệu hóa "${user.full_name}"?\n\n` +
      `Người này sẽ bị đăng xuất ngay và không đăng nhập được nữa. ` +
      `Nhật ký kiểm toán của họ vẫn được giữ nguyên.`)) {
      return;
    }
    await call(`/api/quan-tri/users/${user.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: disabling ? "disabled" : "active" }),
    }, disabling ? "Đã vô hiệu hóa tài khoản" : "Đã kích hoạt lại tài khoản");
  }

  async function handleUnlock(user) {
    await call(`/api/quan-tri/users/${user.id}/unlock`, { method: "POST" }, "Đã mở khóa tài khoản");
  }

  return (
    <PageShell
      title="Quản trị người dùng"
      activeKey="users"
      action={
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="rounded-lg px-4 py-2 text-sm font-medium text-white"
          style={{ backgroundColor: "#1e3a5f" }}
        >
          {showCreate ? "Đóng" : "+ Thêm người dùng"}
        </button>
      }
    >
      {error && <ErrorBox message={error} />}
      {notice && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-2 text-sm text-green-800 mb-4">
          {notice}
        </div>
      )}

      {tempPassword && (
        <TempPasswordBox info={tempPassword} onClose={() => setTempPassword(null)} />
      )}

      {showCreate && (
        <CreateUserForm
          onDone={async (body) => {
            const data = await call("/api/quan-tri/users", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
            });
            if (data) setShowCreate(false);
          }}
        />
      )}

      <section className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <p className="p-4 text-sm text-gray-500">Đang tải…</p>
        ) : users.length === 0 ? (
          <p className="p-4 text-sm text-gray-500">
            Chưa có người dùng nào{error ? "" : ". Bấm “Thêm người dùng” để tạo tài khoản đầu tiên."}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-gray-600">
                <tr>
                  <Th>Tên đăng nhập</Th>
                  <Th>Họ và tên</Th>
                  <Th>Vai trò</Th>
                  <Th>Trạng thái</Th>
                  <Th>Đăng nhập gần nhất</Th>
                  <Th>Thao tác</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {users.map((u) => (
                  <UserRow
                    key={u.id}
                    user={u}
                    onResetPassword={() => handleResetPassword(u)}
                    onToggleStatus={() => handleToggleStatus(u)}
                    onUnlock={() => handleUnlock(u)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className="text-xs text-gray-500 mt-4">
        Người dùng mới luôn phải đổi mật khẩu ở lần đăng nhập đầu. Vô hiệu hóa tài khoản không xóa
        nhật ký — mọi thao tác đã ghi vẫn truy được trách nhiệm.
      </p>
    </PageShell>
  );
}

function Th({ children }) {
  return <th className="px-4 py-2 font-medium whitespace-nowrap">{children}</th>;
}

function UserRow({ user, onResetPassword, onToggleStatus, onUnlock }) {
  const status = STATUS_STYLE[user.status] || STATUS_STYLE.disabled;
  const locked = user.locked_until && new Date(user.locked_until) > new Date();

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-2 font-medium text-gray-800">{user.username}</td>
      <td className="px-4 py-2 text-gray-700">{user.full_name}</td>
      <td className="px-4 py-2 text-gray-700">{ROLE_LABELS[user.role] || user.role}</td>
      <td className="px-4 py-2">
        <span className={`inline-block rounded border px-2 py-0.5 text-xs ${status.cls}`}>
          {status.label}
        </span>
        {locked && (
          <span className="ml-1 inline-block rounded border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs text-amber-700">
            Đang bị khóa
          </span>
        )}
      </td>
      <td className="px-4 py-2 text-gray-600 whitespace-nowrap">
        {user.last_login_at ? formatDateTime(user.last_login_at) : "Chưa đăng nhập lần nào"}
      </td>
      <td className="px-4 py-2">
        <div className="flex flex-wrap gap-2">
          {locked && <SmallButton onClick={onUnlock}>Mở khóa</SmallButton>}
          <SmallButton onClick={onResetPassword}>Đặt lại mật khẩu</SmallButton>
          <SmallButton onClick={onToggleStatus} danger={user.status === "active"}>
            {user.status === "active" ? "Vô hiệu hóa" : "Kích hoạt"}
          </SmallButton>
        </div>
      </td>
    </tr>
  );
}

function SmallButton({ children, onClick, danger }) {
  return (
    <button
      onClick={onClick}
      className={`rounded border px-2 py-1 text-xs font-medium ${
        danger
          ? "border-red-200 bg-red-50 text-red-700 hover:bg-red-100"
          : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
      }`}
    >
      {children}
    </button>
  );
}

function TempPasswordBox({ info, onClose }) {
  return (
    <div className="rounded-xl border-2 border-amber-300 bg-amber-50 p-4 mb-4">
      <h3 className="font-semibold text-amber-900">Mật khẩu tạm — chỉ hiện một lần</h3>
      <p className="text-sm text-amber-800 mt-1">
        Chuyển mật khẩu này cho <strong>{info.username}</strong>. Đóng hộp thoại là không xem lại được;
        nếu quên thì đặt lại lần nữa.
      </p>
      <code className="mt-2 inline-block rounded bg-white border border-amber-300 px-3 py-2 font-mono text-base">
        {info.password}
      </code>
      <div className="mt-3">
        <button
          onClick={onClose}
          className="rounded-lg border border-amber-400 bg-white px-3 py-1.5 text-sm font-medium text-amber-900"
        >
          Tôi đã chuyển mật khẩu — đóng
        </button>
      </div>
    </div>
  );
}

function CreateUserForm({ onDone }) {
  const [form, setForm] = useState({
    username: "", full_name: "", password: "", role: "librarian", email: "",
  });

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onDone(form);
      }}
      className="bg-white rounded-xl border border-gray-200 p-4 mb-4 grid gap-3 md:grid-cols-2"
    >
      <Input label="Tên đăng nhập" value={form.username} onChange={set("username")} required />
      <Input label="Họ và tên" value={form.full_name} onChange={set("full_name")} required />
      <Input label="Mật khẩu ban đầu" type="password" value={form.password}
             onChange={set("password")} required
             hint="Tối thiểu 10 ký tự. Người dùng sẽ phải đổi khi đăng nhập lần đầu." />
      <Input label="Email (không bắt buộc)" value={form.email} onChange={set("email")} />
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Vai trò</label>
        <select
          value={form.role}
          onChange={set("role")}
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
        >
          {Object.entries(ROLE_LABELS).map(([code, label]) => (
            <option key={code} value={code}>{label}</option>
          ))}
        </select>
      </div>
      <div className="flex items-end">
        <button
          type="submit"
          className="rounded-lg px-4 py-2 text-sm font-medium text-white"
          style={{ backgroundColor: "#1e3a5f" }}
        >
          Tạo tài khoản
        </button>
      </div>
    </form>
  );
}

function Input({ label, hint, ...props }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <input
        {...props}
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
                   focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      {hint && <p className="text-xs text-gray-500 mt-1">{hint}</p>}
    </div>
  );
}

function formatDateTime(iso) {
  // Hiển thị DD/MM/YYYY theo quy ước dự án
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
