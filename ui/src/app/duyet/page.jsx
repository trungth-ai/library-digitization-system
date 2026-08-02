"use client";

// TRANG DUYỆT TÀI LIỆU (YC-RV-01/02/03/06 — sprint V8).
//
// VÌ SAO ĐÂY LÀ HẠNG MỤC ĐÁNG LÀM NHẤT CÒN LẠI: mọi thứ cần cho nó đã có từ tháng 7 —
// `GET /api/v2/jobs?needs_review=true`, cột `metadata_fields.confidence`, thành phần `ConfidenceBadge`.
// Chỉ thiếu đúng một trang giao diện, nên cán bộ vẫn phải sửa metadata trong bảng danh sách chung
// và không có cách nào biết trường nào đáng ngờ.
//
// BỐ CỤC HAI CỘT (YC-RV-02): PDF bên trái, trường metadata bên phải. Cán bộ phải ĐỐI CHIẾU — bắt họ
// mở PDF ở tab khác rồi chuyển qua lại là lý do chính khiến việc duyệt bị bỏ dở.

import React, { useCallback, useEffect, useState } from "react";
import { PageShell, ErrorBox } from "@/components/hpu/HpuLayout";
import { formatNumber } from "@/lib/format";

export default function DuyetPage() {
  const [pending, setPending] = useState([]);
  const [selected, setSelected] = useState(null);
  const [metadata, setMetadata] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [checked, setChecked] = useState(new Set());

  const loadPending = useCallback(async () => {
    try {
      const res = await fetch("/api/duyet/pending?per_page=100", { credentials: "include" });
      const payload = await res.json();
      if (!res.ok) {
        setError(payload.message || `Không tải được danh sách (HTTP ${res.status})`);
        return;
      }
      setError("");
      setPending(payload.data || []);
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    }
  }, []);

  useEffect(() => {
    loadPending();
  }, [loadPending]);

  const openDocument = useCallback(async (doc) => {
    setSelected(doc);
    setMetadata([]);
    try {
      const res = await fetch(`/api/ocr/jobs/${doc.id}/metadata`, { credentials: "include" });
      if (!res.ok) return;
      const payload = await res.json();
      setMetadata(payload.metadata || payload.data?.metadata || []);
    } catch {
      /* không tải được metadata thì vẫn xem được PDF — không chặn cả màn hình */
    }
  }, []);

  async function confirmOne(jobId) {
    setBusy(true);
    setNotice("");
    try {
      const res = await fetch(`/api/ocr/jobs/${jobId}/confirm`, {
        method: "POST",
        credentials: "include",
      });
      const payload = await res.json();
      if (!res.ok) {
        setError(payload.message || "Không xác nhận được");
        return;
      }
      setNotice(payload.message);
      setSelected(null);
      await loadPending();
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    } finally {
      setBusy(false);
    }
  }

  async function confirmBulk() {
    const ids = Array.from(checked);
    if (ids.length === 0) return;
    if (!confirm(
      `Xác nhận ${ids.length} tài liệu cùng lúc?\n\n` +
      `Xác nhận là hành vi chịu trách nhiệm — chỉ nên làm sau khi đã xem qua từng tài liệu. ` +
      `Sau khi xác nhận, tài liệu sẽ được phép đẩy lên DSpace.`
    )) return;

    setBusy(true);
    try {
      const res = await fetch("/api/duyet/bulk-confirm", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_ids: ids }),
      });
      const payload = await res.json();
      if (!res.ok) {
        setError(payload.message || "Không xác nhận được");
        return;
      }
      setNotice(payload.message);
      setChecked(new Set());
      await loadPending();
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    } finally {
      setBusy(false);
    }
  }

  // Phím tắt (YC-RV-03): cán bộ duyệt hàng trăm tài liệu/tuần — mỗi lần với chuột là một lần chậm.
  useEffect(() => {
    function onKey(e) {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if (!selected) return;

      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        confirmOne(selected.id);
      } else if (e.key === "Escape") {
        setSelected(null);
      } else if (e.key === "j" || e.key === "ArrowDown") {
        const i = pending.findIndex((d) => d.id === selected.id);
        if (i >= 0 && i < pending.length - 1) openDocument(pending[i + 1]);
      } else if (e.key === "k" || e.key === "ArrowUp") {
        const i = pending.findIndex((d) => d.id === selected.id);
        if (i > 0) openDocument(pending[i - 1]);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, pending, openDocument]);

  return (
    <PageShell
      title="Duyệt tài liệu"
      activeKey="review"
      action={
        checked.size > 0 && (
          <button
            onClick={confirmBulk}
            disabled={busy}
            className="rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            style={{ backgroundColor: "#1e3a5f" }}
          >
            Xác nhận {checked.size} tài liệu đã chọn
          </button>
        )
      }
    >
      {error && <ErrorBox message={error} />}
      {notice && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-2 text-sm text-green-800 mb-4">
          {notice}
        </div>
      )}

      {selected ? (
        <ReviewPane
          doc={selected}
          metadata={metadata}
          busy={busy}
          onConfirm={() => confirmOne(selected.id)}
          onClose={() => setSelected(null)}
        />
      ) : (
        <PendingList
          docs={pending}
          checked={checked}
          onToggle={(id) => {
            const next = new Set(checked);
            next.has(id) ? next.delete(id) : next.add(id);
            setChecked(next);
          }}
          onOpen={openDocument}
        />
      )}
    </PageShell>
  );
}

