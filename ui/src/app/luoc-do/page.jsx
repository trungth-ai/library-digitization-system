"use client";
// Màn quản trị lược đồ trích xuất (YC-SC-05) — DEMO với dữ liệu mẫu.
// Khi tích hợp: thay MOCK bằng GET /api/v2/schemas + /api/v2/schemas/{code}.

import { useState } from "react";
import { PageShell } from "@/components/hpu/HpuLayout";
import { SensitivityBadge } from "@/components/hpu/Badges";

const SCHEMAS = {
  dublin_core: {
    code: "dublin_core", name: "Dublin Core (sách/khóa luận)", document_type: "book",
    sensitivity: "public", context_strategy: "first8_last2",
    fields: [
      { key: "dc.title", label: "Tiêu đề", required: true, data_type: "text" },
      { key: "dc.contributor.author", label: "Tác giả", required: true, data_type: "list" },
      { key: "dc.date.issued", label: "Năm xuất bản", required: false, data_type: "number" },
      { key: "dc.subject", label: "Từ khóa", required: false, data_type: "list" },
      { key: "dc.type", label: "Loại", required: true, data_type: "text" },
    ],
  },
  cong_van: {
    code: "cong_van", name: "Công văn hành chính", document_type: "cong_van",
    sensitivity: "internal", context_strategy: "full",
    fields: [
      { key: "so_hieu", label: "Số hiệu", required: true, data_type: "text" },
      { key: "ngay_ban_hanh", label: "Ngày ban hành", required: false, data_type: "date" },
      { key: "co_quan_ban_hanh", label: "Cơ quan ban hành", required: true, data_type: "text" },
      { key: "trich_yeu", label: "Trích yếu", required: true, data_type: "text" },
      { key: "do_mat", label: "Độ mật", required: false, data_type: "text" },
      { key: "nguoi_ky", label: "Người ký", required: false, data_type: "text" },
    ],
  },
};

export default function LuocDoPage() {
  const codes = Object.keys(SCHEMAS);
  const [selected, setSelected] = useState(codes[0]);
  const schema = SCHEMAS[selected];

  return (
    <PageShell
      title="Quản trị lược đồ trích xuất"
      activeKey="schemas"
      action={
        <button className="rounded-lg bg-hpu-primary hover:bg-hpu-primary-hover text-white text-sm font-medium px-4 py-2">
          + Tạo lược đồ mới
        </button>
      }
    >
      <div className="grid lg:grid-cols-3 gap-4">
        {/* Danh sách lược đồ */}
        <div className="space-y-2">
          {codes.map((code) => {
            const s = SCHEMAS[code];
            const active = code === selected;
            return (
              <button key={code} onClick={() => setSelected(code)}
                className={`w-full text-left rounded-xl border p-3 transition-colors ${
                  active ? "border-hpu-primary bg-hpu-primary-light" : "border-gray-200 bg-white hover:bg-gray-50"
                }`}>
                <div className="flex items-center justify-between">
                  <span className="font-medium text-gray-900">{s.name}</span>
                  <SensitivityBadge value={s.sensitivity} />
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  <span className="font-mono">{s.code}</span> · {s.fields.length} trường
                </div>
              </button>
            );
          })}
        </div>

        {/* Chi tiết lược đồ đang chọn */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-lg font-semibold text-gray-900">{schema.name}</h2>
            <div className="flex gap-2">
              <button className="text-xs rounded-md border border-gray-300 px-2.5 py-1 hover:bg-gray-50">Nhân bản</button>
              <button className="text-xs rounded-md border border-gray-300 px-2.5 py-1 hover:bg-gray-50">Xuất JSON</button>
            </div>
          </div>
          <div className="flex flex-wrap gap-3 text-xs text-gray-500 mb-4">
            <span>Loại: <b className="text-gray-700">{schema.document_type}</b></span>
            <span>Độ nhạy cảm: <SensitivityBadge value={schema.sensitivity} /></span>
            <span>Chọn ngữ cảnh: <b className="text-gray-700 font-mono">{schema.context_strategy}</b></span>
          </div>

          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-100">
                <th className="py-2 font-medium">Khóa</th>
                <th className="py-2 font-medium">Nhãn</th>
                <th className="py-2 font-medium text-center">Bắt buộc</th>
                <th className="py-2 font-medium">Kiểu</th>
              </tr>
            </thead>
            <tbody>
              {schema.fields.map((f) => (
                <tr key={f.key} className="border-b border-gray-50">
                  <td className="py-2 font-mono text-xs text-gray-700">{f.key}</td>
                  <td className="py-2 text-gray-900">{f.label}</td>
                  <td className="py-2 text-center">
                    {f.required
                      ? <span className="text-hpu-danger font-bold">✓</span>
                      : <span className="text-gray-300">—</span>}
                  </td>
                  <td className="py-2"><span className="font-mono text-xs text-gray-600">{f.data_type}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-gray-500 mt-3">
            Lược đồ là dữ liệu trong CSDL (YC-SC-01) — quản trị viên thêm/sửa không cần lập trình (YC-SC-05).
          </p>
        </div>
      </div>
    </PageShell>
  );
}
