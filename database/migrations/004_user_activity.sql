-- =====================================================================
-- Migration 004 — Nhật ký người dùng (YC-NK, sprint V4)
-- ---------------------------------------------------------------------
-- VÌ SAO TÁCH KHỎI `audit_log`: audit ghi thao tác NGHIỆP VỤ trên TÀI LIỆU (tải lên, sửa trường,
-- duyệt, đẩy DSpace) và phải giữ vĩnh viễn. Bảng này ghi HÀNH VI NGƯỜI DÙNG, phần lớn không gắn với
-- tài liệu nào: đăng nhập, đăng xuất, sai mật khẩu, BỊ TỪ CHỐI QUYỀN, tìm kiếm, kết xuất báo cáo.
--
-- Trộn hai loại vào một bảng sẽ làm nhật ký kiểm toán ngập những lần đăng nhập thường ngày, và buộc
-- phải giữ vĩnh viễn cả dữ liệu chỉ có giá trị điều tra trong vòng một năm.
--
-- Đây là lớp thứ BA trong bốn lớp nhật ký (xem docs/UPGRADE_REQUIREMENTS.md mục 2.1):
--   audit_log      nghiệp vụ, bất biến, vĩnh viễn
--   user_activity  hành vi người dùng, bất biến, 365 ngày   ← bảng này
--   system_events  sự cố hạ tầng, xóa được, 90 ngày
--   tệp JSONL      chi tiết kỹ thuật, 14 ngày
--
-- AN TOÀN: chỉ CREATE. Chạy nhiều lần không lỗi.
-- =====================================================================

SET client_encoding = 'UTF8';

CREATE TABLE IF NOT EXISTS user_activity (
    id            BIGSERIAL PRIMARY KEY,
    -- Giữ CẢ user_id lẫn username: user_id để nối bảng, username để nhật ký còn đọc được nguyên vẹn
    -- kể cả sau khi tài khoản bị xóa mềm. Nhật ký mà phải nối bảng mới biết là ai thì mất giá trị
    -- ngay khi người đó rời cơ quan.
    user_id       BIGINT,
    username      VARCHAR(100),
    action        VARCHAR(50)  NOT NULL,   -- login|logout|login_failed|permission_denied|view|export|...
    resource_type VARCHAR(50),             -- document|report|user|session|...
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
-- Bị từ chối quyền là tín hiệu an ninh quan trọng nhất trong bảng này → index riêng để tra nhanh
CREATE INDEX IF NOT EXISTS idx_user_activity_denied  ON user_activity(created_at DESC)
    WHERE result <> 'ok';

-- BẤT BIẾN (YC-NK-01): dùng lại đúng hàm chặn của `audit_log` trong init.sql. Nhật ký hành vi mà
-- sửa/xóa được thì vô giá trị đúng lúc cần nhất — khi phải chứng minh ai đã làm gì.
DROP TRIGGER IF EXISTS trg_user_activity_no_update ON user_activity;
CREATE TRIGGER trg_user_activity_no_update BEFORE UPDATE ON user_activity
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();

-- ⚠️ KHÔNG chặn DELETE ở bảng này (khác `audit_log`): thời hạn lưu là 365 ngày và việc dọn theo
-- tuổi (YC-LG-07) cần xóa được bản ghi quá hạn. Chặn UPDATE là đủ để bảo đảm bản ghi không bị SỬA;
-- việc xóa chỉ xảy ra qua `scripts/core/retention.py`, có ghi nhận số lượng vào `system_events`.

DROP TRIGGER IF EXISTS trg_user_activity_touch ON user_activity;
CREATE TRIGGER trg_user_activity_touch BEFORE UPDATE ON user_activity
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
