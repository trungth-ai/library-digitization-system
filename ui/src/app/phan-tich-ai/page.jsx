// Trang PHÂN TÍCH KẾT QUẢ AI (YC-AN-09 — sprint V2). Server component, dữ liệu THẬT.
//
// RÀNG BUỘC HIỂN THỊ (nguyên tắc "đo được mới tuyên bố" của SRS):
//   • Mọi tỉ lệ % PHẢI kèm cỡ mẫu. Dưới ngưỡng tối thiểu thì hiện "chưa đủ dữ liệu", KHÔNG hiện %.
//   • Ghi rõ phương pháp ngay trên trang: đây là đối chiếu với giá trị cán bộ đã duyệt, không phải
//     với đáp án chuẩn độc lập. Thiếu câu này thì số liệu dễ bị trích vào hồ sơ như thể đã đối chiếu BD-01.
//   • Backend chưa chạy / chưa di trú → hiện LÝ DO, không vẽ bảng rỗng trông như đã đo.

import { ErrorBox, PageShell, StatCard } from "@/components/hpu/HpuLayout";
import { fetchApi } from "@/lib/api";
import { formatNumber } from "@/lib/format";

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

/**
 * Ô hiển thị độ chính xác.
 *
 * `null` KHÔNG được hiển thị thành 0% — hai điều đó khác hẳn nhau: một là "đo được và kết quả là 0",
 * một là "chưa đo được". Hiển thị nhầm sẽ làm cán bộ tưởng model hỏng hoàn toàn.
 */
function AccuracyCell({ value, sampleSize, note }) {
  if (value === null || value === undefined) {
    return (
      <span className="text-gray-500 text-xs italic">
        {note || "chưa đủ dữ liệu"} ({formatNumber(sampleSize)} mẫu)
      </span>
    );
  }

  const tone =
    value >= 90 ? "text-green-700" : value >= 70 ? "text-amber-700" : "text-red-700";

  return (
    <span>
      <strong className={tone}>{value}%</strong>{" "}
      <span className="text-xs text-gray-500">({formatNumber(sampleSize)} mẫu)</span>
    </span>
  );
}

