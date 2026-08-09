"use client";

// TRANG NGUỒN GOOGLE DRIVE (YC-BU-21).
//
// VÌ SAO CÓ TRANG NÀY: quy trình thật là cán bộ quét tài liệu rồi đổ vào một thư mục Drive dùng
// chung. Trước đây phải tải từng tệp về máy rồi tải lại lên hệ thống — hai lần chuyển tệp thủ công
// cho MỖI tài liệu, và không ai nhớ được tệp nào đã nạp.
//
// ĐIỀU QUAN TRỌNG NHẤT MÀN HÌNH NÀY PHẢI TRẢ LỜI: "tính năng nền này có đang chạy không, và lần
// gần nhất nó làm được gì?". Một việc chạy ngầm mà không nói được lần chạy cuối ra sao thì không
// ai dám tin — và khi có sự cố thì không ai biết bắt đầu tìm từ đâu.
//
// TỰ ĐỘNG DỪNG Ở ĐÂU: nạp → OCR → đoán loại → trích metadata. Hết. Việc chọn bộ sưu tập và xác
// nhận vẫn ở màn hình Duyệt — không tài liệu nào lên DSpace mà thiếu chữ ký của con người.

import React, { useCallback, useEffect, useState } from "react";
import { PageShell, ErrorBox, StatCard } from "@/components/hpu/HpuLayout";
import DocumentTypeSelect, { AUTO } from "@/components/DocumentTypeSelect";
import { formatNumber } from "@/lib/format";

const TRANG_THAI = {
  active: { text: "Đang quét", cls: "bg-green-50 text-green-700 border-green-200" },
  paused: { text: "Tạm dừng", cls: "bg-amber-50 text-amber-700 border-amber-200" },
};

export default function NguonDrivePage() {
  const [sources, setSources] = useState([]);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(null);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/nguon-drive", { credentials: "include" });
      const payload = await res.json();
      if (!res.ok) {
        setError(payload.message || `Không tải được danh sách nguồn (HTTP ${res.status})`);
        setSources([]);
        return;
      }
      setError("");
      setSources(payload.data || []);
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    } finally {
      setLoading(false);
    }
  }, []);

  // Kiểm tra cấu hình xác thực TRƯỚC khi cán bộ mất công thêm thư mục rồi mới nhận lỗi 403
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/nguon-drive/health", { credentials: "include" });
        const payload = await res.json();
        setHealth(payload.data || null);
      } catch {
        /* không kiểm được thì thôi — danh sách nguồn vẫn xem được */
      }
    })();
  }, []);

  useEffect(() => {
    load();
    // Chu kỳ dài (30 giây): quét chạy mỗi vài phút, làm mới dày hơn chỉ tốn request mà không thấy
    // gì mới — khác hẳn màn hình lô, nơi tiến độ nhích từng giây.
    const timer = setInterval(load, 30000);
    return () => clearInterval(timer);
  }, [load]);

  async function quetNgay(sourceId) {
    setScanning(sourceId);
    setError("");
    setNotice("");
    try {
      const res = await fetch(`/api/nguon-drive/${sourceId}/scan`, {
        method: "POST",
        credentials: "include",
      });
      const payload = await res.json();
      if (!res.ok) {
        setError(payload.message || "Quét thất bại");
        return;
      }
      setNotice(payload.message);
      await load();
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    } finally {
      setScanning(null);
    }
  }

  async function doiTrangThai(sourceId, status) {
    const hoi = {
      paused: "Tạm dừng quét thư mục này?\n\nCấu hình và lịch sử tệp đã nạp vẫn được giữ nguyên.",
      deleted:
        "Gỡ thư mục này khỏi danh sách?\n\nĐây là xóa mềm — lịch sử tệp đã nạp vẫn còn, " +
        "và các tài liệu đã số hóa không bị ảnh hưởng.",
    }[status];
    if (hoi && !confirm(hoi)) return;

    try {
      const res = await fetch(`/api/nguon-drive/${sourceId}`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      const payload = await res.json();
      if (!res.ok) {
        setError(payload.message || "Không đổi được trạng thái");
        return;
      }
      setNotice(payload.message);
      await load();
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    }
  }

  const tongDaNap = sources.reduce((s, x) => s + Number(x.so_da_nap || 0), 0);
  const tongLoi = sources.reduce((s, x) => s + Number(x.so_loi || 0), 0);

  return (
    <PageShell title="Nguồn Google Drive" activeKey="drive">
      {error && <ErrorBox message={error} />}
      {notice && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-2 text-sm text-green-800 mb-4">
          {notice}
        </div>
      )}

      {health && !health.san_sang && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 mb-4">
          <p className="text-sm font-semibold text-amber-900">Chưa dùng được Google Drive</p>
          <p className="text-sm text-amber-800 mt-0.5">{health.chi_tiet}</p>
          <p className="text-xs text-amber-700 mt-1">
            Người quản trị máy chủ cần đặt <code>GDRIVE_SERVICE_ACCOUNT_FILE</code> (khuyến nghị),
            hoặc bộ ba <code>GDRIVE_OAUTH_CLIENT_ID</code> / <code>_CLIENT_SECRET</code> /
            <code> _REFRESH_TOKEN</code>, rồi khởi động lại dịch vụ.
          </p>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-3 mb-4">
        <StatCard label="Thư mục đang theo dõi" value={sources.filter((s) => s.status === "active").length} />
        <StatCard label="Tài liệu đã nạp" value={tongDaNap} tone="success" />
        <StatCard label="Tệp lỗi" value={tongLoi} tone={tongLoi ? "danger" : "primary"} />
      </div>

      <ThemNguon onDone={(msg) => { setNotice(msg); load(); }} onError={setError} />

      <section className="bg-white rounded-xl border border-gray-200 overflow-hidden mt-4">
        <h2 className="px-4 py-3 text-base font-semibold text-gray-800 border-b border-gray-200">
          Thư mục đang theo dõi
        </h2>
        {loading && sources.length === 0 ? (
          <p className="p-4 text-sm text-gray-500">Đang tải…</p>
        ) : sources.length === 0 ? (
          <p className="p-4 text-sm text-gray-500">
            Chưa kết nối thư mục nào. Dán liên kết thư mục Drive ở trên để bắt đầu.
          </p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {sources.map((s) => (
              <SourceRow
                key={s.id}
                source={s}
                scanning={scanning === s.id}
                expanded={expanded === s.id}
                onToggle={() => setExpanded(expanded === s.id ? null : s.id)}
                onScan={() => quetNgay(s.id)}
                onSetStatus={(st) => doiTrangThai(s.id, st)}
              />
            ))}
          </ul>
        )}
      </section>
    </PageShell>
  );
}

