-- =====================================================================
-- Library Digitization System - PostgreSQL Schema
-- Thư viện Đại học Hải Phòng
-- ---------------------------------------------------------------------
-- File này được Postgres chạy tự động lần đầu khởi tạo container
-- (mount vào /docker-entrypoint-initdb.d/init.sql qua docker-compose).
--
-- Schema được suy ra từ tầng truy vấn scripts/db.py. Thứ tự tạo bảng
-- tuân theo phụ thuộc khóa ngoại: bảng lookup trước → documents → bảng con.
-- =====================================================================

SET client_encoding = 'UTF8';

-- =====================================================================
-- 1. LOOKUP: LOẠI TÀI LIỆU
--    Dùng bởi get_document_types(); documents.document_type tham chiếu code.
-- =====================================================================
CREATE TABLE IF NOT EXISTS document_types (
    code        VARCHAR(50)  PRIMARY KEY,   -- vd: 'book', 'thesis'
    label       VARCHAR(150) NOT NULL,      -- nhãn hiển thị tiếng Việt
    description TEXT,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    sort_order  INTEGER      NOT NULL DEFAULT 0
);

-- =====================================================================
-- 2. LOOKUP: TRẠNG THÁI OCR (job status)
--    Dùng bởi get_job_statuses(), update_document_status() (progress_value,
--    is_terminal), get_stats() (sort_order), get_document() (label, color).
-- =====================================================================
CREATE TABLE IF NOT EXISTS job_statuses (
    code           VARCHAR(50)  PRIMARY KEY,  -- queued|ocr|extracting|exporting|completed|failed|cancelled
    label          VARCHAR(150) NOT NULL,
    progress_value INTEGER      NOT NULL DEFAULT 0,  -- % tiến độ mặc định cho status này
    is_terminal    BOOLEAN      NOT NULL DEFAULT FALSE, -- TRUE => tự set finished_at
    color          VARCHAR(20)  NOT NULL DEFAULT '#6b7280',
    sort_order     INTEGER      NOT NULL DEFAULT 0
);

-- =====================================================================
-- 3. LOOKUP: TRẠNG THÁI UPLOAD DSPACE
--    Dùng bởi get_dspace_upload_statuses(), get_document()/list_documents()
--    (label, color), get_stats() (sort_order).
-- =====================================================================
CREATE TABLE IF NOT EXISTS dspace_upload_statuses (
    code        VARCHAR(50)  PRIMARY KEY,  -- pending|uploading|uploaded|upload_failed
    label       VARCHAR(150) NOT NULL,
    is_terminal BOOLEAN      NOT NULL DEFAULT FALSE,
    color       VARCHAR(20)  NOT NULL DEFAULT '#6b7280',
    sort_order  INTEGER      NOT NULL DEFAULT 0
);

-- =====================================================================
-- 4. BẢNG CHÍNH: DOCUMENTS (mỗi job số hóa 1 dòng)
--    id = job_id (UUID dạng chuỗi do app sinh bằng uuid4()).
--    Dùng TEXT thay vì UUID để khớp cách app truyền chuỗi và cho phép
--    fallback job_id tùy ý từ Redis.
-- =====================================================================
CREATE TABLE IF NOT EXISTS documents (
    id                     TEXT PRIMARY KEY,
    filename               TEXT        NOT NULL,
    collection_id          TEXT        DEFAULT '',
    document_type          VARCHAR(50) NOT NULL DEFAULT 'book'
                               REFERENCES document_types(code),
    status                 VARCHAR(50) NOT NULL DEFAULT 'queued'
                               REFERENCES job_statuses(code),
    progress               INTEGER     NOT NULL DEFAULT 10,
    pdf_path               TEXT,
    error_message          TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- chuẩn HPU: mọi bảng có updated_at
    finished_at            TIMESTAMPTZ,

    -- Trích xuất bằng model nào, chế độ nào (YC-AU-04, YC-DR-06) — điền khi worker chạy xong
    extraction_provider    VARCHAR(50),   -- claude | ollama | vllm | ...
    extraction_mode        VARCHAR(20),   -- cloud | local
    extraction_model       VARCHAR(150),
    needs_review           BOOLEAN     NOT NULL DEFAULT FALSE,  -- YC-CF-03: cần cán bộ xử lý tay
    review_note            TEXT,          -- lý do cần xem lại (lỗi hợp lệ, điểm tin cậy thấp)

    -- Loại tài liệu MÁY đoán (YC-SC-09). Tách khỏi `document_type` (loại cán bộ chốt) để so được
    -- "máy đoán" với "người chốt" → đo được độ chính xác. Không FK: mã lạ do model trả về vẫn phải
    -- ghi được, đoán sai không được biến thành job thất bại.
    detected_type          VARCHAR(50),
    detected_confidence    NUMERIC(4, 3),
    detected_source        VARCHAR(20),   -- filename | text | model | none
    detected_reason        TEXT,          -- dấu hiệu đã khớp, viết bằng tiếng Việt cho cán bộ đọc

    -- Thời gian xử lý (theo dõi vận hành + YC-HN). `finished_at - created_at` KHÔNG dùng được vì
    -- gồm cả thời gian nằm chờ trong hàng đợi; hai cột dưới đây đo đúng phần worker thực sự làm.
    duration_ms            INTEGER,       -- tổng thời gian worker xử lý tài liệu này
    stage_timings          JSONB,         -- {"ocr": 41230, "extract": 1820, "export": 260} (ms)

    -- DSpace tracking
    dspace_status          VARCHAR(50) NOT NULL DEFAULT 'pending'
                               REFERENCES dspace_upload_statuses(code),
    dspace_collection_id   TEXT,
    dspace_collection_name TEXT,
    dspace_community_name  TEXT,
    dspace_item_id         TEXT,
    dspace_handle          TEXT,
    dspace_uploaded_at     TIMESTAMPTZ,
    dspace_error           TEXT
);

CREATE INDEX IF NOT EXISTS idx_documents_status         ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_dspace_status  ON documents(dspace_status);
CREATE INDEX IF NOT EXISTS idx_documents_created_at     ON documents(created_at DESC);
-- Danh sách mặc định loại tài liệu đã xóa mềm → index riêng cho truy vấn phổ biến nhất
CREATE INDEX IF NOT EXISTS idx_documents_not_deleted    ON documents(created_at DESC)
    WHERE status <> 'deleted';
CREATE INDEX IF NOT EXISTS idx_documents_needs_review   ON documents(needs_review)
    WHERE needs_review;
-- Đo độ chính xác của việc đoán loại: "tài liệu nào máy đoán khác loại cán bộ chốt"
CREATE INDEX IF NOT EXISTS idx_documents_detected_mismatch ON documents(created_at DESC)
    WHERE detected_type IS NOT NULL AND detected_type <> document_type;

