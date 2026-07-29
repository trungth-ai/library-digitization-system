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
    CONSTRAINT uq_schema_field UNIQUE (schema_code, key)
);
CREATE INDEX IF NOT EXISTS idx_schema_fields_code ON schema_fields(schema_code);

-- Seed 2 lược đồ khởi tạo: Dublin Core (YC-SC-02) + Công văn hành chính (YC-SC-03)
INSERT INTO extraction_schemas (code, name, document_type, context_strategy, sensitivity) VALUES
    ('dublin_core', 'Dublin Core (sách/khóa luận)', 'book',     'first8_last2', 'public'),
    ('cong_van',    'Công văn hành chính',          'cong_van', 'full',         'internal')
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
    ('dublin_core', 'dc.identifier.isbn',      'ISBN',                 FALSE, 'text',   NULL,    11),
    ('cong_van',    'so_hieu',                 'Số hiệu',              TRUE,  'text',   NULL,    1),
    ('cong_van',    'ngay_ban_hanh',           'Ngày ban hành',        FALSE, 'date',   NULL,    2),
    ('cong_van',    'co_quan_ban_hanh',        'Cơ quan ban hành',     TRUE,  'text',   NULL,    3),
    ('cong_van',    'loai_van_ban',            'Loại văn bản',         FALSE, 'text',   NULL,    4),
    ('cong_van',    'trich_yeu',               'Trích yếu',            TRUE,  'text',   NULL,    5),
    ('cong_van',    'do_khan',                 'Độ khẩn',              FALSE, 'text',   NULL,    6),
    ('cong_van',    'do_mat',                  'Độ mật',               FALSE, 'text',   NULL,    7),
    ('cong_van',    'noi_nhan',                'Nơi nhận',             FALSE, 'list',   NULL,    8),
    ('cong_van',    'nguoi_ky',                'Người ký',             FALSE, 'text',   NULL,    9)
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
    ('cong_van',  'Công văn',             'Công văn, văn bản hành chính',            TRUE, 6)
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
-- END OF SCHEMA
-- =====================================================================
