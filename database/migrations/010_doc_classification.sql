-- =====================================================================
-- Migration 010 — Đoán loại tài liệu (YC-SC-09)
-- ---------------------------------------------------------------------
-- VÌ SAO: `documents.document_type` chỉ ghi loại CUỐI CÙNG đang dùng, không ghi được máy đã đoán
-- gì và cán bộ có sửa lại không. Thiếu chỗ đó thì:
--   • Cán bộ không biết vì sao tài liệu này lại được trích theo lược đồ "Luận văn" → không tin máy.
--   • Không đo được ĐỘ CHÍNH XÁC của việc đoán loại (tỉ lệ cán bộ phải sửa), tức là không cải tiến
--     được bộ dấu hiệu. Nguyên tắc SRS: "đo được mới tuyên bố".
--
-- `detected_*` là Ý KIẾN CỦA MÁY, giữ nguyên kể cả sau khi cán bộ sửa `document_type`. Đúng một cặp
-- (máy đoán, người chốt) mới so sánh được — ghi đè lên nhau thì mất luôn số liệu.
--
-- Đồng thời SỬA sai lệch của migration 009 trên DB ĐÃ TỒN TẠI: 009 chèn thêm trường công văn theo
-- bộ mẫu mới nhưng `ON CONFLICT DO NOTHING` giữ nguyên `sort_order` cũ của 9 trường có sẵn (1–9),
-- nên trường mới (sort_order 4, 6, 8, 9…) TRÙNG số thứ tự với trường cũ → giao diện biên mục hiện
-- các trường theo thứ tự không xác định. DB tạo mới từ init.sql không dính lỗi này.
--
-- AN TOÀN: chỉ ADD COLUMN + UPDATE thứ tự hiển thị. Chạy nhiều lần không lỗi. ⚠️ `pg_dump` trước.
-- =====================================================================

SET client_encoding = 'UTF8';

ALTER TABLE documents
    -- KHÔNG đặt khóa ngoại tới document_types: đây là ý kiến của máy, có thể là mã lạ do model trả
    -- về. Khóa ngoại ở đây sẽ biến "máy đoán sai" thành "job thất bại" — sai bản chất.
    ADD COLUMN IF NOT EXISTS detected_type       VARCHAR(50),
    ADD COLUMN IF NOT EXISTS detected_confidence NUMERIC(4, 3),
    ADD COLUMN IF NOT EXISTS detected_source     VARCHAR(20),   -- filename | text | model | none
    ADD COLUMN IF NOT EXISTS detected_reason     TEXT;          -- dấu hiệu đã khớp, tiếng Việt

COMMENT ON COLUMN documents.detected_type IS
    'Loại tài liệu MÁY đoán (YC-SC-09). Giữ nguyên kể cả khi cán bộ sửa document_type — cặp giá trị '
    'này là dữ liệu đo độ chính xác của bộ đoán loại.';

-- Truy vấn đo độ chính xác: "tài liệu nào máy đoán khác với loại cán bộ chốt"
CREATE INDEX IF NOT EXISTS idx_documents_detected_mismatch ON documents(created_at DESC)
    WHERE detected_type IS NOT NULL AND detected_type <> document_type;

-- ---------------------------------------------------------------------
-- Sửa thứ tự + nhãn trường công văn cho DB đã tồn tại (xem phần VÌ SAO ở trên).
-- Chỉ đụng đúng lược đồ 'cong_van'; không xóa dữ liệu, không đổi khóa `key`.
-- ---------------------------------------------------------------------
UPDATE schema_fields AS f
SET sort_order = m.sort_order,
    label      = m.label,
    source     = m.source
FROM (VALUES
    ('so_hieu',          'Số, ký hiệu văn bản',      1,  'ai'),
    ('loai_van_ban',     'Loại văn bản',             2,  'ai'),
    ('ngay_ban_hanh',    'Ngày ban hành',            3,  'ai'),
    ('don_vi_ban_hanh',  'Đơn vị/bộ phận ban hành',  4,  'ai'),
    ('co_quan_ban_hanh', 'Cơ quan ban hành',         5,  'ai'),
    ('noi_ban_hanh',     'Nơi ban hành',             6,  'ai'),
    ('nguoi_ky',         'Người ký',                 7,  'ai'),
    ('chuc_vu_nguoi_ky', 'Chức vụ người ký',         8,  'ai'),
    ('nhan_de',          'Nhan đề văn bản',          9,  'ai'),
    ('trich_yeu',        'Trích yếu nội dung',       10, 'ai'),
    ('tu_khoa',          'Từ khóa',                  11, 'ai'),
    ('noi_nhan',         'Nơi nhận',                 12, 'ai'),
    ('do_khan',          'Độ khẩn',                  13, 'ai'),
    ('do_mat',           'Độ mật',                   14, 'ai'),
    ('so_trang',         'Số trang',                 15, 'system'),
    ('dung_luong',       'Dung lượng tệp',           16, 'system')
) AS m(key, label, sort_order, source)
WHERE f.schema_code = 'cong_van' AND f.key = m.key;
