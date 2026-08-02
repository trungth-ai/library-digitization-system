-- =====================================================================
-- Migration 008 — Quy trình duyệt tài liệu (YC-RV, sprint V8)
-- ---------------------------------------------------------------------
-- VÌ SAO: `documents.needs_review` cho biết tài liệu CẦN xem lại, nhưng không có chỗ nào ghi tài
-- liệu ĐÃ ĐƯỢC DUYỆT hay chưa. Hệ quả: không phân biệt được "chưa ai xem" với "đã xem và đồng ý",
-- nên không chốt được điều kiện "chưa duyệt thì không đẩy DSpace" (YC-RV-04) — hiện thực hóa nguyên
-- tắc SRS "con người giữ quyền quyết định, không tự ghi vào hệ đích khi chưa có cán bộ xác nhận".
--
-- `audit_log` đã ghi action='confirm' nhưng đó là nhật ký bất biến, không truy vấn nhanh được cho
-- danh sách "tài liệu nào chưa duyệt". Hai cột dưới đây là trạng thái hiện tại, audit vẫn là lịch sử.
--
-- AN TOÀN: chỉ ADD COLUMN. Chạy nhiều lần không lỗi. ⚠️ `pg_dump` trước khi chạy.
-- =====================================================================

SET client_encoding = 'UTF8';

ALTER TABLE documents
    -- NULL = chưa được cán bộ nào xác nhận. Không dùng BOOLEAN mặc định FALSE vì ta cần biết AI
    -- xác nhận LÚC NÀO và BỞI AI để trả lời khi có tranh chấp về một tài liệu cụ thể.
    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS confirmed_by VARCHAR(150);

-- Truy vấn phổ biến nhất của trang duyệt: "tài liệu nào đã xử lý xong mà chưa ai xác nhận"
CREATE INDEX IF NOT EXISTS idx_documents_unconfirmed ON documents(updated_at ASC)
    WHERE confirmed_at IS NULL AND status = 'completed';

-- =====================================================================
-- GHI CHÚ VỀ DỮ LIỆU CŨ
-- ---------------------------------------------------------------------
-- Tài liệu đã xử lý TRƯỚC migration này có `confirmed_at IS NULL` — tức là "chưa duyệt".
--
-- Điều đó ĐÚNG về mặt dữ liệu (chưa ai bấm xác nhận qua quy trình mới), nhưng nếu bật ngay chốt
-- "chưa duyệt thì không đẩy DSpace" thì toàn bộ tài liệu cũ sẽ bị chặn. Vì vậy chốt đó mặc định TẮT
-- (`REQUIRE_CONFIRM_BEFORE_DSPACE=0`) và chỉ nên bật sau khi Trung tâm đã xử lý xong tồn đọng cũ.
--
-- KHÔNG tự động đánh dấu tài liệu cũ là "đã duyệt": đó là bịa ra một sự kiện chưa từng xảy ra, và
-- nó sẽ nằm vĩnh viễn trong dữ liệu với tên một cán bộ không hề bấm nút nào.
-- =====================================================================
