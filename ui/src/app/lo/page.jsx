"use client";

// Trang NẠP & THEO DÕI LÔ TÀI LIỆU (YC-BU-03/12 — sprint V5).
//
// Thay cho đường nạp cũ (trần 10 tệp, không theo dõi được): chọn nhiều tệp hoặc cả thư mục, đặt tên
// lô, rồi theo dõi tiến độ như MỘT mẻ việc.
//
// Nguyên tắc hiển thị quan trọng nhất: **liệt kê từng tệp bị bỏ qua kèm lý do**. Nạp 500 tệp mà chỉ
// báo "30 tệp lỗi" là thông tin vô dụng — cán bộ không biết tệp nào, cũng không biết phải sửa gì.

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { PageShell, ErrorBox, StatCard } from "@/components/hpu/HpuLayout";
import DocumentTypeSelect, { AUTO } from "@/components/DocumentTypeSelect";
import { formatNumber } from "@/lib/format";

const STATUS_LABEL = {
  running: { text: "Đang chạy", cls: "bg-blue-50 text-blue-700 border-blue-200" },
  paused: { text: "Tạm dừng", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  completed: { text: "Hoàn thành", cls: "bg-green-50 text-green-700 border-green-200" },
  cancelled: { text: "Đã hủy", cls: "bg-gray-100 text-gray-600 border-gray-300" },
};

export default function LoPage() {
  const [batches, setBatches] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/lo", { credentials: "include" });
      const payload = await res.json();
      if (!res.ok) {
        setError(payload.message || `Không tải được danh sách lô (HTTP ${res.status})`);
        setBatches([]);
        return;
      }
      setError("");
      setBatches(payload.data || []);
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    // Lô đang chạy thì làm mới định kỳ. 5 giây đủ để thấy tiến độ nhích mà không làm nặng backend.
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);

  async function setStatus(batchId, status) {
    const xacNhan = {
      paused: "Tạm dừng lô này?\n\nTài liệu đang xử lý dở vẫn chạy xong; tài liệu chưa bắt đầu sẽ đợi.",
      cancelled: "HỦY lô này?\n\nTài liệu đã xử lý xong vẫn được giữ nguyên, phần còn lại sẽ không chạy.",
    }[status];
    if (xacNhan && !confirm(xacNhan)) return;

    try {
      const res = await fetch(`/api/lo/${batchId}/status`, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      const payload = await res.json();
      if (!res.ok) {
        setError(payload.message || "Không đổi được trạng thái lô");
        return;
      }
      setNotice(payload.message);
      load();
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    }
  }

  return (
    <PageShell title="Lô tài liệu" activeKey="batches">
      {error && <ErrorBox message={error} />}
      {notice && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-2 text-sm text-green-800 mb-4">
          {notice}
        </div>
      )}

      <BatchUploader
        onDone={(data) => {
          setResult(data);
          setNotice(null);
          load();
        }}
        onError={setError}
      />

      {result && <UploadResult result={result} onClose={() => setResult(null)} />}

      <section className="bg-white rounded-xl border border-gray-200 overflow-hidden mt-4">
        <h2 className="px-4 py-3 text-base font-semibold text-gray-800 border-b border-gray-200">
          Các lô gần đây
        </h2>
        {loading && batches.length === 0 ? (
          <p className="p-4 text-sm text-gray-500">Đang tải…</p>
        ) : batches.length === 0 ? (
          <p className="p-4 text-sm text-gray-500">
            Chưa có lô nào. Chọn tệp ở trên để nạp lô đầu tiên.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-gray-600">
                <tr>
                  <th className="px-4 py-2 font-medium">Tên lô</th>
                  <th className="px-4 py-2 font-medium">Tiến độ</th>
                  <th className="px-4 py-2 font-medium">Kết quả</th>
                  <th className="px-4 py-2 font-medium">Trạng thái</th>
                  <th className="px-4 py-2 font-medium">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {batches.map((b) => (
                  <BatchRow key={b.id} batch={b} onSetStatus={setStatus} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </PageShell>
  );
}

function BatchRow({ batch, onSetStatus }) {
  const status = STATUS_LABEL[batch.status] || STATUS_LABEL.cancelled;
  const total = batch.total_files || 0;
  const done = batch.done_files || 0;

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-2">
        <div className="font-medium text-gray-800">{batch.name}</div>
        <div className="text-xs text-gray-500">
          {batch.nguoi_tao ? `${batch.nguoi_tao} · ` : ""}
          {batch.source === "zip" ? "từ tệp nén" : batch.source === "watch" ? "thư mục theo dõi" : "tải lên"}
        </div>
      </td>
      <td className="px-4 py-2 min-w-[10rem]">
        <div className="h-2 rounded-full bg-gray-200 overflow-hidden">
          <div
            className="h-full rounded-full"
            style={{ width: `${batch.tien_do_phan_tram || 0}%`, backgroundColor: "#1e3a5f" }}
          />
        </div>
        <div className="text-xs text-gray-600 mt-1">
          {formatNumber(done)}/{formatNumber(total)} ({batch.tien_do_phan_tram || 0}%)
        </div>
      </td>
      <td className="px-4 py-2 text-xs">
        <span className="text-green-700">{formatNumber(done)} xong</span>
        {batch.failed_files > 0 && (
          <span className="text-red-700"> · {formatNumber(batch.failed_files)} lỗi</span>
        )}
        {batch.skipped_files > 0 && (
          <span className="text-gray-600"> · {formatNumber(batch.skipped_files)} bỏ qua</span>
        )}
      </td>
      <td className="px-4 py-2">
        <span className={`inline-block rounded border px-2 py-0.5 text-xs ${status.cls}`}>
          {status.text}
        </span>
      </td>
      <td className="px-4 py-2">
        <div className="flex gap-2">
          {batch.status === "running" && (
            <SmallButton onClick={() => onSetStatus(batch.id, "paused")}>Tạm dừng</SmallButton>
          )}
          {batch.status === "paused" && (
            <SmallButton onClick={() => onSetStatus(batch.id, "running")}>Tiếp tục</SmallButton>
          )}
          {(batch.status === "running" || batch.status === "paused") && (
            <SmallButton danger onClick={() => onSetStatus(batch.id, "cancelled")}>
              Hủy
            </SmallButton>
          )}
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

function BatchUploader({ onDone, onError }) {
  const [files, setFiles] = useState([]);
  const [name, setName] = useState("");
  const [uploading, setUploading] = useState(false);
  // Cả lô dùng chung một loại tài liệu. 'auto' = mỗi tệp được đoán riêng theo nội dung sau khi OCR —
  // đúng với cách cán bộ nạp thật: một thư mục thường trộn nhiều loại.
  const [docType, setDocType] = useState(AUTO);

  const tongMB = files.reduce((s, f) => s + f.size, 0) / 1024 / 1024;

  // Thống kê gợi ý theo tên tệp cho cả lô: cán bộ nhìn một dòng là biết lô này gồm những loại gì,
  // thay vì phải mở từng tệp. Chỉ hiện khi để «Tự động» — chọn tay rồi thì gợi ý không còn ý nghĩa.
  const [phanBo, setPhanBo] = useState([]);
  const khoaTen = useMemo(() => files.map((f) => f.name).join("|"), [files]);

  useEffect(() => {
    if (!files.length || docType !== AUTO) {
      setPhanBo([]);
      return;
    }
    let huy = false;
    (async () => {
      try {
        const res = await fetch("/api/loai-tai-lieu", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filenames: files.map((f) => f.name) }),
        });
        if (!res.ok) return;
        const payload = await res.json();
        const dem = new Map();
        for (const item of payload.data || []) {
          // Gợi ý quá yếu thì xếp vào "chưa rõ" — hứa hẹn quá mức còn tệ hơn im lặng
          const nhan = item.confidence >= 0.35 ? item.label : "Chưa rõ (đoán theo nội dung sau OCR)";
          dem.set(nhan, (dem.get(nhan) || 0) + 1);
        }
        if (!huy) setPhanBo([...dem.entries()].sort((a, b) => b[1] - a[1]));
      } catch {
        /* không có gợi ý cũng không sao — worker vẫn đoán lại theo nội dung */
      }
    })();
    return () => {
      huy = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [khoaTen, docType]);

  async function submit(e) {
    e.preventDefault();
    if (files.length === 0) return;

    setUploading(true);
    onError("");
    try {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      form.append("name", name);
      form.append("doc_type", docType);

      const laZip = files.length === 1 && files[0].name.toLowerCase().endsWith(".zip");
      const duong = laZip ? "/api/lo/zip" : "/api/lo";
      if (laZip) {
        form.delete("files");
        form.append("file", files[0]);
      }

      const res = await fetch(duong, { method: "POST", credentials: "include", body: form });
      const payload = await res.json();
      if (!res.ok) {
        onError(payload.message || `Nạp thất bại (HTTP ${res.status})`);
        return;
      }
      onDone(payload.data);
      setFiles([]);
      setName("");
    } catch (err) {
      onError(`Không kết nối được backend (${err.message})`);
    } finally {
      setUploading(false);
    }
  }

  return (
    <form onSubmit={submit} className="bg-white rounded-xl border border-gray-200 p-4">
      <h2 className="text-base font-semibold text-gray-800">Nạp lô mới</h2>
      <p className="text-xs text-gray-500 mt-0.5">
        Chọn nhiều tệp PDF, cả thư mục, hoặc một tệp .zip. Tệp trùng nội dung sẽ tự động bỏ qua.
      </p>

      <div className="grid gap-3 md:grid-cols-2 mt-3">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Tên lô</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="VD: Công văn tháng 8/2026"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Tệp</label>
          <input
            type="file"
            multiple
            accept=".pdf,.zip"
            onChange={(e) => setFiles(Array.from(e.target.files || []))}
            className="w-full text-sm"
          />
        </div>
        <div className="md:col-span-2">
          <DocumentTypeSelect
            value={docType}
            onChange={setDocType}
            disabled={uploading}
            label="Loại tài liệu của cả lô"
          />
          <p className="text-xs text-gray-500 mt-1">
            Để «Tự động» khi lô trộn nhiều loại — mỗi tệp sẽ được đoán riêng theo nội dung sau OCR.
          </p>
        </div>
      </div>

      {files.length > 0 && (
        <p className="text-sm text-gray-700 mt-2">
          Đã chọn <strong>{formatNumber(files.length)}</strong> tệp ({tongMB.toFixed(1)} MB)
        </p>
      )}

      {phanBo.length > 0 && (
        <div className="mt-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
          <p className="text-xs font-medium text-gray-700">Đoán sơ bộ theo tên tệp</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {phanBo.map(([nhan, soLuong]) => (
              <span
                key={nhan}
                className="rounded border border-gray-300 bg-white px-2 py-0.5 text-xs text-gray-700"
              >
                {nhan}: <strong>{formatNumber(soLuong)}</strong>
              </span>
            ))}
          </div>
          <p className="text-xs text-gray-500 mt-1">
            Đây mới là đoán theo tên tệp. Sau khi OCR, hệ thống đọc nội dung và đoán lại chính xác hơn.
          </p>
        </div>
      )}

      <button
        type="submit"
        disabled={uploading || files.length === 0}
        className="mt-3 rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        style={{ backgroundColor: "#1e3a5f" }}
      >
        {uploading ? "Đang nạp…" : `Nạp ${files.length ? formatNumber(files.length) + " tệp" : ""}`}
      </button>
    </form>
  );
}

/**
 * Kết quả nạp — LIỆT KÊ TỪNG TỆP BỊ BỎ QUA KÈM LÝ DO.
 *
 * Đây là phần quan trọng nhất của màn hình: "30 tệp lỗi" không cho cán bộ biết phải làm gì, còn
 * "5 tệp trùng, 3 tệp không phải PDF, 2 tệp có mật khẩu" thì có.
 */
function UploadResult({ result, onClose }) {
  const boQua = result.bo_qua || [];

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 mt-4">
      <div className="grid gap-3 md:grid-cols-3">
        <StatCard label="Đã nhận" value={result.so_da_nhan || 0} tone="success" />
        <StatCard
          label="Bỏ qua"
          value={result.so_bo_qua || 0}
          tone={result.so_bo_qua ? "warning" : "primary"}
        />
        <StatCard label="Tên lô" value={result.name} />
      </div>

      {boQua.length > 0 && (
        <div className="mt-3">
          <h3 className="text-sm font-semibold text-gray-800">Tệp bị bỏ qua</h3>
          <ul className="mt-2 space-y-1 max-h-64 overflow-y-auto">
            {boQua.map((item, i) => (
              <li key={i} className="text-sm text-gray-700 border-b border-gray-100 pb-1">
                <span className="font-mono text-xs">{item.filename}</span>
                <span className="text-gray-500"> — {item.ly_do}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <button
        onClick={onClose}
        className="mt-3 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700"
      >
        Đóng
      </button>
    </div>
  );
}
