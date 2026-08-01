#!/usr/bin/env python3
"""
Kiểm thử mô hình quyền, ba nấc AUTH_MODE, băm mật khẩu (ADR-012) — KT-QT-01/02/06/09/13→16.

Chỉ chạm module THUẦN (`scripts/auth/policy.py`, `scripts/core/passwords.py`) nên không cần
fastapi/psycopg2. Phần cần fastapi được kiểm bằng `tests/test_auth_coverage.py` (phân tích mã nguồn).
"""

import pytest

from scripts.auth import policy
from scripts.core import passwords


# ─────────────────────────────────────────────────────────────
# BĂM MẬT KHẨU — KT-QT-01
# ─────────────────────────────────────────────────────────────

def test_bam_roi_kiem_lai_dung():
    h = passwords.hash_password("MatKhauRatDai2026", iterations=1000)
    assert passwords.verify_password("MatKhauRatDai2026", h) is True


def test_sai_mat_khau_thi_tu_choi():
    h = passwords.hash_password("MatKhauRatDai2026", iterations=1000)
    assert passwords.verify_password("MatKhauRatDai2027", h) is False


def test_khong_luu_mat_khau_tho():
    """Chuỗi băm KHÔNG được chứa mật khẩu gốc ở bất kỳ dạng nào."""
    h = passwords.hash_password("MatKhauRatDai2026", iterations=1000)
    assert "MatKhauRatDai2026" not in h
    assert h.startswith("pbkdf2_sha256$")


def test_moi_lan_bam_ra_khac_nhau():
    """Salt ngẫu nhiên: hai người dùng cùng mật khẩu phải có hai bản băm khác nhau."""
    a = passwords.hash_password("MatKhauRatDai2026", iterations=1000)
    b = passwords.hash_password("MatKhauRatDai2026", iterations=1000)
    assert a != b
    assert passwords.verify_password("MatKhauRatDai2026", a)
    assert passwords.verify_password("MatKhauRatDai2026", b)


def test_mat_khau_tieng_viet_chuan_hoa_unicode():
    """
    Mật khẩu tiếng Việt gõ ở dạng tổ hợp khác nhau (NFC vs NFD) phải cho cùng kết quả.

    Không chuẩn hóa thì cùng một mật khẩu gõ trên hai máy sẽ ra hai chuỗi byte khác nhau, và người
    dùng nhận được thông báo "sai mật khẩu" — cực khó lần ra nguyên nhân.
    """
    import unicodedata
    nfc = unicodedata.normalize("NFC", "MậtKhẩuTiếngViệt2026")
    nfd = unicodedata.normalize("NFD", "MậtKhẩuTiếngViệt2026")
    assert nfc != nfd, "hai dạng phải khác nhau ở mức byte, nếu không thì test này vô nghĩa"

    h = passwords.hash_password(nfc, iterations=1000)
    assert passwords.verify_password(nfd, h) is True


@pytest.mark.parametrize("stored", [
    "", None, "khong-dung-dinh-dang", "pbkdf2_sha256$abc$def$ghi",
    "argon2id$1$salt$hash", "pbkdf2_sha256$1000$zzzz$zzzz",
])
def test_ban_bam_hong_tra_false_khong_nem_loi(stored):
    """
    Bản băm hỏng phải dẫn tới "đăng nhập thất bại", KHÔNG dẫn tới lỗi 500.

    Lỗi 500 ở đường đăng nhập là một kênh rò thông tin về nội bộ hệ thống.
    """
    assert passwords.verify_password("bat-ky", stored) is False


def test_nang_cap_ban_bam_khi_tang_so_vong():
    """Nâng số vòng lặp phải nhận ra bản băm cũ để nâng cấp dần khi người dùng đăng nhập."""
    cu = passwords.hash_password("MatKhauRatDai2026", iterations=1000)
    assert passwords.needs_rehash(cu, iterations=600000) is True
    assert passwords.needs_rehash(cu, iterations=1000) is False


# ─────────────────────────────────────────────────────────────
# CHÍNH SÁCH MẬT KHẨU — KT-QT-06
# ─────────────────────────────────────────────────────────────

def test_mat_khau_dat_chinh_sach():
    assert passwords.check_policy("ThuVienHaiPhong2026").ok is True


@pytest.mark.parametrize("pw,ly_do", [
    ("abc", "quá ngắn"),
    ("123456", "phổ biến"),
    ("password", "phổ biến"),
    ("matkhau123", "phổ biến"),
    ("1234567890123", "chỉ toàn số"),
    ("aaaaaaaaaaaa", "một ký tự lặp lại"),
    ("abcdefghijkl", "dãy liên tiếp"),
])
def test_mat_khau_yeu_bi_tu_choi(pw, ly_do):
    result = passwords.check_policy(pw)
    assert result.ok is False, f"lẽ ra phải từ chối ({ly_do}): {pw}"
    assert result.errors, "phải có thông báo lỗi tiếng Việt cho người dùng"


