// Trang quản trị CÔNG CỤ MÔ HÌNH (YC-MS-08): đang dùng công cụ/model nào, tình trạng ra sao,
// và có những lựa chọn nào. Server component — lấy dữ liệu thật từ FastAPI, không có dữ liệu mẫu.
//
// Vì sao trang này cần thiết: từ khi có 18 lựa chọn công cụ, câu hỏi "hệ thống đang chạy bằng gì"
// không còn trả lời được bằng cách đọc mã. Cán bộ vận hành phải thấy được trên giao diện.

import { ErrorBox, PageShell, StatCard } from "@/components/hpu/HpuLayout";
import { fetchApi } from "@/lib/api";
import { formatNumber } from "@/lib/format";

export const dynamic = "force-dynamic"; // luôn lấy trạng thái mới, không cache

function Card({ title, children, subtitle }) {
  return (
    <section className="bg-white rounded-xl border border-gray-200 p-4">
      <h2 className="text-base font-semibold text-gray-800">{title}</h2>
      {subtitle && <p className="text-xs text-gray-500 mt-0.5 mb-3">{subtitle}</p>}
      {!subtitle && <div className="mb-3" />}
      {children}
    </section>
  );
}

/** Nhãn chế độ: đây là thứ quyết định dữ liệu đi đâu, nên phải nổi bật hơn tên công cụ. */
function ModeBadge({ deployment }) {
  const local = deployment === "local";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
        local
          ? "bg-hpu-success-light text-hpu-success"
          : "bg-hpu-warning-light text-hpu-warning"
      }`}
      title={
        local
          ? "Dữ liệu KHÔNG ra khỏi hạ tầng Nhà trường"
          : "Dữ liệu ra ngoài — chỉ dùng cho tài liệu Công khai (YC-DR-03)"
      }
    >
      {local ? "Tại chỗ" : "Đám mây"}
    </span>
  );
}

function ReadyBadge({ ready }) {
  if (ready === undefined || ready === null) return null;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
        ready ? "bg-hpu-success-light text-hpu-success" : "bg-hpu-danger-light text-hpu-danger"
      }`}
    >
      {ready ? "Sẵn sàng" : "Chưa sẵn sàng"}
    </span>
  );
}

/** Đổi ms sang chuỗi người đọc được: 41230 → "41,2 giây". Dấu "—" = CHƯA ĐO ĐƯỢC, không phải 0. */
function ms(value) {
  if (value === null || value === undefined) return "—";
  if (value < 1000) return `${value} ms`;
  if (value < 60000) return `${(value / 1000).toFixed(1).replace(".", ",")} giây`;
  return `${Math.floor(value / 60000)} phút ${Math.round((value % 60000) / 1000)} giây`;
}

const LEVEL_STYLE = {
  error: "bg-hpu-danger-light text-hpu-danger",
  warning: "bg-hpu-warning-light text-hpu-warning",
  info: "bg-gray-100 text-gray-600",
};

