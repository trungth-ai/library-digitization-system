#!/usr/bin/env python3
"""
Kiểm tra tệp đầu vào trước khi nhận (YC-BU-09 — sprint V5).

VÌ SAO KIỂM SỚM: hệ hiện tại chỉ kiểm `filename.endswith(".pdf")`. Một tệp ảnh đổi tên thành `.pdf`
sẽ đi qua toàn bộ hàng đợi, chiếm một suất worker, chạy OCRmyPDF vài chục giây rồi mới hỏng — và
thông báo lỗi lúc đó là lỗi kỹ thuật của Ghostscript, không phải "đây không phải tệp PDF".

Từ chối ở cửa vào tốn vài mili-giây và cho được thông báo tiếng Việt nói đúng vấn đề.

Kiểm theo **chữ ký tệp** (`%PDF-`) chứ không theo phần mở rộng: phần mở rộng là thứ người dùng gõ,
chữ ký là thứ tệp thật sự chứa.

Module THUẦN (chỉ thư viện chuẩn) → kiểm thử được.
"""

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("core.file_check")

PDF_MAGIC = b"%PDF-"
# Đọc đủ để tìm chữ ký: một số công cụ chèn vài byte rác trước header
HEADER_SCAN_BYTES = 1024

# Ngưỡng dung lượng trống tối thiểu trước khi nhận tệp mới (YC-BU-05)
DISK_MIN_FREE_GB = int(os.getenv("DISK_MIN_FREE_GB", "20"))

# Hạn mức nạp theo lô (YC-BU-02) — thay cho trần cứng 10 tệp
MAX_BATCH_FILES = int(os.getenv("MAX_BATCH_FILES", "500"))
MAX_BATCH_MB = int(os.getenv("MAX_BATCH_MB", "5000"))


@dataclass
class CheckResult:
    """
    Kết quả kiểm tra. `reason` là thông báo TIẾNG VIỆT hiển thị thẳng được cho người dùng.

    `code` để giao diện phân nhóm và thống kê "bao nhiêu tệp bị bỏ qua vì lý do gì" — thông tin cần
    khi nạp một lô 500 tệp và 30 tệp bị loại.
    """
    ok: bool
    code: Optional[str] = None
    reason: Optional[str] = None

    @classmethod
    def fail(cls, code: str, reason: str) -> "CheckResult":
        return cls(ok=False, code=code, reason=reason)


OK = CheckResult(ok=True)


def check_filename(filename: str) -> CheckResult:
    """
    Kiểm tên tệp: có phần mở rộng `.pdf`, không rỗng, không chứa đường dẫn.

    Chặn tên chứa `/` `\\` hoặc `..`: tên tệp đến từ người dùng và sẽ được ghép vào đường dẫn đĩa —
    một tên như `../../etc/passwd.pdf` là đường thoát khỏi thư mục đích.
    """
    if not filename or not filename.strip():
        return CheckResult.fail("empty_name", "Tên tệp trống")

    if "/" in filename or "\\" in filename or ".." in filename:
        return CheckResult.fail(
            "unsafe_name",
            f"Tên tệp không hợp lệ: '{filename}'. Tên không được chứa dấu gạch chéo hoặc '..'")

    if not filename.lower().endswith(".pdf"):
        return CheckResult.fail(
            "not_pdf_extension",
            f"'{filename}' không phải tệp PDF. Hệ thống chỉ nhận tệp .pdf")

    return OK


def check_pdf_content(path: Path, expected_size: Optional[int] = None) -> CheckResult:
    """
    Kiểm nội dung tệp THẬT SỰ là PDF và đọc được.

    Ba trường hợp bị chặn ở đây, mỗi cái có thông báo riêng vì mỗi cái cần một hành động khác nhau:
      - tệp rỗng            → tải lại
      - không phải PDF      → chọn đúng tệp
      - PDF có mật khẩu     → gỡ mật khẩu trước khi tải lên
    """
    try:
        size = path.stat().st_size
    except OSError as e:
        return CheckResult.fail("unreadable", f"Không đọc được tệp: {e}")

    if size == 0:
        return CheckResult.fail("empty_file", "Tệp rỗng (0 byte) — có thể tải lên chưa hoàn tất")

    if expected_size is not None and size != expected_size:
        return CheckResult.fail(
            "size_mismatch",
            f"Tệp ghi xuống không đủ ({size}/{expected_size} byte) — tải lên bị gián đoạn")

    try:
        with path.open("rb") as f:
            head = f.read(HEADER_SCAN_BYTES)
    except OSError as e:
        return CheckResult.fail("unreadable", f"Không đọc được tệp: {e}")

    if PDF_MAGIC not in head:
        return CheckResult.fail(
            "not_pdf_content",
            "Nội dung tệp không phải PDF (có thể là ảnh hoặc tệp nén được đổi tên)")

    # PDF mã hóa: OCR sẽ hỏng ở giữa chừng với thông báo khó hiểu, nên chặn ngay và nói rõ
    if _looks_encrypted(path):
        return CheckResult.fail(
            "encrypted",
            "PDF có mật khẩu bảo vệ. Vui lòng gỡ mật khẩu trước khi tải lên")

    return OK


