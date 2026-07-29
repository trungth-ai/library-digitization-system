-- =====================================================================
-- Migration 002 — Theo dõi vận hành: thời gian xử lý + sự kiện hệ thống
-- Ngày: 29/07/2026 · Liên quan: ADR-009
-- ---------------------------------------------------------------------
-- CÁCH CHẠY (bắt buộc nếu volume postgres_data đã tồn tại — init.sql không chạy lại):
--   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d library_digitization \
--       < database/migrations/002_monitoring.sql
--
-- Idempotent: chạy lại nhiều lần không sao. Không xóa dữ liệu.
-- Yêu cầu: đã chạy migration 001 (cần hàm touch_updated_at).
-- =====================================================================

BEGIN;

-- Bảo đảm có hàm dùng chung, kể cả khi 001 chưa chạy
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 1. documents: thời gian xử lý thực (không tính thời gian nằm chờ hàng đợi)
-- ---------------------------------------------------------------------
ALTER TABLE documents ADD COLUMN IF NOT EXISTS duration_ms   INTEGER;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS stage_timings JSONB;

-- ---------------------------------------------------------------------
-- 2. system_events: lỗi & trạng thái kết nối của hạ tầng
--    Tách khỏi audit_log: audit là nhật ký nghiệp vụ bất biến, không nên bị nhiễu bởi sự cố kỹ thuật.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_events (
    id          BIGSERIAL PRIMARY KEY,
    source      VARCHAR(50)  NOT NULL,
    instance    VARCHAR(150),
    kind        VARCHAR(50)  NOT NULL,
    level       VARCHAR(20)  NOT NULL DEFAULT 'error',
    message     TEXT         NOT NULL,
    detail      TEXT,
    document_id TEXT,
    status      VARCHAR(20)  NOT NULL DEFAULT 'new',
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

COMMIT;

-- Kiểm tra sau khi chạy:
--   SELECT column_name FROM information_schema.columns
--    WHERE table_name='documents' AND column_name IN ('duration_ms','stage_timings');
--   \d system_events
