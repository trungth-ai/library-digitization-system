#!/usr/bin/env python3
"""
Dọn nhật ký theo tuổi (YC-LG-07 — sprint V1). Trả nợ kỹ thuật đã ghi trong `docs/PLAN.md`.

VẤN ĐỀ: `system_events` chỉ có đường ghi vào, không có đường xóa. Mỗi sự cố hạ tầng là một dòng; hệ
chạy dài hạn thì bảng lớn dần vô hạn, làm chậm sao lưu và cuối cùng làm đầy đĩa. Tệp log JSONL cũng
vậy — luân chuyển giới hạn được kích thước mỗi tệp nhưng không giới hạn được tuổi.

NGUYÊN TẮC THỜI HẠN LƯU (QĐ-08) — khác nhau vì giá trị của từng loại khác nhau:

    audit_log        VĨNH VIỄN   nghiệp vụ, bất biến (YC-AU-06). KHÔNG dọn ở đây.
    user_activity    365 ngày    hành vi người dùng, phục vụ điều tra an ninh
    system_events     90 ngày    sự cố hạ tầng, hết giá trị nhanh sau khi đã xử lý
    tệp log JSONL     14 ngày    chi tiết kỹ thuật, chỉ dùng khi đang gỡ lỗi

⚠️ `audit_log` KHÔNG BAO GIỜ bị đụng tới ở module này. Nó bất biến ở tầng DB (trigger chặn DELETE),
nên một lời gọi nhầm sẽ ném lỗi chứ không âm thầm xóa — nhưng vẫn không có hàm nào ở đây nhắm vào nó.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("core.retention")

# Bảng được phép dọn + thời hạn mặc định. Danh sách trắng, KHÔNG nhận tên bảng tùy ý từ nơi gọi:
# tên bảng không thể tham số hóa trong SQL nên phải nội suy chuỗi — chỉ an toàn khi giá trị đến từ
# đây chứ không từ đầu vào bên ngoài.
CLEANABLE_TABLES: Dict[str, str] = {
    "system_events": "SYSTEM_EVENTS_RETENTION_DAYS",
    "user_activity": "USER_ACTIVITY_RETENTION_DAYS",
}

DEFAULT_RETENTION_DAYS = {
    "system_events": 90,
    "user_activity": 365,
}

LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "14"))


@dataclass
class CleanupReport:
    """Kết quả một lượt dọn. Ghi lại số lượng để việc dọn dữ liệu không bao giờ là thao tác vô hình."""
    rows_deleted: Dict[str, int] = field(default_factory=dict)
    files_deleted: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return sum(self.rows_deleted.values())

    def summary(self) -> str:
        parts = [f"{table}: {count} dòng" for table, count in self.rows_deleted.items() if count]
        if self.files_deleted:
            parts.append(f"{len(self.files_deleted)} tệp log")
        return "; ".join(parts) if parts else "không có gì quá hạn"


def retention_days(table: str) -> int:
    """Thời hạn lưu của một bảng, đọc từ biến môi trường, có giá trị mặc định."""
    env_name = CLEANABLE_TABLES.get(table)
    if not env_name:
        raise ValueError(f"Bảng '{table}' không nằm trong danh sách được phép dọn")
    return int(os.getenv(env_name, str(DEFAULT_RETENTION_DAYS.get(table, 90))))


def cleanup_table(table: str, days: Optional[int] = None, batch_size: int = 10000) -> int:
    """
    Xóa bản ghi cũ hơn `days` ngày trong một bảng. Trả về số dòng đã xóa.

    Xóa THEO LÔ chứ không một câu DELETE duy nhất: một lệnh xóa vài triệu dòng giữ khóa rất lâu và
    làm nghẽn ghi mới — trong khi việc dọn dẹp là việc nền, không có gì phải vội.
    """
    if table not in CLEANABLE_TABLES:
        raise ValueError(f"Bảng '{table}' không nằm trong danh sách được phép dọn")

    import scripts.db as db

    days = days if days is not None else retention_days(table)
    total = 0

    # `ctid` là định danh vật lý của dòng trong PostgreSQL — cách rẻ nhất để xóa theo lô mà không
    # cần bảng có khóa chính kiểu số.
    sql = f"""
        DELETE FROM {table}
        WHERE ctid IN (
            SELECT ctid FROM {table}
            WHERE created_at < NOW() - (%s || ' days')::interval
            LIMIT %s
        )
    """

    while True:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (days, batch_size))
                deleted = cur.rowcount
        total += deleted
        if deleted < batch_size:
            break

    if total:
        logger.info("Đã dọn %d dòng quá %d ngày khỏi bảng %s", total, days, table)
    return total


def cleanup_log_files(log_dir: Optional[str] = None,
                      days: Optional[int] = None) -> List[str]:
    """
    Xóa tệp log đã luân chuyển và quá hạn. Trả về danh sách tệp đã xóa.

    CHỈ đụng tệp `.jsonl.N` (bản đã luân chuyển) — KHÔNG bao giờ đụng tệp đang được ghi (`.jsonl`),
    vì xóa tệp đang mở trên Windows sẽ lỗi, còn trên Linux thì tiến trình vẫn ghi vào một tệp đã bị
    gỡ khỏi thư mục và dung lượng không thực sự được giải phóng.
    """
    directory = log_dir if log_dir is not None else os.getenv("LOG_DIR", "")
    if not directory:
        return []

    days = days if days is not None else LOG_RETENTION_DAYS
    cutoff = time.time() - days * 86400
    deleted: List[str] = []

    path = Path(directory)
    if not path.is_dir():
        return []

    for tep in path.glob("*.jsonl.*"):
        try:
            if tep.stat().st_mtime < cutoff:
                tep.unlink()
                deleted.append(tep.name)
        except OSError as e:
            logger.warning("Không xóa được tệp log '%s': %s", tep.name, e)

    if deleted:
        logger.info("Đã xóa %d tệp log quá %d ngày", len(deleted), days)
    return deleted


def cleanup_job_files(data_dir: Optional[str] = None, days: Optional[int] = None,
                      dry_run: bool = False) -> List[str]:
    """
    Dọn tệp TRUNG GIAN của các job đã xong từ lâu (YC-VH-09). Trả về danh sách thư mục đã xóa.

    🔴 CHỈ xóa thư mục job của tài liệu đã ở trạng thái kết thúc VÀ quá hạn. KHÔNG xóa theo tuổi tệp
    đơn thuần: một tài liệu tải lên từ tháng trước mà vẫn đang chờ duyệt thì tệp của nó vẫn cần thiết.

    ⚠️ Đây là hàm xóa dữ liệu — mọi lối ra đều thận trọng:
      • `dry_run=True` để xem trước danh sách mà không xóa gì.
      • Thư mục không khớp mẫu id job (uuid) thì BỎ QUA, không đụng tới.
      • Không đọc được trạng thái tài liệu từ DB → BỎ QUA thư mục đó, không xóa theo phỏng đoán.
    """
    import re
    import shutil

    directory = data_dir if data_dir is not None else os.getenv(
        "DIGITIZE_DATA_DIR", "/data/digitization/jobs")
    days = days if days is not None else int(os.getenv("JOB_FILES_RETENTION_DAYS", "90"))

    root = Path(directory)
    if not root.is_dir():
        return []

    # Chỉ đụng thư mục có tên đúng dạng uuid4 — thư mục lạ (`_zip_staging`, tệp người dùng để nhầm)
    # tuyệt đối không xóa
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)

    try:
        import scripts.db as db
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT id FROM documents
                    WHERE status IN ('completed', 'failed', 'cancelled', 'deleted')
                      AND finished_at IS NOT NULL
                      AND finished_at < NOW() - (%s || ' days')::interval
                """, (days,))
                eligible = {row[0] for row in cur.fetchall()}
    except Exception as e:  # noqa: BLE001
        logger.warning("Không đọc được danh sách tài liệu quá hạn — KHÔNG dọn tệp: %s", e)
        return []

    deleted: List[str] = []
    for child in root.iterdir():
        if not child.is_dir() or not uuid_pattern.match(child.name):
            continue
        if child.name not in eligible:
            continue

        if dry_run:
            deleted.append(child.name)
            continue

        try:
            shutil.rmtree(child)
            deleted.append(child.name)
        except OSError as e:
            logger.warning("Không xóa được thư mục job '%s': %s", child.name, e)

    if deleted:
        logger.info("%s %d thư mục job quá %d ngày",
                    "Sẽ dọn" if dry_run else "Đã dọn", len(deleted), days)
    return deleted