function SourceRow({ source, scanning, expanded, onToggle, onScan, onSetStatus }) {
  const tt = TRANG_THAI[source.status] || TRANG_THAI.paused;
  const quetLoi = source.last_scan_status === "error";

  return (
    <li className="px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-gray-800">{source.name}</span>
            <span className={`rounded border px-2 py-0.5 text-xs ${tt.cls}`}>{tt.text}</span>
          </div>
          <div className="text-xs text-gray-500 mt-0.5 truncate">
            {source.folder_name || source.folder_id} · quét mỗi{" "}
            {Math.round(source.scan_interval_sec / 60)} phút · loại:{" "}
            {source.document_type === "auto" ? "tự động nhận dạng" : source.document_type}
          </div>

          {/* Lần quét gần nhất — thứ quan trọng nhất của một việc chạy ngầm */}
          <div className={`text-xs mt-1 ${quetLoi ? "text-red-700" : "text-gray-600"}`}>
            {source.last_scan_at ? (
              <>
                Lần quét gần nhất: {new Date(source.last_scan_at).toLocaleString("vi-VN")} —{" "}
                {quetLoi ? (
                  <span className="font-medium">lỗi: {source.last_scan_message}</span>
                ) : (
                  <>
                    thấy {formatNumber(source.last_scan_found)} tệp, nạp mới{" "}
                    {formatNumber(source.last_scan_ingested)}
                  </>
                )}
              </>
            ) : (
              "Chưa quét lần nào — bấm «Quét ngay» để kiểm tra cấu hình"
            )}
          </div>

          <div className="text-xs text-gray-500 mt-0.5">
            Tổng đã nạp: <strong>{formatNumber(source.so_da_nap || 0)}</strong>
            {Number(source.so_loi) > 0 && (
              <span className="text-red-700"> · lỗi: {formatNumber(source.so_loi)}</span>
            )}
            {" · "}
            <button onClick={onToggle} className="text-blue-700 hover:underline">
              {expanded ? "ẩn lịch sử tệp" : "xem lịch sử tệp"}
            </button>
          </div>
        </div>

        <div className="flex shrink-0 gap-2">
          <SmallButton onClick={onScan} disabled={scanning}>
            {scanning ? "Đang quét…" : "Quét ngay"}
          </SmallButton>
          {source.status === "active" ? (
            <SmallButton onClick={() => onSetStatus("paused")}>Tạm dừng</SmallButton>
          ) : (
            <SmallButton onClick={() => onSetStatus("active")}>Bật lại</SmallButton>
          )}
          <SmallButton danger onClick={() => onSetStatus("deleted")}>
            Gỡ
          </SmallButton>
        </div>
      </div>

      {expanded && <DriveFileList sourceId={source.id} />}
    </li>
  );
}

/**
 * Lịch sử tệp của một nguồn.
 *
 * Mặc định lọc TỆP LỖI trước: khi cán bộ mở lịch sử ra, thứ họ đang tìm gần như luôn là "tệp nào
 * không nạp được và vì sao", chứ không phải danh sách vài trăm tệp đã chạy trơn tru.
 */