export default async function PhanTichAiPage() {
  const [accuracy, providers, cost, ocr, drift] = await Promise.all([
    fetchApi("/api/v2/analytics/ai/accuracy"),
    fetchApi("/api/v2/analytics/ai/providers"),
    fetchApi("/api/v2/analytics/ai/cost"),
    fetchApi("/api/v2/analytics/ai/ocr-quality"),
    fetchApi("/api/v2/analytics/ai/drift"),
  ]);

  const firstError = [accuracy, providers, cost, ocr, drift].find((r) => !r.ok);
  const fields = accuracy.data?.fields || [];
  const providerRows = providers.data?.providers || [];
  const costByMonth = cost.data?.theo_thang || [];
  const costByProvider = cost.data?.theo_cong_cu || [];
  const ocrSummary = ocr.data?.tong_quan || {};
  const badScans = ocr.data?.tai_lieu_can_quet_lai || [];
  const driftData = drift.data || {};
  const method = accuracy.data?.phuong_phap;

  return (
    <PageShell
      title="Phân tích kết quả AI"
      activeKey="ai"
      action={
        <a
          href="/bao-cao"
          className="rounded-lg border border-gray-300 bg-white hover:bg-gray-50 text-sm font-medium px-4 py-2 text-gray-700"
        >
          Báo cáo chung →
        </a>
      }
    >
      {firstError && <ErrorBox message={firstError.error} />}

      {/* Ghi chú phương pháp đặt NGAY ĐẦU trang, không giấu dưới chân trang: người đọc phải thấy
          giới hạn của số liệu trước khi thấy con số. */}
      {method && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 mb-4">
          <p className="text-sm text-blue-900">
            <strong>Phương pháp đo:</strong> {method}
          </p>
        </div>
      )}

      {driftData.canh_bao && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 mb-4">
          <p className="text-sm text-amber-900">
            <strong>Cảnh báo suy giảm chất lượng:</strong> {driftData.ghi_chu} (
            {driftData.ty_le_can_xem_truoc_do}% → {driftData.ty_le_can_xem_gan_day}%)
          </p>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-4 mb-4">
        <StatCard label="Tài liệu đã OCR" value={formatNumber(ocrSummary.so_tai_lieu || 0)} />
        <StatCard label="Tổng số trang" value={formatNumber(ocrSummary.tong_trang || 0)} />
        <StatCard
          label="Tài liệu scan xấu"
          value={formatNumber(ocrSummary.tai_lieu_scan_xau || 0)}
          tone={ocrSummary.tai_lieu_scan_xau > 0 ? "warning" : "primary"}
        />
        <StatCard
          label="Chi phí tháng gần nhất"
          value={costByMonth[0]?.chi_phi_hien_thi || "chưa có số liệu"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card
          title="Độ chính xác theo trường"
          subtitle="So giá trị AI trả về với giá trị cán bộ đã duyệt"
        >
          {fields.length === 0 ? (
            <Empty>
              Chưa có dữ liệu. Số liệu tích lũy dần sau khi cán bộ duyệt tài liệu — cần chạy
              migration 005 và xử lý ít nhất một tài liệu.
            </Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-gray-600 border-b border-gray-200">
                  <tr>
                    <th className="py-2 font-medium">Trường</th>
                    <th className="py-2 font-medium">Đúng</th>
                    <th className="py-2 font-medium">Độ chính xác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {fields.map((row) => (
                    <tr key={row.field_key}>
                      <td className="py-2 font-mono text-xs">{row.field_key}</td>
                      <td className="py-2 text-gray-700">
                        {formatNumber(row.so_dung)}/{formatNumber(row.sample_size)}
                      </td>
                      <td className="py-2">
                        <AccuracyCell
                          value={row.do_chinh_xac}
                          sampleSize={row.sample_size}
                          note={row.ghi_chu}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card
          title="So sánh công cụ mô hình"
          subtitle="Cùng khoảng thời gian, cùng loại tài liệu thật"
        >
          {providerRows.length === 0 ? (
            <Empty>Chưa có dữ liệu so sánh.</Empty>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-gray-600 border-b border-gray-200">
                <tr>
                  <th className="py-2 font-medium">Công cụ</th>
                  <th className="py-2 font-medium">Độ chính xác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {providerRows.map((row) => (
                  <tr key={row.nhom}>
                    <td className="py-2 text-gray-800">{row.nhom}</td>
                    <td className="py-2">
                      <AccuracyCell
                        value={row.do_chinh_xac}
                        sampleSize={row.sample_size}
                        note={row.ghi_chu}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card
          title="Chi phí gọi model"
          subtitle={
            cost.data?.ty_gia_usd_vnd
              ? `Quy đổi theo tỉ giá ${formatNumber(cost.data.ty_gia_usd_vnd)} đ/USD · chế độ tại chỗ = 0 đ`
              : "Chế độ tại chỗ không phát sinh chi phí theo lượt gọi"
          }
        >
          {costByProvider.length === 0 ? (
            <Empty>Chưa có lượt gọi model nào được ghi nhận.</Empty>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-gray-600 border-b border-gray-200">
                <tr>
                  <th className="py-2 font-medium">Công cụ</th>
                  <th className="py-2 font-medium">Lượt gọi</th>
                  <th className="py-2 font-medium">Token</th>
                  <th className="py-2 font-medium">Chi phí</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {costByProvider.map((row) => (
                  <tr key={`${row.provider}-${row.deployment}`}>
                    <td className="py-2 text-gray-800">
                      {row.provider}{" "}
                      <span className="text-xs text-gray-500">
                        ({row.deployment === "local" ? "tại chỗ" : "đám mây"})
                      </span>
                    </td>
                    <td className="py-2 text-gray-700">{formatNumber(row.so_luot_goi)}</td>
                    <td className="py-2 text-gray-700">{formatNumber(row.tong_token)}</td>
                    <td className="py-2 text-gray-800">{row.chi_phi_hien_thi}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card
          title="Tài liệu nên quét lại"
          subtitle="Có trang không tạo được lớp text — nội dung sẽ không tra cứu được trên DSpace"
        >
          {badScans.length === 0 ? (
            <Empty>
              {ocrSummary.so_tai_lieu
                ? "Không có tài liệu nào cần quét lại."
                : "Chưa có dữ liệu OCR."}
            </Empty>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-gray-600 border-b border-gray-200">
                <tr>
                  <th className="py-2 font-medium">Tài liệu</th>
                  <th className="py-2 font-medium">Trang hỏng</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {badScans.slice(0, 15).map((row) => (
                  <tr key={row.document_id}>
                    <td className="py-2 text-gray-800 truncate max-w-xs">
                      {row.filename || row.document_id}
                    </td>
                    <td className="py-2 text-gray-700">
                      {row.pages_without_text}/{row.pages}
                      {row.ty_le_trang_hong !== null && (
                        <span className="ml-1 text-xs text-red-700">
                          ({row.ty_le_trang_hong}%)
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      {!driftData.du_lieu_du && driftData.ghi_chu && (
        <p className="text-xs text-gray-500 mt-4">
          Theo dõi suy giảm chất lượng: {driftData.ghi_chu}.
        </p>
      )}
    </PageShell>
  );
}
