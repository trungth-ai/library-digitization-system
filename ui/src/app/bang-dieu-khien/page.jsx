"use client";

// BẢNG ĐIỀU KHIỂN THEO DÕI CÔNG VIỆC (YC-DB — sprint V7).
//
// Trả lời hai câu hỏi, cho hai đối tượng:
//   Cán bộ:  "hôm nay tôi phải làm gì?"
//   Quản lý: "việc đang tắc ở đâu, ai đang quá tải?"
//
// Ba nguyên tắc hiển thị kế thừa từ /bao-cao và /cong-cu:
//   • Không vẽ bảng rỗng trông như đã đo — chưa có dữ liệu thì NÓI RÕ là chưa có.
//   • Không có worker thì nói thẳng, không hiện 0 im lặng (ADR-009).
//   • Một nguồn dữ liệu hỏng không được làm trắng cả trang.

import React, { useCallback, useEffect, useState } from "react";
import { PageShell, ErrorBox, StatCard } from "@/components/hpu/HpuLayout";
import { formatNumber } from "@/lib/format";

export default function BangDieuKhienPage() {
  const [data, setData] = useState(null);
  const [workload, setWorkload] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [summaryRes, workloadRes] = await Promise.all([
        fetch("/api/bang-dieu-khien/summary", { credentials: "include" }),
        fetch("/api/bang-dieu-khien/workload?days=7", { credentials: "include" }),
      ]);
      const summaryPayload = await summaryRes.json();

      if (!summaryRes.ok) {
        setError(summaryPayload.message || `Không tải được bảng điều khiển (HTTP ${summaryRes.status})`);
        return;
      }
      setError("");
      setData(summaryPayload.data);
      setWorkload(workloadRes.ok ? (await workloadRes.json()).data : null);
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [load]);

  if (!data && !error) {
    return (
      <PageShell title="Bảng điều khiển" activeKey="dashboard">
        <p className="text-sm text-gray-500">Đang tải…</p>
      </PageShell>
    );
  }

  const tong = data?.tong_quan || {};
  const toi = data?.viec_cua_toi || {};
  const hangDoi = data?.hang_doi;
  const sla = data?.sla || {};
  const loDangChay = data?.lo_dang_chay || [];

  return (
    <PageShell
      title="Bảng điều khiển"
      activeKey="dashboard"
      action={
        <a
          href="/api/bang-dieu-khien/export?days=7"
          className="rounded-lg border border-gray-300 bg-white hover:bg-gray-50 text-sm font-medium px-4 py-2 text-gray-700"
        >
          Xuất bảng tính
        </a>
      }
    >
      {error && <ErrorBox message={error} />}

      {/* Phần nguồn dữ liệu hỏng: nói rõ THẺ NÀO hỏng, phần còn lại vẫn dùng được */}
      {data?.phan_loi && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 mb-4">
          <p className="text-sm text-amber-900">
            <strong>Một số thẻ chưa đọc được dữ liệu:</strong> {data.phan_loi.join("; ")}.
            Có thể do chưa chạy migration mới nhất — xem <code>docs/PLAN.md</code>.
          </p>
        </div>
      )}

      {/* ── Việc của tôi ─────────────────────────────────────── */}
      <section className="mb-5">
        <h2 className="text-base font-semibold text-gray-800 mb-2">
          {toi.theo_ca_nhan ? "Việc của tôi" : "Việc toàn hệ thống"}
        </h2>
        {!toi.theo_ca_nhan && (
          <p className="text-xs text-gray-500 mb-2">
            Chưa bật xác thực nên đây là số liệu chung, không phải của riêng bạn.
          </p>
        )}
        <div className="grid gap-4 md:grid-cols-4">
          <StatCard
            label="Chờ duyệt"
            value={toi.cho_toi_duyet ?? 0}
            tone={toi.cho_toi_duyet > 0 ? "warning" : "primary"}
          />
          <StatCard label="Đang xử lý" value={toi.toi_tai_len_dang_xu_ly ?? 0} />
          <StatCard
            label="Bị lỗi"
            value={toi.toi_tai_len_bi_loi ?? 0}
            tone={toi.toi_tai_len_bi_loi > 0 ? "danger" : "primary"}
          />
          <StatCard
            label="Đã duyệt hôm nay"
            value={toi.toi_duyet_hom_nay === null ? "—" : toi.toi_duyet_hom_nay ?? 0}
            tone="success"
          />
        </div>
      </section>

      {/* ── Hôm nay ──────────────────────────────────────────── */}
      <section className="mb-5">
        <h2 className="text-base font-semibold text-gray-800 mb-2">Hôm nay</h2>
        <div className="grid gap-4 md:grid-cols-4">
          <StatCard label="Đã nạp" value={tong.nap_hom_nay ?? 0} />
          <StatCard label="Xử lý xong" value={tong.xong_hom_nay ?? 0} tone="success" />
          <StatCard
            label="Thất bại"
            value={tong.loi_hom_nay ?? 0}
            tone={tong.loi_hom_nay > 0 ? "danger" : "primary"}
          />
          <StatCard label="Đã đẩy DSpace" value={tong.da_day_dspace ?? 0} />
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* ── Hàng đợi ───────────────────────────────────────── */}
        <Card title="Hàng đợi" subtitle="Cập nhật mỗi 10 giây">
          {hangDoi === null || hangDoi === undefined ? (
            <p className="text-sm text-gray-500">Không đọc được hàng đợi (Redis).</p>
          ) : (
            <>
              {/* Không có worker nào là tình huống PHẢI nói thẳng — nếu không, tài liệu nằm im
                  và người dùng đợi vô ích mà không hiểu vì sao (ADR-009). */}
              {hangDoi.workers_alive === 0 && (
                <div className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 mb-3">
                  <p className="text-sm text-red-800">
                    <strong>Không có worker nào đang chạy.</strong> Tài liệu sẽ nằm chờ mãi cho tới
                    khi worker được khởi động lại.
                  </p>
                </div>
              )}
              <dl className="grid grid-cols-2 gap-2 text-sm">
                <Row label="Chờ xử lý" value={hangDoi.ready} />
                <Row label="Ưu tiên cao" value={hangDoi.high} />
                <Row label="Đang xử lý" value={hangDoi.processing} />
                <Row label="Chờ thử lại" value={hangDoi.delayed} warn={hangDoi.delayed > 0} />
                <Row label="Đã chết" value={hangDoi.dead} warn={hangDoi.dead > 0} />
                <Row
                  label="Worker đang sống"
                  value={hangDoi.workers_alive === null ? "không rõ" : hangDoi.workers_alive}
                  warn={hangDoi.workers_alive === 0}
                />
              </dl>
              {hangDoi.dead > 0 && (
                <a href="/hang-doi" className="inline-block mt-3 text-sm text-blue-700 hover:underline">
                  Xem {formatNumber(hangDoi.dead)} tài liệu trong hàng đợi chết →
                </a>
              )}
            </>
          )}
        </Card>

        {/* ── Quá hạn SLA ────────────────────────────────────── */}
        <Card
          title="Tồn đọng quá hạn"
          subtitle="Tài liệu nằm quá lâu ở một trạng thái"
        >
          {sla.tong_so === undefined ? (
            <p className="text-sm text-gray-500">Chưa đọc được số liệu.</p>
          ) : sla.tong_so === 0 ? (
            <p className="text-sm text-gray-600">Không có tài liệu nào quá hạn.</p>
          ) : (
            <>
              <p className="text-sm text-gray-800 mb-2">
                <strong className="text-red-700">{formatNumber(sla.tong_so)}</strong> tài liệu quá hạn
              </p>
              <ul className="space-y-1 max-h-56 overflow-y-auto">
                {(sla.danh_sach || []).slice(0, 10).map((doc) => (
                  <li key={doc.id} className="text-sm border-b border-gray-100 pb-1">
                    <span className="text-gray-800">{doc.filename}</span>
                    <span className="text-xs text-red-700 ml-1">
                      — tồn {formatNumber(doc.gio_ton_dong)} giờ
                    </span>
                    <span className="text-xs text-gray-500 ml-1">({doc.status})</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>

        {/* ── Lô đang chạy ───────────────────────────────────── */}
        <Card title="Lô đang chạy">
          {loDangChay.length === 0 ? (
            <p className="text-sm text-gray-500">Không có lô nào đang chạy.</p>
          ) : (
            <ul className="space-y-3">
              {loDangChay.map((lo) => (
                <li key={lo.id}>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-800">{lo.name}</span>
                    <span className="text-gray-600">
                      {formatNumber(lo.done_files)}/{formatNumber(lo.total_files)}
                      {lo.status === "paused" && (
                        <span className="ml-1 text-amber-700">(tạm dừng)</span>
                      )}
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-gray-200 overflow-hidden mt-1">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${lo.tien_do_phan_tram}%`,
                        backgroundColor: lo.status === "paused" ? "#f59e0b" : "#1e3a5f",
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* ── Năng suất (QĐ-06: công khai) ───────────────────── */}
        <Card title="Năng suất duyệt 7 ngày" subtitle={workload?.ghi_chu}>
          {!workload || (workload.can_bo || []).length === 0 ? (
            <p className="text-sm text-gray-500">
              Chưa có tài liệu nào được duyệt trong 7 ngày qua.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-gray-600 border-b border-gray-200">
                <tr>
                  <th className="py-2 font-medium">Cán bộ</th>
                  <th className="py-2 font-medium">Tài liệu</th>
                  <th className="py-2 font-medium">Trang</th>
                  <th className="py-2 font-medium">Trường đã sửa</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {workload.can_bo.map((row) => (
                  <tr key={row.can_bo}>
                    <td className="py-2 text-gray-800">{row.can_bo}</td>
                    <td className="py-2 text-gray-700">{formatNumber(row.so_tai_lieu)}</td>
                    <td className="py-2 text-gray-700">
                      {row.so_trang ? formatNumber(row.so_trang) : "—"}
                    </td>
                    <td className="py-2 text-gray-700">{formatNumber(row.so_truong_da_sua)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </PageShell>
  );
}

function Card({ title, subtitle, children }) {
  return (
    <section className="bg-white rounded-xl border border-gray-200 p-4">
      <h2 className="text-base font-semibold text-gray-800">{title}</h2>
      {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Row({ label, value, warn }) {
  return (
    <>
      <dt className="text-gray-600">{label}</dt>
      <dd className={`text-right font-medium ${warn ? "text-amber-700" : "text-gray-800"}`}>
        {typeof value === "number" ? formatNumber(value) : value}
      </dd>
    </>
  );
}
