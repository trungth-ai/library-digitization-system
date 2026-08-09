"use client";

// Dropdown CHỌN LOẠI TÀI LIỆU kèm gợi ý tự động (YC-SC-09).
//
// VÌ SAO CẦN: từ khi có 7 lược đồ biên mục, chọn sai loại nghĩa là trích xuất theo sai lược đồ —
// sai từ gốc, cán bộ phải gõ lại toàn bộ. Nhưng bắt chọn tay từng tệp trong lô 500 tệp thì không
// ai làm. Nên mặc định là "Tự động", còn dropdown để cán bộ ghi đè khi biết rõ.
//
// BA TẦNG GỢI Ý, hiện dần theo lượng thông tin có được:
//   1. Ngay khi chọn tệp  — đoán từ TÊN TỆP (thành phần này gọi `/api/loai-tai-lieu`)
//   2. Sau khi OCR xong   — đoán từ NỘI DUNG, hiện ở màn hình duyệt (`detected_*`)
//   3. Cán bộ chốt        — luôn thắng máy
//
// Gợi ý luôn kèm LÝ DO ("thấy: 'luan van thac si'"). Một con số tin cậy trần trụi không giúp cán bộ
// quyết định được gì; biết máy nhìn thấy chữ gì thì mới kiểm tra được trong hai giây.

import React, { useCallback, useEffect, useState } from "react";

// Giá trị đặc biệt: để hệ thống tự đoán. Backend hiểu chuỗi "auto".
export const AUTO = "auto";

/**
 * Tải danh sách loại tài liệu MỘT LẦN cho cả trang.
 * Trả về [] khi lỗi — dropdown vẫn dùng được với riêng lựa chọn "Tự động", tức là form nạp tài liệu
 * không bao giờ bị chặn chỉ vì bảng tra cứu không tải được.
 */
export function useDocumentTypes() {
  const [types, setTypes] = useState([]);

  useEffect(() => {
    let huy = false;
    (async () => {
      try {
        const res = await fetch("/api/loai-tai-lieu", { credentials: "include" });
        if (!res.ok) return;
        const payload = await res.json();
        // Endpoint cũ trả mảng thô, endpoint mới trả envelope {status, data} (ADR-003)
        const rows = Array.isArray(payload) ? payload : payload.data || [];
        if (!huy) setTypes(rows);
      } catch {
        /* im lặng: đã có lựa chọn "Tự động" làm đường lùi */
      }
    })();
    return () => {
      huy = true;
    };
  }, []);

  return types;
}

/**
 * Gợi ý loại tài liệu cho một DANH SÁCH tên tệp, gọi backend đúng MỘT lượt.
 *
 * Cố ý không đoán ở phía trình duyệt dù chỉ là đối sánh chuỗi: bộ dấu hiệu phải có MỘT nguồn duy
 * nhất (`scripts/core/doc_classifier.py`). Hai bản sao sẽ lệch nhau ngay lần chỉnh đầu tiên, và
 * lúc đó gợi ý trước khi tải lên sẽ khác gợi ý sau khi OCR mà không ai hiểu vì sao.
 */
export function useFilenameSuggestions(filenames) {
  const [suggestions, setSuggestions] = useState({});
  const khoa = filenames.join("|");

  useEffect(() => {
    if (!filenames.length) {
      setSuggestions({});
      return;
    }
    let huy = false;
    (async () => {
      try {
        const res = await fetch("/api/loai-tai-lieu", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filenames }),
        });
        if (!res.ok) return;
        const payload = await res.json();
        const theoTen = {};
        for (const item of payload.data || []) theoTen[item.filename] = item;
        if (!huy) setSuggestions(theoTen);
      } catch {
        /* không có gợi ý thì cán bộ chọn tay — không phải lỗi chặn việc */
      }
    })();
    return () => {
      huy = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [khoa]);

  return suggestions;
}

/**
 * Dropdown chọn loại tài liệu.
 *
 * @param {string}   value      mã loại đang chọn ("auto" = để hệ thống đoán)
 * @param {function} onChange   nhận mã loại mới
 * @param {object}   suggestion gợi ý của máy {document_type, label, confidence, reason} — có thể null
 * @param {boolean}  disabled
 */
export default function DocumentTypeSelect({
  value,
  onChange,
  suggestion = null,
  types = null,
  disabled = false,
  label = "Loại tài liệu",
  compact = false,
}) {
  const tuHook = useDocumentTypes();
  const danhSach = types ?? tuHook;

  // Chỉ mời cán bộ áp dụng khi máy có gợi ý KHÁC lựa chọn hiện tại — nút "áp dụng" cho đúng thứ
  // đang chọn chỉ làm rối màn hình.
  const coTheApDung =
    suggestion &&
    suggestion.document_type &&
    suggestion.confidence > 0 &&
    suggestion.document_type !== value;

  const apDung = useCallback(() => {
    if (suggestion?.document_type) onChange(suggestion.document_type);
  }, [suggestion, onChange]);

  return (
    <div>
      {!compact && (
        <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      )}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        aria-label={label}
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm disabled:bg-gray-100"
      >
        <option value={AUTO}>Tự động nhận dạng (hệ thống đoán)</option>
        {danhSach.map((t) => (
          <option key={t.code} value={t.code}>
            {t.label}
          </option>
        ))}
      </select>

      {suggestion && suggestion.confidence > 0 && (
        <SuggestionHint suggestion={suggestion} onApply={coTheApDung ? apDung : null} />
      )}
    </div>
  );
}

/**
 * Dòng gợi ý dưới dropdown.
 *
 * Màu theo ĐỘ TIN CẬY chứ không phải một màu "thông tin" chung: gợi ý chắc chắn và gợi ý mò phải
 * trông khác nhau, nếu không cán bộ sẽ tin cả hai như nhau rồi bấm qua.
 */
export function SuggestionHint({ suggestion, onApply = null }) {
  const chac = suggestion.confidence >= 0.55;
  const mau = chac
    ? "border-green-200 bg-green-50 text-green-800"
    : "border-amber-200 bg-amber-50 text-amber-800";

  return (
    <div className={`mt-1.5 rounded-lg border px-2.5 py-1.5 text-xs ${mau}`}>
      <span className="font-medium">
        {chac ? "Gợi ý: " : "Có thể là: "}
        {suggestion.label}
      </span>
      <span className="opacity-70"> · {Math.round(suggestion.confidence * 100)}% </span>
      {onApply && (
        <button
          type="button"
          onClick={onApply}
          className="ml-1 underline underline-offset-2 font-medium hover:opacity-80"
        >
          dùng gợi ý này
        </button>
      )}
      <div className="opacity-80 mt-0.5">{suggestion.reason}</div>
    </div>
  );
}
