-- =====================================================================
-- Migration 006 — Nạp tài liệu khối lượng lớn (YC-BU, sprint V5)
-- ---------------------------------------------------------------------
-- VÌ SAO: hệ hiện tại không có khái niệm "lô". Tải 300 tệp lên là 300 job rời rạc — không theo dõi
-- được như một mẻ việc, không biết còn bao nhiêu, không dừng/chạy lại cả mẻ được. Và không có cơ
-- chế chống trùng: tải lại cùng một tệp là xử lý lại từ đầu, tốn OCR và tạo bản ghi trùng trên DSpace.
--
-- `file_hash` đã được tính SẴN từ ADR-010 (băm trong cùng lượt đọc khi ghi tệp) — migration này chỉ
-- là nơi để lưu nó. Đó là lý do việc băm được làm sớm dù chưa dùng ngay.
--
-- AN TOÀN: chỉ ADD COLUMN / CREATE TABLE. Chạy nhiều lần không lỗi. ⚠️ `pg_dump` trước khi chạy.
-- =====================================================================

SET client_encoding = 'UTF8';

-- =====================================================================
-- 1. LÔ NẠP TÀI LIỆU
-- =====================================================================
CREATE TABLE IF NOT EXISTS batches (
    id            TEXT PRIMARY KEY,                       -- uuid4 dạng chuỗi, khớp cách documents.id
    name          VARCHAR(200) NOT NULL,                  -- "Công văn tháng 7/2026"
    source        VARCHAR(20)  NOT NULL DEFAULT 'web',    -- web|folder|zip|watch|api
    created_by    BIGINT,                                 -- users(id); không đặt FK để lô sống độc lập
    priority      VARCHAR(10)  NOT NULL DEFAULT 'normal', -- high|normal|low (ADR-011)
    -- Bốn bộ đếm thay vì tính bằng COUNT mỗi lần hiển thị: một lô 500 tệp sẽ được mở xem liên tục
    -- trong lúc chạy, và đếm lại toàn bảng mỗi lần làm mới là lãng phí.
    total_files   INTEGER      NOT NULL DEFAULT 0,
    done_files    INTEGER      NOT NULL DEFAULT 0,
    failed_files  INTEGER      NOT NULL DEFAULT 0,
    skipped_files INTEGER      NOT NULL DEFAULT 0,        -- trùng, sai định dạng, vượt hạn mức
    status        VARCHAR(20)  NOT NULL DEFAULT 'running',-- running|paused|completed|cancelled|deleted
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

-- =====================================================================
-- 2. CỘT MỚI CHO documents
-- =====================================================================
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS batch_id    TEXT REFERENCES batches(id),
    -- SHA-256 của tệp gốc — nền tảng chống trùng (YC-BU-04). Đã được tính sẵn ở đường tải lên.
    ADD COLUMN IF NOT EXISTS file_hash   CHAR(64),
    ADD COLUMN IF NOT EXISTS file_size   BIGINT,
    ADD COLUMN IF NOT EXISTS page_count  INTEGER,
    ADD COLUMN IF NOT EXISTS priority    VARCHAR(10) NOT NULL DEFAULT 'normal',
    ADD COLUMN IF NOT EXISTS attempts    INTEGER     NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS uploaded_by BIGINT,
    -- Ai chịu trách nhiệm duyệt tài liệu này (YC-RV-07, dùng ở sprint V8)
    ADD COLUMN IF NOT EXISTS assigned_to BIGINT;

CREATE INDEX IF NOT EXISTS idx_documents_batch    ON documents(batch_id);
-- KHÔNG dùng UNIQUE: cùng một tệp có thể cần xử lý lại có chủ đích (DEDUP_MODE=reprocess), và một
-- ràng buộc duy nhất sẽ biến việc đó thành lỗi cứng thay vì một lựa chọn vận hành.
CREATE INDEX IF NOT EXISTS idx_documents_hash     ON documents(file_hash)
    WHERE file_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_uploader ON documents(uploaded_by);
CREATE INDEX IF NOT EXISTS idx_documents_assignee ON documents(assigned_to)
    WHERE assigned_to IS NOT NULL;
