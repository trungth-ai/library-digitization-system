"use client";

// TRANG THỐNG KÊ THEO NGƯỜI DÙNG & QUẢN TRỊ (YC-TT).
//
// VÌ SAO TÁCH KHỎI TRANG BÁO CÁO: trang Báo cáo trả lời "hệ thống làm được bao nhiêu" (thông lượng,
// tỉ lệ sửa trường, chế độ xử lý). Trang này trả lời ba câu hỏi khác hẳn:
//     "AI đã làm gì?"          → bảng theo từng cán bộ
//     "Toàn Trung tâm ra sao?" → khối lượng, nhịp làm việc theo ngày
//     "Có gì bất thường?"      → đăng nhập hỏng, IP dò mật khẩu, tỉ lệ cần xem lại
//
// QĐ-06 ĐƯỢC TÔN TRỌNG NGHIÊM NGẶT: đây KHÔNG phải bảng xếp hạng thi đua. Ghi chú cách đọc do
// backend trả về và LUÔN hiển thị — không để giao diện tự quyết định có hiện hay không, vì đúng
// lúc màn hình chật là lúc nó bị cắt đi đầu tiên.

import React, { useCallback, useEffect, useState } from "react";
import { PageShell, ErrorBox, StatCard } from "@/components/hpu/HpuLayout";
import { formatNumber } from "@/lib/format";

const KY = [
  { days: 7, label: "7 ngày" },
  { days: 30, label: "30 ngày" },
  { days: 90, label: "90 ngày" },
];

const MUC_CANH_BAO = {
  nguy_hiem: "border-red-200 bg-red-50 text-red-800",
  canh_bao: "border-amber-200 bg-amber-50 text-amber-800",
  thong_tin: "border-blue-200 bg-blue-50 text-blue-800",
};

