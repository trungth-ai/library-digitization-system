-- =====================================================================
-- Migration 005 — Phân tích chi tiết kết quả AI (YC-AN, sprint V2)
-- ---------------------------------------------------------------------
-- VÌ SAO: `model_calls` hiện chỉ đếm `n_fields` — biết model trả về BAO NHIÊU trường, không biết
-- trả về CÁI GÌ. Nên không trả lời được ba câu hỏi quan trọng nhất về lớp AI:
--   • "Claude đúng bao nhiêu % trên trường dc.title, trên bao nhiêu mẫu?"
--   • "Tháng này tốn bao nhiêu tiền API?"
--   • "Tài liệu nào scan xấu tới mức nên quét lại?"
--
-- ĐIỂM CỐT LÕI (YC-AN-05): hệ đang chạy thật đã có sẵn một nguồn ĐÁP ÁN CHUẨN liên tục — giá trị
-- cuối cùng mà cán bộ duyệt. Nếu AI trả "Bao cao tong ket" và cán bộ sửa thành "Báo cáo tổng kết"
-- thì đó là một điểm dữ liệu về độ chính xác: miễn phí, có thật, tích lũy mỗi ngày. Bảng
-- `model_call_fields` lưu đúng thứ cần để so sánh đó thành số liệu.
--
-- ⚠️ Số liệu này là CHỈ BÁO XU HƯỚNG, không thay thế đối chiếu đáp án chuẩn BD-01: cán bộ cũng có
-- thể bỏ sót. Giao diện BẮT BUỘC ghi rõ phương pháp và cỡ mẫu (xem scripts/core/analytics.py).
--
-- AN TOÀN: chỉ ADD COLUMN / CREATE TABLE. KHÔNG DROP, KHÔNG đổi kiểu, KHÔNG đổi tên.
-- Chạy được nhiều lần không lỗi. ⚠️ `pg_dump` trước khi chạy trên dữ liệu thật.
-- =====================================================================

SET client_encoding = 'UTF8';

-- =====================================================================
-- 1. MỞ RỘNG model_calls
-- =====================================================================
ALTER TABLE model_calls
    ADD COLUMN IF NOT EXISTS prompt_tokens     INTEGER,
    ADD COLUMN IF NOT EXISTS completion_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS total_tokens      INTEGER,
    -- Chi phí lưu hai đơn vị, CẢ HAI đều là SỐ NGUYÊN (chuẩn HPU: tiền không dùng dấu phẩy động).
    -- micro-USD giữ độ chính xác của đơn giá gốc; VNĐ là thứ người dùng đọc.
    ADD COLUMN IF NOT EXISTS cost_micro_usd    BIGINT,
    ADD COLUMN IF NOT EXISTS cost_vnd          BIGINT,
    ADD COLUMN IF NOT EXISTS prompt_version    VARCHAR(50),
    -- Băm prompt thay vì lưu prompt: đủ để biết "hai lần gọi này dùng cùng một prompt hay không"
    -- mà không lưu nội dung tài liệu vào bảng nhật ký (AI_LOG_RAW mới là thứ lưu nội dung, mặc định TẮT)
    ADD COLUMN IF NOT EXISTS prompt_hash       CHAR(64),
    ADD COLUMN IF NOT EXISTS context_chars     INTEGER,
    ADD COLUMN IF NOT EXISTS context_pages     INTEGER,
    ADD COLUMN IF NOT EXISTS retry_reason      TEXT,
    ADD COLUMN IF NOT EXISTS confidence_avg    NUMERIC(4,3),
    ADD COLUMN IF NOT EXISTS confidence_min    NUMERIC(4,3),
    -- Tỉ lệ trường tìm thấy trong văn bản gốc (YC-CF-05) — chỉ báo ảo giác ở mức LƯỢT GỌI
    ADD COLUMN IF NOT EXISTS grounded_ratio    NUMERIC(4,3),
    -- Nối với tệp log JSONL (YC-LG-02): từ một lượt gọi model tra ngược ra toàn bộ log của request
    ADD COLUMN IF NOT EXISTS request_id        VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_model_calls_schema ON model_calls(schema_code, created_at DESC);

-- =====================================================================
-- 2. KẾT QUẢ TỪNG TRƯỜNG (YC-AN-02)
--    Một dòng cho mỗi trường mà model trả về, trong mỗi lượt gọi.
-- =====================================================================
CREATE TABLE IF NOT EXISTS model_call_fields (
    id            BIGSERIAL PRIMARY KEY,
    model_call_id BIGINT       REFERENCES model_calls(id) ON DELETE CASCADE,
    document_id   TEXT,
    field_key     VARCHAR(100) NOT NULL,
    -- CẮT NGẮN, không lưu toàn văn: đủ để đối chiếu với giá trị cán bộ đã duyệt, mà không biến bảng
    -- nhật ký thành bản sao thứ hai của nội dung tài liệu.
    value_preview TEXT,
    confidence    NUMERIC(4,3),
    grounded      BOOLEAN,       -- giá trị có xuất hiện trong văn bản gốc không (YC-CF-05)
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

-- =====================================================================
-- 3. CHỈ SỐ OCR (YC-AN-03)
--    `pages_without_text` là chỉ báo scan xấu: OCR chạy xong nhưng không tạo được lớp text cho
--    trang đó, nghĩa là ảnh quá mờ/lệch. Biết sớm thì đề nghị quét lại, thay vì để tài liệu đi
--    tiếp vào DSpace với nội dung không tra cứu được.
-- =====================================================================
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
-- Truy vấn hay dùng nhất: "tài liệu nào scan xấu cần quét lại"
CREATE INDEX IF NOT EXISTS idx_ocr_runs_bad      ON ocr_runs(created_at DESC)
    WHERE pages_without_text > 0;

DROP TRIGGER IF EXISTS trg_ocr_runs_touch ON ocr_runs;
CREATE TRIGGER trg_ocr_runs_touch BEFORE UPDATE ON ocr_runs
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
