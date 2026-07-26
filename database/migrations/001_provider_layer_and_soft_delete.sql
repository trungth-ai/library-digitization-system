-- =====================================================================
-- Migration 001 — Lớp provider vào pipeline + xóa mềm + nhật ký gọi model
-- Ngày: 25/07/2026 · Liên quan: ADR-008
-- ---------------------------------------------------------------------
-- VÌ SAO CẦN FILE NÀY: PostgreSQL chỉ chạy `init.sql` khi khởi tạo volume LẦN ĐẦU
-- (xem docs/DEPLOY.md mục 3). Máy chủ đang chạy đã có volume `postgres_data` → init.sql
-- KHÔNG chạy lại, nên phải áp migration này bằng tay, nếu không code mới sẽ lỗi
-- "column does not exist".
--
-- CÁCH CHẠY:
--   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d library_digitization \
--       < database/migrations/001_provider_layer_and_soft_delete.sql
--
-- AN TOÀN: toàn bộ câu lệnh đều idempotent (IF NOT EXISTS / ON CONFLICT) → chạy lại nhiều
-- lần không sao. KHÔNG xóa dữ liệu, KHÔNG đổi kiểu cột đang có.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. Hàm dùng chung: tự cập nhật updated_at (chuẩn HPU)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 2. documents: updated_at + thông tin trích xuất + cờ cần xem lại
-- ---------------------------------------------------------------------
ALTER TABLE documents ADD COLUMN IF NOT EXISTS updated_at          TIMESTAMPTZ;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extraction_provider VARCHAR(50);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extraction_mode     VARCHAR(20);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extraction_model    VARCHAR(150);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS needs_review        BOOLEAN;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS review_note         TEXT;

-- Dữ liệu cũ: updated_at lấy theo created_at để không có giá trị NULL vô nghĩa
UPDATE documents SET updated_at = COALESCE(finished_at, created_at) WHERE updated_at IS NULL;
UPDATE documents SET needs_review = FALSE WHERE needs_review IS NULL;

ALTER TABLE documents ALTER COLUMN updated_at   SET DEFAULT NOW();
ALTER TABLE documents ALTER COLUMN updated_at   SET NOT NULL;
ALTER TABLE documents ALTER COLUMN needs_review SET DEFAULT FALSE;
ALTER TABLE documents ALTER COLUMN needs_review SET NOT NULL;

DROP TRIGGER IF EXISTS trg_documents_touch ON documents;
CREATE TRIGGER trg_documents_touch BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- ---------------------------------------------------------------------
-- 3. Trạng thái 'deleted' cho xóa mềm (chuẩn HPU: KHÔNG hard delete)
--    Phải seed TRƯỚC khi code mới chạy, vì documents.status có khóa ngoại tới job_statuses.
-- ---------------------------------------------------------------------
INSERT INTO job_statuses (code, label, progress_value, is_terminal, color, sort_order) VALUES
    ('deleted', 'Đã xóa', 0, TRUE, '#9ca3af', 8)
ON CONFLICT (code) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_documents_not_deleted  ON documents(created_at DESC)
    WHERE status <> 'deleted';
CREATE INDEX IF NOT EXISTS idx_documents_needs_review ON documents(needs_review)
    WHERE needs_review;

-- ---------------------------------------------------------------------
-- 4. metadata_fields: điểm tin cậy (YC-CF-01) + dấu thời gian
-- ---------------------------------------------------------------------
ALTER TABLE metadata_fields ADD COLUMN IF NOT EXISTS confidence NUMERIC(4,3);
ALTER TABLE metadata_fields ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;
ALTER TABLE metadata_fields ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

UPDATE metadata_fields SET created_at = NOW() WHERE created_at IS NULL;
UPDATE metadata_fields SET updated_at = NOW() WHERE updated_at IS NULL;

ALTER TABLE metadata_fields ALTER COLUMN created_at SET DEFAULT NOW();
ALTER TABLE metadata_fields ALTER COLUMN created_at SET NOT NULL;
ALTER TABLE metadata_fields ALTER COLUMN updated_at SET DEFAULT NOW();
ALTER TABLE metadata_fields ALTER COLUMN updated_at SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_metadata_confidence') THEN
        ALTER TABLE metadata_fields ADD CONSTRAINT ck_metadata_confidence
            CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_metadata_low_conf ON metadata_fields(document_id)
    WHERE confidence IS NOT NULL AND confidence < 0.5;

DROP TRIGGER IF EXISTS trg_metadata_touch ON metadata_fields;
CREATE TRIGGER trg_metadata_touch BEFORE UPDATE ON metadata_fields
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- ---------------------------------------------------------------------
-- 5. model_calls: nhật ký gọi model bền vững (YC-MP-06) + tài nguyên (YC-MS-07)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_calls (
    id            BIGSERIAL PRIMARY KEY,
    document_id   TEXT,
    provider      VARCHAR(50)  NOT NULL,
    deployment    VARCHAR(20)  NOT NULL,
    model         VARCHAR(150),
    model_version VARCHAR(100),
    schema_code   VARCHAR(50),
    used_ai       BOOLEAN      NOT NULL DEFAULT TRUE,
    attempts      INTEGER      NOT NULL DEFAULT 1,
    latency_ms    INTEGER,
    rss_mb        NUMERIC(10,1),
    gpu_mem_mb    NUMERIC(10,1),
    n_fields      INTEGER      NOT NULL DEFAULT 0,
    fallback_from VARCHAR(50),
    error         TEXT,
    status        VARCHAR(20)  NOT NULL DEFAULT 'success',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_calls_document ON model_calls(document_id);
CREATE INDEX IF NOT EXISTS idx_model_calls_created  ON model_calls(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_calls_provider ON model_calls(provider, deployment);

DROP TRIGGER IF EXISTS trg_model_calls_touch ON model_calls;
CREATE TRIGGER trg_model_calls_touch BEFORE UPDATE ON model_calls
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

COMMIT;

-- Kiểm tra sau khi chạy:
--   SELECT column_name FROM information_schema.columns
--    WHERE table_name='documents' AND column_name IN ('updated_at','needs_review');
--   SELECT code FROM job_statuses WHERE code='deleted';
--   \d model_calls
