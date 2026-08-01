#!/usr/bin/env python3
"""
Băm & kiểm mật khẩu + chính sách mật khẩu (YC-QT-01, YC-QT-06 — ADR-012).

QUYẾT ĐỊNH VỀ THUẬT TOÁN (điều chỉnh `QĐ-04`): mặc định **PBKDF2-HMAC-SHA256 của thư viện chuẩn**,
không phải Argon2id. Ba lý do:
  1. `argon2-cffi`/`bcrypt` là phụ thuộc BIÊN DỊCH — cài được trong image nhưng KHÔNG có trên máy dev,
     nghĩa là phần bảo mật quan trọng nhất lại là phần không kiểm thử được tại chỗ.
  2. Hệ thống chạy **air-gapped** (YC-MS-03): mọi phụ thuộc mới đều là một thứ phải tải trước khi
     ngắt mạng, và là một thứ có thể thiếu lúc triển khai.
  3. PBKDF2-SHA256 với số vòng lặp đủ lớn là lựa chọn OWASP còn khuyến nghị. Với hệ nội bộ một Trung
     tâm (vài chục tài khoản, không mở ra Internet), đây là mức phù hợp.

Nhưng KHÔNG khóa cứng vào một thuật toán: chuỗi băm mang theo tên lược đồ (`pbkdf2_sha256$...`) nên
thêm Argon2 về sau chỉ là thêm một lược đồ + nâng cấp dần khi người dùng đăng nhập. Đây cùng một mẫu
"lớp trừu tượng viết trước, chọn công cụ sau" đã dùng cho lớp mô hình (YC-MP).

Module thuần: không import psycopg2/fastapi → kiểm thử được trên máy dev.
"""

import hashlib
import hmac
import os
import re
import secrets
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Số vòng lặp PBKDF2. OWASP 2023 khuyến nghị ≥ 600.000 cho PBKDF2-HMAC-SHA256.
# Cấu hình được để nâng dần theo phần cứng mà không phải sửa mã.
PBKDF2_ITERATIONS = int(os.getenv("PASSWORD_PBKDF2_ITERATIONS", "600000"))
SALT_BYTES = 16
SCHEME_PBKDF2 = "pbkdf2_sha256"

# ── Chính sách mật khẩu (YC-QT-06) ────────────────────────────────────
MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "10"))
# Danh sách mật khẩu phổ biến — cố tình NGẮN và có tiếng Việt: đây là những mật khẩu thật hay gặp
# trong môi trường Nhà trường, không phải danh sách 10.000 mật khẩu tải từ Internet (air-gapped).
COMMON_PASSWORDS = frozenset({
    "123456", "12345678", "123456789", "1234567890", "password", "matkhau",
    "qwerty", "abc123", "111111", "000000", "iloveyou", "admin", "admin123",
    "administrator", "letmein", "welcome", "monkey", "dragon", "sunshine",
    "docuflow", "thuvien", "hpu", "hpu123", "haiphong", "vietnam", "vietnam123",
    "matkhau123", "khongbiet", "capcha", "123123", "abcd1234", "p@ssw0rd",
    "password1", "password123", "qwerty123", "1qaz2wsx", "zaq12wsx",
})


@dataclass
class PolicyResult:
    """Kết quả kiểm chính sách. `errors` là thông báo TIẾNG VIỆT hiển thị được ngay cho người dùng."""
    ok: bool
    errors: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# BĂM & KIỂM
# ─────────────────────────────────────────────────────────────

def _normalize(password: str) -> bytes:
    """
    Chuẩn hóa Unicode NFKC trước khi băm.

    VÌ SAO CẦN: mật khẩu có tiếng Việt (rất có thể ở đây) có thể được nhập ở dạng tổ hợp khác nhau —
    "ế" là một ký tự (NFC) hay "e" + dấu (NFD) tùy bàn phím/hệ điều hành. Không chuẩn hóa thì cùng
    một mật khẩu gõ trên hai máy sẽ cho hai chuỗi byte khác nhau và người dùng không đăng nhập được,
    mà thông báo lỗi lại là "sai mật khẩu" — cực khó lần ra.
    """
    return unicodedata.normalize("NFKC", password).encode("utf-8")


