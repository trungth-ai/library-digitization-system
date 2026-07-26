// Trang BÁO CÁO & THỐNG KÊ — dữ liệu THẬT từ FastAPI (trước đây là dữ liệu mẫu).
// Server component: lấy dữ liệu phía server nên không cần NEXT_PUBLIC_* lúc build (xem docs/DEPLOY.md mục 4).
//
// Nguyên tắc: KHÔNG hiển thị con số bịa. Backend chưa chạy → hiện lý do; chưa có dữ liệu → nói rõ
// "chưa có", không vẽ bảng rỗng trông như đã đo.

import { ErrorBox, PageShell, StatCard } from "@/components/hpu/HpuLayout";
import { fetchApi } from "@/lib/api";
import { formatNumber, formatPercent } from "@/lib/format";

export const dynamic = "force-dynamic";

function Card({ title, subtitle, children }) {
  return (
    <section className="bg-white rounded-xl border border-gray-200 p-4">
      <h2 className="text-base font-semibold text-gray-800">{title}</h2>
      {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Empty({ children }) {
  return <p className="text-sm text-gray-500">{children}</p>;
}

const MODE_LABEL = { cloud: "Đám mây", local: "Tại chỗ" };

export default async function BaoCaoPage() {
  // Gọi song song — trang không phải chờ tuần tự 4 lượt
  const [stats, byMode, fieldEdits, throughput] = await Promise.all([
    fetchApi("/api/v2/stats"),
    fetchApi("/api/v2/reports/by-mode"),
    fetchApi("/api/v2/reports/field-edits"),
    fetchApi("/api/v2/reports/throughput"),
  ]);

  const ocr = stats.data?.ocr || {};
  const modeRows = byMode.data || [];
  const editRows = fieldEdits.data || [];
  const dayRows = (throughput.data || []).slice(0, 7); // 7 ngày gần nhất là đủ để thấy xu hướng

  const firstError = [stats, byMode, fieldEdits, throughput].find((r) => !r.ok);
  const totalByMode = modeRows.reduce((sum, r) => sum + Number(r.so_tai_lieu || 0), 0);

  return (
    <PageShell
      title="Báo cáo & Thống kê"
      activeKey="reports"
      action={
        <a
          href="/cong-cu"
          className="rounded-lg border border-gray-300 bg-white hover:bg-gray-50 text-sm font-medium px-4 py-2 text-gray-700"
        >
          Công cụ mô hình →
        </a>
      }
    >
      {firstError && <ErrorBox message={firstError.error} />}

      {/* Tổng quan trạng thái OCR */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        <StatCard label="Tổng tài liệu" value={ocr.total ?? 0} tone="primary" />
        <StatCard label="Hoàn thành" value={ocr.completed ?? 0} tone="success" />
        <StatCard
          label="Đang xử lý"
          value={(ocr.queued ?? 0) + (ocr.ocr ?? 0) + (ocr.extracting ?? 0) + (ocr.exporting ?? 0)}
          tone="warning"
        />
        <StatCard label="Thất bại" value={ocr.failed ?? 0} tone="danger" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4 mb-5">
        {/* YC-DR-06: theo chế độ xử lý */}
        <Card
          title="Xử lý theo chế độ (YC-DR-06)"
          subtitle="Mỗi chế độ có thể do nhiều công cụ đảm nhiệm — xem trang Công cụ mô hình."
        >
          {modeRows.length ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-100">
                  <th className="py-2 font-medium">Chế độ</th>
                  <th className="py-2 font-medium text-right">Số tài liệu</th>
                  <th className="py-2 font-medium text-right">Tỉ lệ</th>
                </tr>
              </thead>
              <tbody>
                {modeRows.map((r) => (
                  <tr key={r.mode} className="border-b border-gray-50">
                    <td className="py-2 text-gray-800">{MODE_LABEL[r.mode] || r.mode}</td>
                    <td className="py-2 text-right tabular-nums">
                      {formatNumber(Number(r.so_tai_lieu || 0))}
                    </td>
                    <td className="py-2 text-right tabular-nums">
                      {totalByMode ? formatPercent(Number(r.so_tai_lieu || 0) / totalByMode) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty>
              Chưa có tài liệu nào được xử lý qua lớp provider. Số liệu xuất hiện sau khi worker chạy
              với <code>USE_PROVIDER_LAYER=1</code>.
            </Empty>
          )}
        </Card>

        {/* YC-CF-07: trường bị sửa nhiều nhất */}
        <Card
          title="Trường bị sửa nhiều nhất (YC-CF-07)"
          subtitle="Trường hay bị sửa là chỉ dấu lược đồ hoặc model cần cải thiện."
        >
          {editRows.length ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-100">
                  <th className="py-2 font-medium">Trường</th>
                  <th className="py-2 font-medium text-right">Số lần sửa</th>
                  <th className="py-2 font-medium text-right">Số tài liệu</th>
                </tr>
              </thead>
              <tbody>
                {editRows.slice(0, 10).map((r) => (
                  <tr key={r.field_key} className="border-b border-gray-50">
                    <td className="py-2 text-gray-800 font-mono text-xs">{r.field_key}</td>
                    <td className="py-2 text-right tabular-nums">
                      {formatNumber(Number(r.so_lan_sua || 0))}
                    </td>
                    <td className="py-2 text-right tabular-nums">
                      {formatNumber(Number(r.so_tai_lieu || 0))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty>Chưa có lượt hiệu chỉnh metadata nào được ghi nhận.</Empty>
          )}
        </Card>
      </div>

      {/* Throughput theo ngày */}
      <Card title="Thông lượng 7 ngày gần nhất" subtitle="Số tài liệu tạo mới và kết quả xử lý theo ngày.">
        {dayRows.length ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-100">
                <th className="py-2 font-medium">Ngày</th>
                <th className="py-2 font-medium text-right">Tổng</th>
                <th className="py-2 font-medium text-right">Hoàn thành</th>
                <th className="py-2 font-medium text-right">Thất bại</th>
                <th className="py-2 font-medium text-right">Tỉ lệ thành công</th>
              </tr>
            </thead>
            <tbody>
              {dayRows.map((r) => {
                const total = Number(r.tong || 0);
                const done = Number(r.hoan_thanh || 0);
                return (
                  <tr key={r.ngay} className="border-b border-gray-50">
                    <td className="py-2 text-gray-800">{r.ngay}</td>
                    <td className="py-2 text-right tabular-nums">{formatNumber(total)}</td>
                    <td className="py-2 text-right tabular-nums text-hpu-success">
                      {formatNumber(done)}
                    </td>
                    <td className="py-2 text-right tabular-nums text-hpu-danger">
                      {formatNumber(Number(r.that_bai || 0))}
                    </td>
                    <td className="py-2 text-right tabular-nums">
                      {total ? formatPercent(done / total) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <Empty>Chưa có tài liệu nào trong khoảng thời gian này.</Empty>
        )}
      </Card>
    </PageShell>
  );
}