-- =====================================================================
-- 4b. TRIGGER: tự cập nhật updated_at (chuẩn HPU — không phụ thuộc app nhớ set)
-- =====================================================================
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_documents_touch ON documents;
CREATE TRIGGER trg_documents_touch BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- =====================================================================
-- 5. METADATA FIELDS (metadata Dublin Core, hỗ trợ multi-value)
--    save_metadata() dùng ON CONFLICT (document_id, key, value) DO NOTHING
--    => cần UNIQUE đúng bộ 3 cột này.
--    get_metadata() ORDER BY id => cần cột id tự tăng.
--    Xóa document sẽ CASCADE xóa metadata.
-- =====================================================================
CREATE TABLE IF NOT EXISTS metadata_fields (
    id          BIGSERIAL PRIMARY KEY,
    document_id TEXT        NOT NULL
                    REFERENCES documents(id) ON DELETE CASCADE,
    key         VARCHAR(100) NOT NULL,   -- vd: dc.title, dc.contributor.author
    value       TEXT         NOT NULL,
    language    VARCHAR(20),             -- vd: vi_VN, en_US, hoặc NULL
    -- YC-CF-01: điểm tin cậy 0.000–1.000; NULL = chưa tính (dữ liệu cũ trước khi bật lớp provider)
    confidence  NUMERIC(4,3),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_metadata_doc_key_value UNIQUE (document_id, key, value),
    CONSTRAINT ck_metadata_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE INDEX IF NOT EXISTS idx_metadata_document_id ON metadata_fields(document_id);
-- YC-CF-04: UI cần lọc nhanh trường điểm thấp để cán bộ tập trung kiểm tra
CREATE INDEX IF NOT EXISTS idx_metadata_low_conf    ON metadata_fields(document_id)
    WHERE confidence IS NOT NULL AND confidence < 0.5;

DROP TRIGGER IF EXISTS trg_metadata_touch ON metadata_fields;
CREATE TRIGGER trg_metadata_touch BEFORE UPDATE ON metadata_fields
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- =====================================================================
-- 6. METADATA HISTORY (lịch sử hiệu chỉnh metadata)
--    get_metadata_history() đọc: key, old_value, new_value, changed_at, changed_by.
--    Ghi tự động qua trigger AFTER UPDATE trên metadata_fields (xem mục 7).
-- =====================================================================
CREATE TABLE IF NOT EXISTS metadata_history (
    id          BIGSERIAL PRIMARY KEY,
    document_id TEXT        NOT NULL
                    REFERENCES documents(id) ON DELETE CASCADE,
    key         VARCHAR(100) NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by  VARCHAR(150) DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_metadata_history_document_id ON metadata_history(document_id);

-- =====================================================================
-- 7. TRIGGER: tự ghi metadata_history khi value của 1 field thay đổi
--    LƯU Ý: update_metadata() hiện tại dùng DELETE + INSERT nên trigger
--    AFTER UPDATE này ít khi kích hoạt. Bảng vẫn cần tồn tại để
--    get_metadata_history() không lỗi. Nếu sau này chuyển update_metadata
--    sang câu lệnh UPDATE thì lịch sử sẽ được ghi tự động.
-- =====================================================================
CREATE OR REPLACE FUNCTION log_metadata_change()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.value IS DISTINCT FROM OLD.value THEN
        INSERT INTO metadata_history (document_id, key, old_value, new_value)
        VALUES (OLD.document_id, OLD.key, OLD.value, NEW.value);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_log_metadata_change ON metadata_fields;
CREATE TRIGGER trg_log_metadata_change
    AFTER UPDATE ON metadata_fields
    FOR EACH ROW
    EXECUTE FUNCTION log_metadata_change();

-- =====================================================================
-- 7b. AUDIT LOG — nhật ký kiểm toán BẤT BIẾN (YC-AU)
--   Append-only: chặn UPDATE/DELETE/TRUNCATE bằng trigger (YC-AU-03) — kể cả quản trị viên.
--   get: truy được toàn vòng đời tài liệu (YC-AU-01); ghi ai/khi nào/cũ→mới (YC-AU-02);
--        chế độ + model đã dùng (YC-AU-04).
-- =====================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id           BIGSERIAL PRIMARY KEY,
    document_id  TEXT,                    -- tài liệu liên quan (NULL nếu thao tác hệ thống)
    action       VARCHAR(50)  NOT NULL,   -- upload|process|edit_field|confirm|dspace_push|sensitivity_change|...
    actor        VARCHAR(150),            -- ai thực hiện (YC-AU-02)
    field_key    VARCHAR(100),            -- trường bị sửa (nếu có)
    old_value    TEXT,                    -- giá trị cũ (YC-AU-02)
    new_value    TEXT,                    -- giá trị mới
    mode         VARCHAR(20),             -- cloud|local (YC-AU-04)
    model        VARCHAR(150),            -- tên + phiên bản model (YC-AU-04)
    detail       JSONB,                   -- thông tin bổ sung
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_document_id ON audit_log(document_id);
CREATE INDEX IF NOT EXISTS idx_audit_created_at  ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor       ON audit_log(actor);
CREATE INDEX IF NOT EXISTS idx_audit_action      ON audit_log(action);

-- Bất biến (YC-AU-03): mọi UPDATE/DELETE/TRUNCATE đều bị từ chối, kể cả bởi quản trị viên.
CREATE OR REPLACE FUNCTION prevent_audit_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_log bất biến (append-only): không được thực hiện % (YC-AU-03)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_no_update ON audit_log;
CREATE TRIGGER trg_audit_no_update BEFORE UPDATE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();

DROP TRIGGER IF EXISTS trg_audit_no_delete ON audit_log;
CREATE TRIGGER trg_audit_no_delete BEFORE DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();

DROP TRIGGER IF EXISTS trg_audit_no_truncate ON audit_log;
CREATE TRIGGER trg_audit_no_truncate BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION prevent_audit_mutation();

-- =====================================================================
-- 7c. LƯỢC ĐỒ TRÍCH XUẤT dạng DỮ LIỆU (YC-SC-01) — cấu hình được, không sửa mã
--   Mỗi lược đồ có độ nhạy cảm (YC-DR-01) + chiến lược chọn ngữ cảnh (YC-SC-04).
-- =====================================================================
CREATE TABLE IF NOT EXISTS extraction_schemas (
    code             VARCHAR(50)  PRIMARY KEY,
    name             VARCHAR(200) NOT NULL,
    document_type    VARCHAR(50)  NOT NULL,
    context_strategy VARCHAR(50)  NOT NULL DEFAULT 'first8_last2',
    sensitivity      VARCHAR(20)  NOT NULL DEFAULT 'public',
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS schema_fields (
    id          BIGSERIAL PRIMARY KEY,
    schema_code VARCHAR(50)  NOT NULL REFERENCES extraction_schemas(code) ON DELETE CASCADE,
    key         VARCHAR(100) NOT NULL,
    label       VARCHAR(200),
    required    BOOLEAN      NOT NULL DEFAULT FALSE,
    data_type   VARCHAR(20)  NOT NULL DEFAULT 'text',   -- text|date|number|list
    language    VARCHAR(20),
    description TEXT,
    sort_order  INTEGER      NOT NULL DEFAULT 0,
    source      VARCHAR(10)  NOT NULL DEFAULT 'ai',  -- ai | system | manual (YC-CF: chỉ 'ai' đưa vào prompt)
    CONSTRAINT uq_schema_field UNIQUE (schema_code, key)
);
CREATE INDEX IF NOT EXISTS idx_schema_fields_code ON schema_fields(schema_code);

-- Seed lược đồ khởi tạo:
--   • dublin_core (document_type=book) — GIỮ đường Claude cũ (KT-KH), không xóa.
--   • 7 lược đồ biên mục theo bộ mẫu HPU (sach/de_cuong/khoa_luan/luan_van/hoi_thao/bao_nckh/cong_van)
--     seed ở khối "CATALOG SCHEMAS" ngay bên dưới — sinh từ scripts/eval/schemas.py (docs/CATALOG_SCHEMAS.md).
INSERT INTO extraction_schemas (code, name, document_type, context_strategy, sensitivity) VALUES
    ('dublin_core', 'Dublin Core (sách/khóa luận)', 'book', 'first8_last2', 'public')
ON CONFLICT (code) DO NOTHING;

INSERT INTO schema_fields (schema_code, key, label, required, data_type, language, sort_order) VALUES
    ('dublin_core', 'dc.title',                'Tiêu đề',              TRUE,  'text',   'vi_VN', 1),
    ('dublin_core', 'dc.title.alternative',    'Tiêu đề phụ',          FALSE, 'text',   'en_US', 2),
    ('dublin_core', 'dc.contributor.author',   'Tác giả',              TRUE,  'list',   'vi_VN', 3),
    ('dublin_core', 'dc.contributor.advisor',  'Giảng viên hướng dẫn', FALSE, 'list',   'vi_VN', 4),
    ('dublin_core', 'dc.publisher',            'Nhà xuất bản',         FALSE, 'text',   'vi_VN', 5),
    ('dublin_core', 'dc.date.issued',          'Năm xuất bản',         FALSE, 'number', NULL,    6),
    ('dublin_core', 'dc.subject',              'Từ khóa',              FALSE, 'list',   'vi_VN', 7),
    ('dublin_core', 'dc.description.abstract', 'Tóm tắt',              FALSE, 'text',   'vi_VN', 8),
    ('dublin_core', 'dc.type',                 'Loại',                 TRUE,  'text',   'en_US', 9),
    ('dublin_core', 'dc.language.iso',         'Ngôn ngữ',             FALSE, 'text',   NULL,    10),
    ('dublin_core', 'dc.identifier.isbn',      'ISBN',                 FALSE, 'text',   NULL,    11)
ON CONFLICT (schema_code, key) DO NOTHING;

-- ===== CATALOG SCHEMAS (7 loại theo bộ mẫu biên mục HPU) =====
INSERT INTO extraction_schemas (code, name, document_type, context_strategy, sensitivity) VALUES
    ('sach', 'Sách', 'sach', 'first8_last2', 'public'),
    ('de_cuong', 'Đề cương môn học', 'de_cuong', 'first8_last2', 'public'),
    ('khoa_luan', 'Khóa luận / Đồ án', 'khoa_luan', 'first8_last2', 'public'),
    ('luan_van', 'Luận văn thạc sỹ', 'luan_van', 'first8_last2', 'public'),
    ('hoi_thao', 'Kỷ yếu hội thảo', 'hoi_thao', 'first8_last2', 'public'),
    ('bao_nckh', 'Báo / Tạp chí NCKH', 'bao_nckh', 'first8_last2', 'public'),
    ('cong_van', 'Công văn hành chính', 'cong_van', 'full', 'internal')
ON CONFLICT (code) DO NOTHING;

INSERT INTO schema_fields (schema_code, key, label, required, data_type, language, sort_order, source) VALUES
    ('sach', 'dc.identifier.other', 'Mã tài liệu (HPU)', TRUE, 'text', NULL, 1, 'manual'),
    ('sach', 'dc.title', 'Nhan đề', TRUE, 'text', 'vi_VN', 2, 'ai'),
    ('sach', 'dc.title.alternative', 'Nhan đề khác', FALSE, 'text', 'vi_VN', 3, 'ai'),
    ('sach', 'dc.contributor.author', 'Tác giả', TRUE, 'list', 'vi_VN', 4, 'ai'),
    ('sach', 'dc.contributor.editor', 'Biên tập / Chủ biên', FALSE, 'list', 'vi_VN', 5, 'ai'),
    ('sach', 'dc.publisher', 'Nhà xuất bản', FALSE, 'text', 'vi_VN', 6, 'ai'),
    ('sach', 'dc.date.issued', 'Năm xuất bản', FALSE, 'number', NULL, 7, 'ai'),
    ('sach', 'dc.subject', 'Từ khóa', TRUE, 'list', 'vi_VN', 8, 'ai'),
    ('sach', 'dc.description.abstract', 'Tóm tắt', FALSE, 'text', 'vi_VN', 9, 'ai'),
    ('sach', 'dc.identifier.isbn', 'ISBN', FALSE, 'text', NULL, 10, 'ai'),
    ('sach', 'dc.language.iso', 'Ngôn ngữ', FALSE, 'text', NULL, 11, 'ai'),
    ('sach', 'dc.department', 'Bộ sưu tập / Khoa', FALSE, 'text', 'en_US', 12, 'ai'),
    ('sach', 'dc.type', 'Loại tài liệu', TRUE, 'text', 'en_US', 13, 'system'),
    ('sach', 'dc.format.extent', 'Số trang', FALSE, 'text', NULL, 14, 'system'),
    ('sach', 'dc.size', 'Dung lượng', FALSE, 'text', 'en_US', 15, 'system'),
    ('sach', 'dc.format.mimetype', 'Định dạng', FALSE, 'text', NULL, 16, 'system'),
    ('de_cuong', 'dc.identifier.other', 'Mã tài liệu (HPU)', TRUE, 'text', NULL, 1, 'manual'),
    ('de_cuong', 'dc.title', 'Nhan đề', TRUE, 'text', 'vi_VN', 2, 'ai'),
    ('de_cuong', 'dc.title.alternative', 'Nhan đề khác', FALSE, 'text', 'vi_VN', 3, 'ai'),
    ('de_cuong', 'dc.contributor.author', 'Tác giả', TRUE, 'list', 'vi_VN', 4, 'ai'),
    ('de_cuong', 'dc.contributor.editor', 'Biên tập / Chủ biên', FALSE, 'list', 'vi_VN', 5, 'ai'),
    ('de_cuong', 'dc.publisher', 'Nhà xuất bản', FALSE, 'text', 'vi_VN', 6, 'ai'),
    ('de_cuong', 'dc.date.issued', 'Năm xuất bản', FALSE, 'number', NULL, 7, 'ai'),
    ('de_cuong', 'dc.subject', 'Từ khóa', TRUE, 'list', 'vi_VN', 8, 'ai'),
    ('de_cuong', 'dc.description.abstract', 'Tóm tắt', FALSE, 'text', 'vi_VN', 9, 'ai'),
    ('de_cuong', 'dc.identifier.isbn', 'ISBN', FALSE, 'text', NULL, 10, 'ai'),
    ('de_cuong', 'dc.language.iso', 'Ngôn ngữ', FALSE, 'text', NULL, 11, 'ai'),
    ('de_cuong', 'dc.department', 'Bộ sưu tập / Khoa', FALSE, 'text', 'en_US', 12, 'ai'),
    ('de_cuong', 'dc.type', 'Loại tài liệu', TRUE, 'text', 'en_US', 13, 'system'),
    ('de_cuong', 'dc.format.extent', 'Số trang', FALSE, 'text', NULL, 14, 'system'),
    ('de_cuong', 'dc.size', 'Dung lượng', FALSE, 'text', 'en_US', 15, 'system'),
    ('de_cuong', 'dc.format.mimetype', 'Định dạng', FALSE, 'text', NULL, 16, 'system'),
    ('khoa_luan', 'dc.identifier.other', 'Mã tài liệu (HPU)', TRUE, 'text', NULL, 1, 'manual'),
    ('khoa_luan', 'dc.title', 'Nhan đề', TRUE, 'text', 'vi_VN', 2, 'ai'),
    ('khoa_luan', 'dc.contributor.author', 'Tác giả', TRUE, 'list', 'vi_VN', 3, 'ai'),
    ('khoa_luan', 'dc.contributor.advisor', 'Người hướng dẫn', TRUE, 'list', 'vi_VN', 4, 'ai'),
    ('khoa_luan', 'dc.publisher', 'Đơn vị đào tạo', FALSE, 'text', 'vi_VN', 5, 'ai'),
    ('khoa_luan', 'dc.date.issued', 'Năm bảo vệ', FALSE, 'number', NULL, 6, 'ai'),
    ('khoa_luan', 'dc.subject', 'Từ khóa', TRUE, 'list', 'vi_VN', 7, 'ai'),
    ('khoa_luan', 'dc.description.abstract', 'Tóm tắt', FALSE, 'text', 'vi_VN', 8, 'ai'),
    ('khoa_luan', 'dc.description.degree', 'Học vị / Loại', FALSE, 'text', 'en_US', 9, 'ai'),
    ('khoa_luan', 'dc.language.iso', 'Ngôn ngữ', FALSE, 'text', NULL, 10, 'ai'),
    ('khoa_luan', 'dc.department', 'Khoa / Bộ môn', FALSE, 'text', 'en_US', 11, 'ai'),
    ('khoa_luan', 'dc.type', 'Loại tài liệu', TRUE, 'text', 'en_US', 12, 'system'),
    ('khoa_luan', 'dc.format.extent', 'Số trang', FALSE, 'text', NULL, 13, 'system'),
    ('khoa_luan', 'dc.size', 'Dung lượng', FALSE, 'text', 'en_US', 14, 'system'),
    ('khoa_luan', 'dc.format.mimetype', 'Định dạng', FALSE, 'text', NULL, 15, 'system'),
    ('luan_van', 'dc.identifier.other', 'Mã tài liệu (HPU)', TRUE, 'text', NULL, 1, 'manual'),
    ('luan_van', 'dc.title', 'Nhan đề', TRUE, 'text', 'vi_VN', 2, 'ai'),
    ('luan_van', 'dc.contributor.author', 'Tác giả', TRUE, 'list', 'vi_VN', 3, 'ai'),
    ('luan_van', 'dc.contributor.advisor', 'Người hướng dẫn', TRUE, 'list', 'vi_VN', 4, 'ai'),
    ('luan_van', 'dc.publisher', 'Đơn vị đào tạo', FALSE, 'text', 'vi_VN', 5, 'ai'),
    ('luan_van', 'dc.date.issued', 'Năm bảo vệ', FALSE, 'number', NULL, 6, 'ai'),
    ('luan_van', 'dc.subject', 'Từ khóa', TRUE, 'list', 'vi_VN', 7, 'ai'),
    ('luan_van', 'dc.description.abstract', 'Tóm tắt', FALSE, 'text', 'vi_VN', 8, 'ai'),
    ('luan_van', 'dc.description.degree', 'Học vị / Loại', FALSE, 'text', 'en_US', 9, 'ai'),
    ('luan_van', 'dc.language.iso', 'Ngôn ngữ', FALSE, 'text', NULL, 10, 'ai'),
    ('luan_van', 'dc.department', 'Khoa / Bộ môn', FALSE, 'text', 'en_US', 11, 'ai'),
    ('luan_van', 'dc.type', 'Loại tài liệu', TRUE, 'text', 'en_US', 12, 'system'),
    ('luan_van', 'dc.format.extent', 'Số trang', FALSE, 'text', NULL, 13, 'system'),
    ('luan_van', 'dc.size', 'Dung lượng', FALSE, 'text', 'en_US', 14, 'system'),
    ('luan_van', 'dc.format.mimetype', 'Định dạng', FALSE, 'text', NULL, 15, 'system'),
    ('hoi_thao', 'dc.identifier.other', 'Mã tài liệu (HPU)', TRUE, 'text', NULL, 1, 'manual'),
    ('hoi_thao', 'dc.title', 'Nhan đề', TRUE, 'text', 'vi_VN', 2, 'ai'),
    ('hoi_thao', 'dc.contributor.author', 'Tác giả', TRUE, 'list', 'vi_VN', 3, 'ai'),
    ('hoi_thao', 'dc.contributor.advisor', 'Người hướng dẫn', FALSE, 'list', 'vi_VN', 4, 'ai'),
    ('hoi_thao', 'dc.publisher', 'Nơi công bố / Tạp chí', FALSE, 'text', 'vi_VN', 5, 'ai'),
    ('hoi_thao', 'dc.date.issued', 'Năm công bố', FALSE, 'number', NULL, 6, 'ai'),
    ('hoi_thao', 'dc.subject', 'Từ khóa', TRUE, 'list', 'vi_VN', 7, 'ai'),
    ('hoi_thao', 'dc.description.abstract', 'Tóm tắt', FALSE, 'text', 'vi_VN', 8, 'ai'),
    ('hoi_thao', 'dc.description.degree', 'Loại bài', FALSE, 'text', 'en_US', 9, 'ai'),
    ('hoi_thao', 'dc.language.iso', 'Ngôn ngữ', FALSE, 'text', NULL, 10, 'ai'),
    ('hoi_thao', 'dc.department', 'Lĩnh vực / Khoa', FALSE, 'text', 'en_US', 11, 'ai'),
    ('hoi_thao', 'dc.type', 'Loại tài liệu', TRUE, 'text', 'en_US', 12, 'system'),
    ('hoi_thao', 'dc.format.extent', 'Số trang', FALSE, 'text', NULL, 13, 'system'),
    ('hoi_thao', 'dc.size', 'Dung lượng', FALSE, 'text', 'en_US', 14, 'system'),
    ('hoi_thao', 'dc.format.mimetype', 'Định dạng', FALSE, 'text', NULL, 15, 'system'),
    ('bao_nckh', 'dc.identifier.other', 'Mã tài liệu (HPU)', TRUE, 'text', NULL, 1, 'manual'),
    ('bao_nckh', 'dc.title', 'Nhan đề', TRUE, 'text', 'vi_VN', 2, 'ai'),
    ('bao_nckh', 'dc.contributor.author', 'Tác giả', TRUE, 'list', 'vi_VN', 3, 'ai'),
    ('bao_nckh', 'dc.contributor.advisor', 'Người hướng dẫn', FALSE, 'list', 'vi_VN', 4, 'ai'),
    ('bao_nckh', 'dc.publisher', 'Nơi công bố / Tạp chí', FALSE, 'text', 'vi_VN', 5, 'ai'),
    ('bao_nckh', 'dc.date.issued', 'Năm công bố', FALSE, 'number', NULL, 6, 'ai'),
    ('bao_nckh', 'dc.subject', 'Từ khóa', TRUE, 'list', 'vi_VN', 7, 'ai'),
    ('bao_nckh', 'dc.description.abstract', 'Tóm tắt', FALSE, 'text', 'vi_VN', 8, 'ai'),
    ('bao_nckh', 'dc.description.degree', 'Loại bài', FALSE, 'text', 'en_US', 9, 'ai'),
    ('bao_nckh', 'dc.language.iso', 'Ngôn ngữ', FALSE, 'text', NULL, 10, 'ai'),
    ('bao_nckh', 'dc.department', 'Lĩnh vực / Khoa', FALSE, 'text', 'en_US', 11, 'ai'),
    ('bao_nckh', 'dc.type', 'Loại tài liệu', TRUE, 'text', 'en_US', 12, 'system'),
    ('bao_nckh', 'dc.format.extent', 'Số trang', FALSE, 'text', NULL, 13, 'system'),
    ('bao_nckh', 'dc.size', 'Dung lượng', FALSE, 'text', 'en_US', 14, 'system'),
    ('bao_nckh', 'dc.format.mimetype', 'Định dạng', FALSE, 'text', NULL, 15, 'system'),
    ('cong_van', 'so_hieu', 'Số, ký hiệu văn bản', TRUE, 'text', NULL, 1, 'ai'),
    ('cong_van', 'loai_van_ban', 'Loại văn bản', FALSE, 'text', NULL, 2, 'ai'),
    ('cong_van', 'ngay_ban_hanh', 'Ngày ban hành', FALSE, 'date', NULL, 3, 'ai'),
    ('cong_van', 'don_vi_ban_hanh', 'Đơn vị/bộ phận ban hành', FALSE, 'text', NULL, 4, 'ai'),
    ('cong_van', 'co_quan_ban_hanh', 'Cơ quan ban hành', TRUE, 'text', NULL, 5, 'ai'),
    ('cong_van', 'noi_ban_hanh', 'Nơi ban hành', FALSE, 'text', NULL, 6, 'ai'),
    ('cong_van', 'nguoi_ky', 'Người ký', FALSE, 'text', NULL, 7, 'ai'),
    ('cong_van', 'chuc_vu_nguoi_ky', 'Chức vụ người ký', FALSE, 'text', NULL, 8, 'ai'),
    ('cong_van', 'nhan_de', 'Nhan đề văn bản', FALSE, 'text', NULL, 9, 'ai'),
    ('cong_van', 'trich_yeu', 'Trích yếu nội dung', TRUE, 'text', NULL, 10, 'ai'),
    ('cong_van', 'tu_khoa', 'Từ khóa', FALSE, 'list', NULL, 11, 'ai'),
    ('cong_van', 'noi_nhan', 'Nơi nhận', FALSE, 'list', NULL, 12, 'ai'),
    ('cong_van', 'do_khan', 'Độ khẩn', FALSE, 'text', NULL, 13, 'ai'),
    ('cong_van', 'do_mat', 'Độ mật', FALSE, 'text', NULL, 14, 'ai'),
    ('cong_van', 'so_trang', 'Số trang', FALSE, 'text', NULL, 15, 'system'),
    ('cong_van', 'dung_luong', 'Dung lượng tệp', FALSE, 'text', NULL, 16, 'system')
ON CONFLICT (schema_code, key) DO NOTHING;

-- =====================================================================
-- 7d. NHẬT KÝ GỌI MODEL (YC-MP-06 bền vững + YC-MS-07 tài nguyên)
--   Trước đây mỗi lần gọi model chỉ ghi ra log file → không truy vấn được, không dựng báo cáo được.
--   Bảng này cho phép trả lời: tài liệu này do công cụ/model nào trích, mất bao lâu, tốn bao nhiêu RAM,
--   có phải dự phòng không. Là nguồn số liệu cho so sánh công cụ (KT-HN) mà không cần chạy lại harness.
-- =====================================================================
CREATE TABLE IF NOT EXISTS model_calls (
    id            BIGSERIAL PRIMARY KEY,
    document_id   TEXT,                    -- không đặt khóa ngoại: nhật ký sống độc lập với tài liệu
    provider      VARCHAR(50)  NOT NULL,   -- claude | ollama | vllm | gemini | ...
    deployment    VARCHAR(20)  NOT NULL,   -- cloud | local (YC-DR-06)
    model         VARCHAR(150),
    model_version VARCHAR(100),
    schema_code   VARCHAR(50),
    used_ai       BOOLEAN      NOT NULL DEFAULT TRUE,  -- FALSE = rơi về basic extraction
    attempts      INTEGER      NOT NULL DEFAULT 1,     -- YC-CF-03 số lần thử
    latency_ms    INTEGER,
    rss_mb        NUMERIC(10,1),           -- YC-MS-07 bộ nhớ tiến trình sau lời gọi
    gpu_mem_mb    NUMERIC(10,1),           -- YC-MS-07 chỉ có khi bật METRICS_GPU và có nvidia-smi
    n_fields      INTEGER      NOT NULL DEFAULT 0,
    fallback_from VARCHAR(50),             -- công cụ đã lỗi trước khi chuyển sang công cụ này
    error         TEXT,
    status        VARCHAR(20)  NOT NULL DEFAULT 'success',  -- success | fallback | failed
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_calls_document ON model_calls(document_id);
CREATE INDEX IF NOT EXISTS idx_model_calls_created  ON model_calls(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_calls_provider ON model_calls(provider, deployment);

DROP TRIGGER IF EXISTS trg_model_calls_touch ON model_calls;
CREATE TRIGGER trg_model_calls_touch BEFORE UPDATE ON model_calls
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- =====================================================================
-- 7e. SỰ KIỆN HỆ THỐNG — lỗi & trạng thái kết nối (theo dõi vận hành)
--   KHÁC `audit_log`: audit ghi thao tác NGHIỆP VỤ của con người và bất biến; bảng này ghi sự cố
--   HẠ TẦNG (mất Redis/PostgreSQL, lỗi vòng lặp worker, công cụ mô hình không dùng được).
--   Trộn hai loại vào một bảng sẽ làm nhật ký kiểm toán bị nhiễu bởi sự cố kỹ thuật.
--
--   VÌ SAO CẦN: trước đây lỗi chỉ nằm trong log container. Muốn biết "hôm qua worker có mất kết nối
--   Redis lần nào không" thì phải đọc log thủ công, mà log container bị cắt vòng.
-- =====================================================================
CREATE TABLE IF NOT EXISTS system_events (
    id          BIGSERIAL PRIMARY KEY,
    source      VARCHAR(50)  NOT NULL,          -- worker | api | ui
    instance    VARCHAR(150),                   -- id/hostname của tiến trình (phân biệt replica)
    kind        VARCHAR(50)  NOT NULL,          -- redis_down|redis_up|db_down|db_up|worker_error|...
    level       VARCHAR(20)  NOT NULL DEFAULT 'error',   -- info | warning | error
    message     TEXT         NOT NULL,
    detail      TEXT,                           -- traceback hoặc thông tin thêm
    document_id TEXT,                           -- tài liệu liên quan (nếu có)
    status      VARCHAR(20)  NOT NULL DEFAULT 'new',     -- new | resolved (vd Redis nối lại được)
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_system_events_created ON system_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_events_level   ON system_events(level, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_events_kind    ON system_events(kind);
CREATE INDEX IF NOT EXISTS idx_system_events_open    ON system_events(kind)
    WHERE status = 'new';

DROP TRIGGER IF EXISTS trg_system_events_touch ON system_events;
CREATE TRIGGER trg_system_events_touch BEFORE UPDATE ON system_events
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- =====================================================================
-- 8. SEED DATA cho các bảng lookup
--    Bắt buộc: các giá trị mặc định app dùng phải tồn tại trước khi
--    documents insert (book, queued, pending).
-- =====================================================================

-- 8.1 Loại tài liệu
INSERT INTO document_types (code, label, description, is_active, sort_order) VALUES
    ('book',      'Sách',                 'Sách in, sách tham khảo',                 TRUE, 1),
    ('thesis',    'Khóa luận / Đồ án',    'Khóa luận, đồ án, luận văn tốt nghiệp',   TRUE, 2),
    ('textbook',  'Giáo trình',           'Giáo trình giảng dạy',                    TRUE, 3),
    ('journal',   'Tạp chí',              'Tạp chí, kỷ yếu khoa học',                TRUE, 4),
    ('reference', 'Tài liệu tham khảo',   'Tài liệu tham khảo khác',                 TRUE, 5),
    ('cong_van',  'Công văn',             'Công văn, văn bản hành chính',            TRUE, 6),
    -- 6 loại biên mục theo bộ mẫu HPU (mỗi loại 1 lược đồ trong extraction_schemas)
    ('sach',      'Sách',                 'Sách (biên mục Dublin Core)',             TRUE, 7),
    ('de_cuong',  'Đề cương môn học',     'Đề cương chi tiết học phần',              TRUE, 8),
    ('khoa_luan', 'Khóa luận / Đồ án',    'Khóa luận, đồ án tốt nghiệp',             TRUE, 9),
    ('luan_van',  'Luận văn thạc sỹ',     'Luận văn cao học',                        TRUE, 10),
    ('hoi_thao',  'Kỷ yếu hội thảo',      'Bài tham luận hội thảo khoa học',         TRUE, 11),
    ('bao_nckh',  'Báo / Tạp chí NCKH',   'Bài báo khoa học, tạp chí',               TRUE, 12)
ON CONFLICT (code) DO NOTHING;

-- 8.2 Trạng thái OCR (khớp worker.py: queued→ocr→extracting→exporting→completed/failed)
INSERT INTO job_statuses (code, label, progress_value, is_terminal, color, sort_order) VALUES
    ('queued',     'Chờ xử lý',      10,  FALSE, '#6b7280', 1),
    ('ocr',        'Đang OCR',       20,  FALSE, '#3b82f6', 2),
    ('extracting', 'Trích metadata', 60,  FALSE, '#8b5cf6', 3),
    ('exporting',  'Đang xuất',      80,  FALSE, '#f59e0b', 4),
    ('completed',  'Hoàn thành',     100, TRUE,  '#10b981', 5),
    ('failed',     'Thất bại',       0,   TRUE,  '#ef4444', 6),
    ('cancelled',  'Đã hủy',         0,   TRUE,  '#9ca3af', 7),
    -- XÓA MỀM (chuẩn HPU: KHÔNG hard delete). Tài liệu ở trạng thái này bị ẩn khỏi danh sách và
    -- thống kê, nhưng dữ liệu + nhật ký kiểm toán vẫn còn để truy được trách nhiệm (YC-AU).
    ('deleted',    'Đã xóa',         0,   TRUE,  '#9ca3af', 8)
ON CONFLICT (code) DO NOTHING;

-- 8.3 Trạng thái upload DSpace (khớp api.py: pending|uploading|uploaded|upload_failed)
INSERT INTO dspace_upload_statuses (code, label, is_terminal, color, sort_order) VALUES
    ('pending',       'Chưa đẩy',       FALSE, '#6b7280', 1),
    ('uploading',     'Đang đẩy',       FALSE, '#3b82f6', 2),
    ('uploaded',      'Đã đẩy',         TRUE,  '#10b981', 3),
    ('upload_failed', 'Đẩy thất bại',   FALSE, '#ef4444', 4)
ON CONFLICT (code) DO NOTHING;

-- =====================================================================
-- 9. DANH TÍNH & PHÂN QUYỀN (ADR-012 — vá lỗ hổng N-01 "không có xác thực")
--    Giữ ĐỒNG BỘ với database/migrations/003_users_rbac.sql: file này cho cài MỚI, migration cho DB
--    đã tồn tại. Lệch nhau sẽ tạo ra hai hệ thống hành xử khác nhau tùy theo cài lúc nào.
--
--    Sau khi tạo, hệ thống VẪN chạy như cũ vì AUTH_MODE=off là mặc định. Quy trình bật ba nấc
--    off → shadow → on xem ADR-012 và docs/DEPLOY.md.
-- =====================================================================

CREATE TABLE IF NOT EXISTS roles (
    code        VARCHAR(50)  PRIMARY KEY,
    label       VARCHAR(150) NOT NULL,
    description TEXT,
    is_system   BOOLEAN      NOT NULL DEFAULT FALSE,   -- không cho xóa/đổi tên vai trò hệ thống
    sort_order  INTEGER      NOT NULL DEFAULT 0,
    status      VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Quyền là DỮ LIỆU, không phải hằng số trong mã (YC-QT-09) — cùng triết lý với extraction_schemas
CREATE TABLE IF NOT EXISTS role_permissions (
    id         BIGSERIAL PRIMARY KEY,
    role_code  VARCHAR(50)  NOT NULL REFERENCES roles(code) ON DELETE CASCADE,
    permission VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_role_permission UNIQUE (role_code, permission)
);
CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions(role_code);

CREATE TABLE IF NOT EXISTS users (
    id                   BIGSERIAL PRIMARY KEY,
    username             VARCHAR(100) NOT NULL UNIQUE,
    email                VARCHAR(200),
    full_name            VARCHAR(200) NOT NULL,
    -- Băm tự mô tả `pbkdf2_sha256$<vòng>$<salt>$<hash>` — cho phép nâng số vòng lặp / đổi thuật toán
    -- về sau mà không phải đặt lại mật khẩu hàng loạt (scripts/core/passwords.py)
    password_hash        TEXT         NOT NULL,
    role                 VARCHAR(50)  NOT NULL DEFAULT 'viewer' REFERENCES roles(code),
    must_change_password BOOLEAN      NOT NULL DEFAULT FALSE,   -- YC-QT-05
    failed_attempts      INTEGER      NOT NULL DEFAULT 0,       -- YC-QT-06 khóa sau N lần sai
    locked_until         TIMESTAMPTZ,
    last_login_at        TIMESTAMPTZ,
    last_login_ip        VARCHAR(64),
    -- Xóa MỀM (YC-QT-08): audit_log tham chiếu tới người dùng, xóa cứng là mất khả năng truy trách nhiệm
    status               VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    created_by           BIGINT,
    CONSTRAINT ck_users_status CHECK (status IN ('active', 'disabled', 'deleted'))
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_active   ON users(username) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_users_role     ON users(role);

DROP TRIGGER IF EXISTS trg_users_touch ON users;
CREATE TRIGGER trg_users_touch BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
DROP TRIGGER IF EXISTS trg_roles_touch ON roles;
CREATE TRIGGER trg_roles_touch BEFORE UPDATE ON roles
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- Phiên lưu ở PostgreSQL, KHÔNG ở Redis (QĐ-02): Redis ở hệ này là hàng đợi không bền vững, restart
-- là đăng xuất toàn bộ. Lưu ở đây còn cho phép THU HỒI phiên ngay lập tức — điều JWT không làm được.
CREATE TABLE IF NOT EXISTS user_sessions (
    -- Băm SHA-256 của token, KHÔNG lưu token thô: rò CSDL không đồng nghĩa với chiếm được phiên
    token_hash   CHAR(64)     PRIMARY KEY,
    user_id      BIGINT       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ip           VARCHAR(64),
    user_agent   TEXT,
    expires_at   TIMESTAMPTZ  NOT NULL,
    last_seen_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    revoked_at   TIMESTAMPTZ,
    status       VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sessions_user    ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON user_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_active  ON user_sessions(user_id) WHERE status = 'active';

DROP TRIGGER IF EXISTS trg_sessions_touch ON user_sessions;
CREATE TRIGGER trg_sessions_touch BEFORE UPDATE ON user_sessions
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- 9.1 Seed vai trò & quyền — phải khớp scripts/auth/policy.py
INSERT INTO roles (code, label, description, is_system, sort_order) VALUES
    ('admin',     'Quản trị hệ thống', 'Toàn quyền: quản lý người dùng, cấu hình, độ nhạy cảm lược đồ', TRUE, 1),
    ('approver',  'Cán bộ duyệt',      'Duyệt tài liệu và đẩy DSpace, kể cả tài liệu do mình tải lên',  TRUE, 2),
    ('librarian', 'Cán bộ nghiệp vụ',  'Tải lên, sửa metadata, gửi duyệt',                              TRUE, 3),
    ('viewer',    'Người xem',         'Chỉ xem tài liệu và báo cáo',                                   TRUE, 4),
    ('service',   'Tài khoản dịch vụ', 'Dùng cho tích hợp qua API key; không có quyền mặc định nào',     TRUE, 5)
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_code, permission) VALUES
    ('viewer', 'document:read'), ('viewer', 'report:read'),
    ('librarian', 'document:read'), ('librarian', 'report:read'),
    ('librarian', 'document:upload'), ('librarian', 'document:edit'),
    ('librarian', 'document:download'), ('librarian', 'schema:read'),
    ('approver', 'document:read'), ('approver', 'report:read'),
    ('approver', 'document:upload'), ('approver', 'document:edit'),
    ('approver', 'document:download'), ('approver', 'schema:read'),
    ('approver', 'document:approve'), ('approver', 'document:delete'),
    ('approver', 'dspace:push'), ('approver', 'queue:manage'), ('approver', 'audit:read'),
    ('admin', 'document:read'), ('admin', 'report:read'), ('admin', 'document:upload'),
    ('admin', 'document:edit'), ('admin', 'document:download'), ('admin', 'document:approve'),
    ('admin', 'document:delete'), ('admin', 'document:purge'), ('admin', 'dspace:push'),
    ('admin', 'schema:read'), ('admin', 'schema:write'), ('admin', 'schema:sensitivity'),
    ('admin', 'audit:read'), ('admin', 'log:read'), ('admin', 'queue:manage'),
    ('admin', 'user:manage'), ('admin', 'system:config')
ON CONFLICT (role_code, permission) DO NOTHING;

-- =====================================================================
-- 10. NHẬT KÝ HÀNH VI NGƯỜI DÙNG (YC-NK — sprint V4)
--     Giữ ĐỒNG BỘ với database/migrations/004_user_activity.sql.
--
--     Lớp thứ BA trong bốn lớp nhật ký. KHÁC `audit_log`: bảng kia ghi thao tác NGHIỆP VỤ trên TÀI
--     LIỆU và giữ vĩnh viễn; bảng này ghi HÀNH VI truy cập (đăng nhập, sai mật khẩu, bị từ chối
--     quyền, kết xuất) và giữ 365 ngày. Trộn hai loại sẽ làm nhật ký kiểm toán ngập những lần đăng
--     nhập thường ngày, và buộc giữ vĩnh viễn cả dữ liệu chỉ có giá trị điều tra trong một năm.
-- =====================================================================
CREATE TABLE IF NOT EXISTS user_activity (
    id            BIGSERIAL PRIMARY KEY,
    -- Giữ CẢ user_id lẫn username: username để nhật ký còn đọc được sau khi tài khoản bị xóa mềm
    user_id       BIGINT,
    username      VARCHAR(100),
    action        VARCHAR(50)  NOT NULL,   -- login|logout|login_failed|permission_denied|view|export
    resource_type VARCHAR(50),
    resource_id   TEXT,
    ip            VARCHAR(64),
    user_agent    TEXT,
    request_id    VARCHAR(64),             -- nối với tệp log JSONL (YC-LG-02)
    result        VARCHAR(20)  NOT NULL DEFAULT 'ok',   -- ok | denied | failed
    detail        JSONB,
    status        VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_activity_user    ON user_activity(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_activity_created ON user_activity(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_activity_action  ON user_activity(action);
CREATE INDEX IF NOT EXISTS idx_user_activity_ip      ON user_activity(ip);
-- Bị từ chối quyền là tín hiệu an ninh quan trọng nhất trong bảng này → index riêng
CREATE INDEX IF NOT EXISTS idx_user_activity_denied  ON user_activity(created_at DESC)
    WHERE result <> 'ok';

-- Chặn SỬA (YC-NK-01), KHÔNG chặn xóa: thời hạn lưu 365 ngày cần xóa được bản ghi quá hạn qua
-- `scripts/core/retention.py` (việc dọn có ghi số lượng vào system_events).
DROP TRIGGER IF EXISTS trg_user_activity_no_update ON user_activity;
CREATE TRIGGER trg_user_activity_no_update BEFORE UPDATE ON user_activity
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();

-- =====================================================================
-- 11. PHÂN TÍCH CHI TIẾT KẾT QUẢ AI (YC-AN — sprint V2)
--     Giữ ĐỒNG BỘ với database/migrations/005_ai_analytics.sql.
--
--     `model_calls` gốc chỉ đếm `n_fields` — biết model trả BAO NHIÊU trường, không biết trả CÁI GÌ.
--     Hai bảng dưới đây cho phép đo độ chính xác trên VIỆC THẬT: so giá trị AI trả về với giá trị
--     cán bộ duyệt sau đó. Nguồn đáp án chuẩn miễn phí, tích lũy mỗi ngày.
-- =====================================================================

-- Cột phân tích bổ sung cho model_calls (xem migration 005 để biết lý do từng cột)
ALTER TABLE model_calls
    ADD COLUMN IF NOT EXISTS prompt_tokens     INTEGER,
    ADD COLUMN IF NOT EXISTS completion_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS total_tokens      INTEGER,
    -- Tiền là SỐ NGUYÊN (chuẩn HPU): micro-USD giữ độ chính xác đơn giá, VNĐ là thứ người dùng đọc
    ADD COLUMN IF NOT EXISTS cost_micro_usd    BIGINT,
    ADD COLUMN IF NOT EXISTS cost_vnd          BIGINT,
    ADD COLUMN IF NOT EXISTS prompt_version    VARCHAR(50),
    ADD COLUMN IF NOT EXISTS prompt_hash       CHAR(64),
    ADD COLUMN IF NOT EXISTS context_chars     INTEGER,
    ADD COLUMN IF NOT EXISTS context_pages     INTEGER,
    ADD COLUMN IF NOT EXISTS retry_reason      TEXT,
    ADD COLUMN IF NOT EXISTS confidence_avg    NUMERIC(4,3),
    ADD COLUMN IF NOT EXISTS confidence_min    NUMERIC(4,3),
    ADD COLUMN IF NOT EXISTS grounded_ratio    NUMERIC(4,3),
    ADD COLUMN IF NOT EXISTS request_id        VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_model_calls_schema ON model_calls(schema_code, created_at DESC);

CREATE TABLE IF NOT EXISTS model_call_fields (
    id            BIGSERIAL PRIMARY KEY,
    model_call_id BIGINT       REFERENCES model_calls(id) ON DELETE CASCADE,
    document_id   TEXT,
    field_key     VARCHAR(100) NOT NULL,
    -- CẮT NGẮN: đủ để đối chiếu, không biến bảng nhật ký thành bản sao nội dung tài liệu
    value_preview TEXT,
    confidence    NUMERIC(4,3),
    grounded      BOOLEAN,       -- giá trị có trong văn bản gốc không (YC-CF-05, chống ảo giác)
    attempt       INTEGER      NOT NULL DEFAULT 1,
    status        VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_mcf_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);
CREATE INDEX IF NOT EXISTS idx_mcf_document ON model_call_fields(document_id);
CREATE INDEX IF NOT EXISTS idx_mcf_field    ON model_call_fields(field_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mcf_call     ON model_call_fields(model_call_id);

DROP TRIGGER IF EXISTS trg_mcf_touch ON model_call_fields;
CREATE TRIGGER trg_mcf_touch BEFORE UPDATE ON model_call_fields
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- `pages_without_text` là chỉ báo scan xấu: OCR chạy xong nhưng trang đó không có lớp text, nghĩa là
-- nội dung KHÔNG tra cứu được sau khi lên DSpace — hỏng một cách im lặng.
CREATE TABLE IF NOT EXISTS ocr_runs (
    id                 BIGSERIAL PRIMARY KEY,
    document_id        TEXT         NOT NULL,
    engine             VARCHAR(50)  NOT NULL DEFAULT 'ocrmypdf',
    language           VARCHAR(20),
    pages              INTEGER,
    pages_without_text INTEGER,
    dpi_pre            INTEGER,
    dpi_post           INTEGER,
    size_in_bytes      BIGINT,
    size_out_bytes     BIGINT,
    text_chars         INTEGER,
    duration_ms        INTEGER,
    warnings           TEXT,
    status             VARCHAR(20)  NOT NULL DEFAULT 'success',
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ocr_runs_document ON ocr_runs(document_id);
CREATE INDEX IF NOT EXISTS idx_ocr_runs_created  ON ocr_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ocr_runs_bad      ON ocr_runs(created_at DESC)
    WHERE pages_without_text > 0;

DROP TRIGGER IF EXISTS trg_ocr_runs_touch ON ocr_runs;
CREATE TRIGGER trg_ocr_runs_touch BEFORE UPDATE ON ocr_runs
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- =====================================================================
-- 12. LÔ NẠP TÀI LIỆU (YC-BU — sprint V5)
--     Giữ ĐỒNG BỘ với database/migrations/006_batches.sql.
--
--     Không có khái niệm lô thì tải 300 tệp là 300 job rời rạc: không biết còn bao nhiêu, tệp nào
--     lỗi, và không dừng/chạy lại cả mẻ được. `file_hash` được tính SẴN ở đường tải lên (ADR-010)
--     nên chống trùng chỉ là một truy vấn.
-- =====================================================================
CREATE TABLE IF NOT EXISTS batches (
    id            TEXT PRIMARY KEY,
    name          VARCHAR(200) NOT NULL,
    source        VARCHAR(20)  NOT NULL DEFAULT 'web',    -- web|folder|zip|watch|api
    created_by    BIGINT,
    priority      VARCHAR(10)  NOT NULL DEFAULT 'normal',
    -- Bộ đếm thay vì COUNT mỗi lần hiển thị: lô đang chạy được mở xem liên tục
    total_files   INTEGER      NOT NULL DEFAULT 0,
    done_files    INTEGER      NOT NULL DEFAULT 0,
    failed_files  INTEGER      NOT NULL DEFAULT 0,
    skipped_files INTEGER      NOT NULL DEFAULT 0,
    status        VARCHAR(20)  NOT NULL DEFAULT 'running',
    note          TEXT,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at   TIMESTAMPTZ,
    CONSTRAINT ck_batches_status CHECK (
        status IN ('running', 'paused', 'completed', 'cancelled', 'deleted')),
    CONSTRAINT ck_batches_priority CHECK (priority IN ('high', 'normal', 'low'))
);
CREATE INDEX IF NOT EXISTS idx_batches_created ON batches(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_batches_status  ON batches(status)
    WHERE status IN ('running', 'paused');
CREATE INDEX IF NOT EXISTS idx_batches_creator ON batches(created_by);

DROP TRIGGER IF EXISTS trg_batches_touch ON batches;
CREATE TRIGGER trg_batches_touch BEFORE UPDATE ON batches
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS batch_id    TEXT REFERENCES batches(id),
    ADD COLUMN IF NOT EXISTS file_hash   CHAR(64),      -- SHA-256, nền tảng chống trùng (YC-BU-04)
    ADD COLUMN IF NOT EXISTS file_size   BIGINT,
    ADD COLUMN IF NOT EXISTS page_count  INTEGER,
    ADD COLUMN IF NOT EXISTS priority    VARCHAR(10) NOT NULL DEFAULT 'normal',
    ADD COLUMN IF NOT EXISTS attempts    INTEGER     NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS uploaded_by BIGINT,
    ADD COLUMN IF NOT EXISTS assigned_to BIGINT;       -- ai chịu trách nhiệm duyệt (YC-RV-07)

CREATE INDEX IF NOT EXISTS idx_documents_batch    ON documents(batch_id);
-- KHÔNG dùng UNIQUE: cùng một tệp có thể cần xử lý lại có chủ đích (DEDUP_MODE=reprocess)
CREATE INDEX IF NOT EXISTS idx_documents_hash     ON documents(file_hash)
    WHERE file_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_uploader ON documents(uploaded_by);
CREATE INDEX IF NOT EXISTS idx_documents_assignee ON documents(assigned_to)
    WHERE assigned_to IS NOT NULL;

-- =====================================================================
-- 13. LẤY MẪU ĐỘ SÂU HÀNG ĐỢI (YC-BU-18, YC-DB-06 — sprint V6)
--     Giữ ĐỒNG BỘ với database/migrations/007_queue_samples.sql.
--
--     `/api/v2/stats` chỉ cho biết độ sâu NGAY LÚC NÀY. Câu hỏi vận hành thật lại là câu về thời
--     gian: "giờ nào dồn nhất", "thêm worker có giảm tồn đọng không". Không có lịch sử thì không
--     trả lời được câu nào.
-- =====================================================================
CREATE TABLE IF NOT EXISTS queue_samples (
    id            BIGSERIAL PRIMARY KEY,
    -- Tách theo mức ưu tiên: gộp thành một số sẽ che mất tình huống đáng lo nhất — hàng đợi `high`
    -- bị dồn trong khi tổng số trông bình thường vì `low` đã vơi.
    high          INTEGER NOT NULL DEFAULT 0,
    normal        INTEGER NOT NULL DEFAULT 0,
    low           INTEGER NOT NULL DEFAULT 0,
    delayed       INTEGER NOT NULL DEFAULT 0,
    dead          INTEGER NOT NULL DEFAULT 0,
    processing    INTEGER NOT NULL DEFAULT 0,
    workers_alive INTEGER,     -- NULL = không đọc được Redis, KHÁC 0 = không có worker nào
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_queue_samples_created ON queue_samples(created_at DESC);

-- =====================================================================
-- 14. QUY TRÌNH DUYỆT TÀI LIỆU (YC-RV — sprint V8)
--     Giữ ĐỒNG BỘ với database/migrations/008_review_workflow.sql.
--
--     `needs_review` cho biết tài liệu CẦN xem lại, nhưng không có chỗ nào ghi tài liệu ĐÃ ĐƯỢC
--     DUYỆT — nên không chốt được điều kiện "chưa duyệt thì không đẩy DSpace" (YC-RV-04), tức là
--     nguyên tắc SRS "con người giữ quyền quyết định" không cưỡng chế được.
-- =====================================================================
ALTER TABLE documents
    -- NULL = chưa ai xác nhận. Không dùng BOOLEAN vì cần biết xác nhận LÚC NÀO và BỞI AI
    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS confirmed_by VARCHAR(150);

CREATE INDEX IF NOT EXISTS idx_documents_unconfirmed ON documents(updated_at ASC)
    WHERE confirmed_at IS NULL AND status = 'completed';

-- =====================================================================
-- END OF SCHEMA
-- =====================================================================