def hash_password(password: str, iterations: Optional[int] = None) -> str:
    """
    Băm mật khẩu, trả về chuỗi tự mô tả: `pbkdf2_sha256$<vòng>$<salt_hex>$<hash_hex>`.

    Dạng tự mô tả (modular crypt) là điều kiện để nâng số vòng lặp hoặc đổi thuật toán về sau mà
    không phải đặt lại mật khẩu của tất cả mọi người.
    """
    if not password:
        raise ValueError("Mật khẩu rỗng không băm được")

    iterations = iterations or PBKDF2_ITERATIONS
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", _normalize(password), salt, iterations)
    return f"{SCHEME_PBKDF2}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """
    Kiểm mật khẩu. So sánh bằng `hmac.compare_digest` (thời gian không đổi) chống tấn công đo thời gian.

    Trả `False` cho mọi đầu vào không hợp lệ thay vì ném ngoại lệ: bản ghi băm hỏng phải dẫn tới
    "đăng nhập thất bại", không dẫn tới lỗi 500 làm lộ thông tin về nội bộ hệ thống.
    """
    if not password or not stored:
        return False

    try:
        scheme, iter_s, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False

    if scheme != SCHEME_PBKDF2:
        return False

    try:
        iterations = int(iter_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", _normalize(password), salt, iterations)
    return hmac.compare_digest(actual, expected)


def needs_rehash(stored: str, iterations: Optional[int] = None) -> bool:
    """
    Bản băm này có nên được tạo lại khi người dùng đăng nhập lần tới không?

    Dùng để nâng số vòng lặp (hoặc đổi thuật toán) **dần dần**, không cần đặt lại mật khẩu hàng loạt:
    mỗi lần ai đó đăng nhập đúng là một cơ hội nâng cấp bản băm của họ.
    """
    iterations = iterations or PBKDF2_ITERATIONS
    try:
        scheme, iter_s, _, _ = stored.split("$")
    except (ValueError, AttributeError):
        return True
    if scheme != SCHEME_PBKDF2:
        return True
    try:
        return int(iter_s) < iterations
    except ValueError:
        return True


# ─────────────────────────────────────────────────────────────
# CHÍNH SÁCH MẬT KHẨU (YC-QT-06)
# ─────────────────────────────────────────────────────────────

def check_policy(password: str, username: Optional[str] = None,
                 full_name: Optional[str] = None) -> PolicyResult:
    """
    Kiểm mật khẩu có đạt chính sách. Trả về mọi lỗi cùng lúc, bằng TIẾNG VIỆT.

    Trả về tất cả lỗi thay vì lỗi đầu tiên là chủ ý: người dùng sửa một lần cho xong, không phải thử
    đi thử lại từng điều kiện — mỗi vòng thử lại là một lần họ có xu hướng chọn mật khẩu yếu hơn.

    KHÔNG bắt buộc "phải có ký tự đặc biệt": quy tắc đó đẩy người dùng tới `Matkhau@123` (đạt mọi quy
    tắc, vẫn yếu) và tới việc dán mật khẩu lên màn hình. Thay vào đó ưu tiên ĐỘ DÀI và loại bỏ những
    mật khẩu đoán được — đúng khuyến nghị hiện hành của NIST.
    """
    errors: List[str] = []

    if not password:
        return PolicyResult(False, ["Mật khẩu không được để trống"])

    if len(password) < MIN_LENGTH:
        errors.append(f"Mật khẩu phải có ít nhất {MIN_LENGTH} ký tự (hiện có {len(password)})")

    lowered = password.lower().strip()
    if lowered in COMMON_PASSWORDS:
        errors.append("Mật khẩu này quá phổ biến, rất dễ bị đoán — hãy chọn mật khẩu khác")

    # Chỉ toàn số thì dù dài vẫn dễ dò
    if password.isdigit():
        errors.append("Mật khẩu không được chỉ gồm chữ số")

    # Một ký tự lặp lại (aaaaaaaaaa) hoặc dãy liên tiếp (1234567890, abcdefghij)
    if len(set(password)) <= 2:
        errors.append("Mật khẩu không được chỉ gồm một hai ký tự lặp lại")
    if _is_sequential(lowered):
        errors.append("Mật khẩu không được là dãy ký tự liên tiếp (vd 12345678, abcdefgh)")

    # So sánh sau khi BỎ DẤU cả hai phía: người dùng gõ tên mình vào mật khẩu hầu như luôn không dấu
    # ("nguyenvanan2026") trong khi hệ thống lưu tên có dấu ("Nguyễn Văn An").
    bare = strip_diacritics(password)

    if username and len(username) >= 3 and strip_diacritics(username) in bare:
        errors.append("Mật khẩu không được chứa tên đăng nhập")

    if full_name:
        for part in re.split(r"\s+", full_name.strip()):
            bare_part = strip_diacritics(part)
            # Bỏ qua họ/đệm quá ngắn ("Lê", "Đỗ") — cấm chúng sẽ loại oan rất nhiều mật khẩu tốt
            if len(bare_part) >= 3 and bare_part in bare:
                errors.append("Mật khẩu không được chứa tên của bạn")
                break

    return PolicyResult(ok=not errors, errors=errors)


def strip_diacritics(text: str) -> str:
    """
    Bỏ dấu tiếng Việt để so sánh: "Nguyễn Văn An" → "nguyen van an".

    VÌ SAO CẦN cho việc kiểm mật khẩu: người Việt gõ tên mình vào mật khẩu hầu như luôn **không dấu**
    (`nguyenvanan2026`), trong khi `full_name` trong hệ thống thì **có dấu** ("Nguyễn Văn An"). So
    sánh trực tiếp sẽ không khớp, và quy tắc "mật khẩu không được chứa tên của bạn" trở thành vô dụng
    đúng với nhóm mật khẩu yếu phổ biến nhất ở đây.

    Cũng xử lý đ/Đ — ký tự này không phân rã được bằng NFD nên phải thay riêng.
    """
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _is_sequential(text: str) -> bool:
    """Toàn bộ chuỗi là dãy tăng/giảm liên tiếp theo mã ký tự (chỉ xét chuỗi từ 4 ký tự)."""
    if len(text) < 4:
        return False
    deltas = {ord(text[i + 1]) - ord(text[i]) for i in range(len(text) - 1)}
    return deltas in ({1}, {-1})


def generate_password(length: int = 16) -> str:
    """
    Sinh mật khẩu tạm an toàn (cho việc đặt lại mật khẩu của quản trị viên).

    Bỏ các ký tự dễ đọc nhầm (`0/O`, `1/l/I`) vì mật khẩu tạm thường được **đọc hoặc chép tay** cho
    người dùng — nhầm một ký tự là một lượt hỗ trợ nữa.
    """
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(max(length, MIN_LENGTH)))