export default function ThongKePage() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [phanLoai, setPhanLoai] = useState(null);
  const [chiTiet, setChiTiet] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [tongQuan, doChinhXac] = await Promise.all([
        fetch(`/api/thong-ke/admin?days=${days}`, { credentials: "include" }),
        fetch(`/api/thong-ke/classification?days=${days}`, { credentials: "include" }),
      ]);

      const payload = await tongQuan.json();
      if (!tongQuan.ok) {
        // 403 ở đây không phải lỗi hệ thống mà là "bạn không có quyền" — nói đúng như vậy
        setError(
          tongQuan.status === 403
            ? "Bạn không có quyền xem thống kê quản trị. Cần quyền «Quản trị người dùng»."
            : payload.message || `Không tải được thống kê (HTTP ${tongQuan.status})`
        );
        setData(null);
        return;
      }
      setError("");
      setData(payload.data);

      if (doChinhXac.ok) setPhanLoai((await doChinhXac.json()).data);
    } catch (err) {
      setError(`Không kết nối được backend (${err.message})`);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  async function xemChiTiet(username) {
    setChiTiet({ nguoi_dung: username, dang_tai: true });
    try {
      const res = await fetch(
        `/api/thong-ke/users/${encodeURIComponent(username)}?days=${days}`,
        { credentials: "include" }
      );
      const payload = await res.json();
      setChiTiet(res.ok ? payload.data : { nguoi_dung: username, loi: payload.message });
    } catch (err) {
      setChiTiet({ nguoi_dung: username, loi: err.message });
    }
  }

  const kl = data?.khoi_luong || {};
  const an = data?.an_ninh || {};

  return (
    <PageShell
      title="Thống kê người dùng"
      activeKey="stats"
      action={
        <div className="flex gap-1.5">
          {KY.map((k) => (
            <button
              key={k.days}
              onClick={() => setDays(k.days)}
              className={`rounded-lg border px-3 py-1.5 text-sm ${
                days === k.days
                  ? "border-gray-400 bg-white font-medium text-gray-900"
                  : "border-gray-300 bg-white/60 text-gray-600"
              }`}
            >
              {k.label}
            </button>
          ))}
        </div>
      }
    >
      {error && <ErrorBox message={error} />}
      {loading && !data && <p className="text-sm text-gray-500">Đang tải…</p>}

      {data && (
        <>
          {/* Cảnh báo lên ĐẦU: nếu có gì bất thường thì đó là lý do người ta mở trang này */}
          {(data.canh_bao || []).length > 0 && (
            <div className="space-y-2 mb-4">
              {data.canh_bao.map((c, i) => (
                <div
                  key={i}
                  className={`rounded-lg border px-4 py-2 text-sm ${
                    MUC_CANH_BAO[c.muc] || MUC_CANH_BAO.thong_tin
                  }`}
                >
                  {c.noi_dung}
                </div>
              ))}
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-4 mb-4">
            <StatCard label="Tài liệu tiếp nhận" value={Number(kl.so_tai_lieu || 0)} />
            <StatCard label="Đã duyệt" value={Number(kl.so_da_duyet || 0)} tone="success" />
            <StatCard
              label="Cần xem lại"
              value={Number(kl.so_can_xem_lai || 0)}
              tone={Number(kl.so_can_xem_lai) > 0 ? "warning" : "primary"}
            />
            <StatCard
              label="Xử lý thất bại"
              value={Number(kl.so_that_bai || 0)}
              tone={Number(kl.so_that_bai) > 0 ? "danger" : "primary"}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <BangNguoiDung
                rows={data.nguoi_dung || []}
                ghiChu={data.ghi_chu}
                onXem={xemChiTiet}
              />
            </div>
            <div className="space-y-4">
              <KhungAnNinh anNinh={an} ipHong={data.ip_dang_nhap_hong || []} />
              <DoChinhXacPhanLoai data={phanLoai} />
            </div>
          </div>

          <NhipTheoNgay rows={data.theo_ngay || []} />
        </>
      )}

      {chiTiet && <ChiTietNguoiDung data={chiTiet} onClose={() => setChiTiet(null)} />}
    </PageShell>
  );
}

/**
 * Bảng theo từng cán bộ.
 *
 * Cột SỐ TRANG đứng ngay cạnh SỐ TÀI LIỆU là có chủ đích: theo QĐ-06, số tài liệu một mình sẽ bị
 * đọc thành năng suất, trong khi một công văn 2 trang và một khóa luận 200 trang đều là "1 tài liệu".
 */
function BangNguoiDung({ rows, ghiChu, onXem }) {
  return (
    <section className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-200">
        <h2 className="text-base font-semibold text-gray-800">Hoạt động theo cán bộ</h2>
        {/* Ghi chú do backend trả về — luôn hiển thị, không rút gọn (QĐ-06) */}
        {ghiChu && <p className="text-xs text-gray-500 mt-1 leading-relaxed">{ghiChu}</p>}
      </div>
      {rows.length === 0 ? (
        <p className="p-4 text-sm text-gray-500">Chưa có hoạt động nào trong kỳ này.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-gray-600">
              <tr>
                <th className="px-4 py-2 font-medium">Cán bộ</th>
                <th className="px-3 py-2 font-medium text-right">Tải lên</th>
                <th className="px-3 py-2 font-medium text-right">Đã duyệt</th>
                <th className="px-3 py-2 font-medium text-right">Số trang</th>
                <th className="px-3 py-2 font-medium text-right">Trường đã sửa</th>
                <th className="px-3 py-2 font-medium text-right">Đẩy DSpace</th>
                <th className="px-3 py-2 font-medium text-right">Đăng nhập</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.map((r) => (
                <tr key={r.nguoi_dung} className="hover:bg-gray-50">
                  <td className="px-4 py-2">
                    <button
                      onClick={() => onXem(r.nguoi_dung)}
                      className="text-blue-700 hover:underline"
                    >
                      {r.nguoi_dung}
                    </button>
                    {Number(r.so_dang_nhap_hong) > 0 && (
                      <span className="ml-2 text-xs text-amber-700">
                        {r.so_dang_nhap_hong} lần đăng nhập hỏng
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatNumber(r.so_tai_len)}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-medium">
                    {formatNumber(r.so_da_duyet)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-gray-600">
                    {formatNumber(r.so_trang)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-gray-600">
                    {formatNumber(r.so_truong_da_sua)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-gray-600">
                    {formatNumber(r.so_day_dspace)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-gray-600">
                    {formatNumber(r.so_dang_nhap)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function KhungAnNinh({ anNinh, ipHong }) {
  return (
    <section className="bg-white rounded-xl border border-gray-200 p-4">
      <h2 className="text-base font-semibold text-gray-800">An ninh truy cập</h2>
      <dl className="mt-2 space-y-1 text-sm">
        <Dong nhan="Đăng nhập thành công" gia_tri={anNinh.so_dang_nhap} />
        <Dong nhan="Đăng nhập thất bại" gia_tri={anNinh.so_dang_nhap_hong} canh_bao />
        <Dong nhan="Tài khoản bị khóa" gia_tri={anNinh.so_khoa_tai_khoan} canh_bao />
        <Dong nhan="Bị từ chối quyền" gia_tri={anNinh.so_bi_tu_choi} canh_bao />
        <Dong nhan="Người hoạt động" gia_tri={anNinh.so_nguoi_hoat_dong} />
        <Dong nhan="Số địa chỉ IP" gia_tri={anNinh.so_dia_chi_ip} />
      </dl>

      {ipHong.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-100">
          <h3 className="text-xs font-semibold text-gray-700">
            IP đăng nhập hỏng nhiều (≥5 lần)
          </h3>
          <ul className="mt-1 space-y-0.5">
            {ipHong.map((r) => (
              <li key={r.ip} className="text-xs text-gray-700">
                <span className="font-mono">{r.ip}</span> — {formatNumber(r.so_lan)} lần
                {Number(r.so_tai_khoan_bi_thu) > 1 && (
                  <span className="text-red-700">
                    , thử {r.so_tai_khoan_bi_thu} tài khoản
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/**
 * Độ chính xác của việc đoán loại tài liệu.
 *
 * Hiển thị «chưa đủ dữ liệu» thay vì 0% khi chưa có mẫu nào: nguyên tắc SRS "đo được mới tuyên bố".
 * Một con số 0% ở đây sẽ bị đọc thành "máy đoán sai hết", trong khi sự thật là chưa ai duyệt tài
 * liệu nào để so.
 */
function DoChinhXacPhanLoai({ data }) {
  if (!data) return null;

  return (
    <section className="bg-white rounded-xl border border-gray-200 p-4">
      <h2 className="text-base font-semibold text-gray-800">Đoán loại tài liệu</h2>
      {data.chua_do_duoc ? (
        <p className="text-sm text-gray-500 mt-1">{data.ly_do}</p>
      ) : data.ty_le_dung === null ? (
        <p className="text-sm text-gray-500 mt-1">
          Chưa đủ dữ liệu để đo — cần tài liệu đã được cán bộ xác nhận.
        </p>
      ) : (
        <>
          <p className="text-2xl font-bold text-hpu-primary mt-1 tabular-nums">
            {data.ty_le_dung}%
          </p>
          <p className="text-xs text-gray-500">
            đúng {formatNumber(data.so_dung)}/{formatNumber(data.tong_so)} tài liệu đã duyệt
          </p>

          {data.nham_lan_thuong_gap?.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              <h3 className="text-xs font-semibold text-gray-700">Nhầm lẫn thường gặp</h3>
              <ul className="mt-1 space-y-0.5">
                {data.nham_lan_thuong_gap.slice(0, 5).map((r, i) => (
                  <li key={i} className="text-xs text-gray-600">
                    máy đoán <strong>{r.may_doan}</strong> → thực tế{" "}
                    <strong>{r.can_bo_chot}</strong> ({r.so_lan} lần)
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
      {data.ghi_chu && <p className="text-xs text-gray-400 mt-2">{data.ghi_chu}</p>}
    </section>
  );
}

function NhipTheoNgay({ rows }) {
  if (rows.length === 0) return null;
  const max = Math.max(...rows.map((r) => Number(r.so_tai_lieu) || 0), 1);

  return (
    <section className="bg-white rounded-xl border border-gray-200 p-4 mt-4">
      <h2 className="text-base font-semibold text-gray-800">Tài liệu tiếp nhận theo ngày</h2>
      <div className="mt-3 space-y-1">
        {rows.slice(0, 14).map((r) => (
          <div key={r.ngay} className="flex items-center gap-2 text-xs">
            <span className="w-24 shrink-0 text-gray-600">
              {new Date(r.ngay).toLocaleDateString("vi-VN")}
            </span>
            <div className="flex-1 h-4 bg-gray-100 rounded overflow-hidden">
              <div
                className="h-full rounded"
                style={{
                  width: `${(Number(r.so_tai_lieu) / max) * 100}%`,
                  backgroundColor: "#1e3a5f",
                }}
              />
            </div>
            <span className="w-20 shrink-0 text-right tabular-nums text-gray-700">
              {formatNumber(r.so_tai_lieu)}
              {Number(r.so_that_bai) > 0 && (
                <span className="text-red-700"> ({r.so_that_bai} lỗi)</span>
              )}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function ChiTietNguoiDung({ data, onClose }) {
  return (
    <div
      className="fixed inset-0 bg-black/30 flex items-center justify-center p-4 z-50"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl max-w-2xl w-full max-h-[85vh] overflow-y-auto p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900">{data.nguoi_dung}</h2>
          <button
            onClick={onClose}
            className="rounded-lg border border-gray-300 px-3 py-1 text-sm text-gray-700"
          >
            Đóng
          </button>
        </div>

        {data.dang_tai ? (
          <p className="text-sm text-gray-500">Đang tải…</p>
        ) : data.loi ? (
          <p className="text-sm text-red-700">{data.loi}</p>
        ) : (
          <div className="space-y-4">
            <Muc tieu_de="Theo hành động">
              {(data.theo_hanh_dong || []).length === 0 ? (
                <p className="text-sm text-gray-500">Không có thao tác nào trong kỳ.</p>
              ) : (
                <ul className="text-sm space-y-0.5">
                  {data.theo_hanh_dong.map((r) => (
                    <li key={r.hanh_dong} className="flex justify-between">
                      <span className="text-gray-700">{r.hanh_dong}</span>
                      <span className="tabular-nums font-medium">{formatNumber(r.so_lan)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Muc>

            {(data.theo_loai_tai_lieu || []).length > 0 && (
              <Muc tieu_de="Loại tài liệu đã duyệt">
                <ul className="text-sm space-y-0.5">
                  {data.theo_loai_tai_lieu.map((r) => (
                    <li key={r.loai} className="flex justify-between">
                      <span className="text-gray-700">{r.nhan}</span>
                      <span className="tabular-nums">{formatNumber(r.so_tai_lieu)}</span>
                    </li>
                  ))}
                </ul>
              </Muc>
            )}

            {(data.theo_ngay || []).length > 0 && (
              <Muc tieu_de="Theo ngày">
                <ul className="text-sm space-y-0.5 max-h-48 overflow-y-auto">
                  {data.theo_ngay.map((r) => (
                    <li key={r.ngay} className="flex justify-between text-gray-700">
                      <span>{new Date(r.ngay).toLocaleDateString("vi-VN")}</span>
                      <span className="tabular-nums">
                        {formatNumber(r.so_thao_tac)} thao tác · {formatNumber(r.so_da_duyet)} duyệt
                      </span>
                    </li>
                  ))}
                </ul>
              </Muc>
            )}

            {(data.hoat_dong_gan_nhat || []).length > 0 && (
              <Muc tieu_de="Hoạt động gần nhất">
                <ul className="text-xs space-y-0.5 max-h-48 overflow-y-auto font-mono">
                  {data.hoat_dong_gan_nhat.map((r, i) => (
                    <li
                      key={i}
                      className={r.ket_qua !== "ok" ? "text-red-700" : "text-gray-600"}
                    >
                      {new Date(r.created_at).toLocaleString("vi-VN")} · {r.hanh_dong}
                      {r.ket_qua !== "ok" && ` · ${r.ket_qua}`}
                      {r.ip && ` · ${r.ip}`}
                    </li>
                  ))}
                </ul>
              </Muc>
            )}

            {data.ghi_chu && <p className="text-xs text-gray-400">{data.ghi_chu}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

function Muc({ tieu_de, children }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-800 mb-1">{tieu_de}</h3>
      {children}
    </div>
  );
}

function Dong({ nhan, gia_tri, canh_bao = false }) {
  const so = Number(gia_tri || 0);
  return (
    <div className="flex justify-between">
      <dt className="text-gray-600">{nhan}</dt>
      <dd className={`tabular-nums font-medium ${canh_bao && so > 0 ? "text-amber-700" : "text-gray-900"}`}>
        {formatNumber(so)}
      </dd>
    </div>
  );
}