def run_cleanup(log_dir: Optional[str] = None, record_event: bool = True) -> CleanupReport:
    """
    Chạy trọn một lượt dọn: bảng nhật ký + phiên hết hạn + tệp log.

    Mỗi phần được bọc riêng: một phần hỏng (vd bảng `user_activity` chưa được di trú) không được
    làm mất phần còn lại. Kết quả ghi vào `system_events` để việc dọn dữ liệu **có dấu vết** — dọn
    dữ liệu mà không ai biết đã dọn gì là thứ rất khó truy khi cần đối chiếu về sau.
    """
    report = CleanupReport()

    for table in CLEANABLE_TABLES:
        try:
            report.rows_deleted[table] = cleanup_table(table)
        except Exception as e:  # noqa: BLE001
            message = f"Dọn bảng {table} thất bại: {e}"
            logger.warning(message)
            report.errors.append(message)

    try:
        from scripts.auth import sessions
        report.rows_deleted["user_sessions"] = sessions.cleanup_expired()
    except Exception as e:  # noqa: BLE001
        report.errors.append(f"Dọn phiên hết hạn thất bại: {e}")

    try:
        report.files_deleted = cleanup_log_files(log_dir)
    except Exception as e:  # noqa: BLE001
        report.errors.append(f"Dọn tệp log thất bại: {e}")

    if record_event and (report.total_rows or report.files_deleted or report.errors):
        try:
            import scripts.db as db
            db.log_system_event(
                source="api", kind="retention_cleanup",
                level="warning" if report.errors else "info",
                message=f"Dọn nhật ký theo tuổi: {report.summary()}",
                detail="; ".join(report.errors) if report.errors else None,
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("Không ghi được sự kiện dọn dẹp: %s", e)

    return report
