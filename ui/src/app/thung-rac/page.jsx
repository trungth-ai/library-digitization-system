"use client";

// THÙNG RÁC & PHỤC HỒI (YC-RV-05 — sprint V8).
//
// Xóa mềm đã có từ ADR-008 (`status='deleted'`, giữ nguyên tệp) và API phục hồi đã sẵn sàng từ đó —
// nhưng không có giao diện, nên "có thể phục hồi" là điều chỉ đúng trên lý thuyết: cán bộ xóa nhầm
// một tài liệu thì không có cách nào lấy lại nếu không nhờ người biết gọi API.
//
// Xóa VĨNH VIỄN có xác nhận HAI BƯỚC và chỉ quản trị viên làm được — thao tác này không hoàn tác được.

import React, { useCallback, useEffect, useState } from "react";
import { PageShell, ErrorBox } from "@/components/hpu/HpuLayout";
import { formatNumber } from "@/lib/format";

export default function ThungRacPage() {
  const [docs, setDocs] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/ocr/jobs?include_deleted=true&status=deleted&limit=200", {
        credentials: "include",
      });
      const payload = await res.json();
      if (!res.ok) {
        setError(payload.error || payload.message || `Không tải được (HTTP ${res.status})`);
        return;
      }
      setError("");
      setDocs(payload.jobs || payload.data?.jobs || []);
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function restore(jobId, filename) {
    setBusy(true);
    setNotice("");
    try {
      const res = await fetch(`/api/ocr/jobs/${jobId}/restore`, {
        method: "POST",
        credentials: "include",
      });
      const payload = await res.json();
      if (!res.ok) {
        setError(payload.message || "Không phục hồi được");
        return;
      }
      setNotice(`Đã phục hồi "${filename}"`);
      await load();
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    } finally {
      setBusy(false);
    }
  }

  async function purge(jobId, filename) {
    // Xác nhận HAI BƯỚC: thao tác này không hoàn tác được, và tệp PDF đã OCR là phần dữ liệu giá
    // trị nhất của hệ thống (xem docs/DEPLOY.md mục sao lưu).
    if (!confirm(
      `XÓA VĨNH VIỄN "${filename}"?\n\n` +
      `Thao tác này xóa cả bản ghi lẫn tệp PDF đã OCR. KHÔNG THỂ hoàn tác.\n` +
      `Nhật ký kiểm toán vẫn được giữ lại.`
    )) return;

    const xacNhan = prompt(
      `Để chắc chắn, hãy gõ đúng chữ XOA (không dấu) rồi bấm OK:`
    );
    if (xacNhan !== "XOA") {
      setNotice("Đã hủy thao tác xóa vĩnh viễn.");
      return;
    }

    setBusy(true);
    try {
      const res = await fetch(`/api/ocr/jobs/${jobId}?purge=true`, {
        method: "DELETE",
        credentials: "include",
      });
      const payload = await res.json();
      if (!res.ok) {
        setError(payload.message || payload.detail || "Không xóa được");
        return;
      }
      setNotice(`Đã xóa vĩnh viễn "${filename}"`);
      await load();
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell title="Thùng rác" activeKey="trash">
      {error && <ErrorBox message={error} />}
      {notice && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-2 text-sm text-green-800 mb-4">
          {notice}
        </div>
      )}

      <section className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200">
          <h2 className="text-base font-semibold text-gray-800">
            {formatNumber(docs.length)} tài liệu đã xóa
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Tài liệu xóa mềm vẫn giữ nguyên tệp PDF đã OCR và toàn bộ nhật ký kiểm toán — phục hồi
            được bất cứ lúc nào.
          </p>
        </div>

        {docs.length === 0 ? (
          <p className="p-4 text-sm text-gray-500">Thùng rác trống.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-gray-600">
                <tr>
                  <th className="px-4 py-2 font-medium">Tài liệu</th>
                  <th className="px-4 py-2 font-medium">Xóa lúc</th>
                  <th className="px-4 py-2 font-medium">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {docs.map((doc) => (
                  <tr key={doc.job_id || doc.id} className="hover:bg-gray-50">
                    <td className="px-4 py-2">
                      <div className="text-gray-800">{doc.filename}</div>
                      <div className="font-mono text-xs text-gray-500">
                        {doc.job_id || doc.id}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-gray-600">
                      {doc.finished_at || doc.updated_at || "—"}
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex gap-2">
                        <button
                          onClick={() => restore(doc.job_id || doc.id, doc.filename)}
                          disabled={busy}
                          className="rounded border border-gray-300 bg-white px-2 py-1 text-xs
                                     font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                        >
                          Phục hồi
                        </button>
                        <button
                          onClick={() => purge(doc.job_id || doc.id, doc.filename)}
                          disabled={busy}
                          className="rounded border border-red-200 bg-red-50 px-2 py-1 text-xs
                                     font-medium text-red-700 hover:bg-red-100 disabled:opacity-50"
                        >
                          Xóa vĩnh viễn
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className="text-xs text-gray-500 mt-4">
        Xóa vĩnh viễn cần quyền quản trị và không thể hoàn tác. Nhật ký kiểm toán của tài liệu vẫn
        được giữ để truy trách nhiệm.
      </p>
    </PageShell>
  );
}
