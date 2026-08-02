-- =====================================================================
-- Migration 007 — Lấy mẫu độ sâu hàng đợi (YC-BU-18, YC-DB-06 — sprint V6)
-- ---------------------------------------------------------------------
-- VÌ SAO: `/api/v2/stats` chỉ cho biết độ sâu hàng đợi **ngay lúc này**. Câu hỏi vận hành thật lại
-- là những câu về THỜI GIAN: "giờ nào trong ngày hàng đợi dồn nhất?", "thêm worker có giảm tồn
-- đọng không?", "lô đêm qua chạy hết lúc mấy giờ?". Không có lịch sử thì không trả lời được câu nào.
--
-- Đây cũng là nguồn dữ liệu cho biểu đồ xu hướng của bảng điều khiển (sprint V7) — làm ở đây để V7
-- có sẵn dữ liệu lịch sử khi bắt đầu, thay vì phải chờ tích lũy từ đầu.
--
-- KÍCH THƯỚC: một dòng/phút = 525.600 dòng/năm, mỗi dòng vài chục byte. Nhỏ, nhưng vẫn có thời hạn
-- lưu (dọn qua `scripts/core/retention.py`) vì không có giá trị gì khi quá cũ.
--
-- AN TOÀN: chỉ CREATE. Chạy nhiều lần không lỗi.
-- =====================================================================

SET client_encoding = 'UTF8';

CREATE TABLE IF NOT EXISTS queue_samples (
    id            BIGSERIAL PRIMARY KEY,
    -- Độ sâu từng mức ưu tiên: gộp lại thành một số sẽ che mất tình huống đáng lo nhất — hàng đợi
    -- `high` bị dồn trong khi tổng số trông vẫn bình thường vì `low` đã vơi.
    high          INTEGER NOT NULL DEFAULT 0,
    normal        INTEGER NOT NULL DEFAULT 0,
    low           INTEGER NOT NULL DEFAULT 0,
    delayed       INTEGER NOT NULL DEFAULT 0,   -- đang chờ thử lại
    dead          INTEGER NOT NULL DEFAULT 0,   -- đã hết lượt thử
    processing    INTEGER NOT NULL DEFAULT 0,   -- đang được worker xử lý
    workers_alive INTEGER,                      -- NULL = không đọc được Redis, KHÁC 0 = không có worker
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_queue_samples_created ON queue_samples(created_at DESC);

-- =====================================================================
-- GHI CHÚ: hàng đợi chết vẫn nằm trong Redis (danh sách `digitization_jobs:dead`).
--
-- Không nhân bản nó sang PostgreSQL vì bản ghi CÓ THẨM QUYỀN của một tài liệu thất bại đã nằm ở
-- `documents` (status='failed' + error_message). Danh sách trong Redis chỉ để tiện thao tác "chạy
-- lại"; mất nó khi Redis restart thì tài liệu vẫn truy được và vẫn chạy lại được từ trang tài liệu.
-- Hai nguồn sự thật cho cùng một việc là thứ đắt hơn nhiều so với lợi ích ở đây.
-- =====================================================================