def _looks_encrypted(path: Path) -> bool:
    """
    Dò dấu hiệu PDF được mã hóa mà không cần `pypdf`.

    Tìm `/Encrypt` trong phần đuôi tệp (nơi có trailer). Cách này có thể bắt nhầm trong trường hợp
    hiếm, nhưng đánh đổi đúng hướng: báo "có mật khẩu" cho một tệp lạ khiến người dùng kiểm tra lại,
    còn để lọt thì OCR hỏng với thông báo không ai hiểu.
    """
    try:
        with path.open("rb") as f:
            f.seek(max(0, path.stat().st_size - 4096))
            return b"/Encrypt" in f.read()
    except OSError:
        return False


def check_disk_space(directory: str, min_free_gb: Optional[int] = None) -> CheckResult:
    """
    Kiểm dung lượng trống trước khi nhận (YC-BU-05).

    Đĩa đầy giữa lúc nạp một lô lớn không chỉ làm hỏng tệp đang ghi — nó làm PostgreSQL không ghi
    được, worker không lưu được kết quả, và toàn hệ thống hỏng theo cách rất khó gỡ. Từ chối nhận
    trước là rẻ hơn nhiều so với dọn dẹp sau.
    """
    threshold = DISK_MIN_FREE_GB if min_free_gb is None else min_free_gb
    try:
        usage = shutil.disk_usage(directory)
    except OSError as e:
        # Không đo được thì CHO QUA: chặn nhận tài liệu vì không đọc được thông tin đĩa là phản ứng
        # quá tay — lỗi này thường do đường dẫn tạm chưa tồn tại, không phải do hết chỗ.
        logger.warning("Không đọc được dung lượng đĩa của '%s': %s", directory, e)
        return OK

    free_gb = usage.free / (1024 ** 3)
    if free_gb < threshold:
        return CheckResult.fail(
            "disk_full",
            f"Dung lượng đĩa còn {free_gb:.1f} GB, dưới ngưỡng an toàn {threshold} GB. "
            f"Vui lòng liên hệ quản trị viên trước khi nạp thêm tài liệu")

    return OK


def check_batch_limits(file_count: int, total_bytes: int,
                       max_files: Optional[int] = None,
                       max_mb: Optional[int] = None) -> CheckResult:
    """
    Kiểm hạn mức một lô (YC-BU-02) — thay cho trần cứng 10 tệp.

    Hạn mức theo CẢ số tệp lẫn tổng dung lượng: 500 tệp nhỏ và 20 tệp 500 MB là hai loại tải khác
    hẳn nhau, giới hạn một chiều sẽ để lọt một trong hai.
    """
    limit_files = MAX_BATCH_FILES if max_files is None else max_files
    limit_mb = MAX_BATCH_MB if max_mb is None else max_mb

    if file_count > limit_files:
        return CheckResult.fail(
            "too_many_files",
            f"Vượt hạn mức: {file_count} tệp, tối đa {limit_files} tệp mỗi lần. "
            f"Vui lòng chia thành nhiều lô nhỏ hơn")

    total_mb = total_bytes / (1024 * 1024)
    if total_mb > limit_mb:
        return CheckResult.fail(
            "batch_too_large",
            f"Vượt hạn mức: {total_mb:.0f} MB, tối đa {limit_mb} MB mỗi lần. "
            f"Vui lòng chia thành nhiều lô nhỏ hơn")

    return OK


def safe_extract_path(base_dir: Path, member_name: str) -> Optional[Path]:
    """
    Đường dẫn an toàn để giải nén một mục trong ZIP, hoặc `None` nếu mục đó thoát khỏi thư mục đích.

    🔴 CHỐNG `zip-slip` (KT-BM-20): một mục tên `../../etc/passwd` trong tệp ZIP sẽ ghi đè tệp hệ
    thống nếu ghép đường dẫn ngây thơ. Đây là lỗ hổng cổ điển và vẫn còn rất phổ biến.

    Kiểm bằng cách phân giải đường dẫn TUYỆT ĐỐI rồi khẳng định nó nằm trong `base_dir` — không kiểm
    bằng cách tìm chuỗi `..`, vì còn nhiều cách khác để thoát (đường dẫn tuyệt đối, liên kết mềm,
    mã hóa khác nhau của cùng ký tự).
    """
    if not member_name or member_name.endswith("/"):
        return None

    base_resolved = base_dir.resolve()
    candidate = (base_resolved / member_name).resolve()

    try:
        candidate.relative_to(base_resolved)
    except ValueError:
        logger.warning("Chặn mục ZIP thoát khỏi thư mục đích: %r", member_name)
        return None

    return candidate
