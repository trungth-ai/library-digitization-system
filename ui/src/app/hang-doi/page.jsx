"use client";

// Trang HÀNG ĐỢI (ADR-011, sprint V6).
//
// VÌ SAO CẦN TRANG NÀY: bản vá N-02 đã làm cho job không còn biến mất khi worker chết — job lỗi giờ
// nằm trong "hàng đợi chết" kèm lý do. Nhưng nếu chỉ có API thì thông tin đó vẫn vô hình với cán bộ,
// và triệu chứng ở giao diện vẫn y như trước: tài liệu treo mà không rõ vì sao.
//
// Trang này biến hàng đợi chết thành thứ NHÌN THẤY và BẤM ĐƯỢC.

import React, { useCallback, useEffect, useState } from "react";
import { PageShell, ErrorBox, StatCard } from "@/components/hpu/HpuLayout";
import { formatNumber } from "@/lib/format";

export default function HangDoiPage() {
  const [depth, setDepth] = useState(null);
  const [dead, setDead] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [depthRes, deadRes] = await Promise.all([
        fetch("/api/hang-doi", { credentials: "include" }),
        fetch("/api/hang-doi/dead", { credentials: "include" }),
      ]);
      const depthPayload = await depthRes.json();
      const deadPayload = await deadRes.json();

      if (!depthRes.ok) {
        setError(depthPayload.message || `Không đọc được hàng đợi (HTTP ${depthRes.status})`);
        return;
      }
      setError("");
      setDepth(depthPayload.data);
      setDead(deadRes.ok ? deadPayload.data || [] : []);
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [load]);

  async function retry(jobId) {
    setBusy(true);
    setNotice("");
    try {
      const res = await fetch(`/api/hang-doi/dead/${jobId}/retry`, {
        method: "POST",
        credentials: "include",
      });
      const payload = await res.json();
      if (!res.ok) {
        setError(payload.message || "Không chạy lại được");
        return;
      }
      setNotice(payload.message);
      await load();
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    } finally {
      setBusy(false);
    }
  }

  async function retryAll() {
    if (!confirm(
      `Chạy lại toàn bộ ${dead.length} tài liệu trong hàng đợi chết?\n\n` +
      `Chỉ nên làm sau khi đã sửa nguyên nhân chung (ví dụ: PostgreSQL đã lên lại). ` +
      `Nếu nguyên nhân chưa được sửa, chúng sẽ lại thất bại.`
    )) return;

    setBusy(true);
    try {
      const res = await fetch("/api/hang-doi/dead/retry-all", {
        method: "POST",
        credentials: "include",
      });
      const payload = await res.json();
      if (!res.ok) {
        setError(payload.message || "Không chạy lại được");
        return;
      }
      setNotice(payload.message);
      await load();
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell title="Hàng đợi xử lý" activeKey="queue">
      {error && <ErrorBox message={error} />}
      {notice && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-2 text-sm text-green-800 mb-4">
          {notice}
        </div>
      )}

      {depth === null ? (
        <p className="text-sm text-gray-500">Đang tải…</p>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-6 mb-4">
            <StatCard label="Chờ xử lý" value={depth.ready ?? 0} />
            <StatCard label="Ưu tiên cao" value={depth.high ?? 0} />
            <StatCard label="Đang xử lý" value={depth.processing ?? 0} />
            <StatCard
              label="Chờ thử lại"
              value={depth.delayed ?? 0}
              tone={depth.delayed > 0 ? "warning" : "primary"}
            />
            <StatCard
              label="Đã chết"
              value={depth.dead ?? 0}
              tone={depth.dead > 0 ? "danger" : "primary"}
            />
            <StatCard label="Ưu tiên thấp" value={depth.low ?? 0} />
          </div>

          {depth.mode === "blpop" && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 mb-4">
              <p className="text-sm text-amber-900">
                <strong>Cảnh báo:</strong> hàng đợi đang chạy ở chế độ cũ (<code>QUEUE_MODE=blpop</code>).
                Ở chế độ này, tài liệu <strong>sẽ mất</strong> nếu worker dừng giữa lúc xử lý. Chỉ nên
                dùng tạm để đối chứng khi gỡ lỗi.
              </p>
            </div>
          )}
        </>
      )}

      <section className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-gray-800">Hàng đợi chết</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Tài liệu đã hết lượt thử lại, hoặc lỗi thuộc về chính tài liệu (PDF hỏng, vi phạm độ
              nhạy cảm). Sửa nguyên nhân rồi bấm “Chạy lại”.
            </p>
          </div>
          {dead.length > 0 && (
            <button
              onClick={retryAll}
              disabled={busy}
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              style={{ backgroundColor: "#1e3a5f" }}
            >
              Chạy lại tất cả
            </button>
          )}
        </div>

        {dead.length === 0 ? (
          <p className="p-4 text-sm text-gray-500">
            Không có tài liệu nào trong hàng đợi chết.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-gray-600">
                <tr>
                  <th className="px-4 py-2 font-medium">Tài liệu</th>
                  <th className="px-4 py-2 font-medium">Lý do</th>
                  <th className="px-4 py-2 font-medium">Số lần thử</th>
                  <th className="px-4 py-2 font-medium">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {dead.map((job) => (
                  <tr key={job.job_id} className="hover:bg-gray-50">
                    <td className="px-4 py-2">
                      <div className="text-gray-800">{job.filename || "(không rõ tên)"}</div>
                      <div className="font-mono text-xs text-gray-500">{job.job_id}</div>
                    </td>
                    <td className="px-4 py-2 text-gray-700 max-w-md">
                      {job._error || "(không rõ)"}
                      <div className="text-xs text-gray-500 mt-0.5">
                        {job._dead_reason === "document_error"
                          ? "Lỗi thuộc về tài liệu — chạy lại sẽ hỏng y như vậy nếu chưa sửa"
                          : "Hết lượt thử lại sau nhiều lần lỗi hạ tầng"}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-gray-700">{formatNumber(job._attempts || 0)}</td>
                    <td className="px-4 py-2">
                      <button
                        onClick={() => retry(job.job_id)}
                        disabled={busy}
                        className="rounded border border-gray-300 bg-white px-2 py-1 text-xs
                                   font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                      >
                        Chạy lại
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className="text-xs text-gray-500 mt-4">
        Chạy lại giữ nguyên mã tài liệu — không tạo bản ghi mới, và lịch sử kiểm toán của lần xử lý
        trước vẫn được giữ.
      </p>
    </PageShell>
  );
}