function PendingList({ docs, checked, onToggle, onOpen }) {
  if (docs.length === 0) {
    return (
      <section className="bg-white rounded-xl border border-gray-200 p-4">
        <p className="text-sm text-gray-600">
          Không có tài liệu nào chờ duyệt. 🎉
        </p>
      </section>
    );
  }

  return (
    <section className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-200">
        <h2 className="text-base font-semibold text-gray-800">
          {formatNumber(docs.length)} tài liệu chờ duyệt
        </h2>
        <p className="text-xs text-gray-500 mt-0.5">
          Sắp theo thời gian chờ — tài liệu chờ lâu nhất lên đầu. Bấm vào tên để mở màn hình đối chiếu.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-gray-600">
            <tr>
              <th className="px-3 py-2 w-8"></th>
              <th className="px-4 py-2 font-medium">Tài liệu</th>
              <th className="px-4 py-2 font-medium">Lý do cần xem</th>
              <th className="px-4 py-2 font-medium">Trường điểm thấp</th>
              <th className="px-4 py-2 font-medium">Đã chờ</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {docs.map((doc) => (
              <tr key={doc.id} className="hover:bg-gray-50">
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={checked.has(doc.id)}
                    onChange={() => onToggle(doc.id)}
                    // Chỉ cho chọn hàng loạt tài liệu KHÔNG có trường điểm thấp: duyệt hàng loạt
                    // một tài liệu đáng ngờ là bỏ qua đúng lúc cần xem kỹ nhất
                    disabled={doc.so_truong_diem_thap > 0}
                    title={doc.so_truong_diem_thap > 0
                      ? "Tài liệu có trường điểm tin cậy thấp — cần mở xem từng cái"
                      : ""}
                  />
                </td>
                <td className="px-4 py-2">
                  <button
                    onClick={() => onOpen(doc)}
                    className="text-blue-700 hover:underline text-left"
                  >
                    {doc.filename}
                  </button>
                </td>
                <td className="px-4 py-2 text-gray-600 max-w-md truncate">
                  {doc.review_note || (doc.needs_review ? "Cần kiểm tra" : "—")}
                </td>
                <td className="px-4 py-2">
                  {doc.so_truong_diem_thap > 0 ? (
                    <span className="text-red-700 font-medium">{doc.so_truong_diem_thap}</span>
                  ) : (
                    <span className="text-gray-400">0</span>
                  )}
                </td>
                <td className="px-4 py-2 text-gray-600">
                  {formatNumber(doc.gio_cho)} giờ
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ReviewPane({ doc, metadata, busy, onConfirm, onClose }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-semibold text-gray-800">{doc.filename}</h2>
          {doc.review_note && (
            <p className="text-sm text-amber-800 mt-0.5">{doc.review_note}</p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700"
          >
            Đóng (Esc)
          </button>
          <button
            onClick={onConfirm}
            disabled={busy}
            className="rounded-lg px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            style={{ backgroundColor: "#1e3a5f" }}
          >
            Xác nhận (Ctrl+Enter)
          </button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Cột trái: PDF */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <iframe
            src={`/api/ocr/download/${doc.id}#view=FitH`}
            title={doc.filename}
            className="w-full"
            style={{ height: "70vh" }}
          />
        </div>

        {/* Cột phải: metadata, tô màu trường điểm thấp (YC-CF-04) */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 overflow-y-auto"
             style={{ maxHeight: "70vh" }}>
          <h3 className="text-sm font-semibold text-gray-800 mb-2">Metadata trích xuất</h3>
          {metadata.length === 0 ? (
            <p className="text-sm text-gray-500">Chưa tải được metadata.</p>
          ) : (
            <dl className="space-y-2">
              {metadata.map((field, i) => (
                <MetadataRow key={`${field.key}-${i}`} field={field} />
              ))}
            </dl>
          )}
          <p className="text-xs text-gray-500 mt-4 pt-3 border-t border-gray-100">
            Phím tắt: <kbd>J</kbd>/<kbd>K</kbd> chuyển tài liệu · <kbd>Ctrl+Enter</kbd> xác nhận ·
            <kbd>Esc</kbd> đóng
          </p>
        </div>
      </div>
    </div>
  );
}

/**
 * Một trường metadata, TÔ MÀU theo điểm tin cậy (YC-CF-04).
 *
 * Điểm tin cậy chỉ có ích khi nó dẫn mắt cán bộ tới đúng chỗ cần kiểm. Hiện một cột số 0.42 giữa
 * mười trường khác thì không ai đọc; tô nền đỏ thì không thể bỏ qua.
 */
function MetadataRow({ field }) {
  const conf = field.confidence;
  const low = conf !== null && conf !== undefined && conf < 0.5;
  const medium = conf !== null && conf !== undefined && conf >= 0.5 && conf < 0.8;

  const cls = low
    ? "border-red-300 bg-red-50"
    : medium
      ? "border-amber-200 bg-amber-50"
      : "border-gray-200 bg-white";

  return (
    <div className={`rounded-lg border px-3 py-2 ${cls}`}>
      <dt className="text-xs font-mono text-gray-600 flex justify-between">
        <span>{field.key}</span>
        {conf !== null && conf !== undefined && (
          <span className={low ? "text-red-700 font-semibold" : "text-gray-500"}>
            {Math.round(conf * 100)}%
          </span>
        )}
      </dt>
      <dd className="text-sm text-gray-900 mt-0.5 break-words">
        {field.value || <span className="text-gray-400 italic">(trống)</span>}
      </dd>
      {low && (
        <p className="text-xs text-red-700 mt-1">
          Điểm tin cậy thấp — cần đối chiếu với bản gốc bên trái
        </p>
      )}
    </div>
  );
}
