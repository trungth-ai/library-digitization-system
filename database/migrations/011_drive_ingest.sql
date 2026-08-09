-- =====================================================================
-- Migration 011 — Nạp tài liệu tự động từ Google Drive (YC-BU-21)
-- ---------------------------------------------------------------------
-- VÌ SAO: quy trình thật ở Trung tâm Thông tin Thư viện là cán bộ quét tài liệu bằng máy scan rồi
-- đổ vào một thư mục Drive dùng chung. Hiện phải tải từng tệp về máy rồi tải lại lên hệ thống —
-- hai lần chuyển tệp thủ công cho mỗi tài liệu, và không ai biết tệp nào đã nạp, tệp nào chưa.
--
-- HAI BẢNG, HAI VIỆC KHÁC NHAU:
--   `drive_sources` — CẤU HÌNH: thư mục nào, quét bao lâu một lần, tài liệu vào bộ sưu tập nào.
--   `drive_files`   — SỔ GHI: tệp nào trên Drive đã ứng với job nào. Đây là thứ làm cho việc quét
--                     lặp lại AN TOÀN: quét lần thứ hai thấy tệp đã có trong sổ thì bỏ qua, không
--                     tạo job trùng. Không có bảng này thì mỗi lượt quét lại nạp lại toàn bộ thư mục.
--
-- VÌ SAO KHÔNG ĐÁNH DẤU TRÊN DRIVE (đổi tên/chuyển thư mục "_processed"): tài liệu gốc là của Nhà
-- trường, hệ thống số hóa không được phép sửa. Nếu ghi dấu bên Drive thì một lỗi của ta thành mất
-- mát dữ liệu của họ. Giữ sổ ở phía mình thì sai lầm chỉ nằm ở phía mình.
--
-- AN TOÀN: chỉ CREATE TABLE IF NOT EXISTS. Chạy nhiều lần không lỗi. ⚠️ `pg_dump` trước khi chạy.
-- =====================================================================

SET client_encoding = 'UTF8';

CREATE TABLE IF NOT EXISTS drive_sources (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(200) NOT NULL,
    -- Mã thư mục Drive (đoạn sau /folders/ trong URL). Duy nhất: hai nguồn cùng trỏ một thư mục sẽ
    -- tranh nhau nạp cùng bộ tệp.
    folder_id           VARCHAR(200) NOT NULL UNIQUE,
    folder_name         VARCHAR(300) DEFAULT '',

    -- Tham số cán bộ đặt trước cho mọi tài liệu từ nguồn này.
    -- `document_type='auto'` = để hệ thống đoán theo nội dung (YC-SC-09) — mặc định đúng nhất cho
    -- một thư mục quét trộn nhiều loại tài liệu.
    document_type       VARCHAR(50)  NOT NULL DEFAULT 'auto',
    collection_id       TEXT         NOT NULL DEFAULT '',
    collection_name     TEXT         NOT NULL DEFAULT '',
    language            VARCHAR(20)  NOT NULL DEFAULT 'vie',
    priority            VARCHAR(10)  NOT NULL DEFAULT 'low',   -- mẻ nền, không chen tài liệu lẻ

    -- 'active' = đang quét · 'paused' = giữ cấu hình nhưng ngừng quét · 'deleted' = xóa mềm.
    -- Chuẩn HPU: KHÔNG xóa cứng — lịch sử `drive_files` phải còn để biết tệp nào đã từng nạp.
    status              VARCHAR(20)  NOT NULL DEFAULT 'active',
    scan_interval_sec   INTEGER      NOT NULL DEFAULT 300,

    last_scan_at        TIMESTAMPTZ,
    last_scan_status    VARCHAR(20),        -- ok | error
    last_scan_message   TEXT,               -- lý do tiếng Việt khi lỗi — cán bộ đọc, không phải lập trình viên
    last_scan_found     INTEGER      NOT NULL DEFAULT 0,
    last_scan_ingested  INTEGER      NOT NULL DEFAULT 0,

    created_by          INTEGER,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_drive_sources_active ON drive_sources(last_scan_at NULLS FIRST)
    WHERE status = 'active';

CREATE TABLE IF NOT EXISTS drive_files (
    id             SERIAL PRIMARY KEY,
    source_id      INTEGER      NOT NULL REFERENCES drive_sources(id),
    -- Mã tệp trên Drive. DUY NHẤT TOÀN BẢNG (không phải chỉ trong một nguồn): cùng một tệp được
    -- chia sẻ vào hai thư mục vẫn là MỘT tài liệu, không nên số hóa hai lần.
    drive_file_id  VARCHAR(200) NOT NULL UNIQUE,
    filename       TEXT         NOT NULL,
    size_bytes     BIGINT       NOT NULL DEFAULT 0,
    drive_md5      VARCHAR(64)  DEFAULT '',
    modified_time  TIMESTAMPTZ,

    -- Job đã tạo cho tệp này. NULL khi bỏ qua (trùng nội dung, quá cỡ, tải lỗi).
    job_id         TEXT         REFERENCES documents(id),

    -- ingested = đã tạo job · skipped = cố ý bỏ qua · failed = lỗi, có thể thử lại
    status         VARCHAR(20)  NOT NULL DEFAULT 'ingested',
    note           TEXT,                -- vì sao bỏ qua / lỗi gì, bằng tiếng Việt
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_drive_files_source ON drive_files(source_id, created_at DESC);
-- Tệp lỗi là thứ cán bộ cần thấy đầu tiên khi mở màn hình nguồn Drive
CREATE INDEX IF NOT EXISTS idx_drive_files_failed ON drive_files(source_id, updated_at DESC)
    WHERE status = 'failed';

-- Tự cập nhật updated_at (chuẩn HPU) — dùng lại hàm đã có trong init.sql
DROP TRIGGER IF EXISTS trg_drive_sources_touch ON drive_sources;
CREATE TRIGGER trg_drive_sources_touch BEFORE UPDATE ON drive_sources
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_drive_files_touch ON drive_files;
CREATE TRIGGER trg_drive_files_touch BEFORE UPDATE ON drive_files
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- Nguồn Drive là một nguồn nạp ngang hàng với web/zip/thư mục theo dõi (bảng `batches.source`).
-- Không có ràng buộc CHECK trên cột đó nên không cần sửa gì thêm — ghi chú lại để người sau biết.
COMMENT ON TABLE drive_sources IS
    'Cấu hình thư mục Google Drive được quét định kỳ để nạp tài liệu (YC-BU-21). '
    'Chỉ đọc từ Drive — hệ thống không bao giờ sửa/xóa tệp gốc của Nhà trường.';