export default async function CongCuPage() {
  // Gọi song song — trang theo dõi không nên chờ tuần tự 5 lượt
  const [providers, calls, health, events, timing] = await Promise.all([
    fetchApi("/api/v2/providers"),
    fetchApi("/api/v2/model-calls?summary=true&limit=2000"),
    fetchApi("/api/v2/health/detailed"),
    fetchApi("/api/v2/system-events?since_hours=168&limit=20"),
    fetchApi("/api/v2/reports/processing-time?since_hours=24"),
  ]);

  const view = providers.data || {};
  const current = view.current || null;
  const summary = calls.data || { by_provider: [], total_calls: 0 };
  const components = health.data?.components || {};
  const systemEvents = events.data || [];
  const perf = timing.data || {};
  const openErrors = systemEvents.filter((e) => e.level === "error" && e.status === "new");

  return (
    <PageShell title="Công cụ mô hình & Theo dõi vận hành" activeKey="tools">
      {!providers.ok && <ErrorBox message={providers.error} />}

      {/* ── TÌNH TRẠNG TỪNG THÀNH PHẦN ───────────────────────────────
          Khi hệ thống "im lặng", câu hỏi thật là CÁI NÀO đang hỏng. Một chữ "ok" chung không
          trả lời được, nên hiện từng thành phần kèm lý do bằng tiếng Việt. */}
      <div className="mb-5">
        <h2 className="text-base font-semibold text-gray-800 mb-2">Tình trạng hệ thống</h2>
        {!health.ok ? (
          <ErrorBox title="Không đọc được tình trạng hệ thống" message={health.error} />
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              ["redis", "Redis (hàng đợi)"],
              ["postgres", "PostgreSQL"],
              ["worker", "Worker xử lý"],
              ["model_provider", "Công cụ mô hình"],
            ].map(([key, label]) => {
              const c = components[key] || {};
              return (
                <div
                  key={key}
                  className={`rounded-xl border p-3 ${
                    c.ready
                      ? "bg-white border-gray-200"
                      : "bg-hpu-danger-light border-hpu-danger/30"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2 h-2 rounded-full shrink-0 ${
                        c.ready ? "bg-hpu-success" : "bg-hpu-danger"
                      }`}
                    />
                    <span className="text-sm font-medium text-gray-800">{label}</span>
                  </div>
                  <p
                    className={`text-xs mt-1 ${c.ready ? "text-gray-500" : "text-hpu-danger"}`}
                  >
                    {c.detail || "—"}
                  </p>
                  {key === "redis" && c.queue_length !== null && c.queue_length !== undefined && (
                    <p className="text-xs text-gray-500 mt-1">
                      Hàng đợi: <strong>{formatNumber(c.queue_length)}</strong> tài liệu
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── THỜI GIAN XỬ LÝ ─────────────────────────────────────────
          p50 nói "thường mất bao lâu", p95 nói "trường hợp xấu tới đâu". Chỉ xem trung bình thì
          một tài liệu 500 trang sẽ che mất thực tế của phần lớn tài liệu. */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-5">
        <StatCard label="Tài liệu đã đo (24h)" value={perf.so_tai_lieu ?? 0} />
        <StatCard label="Thường mất (p50)" value={ms(perf.p50_ms)} tone="success" />
        <StatCard label="Chậm nhất 5% (p95)" value={ms(perf.p95_ms)} tone="warning" />
        <StatCard label="Trung bình" value={ms(perf.tb_ms)} />
        <StatCard label="Lâu nhất" value={ms(perf.max_ms)} tone="danger" />
      </div>

      {/* Công cụ đang dùng */}
      {current?.error ? (
        <ErrorBox title="Cấu hình công cụ mô hình không dùng được" message={current.error} />
      ) : current ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
          <StatCard label="Công cụ đang dùng" value={current.provider} />
          <StatCard label="Model" value={current.model || "(mặc định)"} />
          <StatCard
            label="Chế độ"
            value={current.deployment === "local" ? "Tại chỗ" : "Đám mây"}
            tone={current.deployment === "local" ? "success" : "warning"}
          />
          <StatCard
            label="Tình trạng"
            value={current.ready === false ? "Chưa sẵn sàng" : "Sẵn sàng"}
            tone={current.ready === false ? "danger" : "success"}
          />
        </div>
      ) : null}

      {current && !current.error && current.detail && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 mb-5 text-sm text-gray-700">
          <span className="font-medium">Chi tiết kiểm tra sẵn sàng: </span>
          {current.detail}
          {current.endpoint && (
            <div className="text-xs text-gray-500 mt-1 font-mono">{current.endpoint}</div>
          )}
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-4 mb-5">
        {/* Công cụ của từng chế độ + dự phòng */}
        <Card
          title="Định tuyến theo chế độ"
          subtitle="Tài liệu Nội bộ/Nhạy cảm LUÔN đi vào công cụ tại chỗ — ràng buộc cứng, không ghi đè được (YC-DR-03)."
        >
          <table className="w-full text-sm">
            <tbody>
              <tr className="border-b border-gray-50">
                <td className="py-2 text-gray-500 w-40">Chế độ đám mây</td>
                <td className="py-2 font-mono text-gray-900">{view.modes?.cloud || "—"}</td>
              </tr>
              <tr className="border-b border-gray-50">
                <td className="py-2 text-gray-500">Chế độ tại chỗ</td>
                <td className="py-2 font-mono text-gray-900">{view.modes?.local || "—"}</td>
              </tr>
              <tr className="border-b border-gray-50">
                <td className="py-2 text-gray-500">Dự phòng tại chỗ</td>
                <td className="py-2 font-mono text-gray-900">
                  {view.fallback?.local?.length ? view.fallback.local.join(" → ") : "(không cấu hình)"}
                </td>
              </tr>
              <tr>
                <td className="py-2 text-gray-500">Dự phòng đám mây</td>
                <td className="py-2 font-mono text-gray-900">
                  {view.fallback?.cloud?.length ? view.fallback.cloud.join(" → ") : "(không cấu hình)"}
                </td>
              </tr>
            </tbody>
          </table>
          <p className="text-xs text-gray-500 mt-3">
            Dự phòng chỉ diễn ra trong cùng chế độ: một công cụ tại chỗ chết sẽ KHÔNG bao giờ chuyển
            sang đám mây (ADR-008).
          </p>
        </Card>

        {/* Số liệu từ vận hành thật */}
        <Card
          title="Đã gọi model bao nhiêu lần (YC-MP-06 / YC-MS-07)"
          subtitle="Số liệu từ vận hành thật, không phải từ harness đo riêng."
        >
          {summary.by_provider?.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-100">
                    <th className="py-2 font-medium">Công cụ</th>
                    <th className="py-2 font-medium text-right">Lượt gọi</th>
                    <th className="py-2 font-medium text-right">TB (ms)</th>
                    <th className="py-2 font-medium text-right">RAM đỉnh</th>
                    <th className="py-2 font-medium text-right">Lỗi</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.by_provider.map((row) => (
                    <tr key={`${row.provider}/${row.deployment}`} className="border-b border-gray-50">
                      <td className="py-2 text-gray-800">
                        {row.provider} <ModeBadge deployment={row.deployment} />
                      </td>
                      <td className="py-2 text-right tabular-nums">{formatNumber(row.calls)}</td>
                      <td className="py-2 text-right tabular-nums">
                        {row.avg_latency_ms ?? "—"}
                      </td>
                      <td className="py-2 text-right tabular-nums">
                        {row.max_rss_mb ? `${formatNumber(Math.round(row.max_rss_mb))} MB` : "—"}
                      </td>
                      <td className="py-2 text-right tabular-nums">
                        {row.failed > 0 ? (
                          <span className="text-hpu-danger font-medium">{row.failed}</span>
                        ) : (
                          0
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-xs text-gray-500 mt-3">
                Dấu “—” nghĩa là <strong>chưa đo được</strong> (vd RAM không đọc được trên nền tảng
                đó), không phải bằng 0.
              </p>
            </div>
          ) : (
            <p className="text-sm text-gray-500">
              Chưa có lượt gọi model nào được ghi. Số liệu xuất hiện sau khi worker xử lý tài liệu
              đầu tiên với lớp provider đang bật.
            </p>
          )}
        </Card>
      </div>

      {/* Danh sách công cụ khả dụng */}
      <Card
        title={`Công cụ khả dụng (${view.available?.length || 0})`}
        subtitle="Đổi công cụ bằng biến môi trường MODEL_PROVIDER — không sửa mã, không build lại (YC-MP-04)."
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-100">
                <th className="py-2 font-medium">Tên cấu hình</th>
                <th className="py-2 font-medium">Công cụ</th>
                <th className="py-2 font-medium">Chế độ</th>
                <th className="py-2 font-medium">Model mặc định</th>
                <th className="py-2 font-medium">Khóa API</th>
              </tr>
            </thead>
            <tbody>
              {(view.available || []).map((p) => (
                <tr key={p.name} className="border-b border-gray-50 align-top">
                  <td className="py-2 font-mono text-xs text-gray-700">{p.name}</td>
                  <td className="py-2 text-gray-800">
                    {p.label}
                    {p.note && <div className="text-xs text-gray-500 mt-0.5">{p.note}</div>}
                  </td>
                  <td className="py-2">
                    <ModeBadge deployment={p.deployment} />
                  </td>
                  <td className="py-2 font-mono text-xs text-gray-600">
                    {p.default_model || "—"}
                  </td>
                  <td className="py-2 text-xs">
                    {p.key_env ? (
                      <span className={p.key_configured ? "text-hpu-success" : "text-gray-400"}>
                        {p.key_configured ? "✓ đã đặt" : "chưa đặt"}
                        <span className="block font-mono text-gray-400">{p.key_env}</span>
                      </span>
                    ) : (
                      <span className="text-gray-400">không cần</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-gray-500 mt-3">
          ⚠️ Rà giấy phép model TRƯỚC khi tải về/sử dụng — xem <code>docs/LICENSES.md</code> (YC-PL-01/02).
        </p>
      </Card>

      {/* ── SỰ KIỆN & LỖI HẠ TẦNG ───────────────────────────────────
          Trước đây lỗi chỉ nằm trong log container — mà log bị cắt vòng, nên "hôm qua worker có mất
          kết nối Redis lần nào không" là câu không trả lời được. Bảng này lưu trong DB nên tra được. */}
      <div className="mt-4">
        <Card
          title={`Sự kiện hệ thống 7 ngày qua (${systemEvents.length})`}
          subtitle="Mất/nối lại kết nối, lỗi worker, tài liệu xử lý thất bại. Khác nhật ký kiểm toán: đây là sự cố hạ tầng."
        >
          {openErrors.length > 0 && (
            <div className="mb-3 rounded-lg bg-hpu-danger-light border border-hpu-danger/30 p-3 text-sm text-hpu-danger">
              <strong>{openErrors.length} lỗi chưa khắc phục</strong> — xem danh sách bên dưới.
            </div>
          )}

          {systemEvents.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-100">
                    <th className="py-2 font-medium">Thời điểm</th>
                    <th className="py-2 font-medium">Mức</th>
                    <th className="py-2 font-medium">Loại</th>
                    <th className="py-2 font-medium">Nội dung</th>
                    <th className="py-2 font-medium">Nguồn</th>
                  </tr>
                </thead>
                <tbody>
                  {systemEvents.map((e) => (
                    <tr key={e.id} className="border-b border-gray-50 align-top">
                      <td className="py-2 text-gray-500 whitespace-nowrap text-xs">
                        {new Date(e.created_at).toLocaleString("vi-VN")}
                      </td>
                      <td className="py-2">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                            LEVEL_STYLE[e.level] || LEVEL_STYLE.info
                          }`}
                        >
                          {e.level}
                        </span>
                        {e.status === "resolved" && (
                          <span className="ml-1 text-xs text-hpu-success">đã khắc phục</span>
                        )}
                      </td>
                      <td className="py-2 font-mono text-xs text-gray-600">{e.kind}</td>
                      <td className="py-2 text-gray-800 max-w-md break-words">
                        {e.message}
                        {e.detail && (
                          <span
                            className="block text-xs text-gray-400 mt-0.5 line-clamp-2"
                            title={e.detail}
                          >
                            {e.detail}
                          </span>
                        )}
                      </td>
                      <td className="py-2 text-xs text-gray-500 whitespace-nowrap">
                        {e.source}
                        {e.instance && <span className="block text-gray-400">{e.instance}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-gray-500">
              Không có sự kiện nào trong 7 ngày qua — hệ thống chạy êm.
            </p>
          )}
        </Card>
      </div>
    </PageShell>
  );
}
