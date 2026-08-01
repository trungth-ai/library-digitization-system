-- =====================================================================
-- Migration 003 — Danh tính & phân quyền (ADR-012, vá lỗ hổng N-01)
-- ---------------------------------------------------------------------
-- VÌ SAO: backend hiện KHÔNG có cơ chế xác thực nào; `audit_log.actor` là query param mặc định 'api'
-- nên YC-AU-02 ("ghi rõ ai thực hiện") không thỏa mãn được, và YC-DR-04 ("chỉ quản trị viên đổi được
-- độ nhạy cảm") không thể hiện thực.
--
-- AN TOÀN: chỉ CREATE TABLE + INSERT seed. KHÔNG DROP, KHÔNG ALTER cột cũ, KHÔNG đổi tên.
-- Chạy được NHIỀU LẦN không lỗi (mọi lệnh đều IF NOT EXISTS / ON CONFLICT DO NOTHING).
-- Bảng mới KHÔNG ảnh hưởng đường đang chạy: khi `AUTH_MODE=off` hệ thống hành xử y như trước.
--
-- ⚠️ BẮT BUỘC `pg_dump` trước khi chạy trên dữ liệu thật.
--
-- Áp dụng:
--   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d library_digitization \
--       < database/migrations/003_users_rbac.sql
-- =====================================================================

SET client_encoding = 'UTF8';

-- =====================================================================
-- 1. NGƯỜI DÙNG
--    Xóa MỀM (chuẩn HPU + YC-QT-08): `audit_log` tham chiếu tới người dùng nên xóa cứng sẽ làm mất
--    khả năng truy trách nhiệm của những thao tác đã ghi.
-- =====================================================================
CREATE TABLE IF NOT EXISTS users (
    id                  BIGSERIAL PRIMARY KEY,
    username            VARCHAR(100) NOT NULL UNIQUE,
    email               VARCHAR(200),
    full_name           VARCHAR(200) NOT NULL,
    -- Mật khẩu BĂM, dạng tự mô tả `pbkdf2_sha256$<vòng>$<salt>$<hash>` (xem scripts/core/passwords.py).
    -- Dạng tự mô tả cho phép nâng số vòng lặp / đổi thuật toán về sau mà không đặt lại mật khẩu hàng loạt.
    password_hash       TEXT         NOT NULL,
    role                VARCHAR(50)  NOT NULL DEFAULT 'viewer',
    -- Buộc đổi mật khẩu ở lần đăng nhập đầu (YC-QT-05) — dùng cho tài khoản khởi tạo và tài khoản
    -- vừa được quản trị viên đặt lại mật khẩu
    must_change_password BOOLEAN     NOT NULL DEFAULT FALSE,
    -- Khóa sau N lần sai (YC-QT-06). `locked_until` NULL = không bị khóa.
    failed_attempts     INTEGER      NOT NULL DEFAULT 0,
    locked_until        TIMESTAMPTZ,
    last_login_at       TIMESTAMPTZ,
    last_login_ip       VARCHAR(64),
    -- Chuẩn HPU: mọi bảng có status; 'active' | 'disabled' | 'deleted' (xóa mềm)
    status              VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    created_by          BIGINT,
    CONSTRAINT ck_users_status CHECK (status IN ('active', 'disabled', 'deleted'))
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_active   ON users(username) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_users_role     ON users(role);

-- Trigger updated_at đã có từ init.sql (hàm touch_updated_at). Tạo lại cho bảng mới.
DROP TRIGGER IF EXISTS trg_users_touch ON users;
CREATE TRIGGER trg_users_touch BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- =====================================================================
-- 2. VAI TRÒ & QUYỀN — quyền là DỮ LIỆU, không phải hằng số trong mã (YC-QT-09)
--    Cùng triết lý với `extraction_schemas` (YC-SC-01): quản trị viên đổi được mà không cần lập trình.
-- =====================================================================
CREATE TABLE IF NOT EXISTS roles (
    code        VARCHAR(50)  PRIMARY KEY,
    label       VARCHAR(150) NOT NULL,
    description TEXT,
    -- Vai trò hệ thống không cho xóa/đổi tên (tránh tự khóa mình ra ngoài bằng cách xóa vai trò admin)
    is_system   BOOLEAN      NOT NULL DEFAULT FALSE,
    sort_order  INTEGER      NOT NULL DEFAULT 0,
    status      VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS role_permissions (
    id         BIGSERIAL PRIMARY KEY,
    role_code  VARCHAR(50)  NOT NULL REFERENCES roles(code) ON DELETE CASCADE,
    permission VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_role_permission UNIQUE (role_code, permission)
);

CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions(role_code);

DROP TRIGGER IF EXISTS trg_roles_touch ON roles;
CREATE TRIGGER trg_roles_touch BEFORE UPDATE ON roles
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- =====================================================================
-- 3. PHIÊN ĐĂNG NHẬP — lưu ở PostgreSQL, KHÔNG ở Redis (QĐ-02, ADR-012)
--    Redis trong hệ này là hàng đợi, không bật `appendonly` → Redis restart là đăng xuất toàn bộ.
--    Số phiên rất nhỏ (một Trung tâm) nên PostgreSQL thừa sức, và cho phép THU HỒI phiên ngay lập tức.
-- =====================================================================
CREATE TABLE IF NOT EXISTS user_sessions (
    -- Băm SHA-256 của token, KHÔNG lưu token thô: rò cơ sở dữ liệu không đồng nghĩa với chiếm được phiên
    token_hash  CHAR(64)     PRIMARY KEY,
    user_id     BIGINT       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ip          VARCHAR(64),
    user_agent  TEXT,
    expires_at  TIMESTAMPTZ  NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at  TIMESTAMPTZ,
    status      VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user    ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON user_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_sessions_active  ON user_sessions(user_id)
    WHERE status = 'active';

DROP TRIGGER IF EXISTS trg_sessions_touch ON user_sessions;
CREATE TRIGGER trg_sessions_touch BEFORE UPDATE ON user_sessions
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- =====================================================================
-- 4. SEED VAI TRÒ & QUYỀN
--    Phải khớp `scripts/auth/policy.py` — bản trong mã dùng để seed và để còn chạy được khi bảng
--    chưa di trú; bản trong DB là nguồn chân lý lúc chạy.
-- =====================================================================
INSERT INTO roles (code, label, description, is_system, sort_order) VALUES
    ('admin',     'Quản trị hệ thống', 'Toàn quyền: quản lý người dùng, cấu hình, độ nhạy cảm lược đồ', TRUE, 1),
    ('approver',  'Cán bộ duyệt',      'Duyệt tài liệu và đẩy lên DSpace, kể cả tài liệu do mình tải lên', TRUE, 2),
    ('librarian', 'Cán bộ nghiệp vụ',  'Tải lên, sửa metadata, gửi duyệt',                              TRUE, 3),
    ('viewer',    'Người xem',         'Chỉ xem tài liệu và báo cáo',                                   TRUE, 4),
    ('service',   'Tài khoản dịch vụ', 'Dùng cho tích hợp qua API key; không có quyền mặc định nào',     TRUE, 5)
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_code, permission) VALUES
    -- viewer
    ('viewer',    'document:read'),
    ('viewer',    'report:read'),
    -- librarian = viewer + nghiệp vụ số hóa
    ('librarian', 'document:read'),
    ('librarian', 'report:read'),
    ('librarian', 'document:upload'),
    ('librarian', 'document:edit'),
    ('librarian', 'document:download'),
    ('librarian', 'schema:read'),
    -- approver = librarian + duyệt/đẩy DSpace/quản lý hàng đợi
    ('approver',  'document:read'),
    ('approver',  'report:read'),
    ('approver',  'document:upload'),
    ('approver',  'document:edit'),
    ('approver',  'document:download'),
    ('approver',  'schema:read'),
    ('approver',  'document:approve'),
    ('approver',  'document:delete'),
    ('approver',  'dspace:push'),
    ('approver',  'queue:manage'),
    ('approver',  'audit:read'),
    -- admin = tất cả
    ('admin',     'document:read'),
    ('admin',     'report:read'),
    ('admin',     'document:upload'),
    ('admin',     'document:edit'),
    ('admin',     'document:download'),
    ('admin',     'document:approve'),
    ('admin',     'document:delete'),
    ('admin',     'document:purge'),
    ('admin',     'dspace:push'),
    ('admin',     'schema:read'),
    ('admin',     'schema:write'),
    ('admin',     'schema:sensitivity'),
    ('admin',     'audit:read'),
    ('admin',     'log:read'),
    ('admin',     'queue:manage'),
    ('admin',     'user:manage'),
    ('admin',     'system:config')
ON CONFLICT (role_code, permission) DO NOTHING;

-- =====================================================================
-- 5. KHÓA NGOẠI TỪ users → roles
--    Thêm SAU khi đã seed roles, nếu không thì `users.role` mặc định 'viewer' sẽ vi phạm ràng buộc.
--    Bọc trong DO để chạy lại lần hai không lỗi "constraint already exists".
-- =====================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_users_role'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT fk_users_role FOREIGN KEY (role) REFERENCES roles(code);
    END IF;
END $$;

-- =====================================================================
-- 6. GHI CHÚ VẬN HÀNH
-- ---------------------------------------------------------------------
-- Sau migration, hệ thống VẪN chạy như cũ vì `AUTH_MODE=off` là mặc định.
-- Quy trình bật (ADR-012 mục 2) — KHÔNG rút gọn:
--   Nấc 1  AUTH_MODE=off      tạo tài khoản, tập huấn cán bộ
--   Nấc 2  AUTH_MODE=shadow   chạy ≥ 1 TUẦN, đọc cảnh báo, sửa hết chỗ còn sót
--                             điều kiện sang nấc 3: 0 cảnh báo trong 48 giờ liên tiếp
--   Nấc 3  AUTH_MODE=on       chặn thật (lùi lại `shadow` bất cứ lúc nào, không cần build lại)
--
-- Tạo quản trị viên đầu tiên: đặt ADMIN_BOOTSTRAP_USER + ADMIN_BOOTSTRAP_PASSWORD rồi khởi động API.
-- Mất mật khẩu quản trị:  docker compose exec api python -m scripts.auth.cli reset-password <user>
-- =====================================================================
