// Trang DEMO báo cáo (dữ liệu mẫu) — minh họa design system HPU + các báo cáo GĐ2.
// Dùng để xem/kiểm chứng giao diện; khi tích hợp sẽ thay mock bằng API /reports.

import { PageShell, StatCard } from "@/components/hpu/HpuLayout";
import { StatusBadge, ConfidenceBadge } from "@/components/hpu/Badges";
import { formatNumber, formatPercent } from "@/lib/format";

// ---- Dữ liệu mẫu (mock) ----
const STATS = { total: 1284, completed: 1102, processing: 47, failed: 12 };

const BY_MODE = [
  { mode: "Đám mây (Claude)", code: "cloud", docs: 812, ratio: 0.66 },
  { mode: "Tại chỗ (Ollama)", code: "local", docs: 418, ratio: 0.34 },
];

const FIELD_EDITS = [
  { field: "dc.title", edits: 143, docs: 121 },
  { field: "dc.contributor.author", edits: 98, docs: 74 },
  { field: "dc.date.issued", edits: 56, docs: 52 },
  { field: "dc.subject", edits: 40, docs: 33 },
];

// Demo duyệt metadata 1 công văn — có trường điểm thấp (nghi bịa)
const REVIEW = {
  filename: "CV_123_QD-DHQLCN.pdf",
  mode: "local",
  fields: [
    { key: "so_hieu", value: "123/QĐ-ĐHQLCN", confidence: 0.95 },
    { key: "co_quan_ban_hanh", value: "Trường ĐH Quản lý và Công nghệ Hải Phòng", confidence: 0.9 },
    { key: "ngay_ban_hanh", value: "15/03/2024", confidence: 0.72 },
    { key: "nguoi_ky", value: "TS. Nguyễn Văn A", confidence: 0.45 },
  ],
};

function Card({ title, children }) {
  return (
    <section className="bg-white rounded-xl border border-gray-200 p-4">
      <h2 className="text-base font-semibold text-gray-800 mb-3">{title}</h2>
      {children}
    </section>
  );
}

export default function BaoCaoPage() {
  return (
    <PageShell
      title="Báo cáo & Thống kê"
      action={
        <button className="rounded-lg bg-hpu-primary hover:bg-hpu-primary-hover text-white text-sm font-medium px-4 py-2">
          Xuất Excel
        </button>
      }
    >
      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        <StatCard label="Tổng tài liệu" value={STATS.total} tone="primary" />
        <StatCard label="Hoàn thành" value={STATS.completed} tone="success" />
        <StatCard label="Đang xử lý" value={STATS.processing} tone="warning" />
        <StatCard label="Thất bại" value={STATS.failed} tone="danger" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4 mb-5">
        {/* YC-DR-06: theo chế độ */}
        <Card title="Xử lý theo chế độ (YC-DR-06)">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-100">
                <th className="py-2 font-medium">Chế độ</th>
                <th className="py-2 font-medium text-right">Số tài liệu</th>
                <th className="py-2 font-medium text-right">Tỉ lệ</th>
              </tr>
            </thead>
            <tbody>
              {BY_MODE.map((r) => (
                <tr key={r.code} className="border-b border-gray-50">
                  <td className="py-2 text-gray-800">{r.mode}</td>
                  <td className="py-2 text-right tabular-nums">{formatNumber(r.docs)}</td>
                  <td className="py-2 text-right tabular-nums">{formatPercent(r.ratio)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        {/* YC-CF-07: trường bị sửa nhiều nhất */}
        <Card title="Trường bị sửa nhiều nhất (YC-CF-07)">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-100">
                <th className="py-2 font-medium">Trường</th>
                <th className="py-2 font-medium text-right">Số lần sửa</th>
                <th className="py-2 font-medium text-right">Số tài liệu</th>
              </tr>
            </thead>
            <tbody>
              {FIELD_EDITS.map((r) => (
                <tr key={r.field} className="border-b border-gray-50">
                  <td className="py-2 text-gray-800 font-mono text-xs">{r.field}</td>
                  <td className="py-2 text-right tabular-nums">{formatNumber(r.edits)}</td>
                  <td className="py-2 text-right tabular-nums">{formatNumber(r.docs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      {/* YC-CF-04: duyệt metadata với điểm tin cậy tô màu */}
      <Card title="Duyệt metadata — điểm tin cậy (YC-CF-04)">
        <div className="flex items-center gap-2 mb-3 text-sm text-gray-500">
          <span className="font-mono text-xs text-gray-700">{REVIEW.filename}</span>
          <StatusBadge code="completed" label="Hoàn thành" />
          <span>· chế độ:</span><StatusBadge code="processing" label="Tại chỗ" />
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-100">
              <th className="py-2 font-medium">Trường</th>
              <th className="py-2 font-medium">Giá trị trích xuất</th>
              <th className="py-2 font-medium text-right">Tin cậy</th>
            </tr>
          </thead>
          <tbody>
            {REVIEW.fields.map((f) => (
              <tr key={f.key} className="border-b border-gray-50">
                <td className="py-2 text-gray-700 font-mono text-xs align-top w-48">{f.key}</td>
                <td className="py-2 text-gray-900">{f.value}</td>
                <td className="py-2 text-right"><ConfidenceBadge value={f.confidence} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-xs text-gray-500 mt-3">
          Trường điểm thấp (đỏ) được tô màu để cán bộ tập trung kiểm tra — chống giá trị bịa (YC-CF-05).
        </p>
      </Card>
    </PageShell>
  );
}