def test_khong_cho_dung_ten_dang_nhap_lam_mat_khau():
    result = passwords.check_policy("nguyenvanan2026", username="nguyenvanan")
    assert result.ok is False


def test_khong_cho_dung_ten_that_lam_mat_khau():
    result = passwords.check_policy("nguyenvanan-abc", full_name="Nguyễn Văn An")
    assert result.ok is False


def test_tra_ve_MOI_loi_cung_luc():
    """
    Trả về tất cả lỗi, không chỉ lỗi đầu tiên.

    Người dùng sửa một lần cho xong; mỗi vòng thử lại là một lần họ có xu hướng chọn mật khẩu yếu hơn.
    """
    result = passwords.check_policy("123")
    assert len(result.errors) >= 2


def test_mat_khau_sinh_tu_dong_luon_dat_chinh_sach():
    """Mật khẩu tạm do hệ thống sinh không bao giờ được rơi vào ca bị chính sách từ chối."""
    for _ in range(20):
        pw = passwords.generate_password()
        assert passwords.check_policy(pw).ok is True


def test_mat_khau_sinh_tu_dong_khong_co_ky_tu_de_nham():
    """Mật khẩu tạm thường được ĐỌC hoặc CHÉP TAY cho người dùng — nhầm một ký tự là một lượt hỗ trợ nữa."""
    pw = passwords.generate_password(40)
    for ky_tu in "0O1lI":
        assert ky_tu not in pw


# ─────────────────────────────────────────────────────────────
# MÔ HÌNH QUYỀN
# ─────────────────────────────────────────────────────────────

def test_admin_co_moi_quyen():
    assert policy.permissions_for_role(policy.ROLE_ADMIN) == policy.ALL_PERMISSIONS


def test_viewer_khong_co_quyen_ghi_nao():
    """`viewer` chỉ đọc: không được có bất kỳ quyền ghi nào."""
    perms = policy.permissions_for_role(policy.ROLE_VIEWER)
    quyen_ghi = {
        policy.DOCUMENT_UPLOAD, policy.DOCUMENT_EDIT, policy.DOCUMENT_APPROVE,
        policy.DOCUMENT_DELETE, policy.DOCUMENT_PURGE, policy.DSPACE_PUSH,
        policy.SCHEMA_WRITE, policy.SCHEMA_SENSITIVITY, policy.USER_MANAGE,
        policy.SYSTEM_CONFIG, policy.QUEUE_MANAGE,
    }
    assert perms & quyen_ghi == set()


def test_librarian_khong_duyet_khong_day_dspace():
    """Cán bộ nghiệp vụ tải lên và sửa được, nhưng không tự duyệt và không đẩy DSpace."""
    perms = policy.permissions_for_role(policy.ROLE_LIBRARIAN)
    assert policy.DOCUMENT_UPLOAD in perms
    assert policy.DOCUMENT_EDIT in perms
    assert policy.DOCUMENT_APPROVE not in perms
    assert policy.DSPACE_PUSH not in perms


def test_approver_duyet_duoc_ke_ca_tai_lieu_cua_minh():
    """
    QĐ-05 (ADR-012): quyền duyệt do PHÂN QUYỀN quyết định, không do quan hệ sở hữu.

    `approver` có cả `document:upload` và `document:approve` — nghĩa là tải lên rồi tự duyệt được.
    Đây là hành vi ĐÚNG theo quyết định của Trung tâm, không phải lỗ hổng.
    """
    perms = policy.permissions_for_role(policy.ROLE_APPROVER)
    assert policy.DOCUMENT_UPLOAD in perms
    assert policy.DOCUMENT_APPROVE in perms


def test_chi_admin_duoc_xoa_vinh_vien_va_doi_do_nhay_cam():
    """
    `document:purge` không phục hồi được; `schema:sensitivity` là YC-DR-04 (ràng buộc bảo mật cốt lõi).
    Cả hai chỉ `admin` được có.
    """
    for perm in (policy.DOCUMENT_PURGE, policy.SCHEMA_SENSITIVITY, policy.USER_MANAGE):
        co_quyen = [r for r in policy.ALL_ROLES if perm in policy.permissions_for_role(r)]
        assert co_quyen == [policy.ROLE_ADMIN], f"{perm} phải chỉ admin có, hiện: {co_quyen}"