function DriveFileList({ sourceId }) {
  const [files, setFiles] = useState([]);
  const [loc, setLoc] = useState("failed");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let huy = false;
    setLoading(true);
    (async () => {
      try {
        const q = loc ? `?status=${loc}` : "";
        const res = await fetch(`/api/nguon-drive/${sourceId}/files${q}`, {
          credentials: "include",
        });
        const payload = await res.json();
        if (!huy) setFiles(res.ok ? payload.data || [] : []);
      } catch {
        if (!huy) setFiles([]);
      } finally {
        if (!huy) setLoading(false);
      }
    })();
    return () => {
      huy = true;
    };
  }, [sourceId, loc]);

  const NHAN = { failed: "Lỗi", skipped: "Bỏ qua", ingested: "Đã nạp", "": "Tất cả" };

  return (
    <div className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
      <div className="flex gap-1.5 mb-2">
        {["failed", "skipped", "ingested", ""].map((v) => (
          <button
            key={v || "all"}
            onClick={() => setLoc(v)}
            className={`rounded border px-2 py-0.5 text-xs ${
              loc === v
                ? "border-gray-400 bg-white font-medium text-gray-800"
                : "border-gray-300 bg-white/50 text-gray-600"
            }`}
          >
            {NHAN[v]}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-xs text-gray-500">Đang tải…</p>
      ) : files.length === 0 ? (
        <p className="text-xs text-gray-500">
          {loc === "failed" ? "Không có tệp nào lỗi. 🎉" : "Chưa có tệp nào."}
        </p>
      ) : (
        <ul className="space-y-1 max-h-64 overflow-y-auto">
          {files.map((f) => (
            <li key={f.id} className="text-xs text-gray-700 border-b border-gray-200 pb-1">
              <span className="font-mono">{f.filename}</span>
              {f.note && <span className="text-gray-500"> — {f.note}</span>}
              {f.job_status && (
                <span className="text-gray-500"> · trạng thái xử lý: {f.job_status}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ThemNguon({ onDone, onError }) {
  const [folder, setFolder] = useState("");
  const [name, setName] = useState("");
  const [docType, setDocType] = useState(AUTO);
  const [interval, setIntervalMin] = useState(5);
  const [saving, setSaving] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!folder.trim()) return;

    setSaving(true);
    onError("");
    try {
      const res = await fetch("/api/nguon-drive", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          folder_id: folder.trim(),
          document_type: docType,
          scan_interval_sec: Math.max(60, Number(interval) * 60),
        }),
      });
      const payload = await res.json();
      if (!res.ok) {
        onError(payload.message || "Không kết nối được thư mục");
        return;
      }
      onDone(payload.message);
      setFolder("");
      setName("");
    } catch (err) {
      onError(`Không kết nối được backend (${err.message})`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="bg-white rounded-xl border border-gray-200 p-4">
      <h2 className="text-base font-semibold text-gray-800">Kết nối thư mục Drive</h2>
      <p className="text-xs text-gray-500 mt-0.5">
        Chia sẻ thư mục cho tài khoản dịch vụ của hệ thống (quyền «Người xem» là đủ), rồi dán liên
        kết thư mục vào đây. Hệ thống chỉ ĐỌC — không sửa, không xóa tệp gốc trên Drive.
      </p>

      <div className="grid gap-3 md:grid-cols-2 mt-3">
        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Liên kết hoặc mã thư mục
          </label>
          <input
            value={folder}
            onChange={(e) => setFolder(e.target.value)}
            placeholder="https://drive.google.com/drive/folders/1AbC…"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Tên gợi nhớ <span className="font-normal text-gray-400">(để trống sẽ lấy tên thư mục)</span>
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="VD: Kho quét khóa luận 2026"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Quét mỗi (phút)</label>
          <input
            type="number"
            min={1}
            value={interval}
            onChange={(e) => setIntervalMin(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
        </div>
        <div className="md:col-span-2">
          <DocumentTypeSelect
            value={docType}
            onChange={setDocType}
            disabled={saving}
            label="Loại tài liệu cho mọi tệp từ thư mục này"
          />
          <p className="text-xs text-gray-500 mt-1">
            Thư mục quét thường trộn nhiều loại — để «Tự động» thì mỗi tệp được đoán riêng theo nội
            dung sau khi OCR.
          </p>
        </div>
      </div>

      <button
        type="submit"
        disabled={saving || !folder.trim()}
        className="mt-3 rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        style={{ backgroundColor: "#1e3a5f" }}
      >
        {saving ? "Đang kiểm tra kết nối…" : "Kết nối thư mục"}
      </button>
      <p className="text-xs text-gray-500 mt-2">
        Tài liệu nạp về vẫn phải qua màn hình <strong>Duyệt</strong>: cán bộ chọn bộ sưu tập và xác
        nhận thì mới đẩy lên DSpace.
      </p>
    </form>
  );
}

function SmallButton({ children, onClick, danger, disabled }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`rounded border px-2 py-1 text-xs font-medium disabled:opacity-50 ${
        danger
          ? "border-red-200 bg-red-50 text-red-700 hover:bg-red-100"
          : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
      }`}
    >
      {children}
    </button>
  );
}