def test_tai_khoan_dich_vu_khong_co_quyen_mac_dinh():
    """Một tài khoản tự động có quyền rộng là rủi ro khó phát hiện — mặc định phải rỗng (YC-TK-02)."""
    assert policy.permissions_for_role(policy.ROLE_SERVICE) == frozenset()


def test_vai_tro_la_khong_co_quyen_nao():
    """Mặc định AN TOÀN: vai trò không nhận ra thì không có quyền, không phải có tất cả."""
    assert policy.permissions_for_role("khong-ton-tai") == frozenset()


def test_khong_ho_tro_ky_tu_thay_the():
    """
    `document:*` KHÔNG được coi là có `document:read`.

    Một dấu `*` đặt sai chỗ trong cấu hình sẽ mở quyền mà không ai nhận ra khi đọc bảng phân quyền.
    """
    assert policy.has_permission({"document:*"}, policy.DOCUMENT_READ) is False


def test_moi_quyen_deu_co_nhan_tieng_viet():
    """Người cấp quyền không phải lập trình viên — mọi quyền phải có nhãn đọc được."""
    thieu = policy.ALL_PERMISSIONS - set(policy.PERMISSION_LABELS)
    assert thieu == set(), f"thiếu nhãn tiếng Việt cho: {thieu}"


def test_moi_vai_tro_deu_co_nhan_tieng_viet():
    thieu = set(policy.ALL_ROLES) - set(policy.ROLE_LABELS)
    assert thieu == set(), f"thiếu nhãn tiếng Việt cho vai trò: {thieu}"


def test_quyen_cua_vai_tro_nam_trong_danh_sach_quyen():
    """Chống lỗi chính tả: mọi quyền gán cho vai trò phải là quyền có thật."""
    for role in policy.ALL_ROLES:
        la = policy.permissions_for_role(role) - policy.ALL_PERMISSIONS
        assert la == set(), f"vai trò {role} có quyền không tồn tại: {la}"


# ─────────────────────────────────────────────────────────────
# BA NẤC AUTH_MODE — KT-QT-13→16
# ─────────────────────────────────────────────────────────────

def test_mac_dinh_la_off():
    """
    Mặc định `off` để việc CẬP NHẬT MÃ không tự động bật chặn trên hệ đang phục vụ thật.

    Bật là một quyết định vận hành có chủ đích (ADR-012 mục 2), không phải hệ quả của việc deploy.
    """
    assert policy.resolve_auth_mode(None) in policy.AUTH_MODES
    assert policy.resolve_auth_mode("") == policy.AUTH_OFF


@pytest.mark.parametrize("raw,mong_doi", [
    ("off", policy.AUTH_OFF), ("shadow", policy.AUTH_SHADOW), ("on", policy.AUTH_ON),
    ("ON", policy.AUTH_ON), ("  shadow  ", policy.AUTH_SHADOW),
])
def test_doc_dung_nac(raw, mong_doi):
    assert policy.resolve_auth_mode(raw) == mong_doi


def test_gia_tri_la_lui_ve_off_khong_khoa_he_thong():
    """
    Lỗi chính tả trong `.env` (`AUTH_MODE=onn`) phải lùi về `off`, KHÔNG phải `on`.

    Một lỗi chính tả không được làm cả Trung tâm không đăng nhập được vào hệ thống đang phục vụ thật.
    """
    assert policy.resolve_auth_mode("onn") == policy.AUTH_OFF
    assert policy.resolve_auth_mode("true") == policy.AUTH_OFF


def test_chi_nac_on_chan_request():
    assert policy.mode_blocks_requests(policy.AUTH_ON) is True
    assert policy.mode_blocks_requests(policy.AUTH_SHADOW) is False
    assert policy.mode_blocks_requests(policy.AUTH_OFF) is False


def test_chi_nac_shadow_ghi_nhan_thieu_xac_thuc():
    """`off` không ghi (sẽ ngập log); `on` không cần ghi (đã chặn nên không có gì để tìm)."""
    assert policy.mode_records_gaps(policy.AUTH_SHADOW) is True
    assert policy.mode_records_gaps(policy.AUTH_OFF) is False
    assert policy.mode_records_gaps(policy.AUTH_ON) is False


def test_actor_chua_xac_thuc_phan_biet_duoc_voi_nguoi_that():
    """
    Tên chủ thể chưa xác thực phải KHÔNG thể trùng với tên đăng nhập hợp lệ.

    Nếu trùng được thì nhật ký kiểm toán sẽ lẫn "thao tác trước khi bật xác thực" với "thao tác của
    một người thật" — mất khả năng giải trình đúng chỗ cần nhất.
    """
    assert policy.LEGACY_ACTOR == "(chưa xác thực)"
    assert not policy.LEGACY_ACTOR.isidentifier()
