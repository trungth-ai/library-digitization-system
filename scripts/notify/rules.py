#!/usr/bin/env python3
"""
Quy tắc sinh cảnh báo từ trạng thái hệ thống (YC-TB-02/03 — sprint V8).

BỐI CẢNH: ADR-009 đã làm hệ thống *ghi nhận* được sự cố (bảng `system_events`), nhưng ghi nhận không
phải là báo. Worker chết lúc 2 giờ sáng thì tới 8 giờ sáng mới có người mở trang `/cong-cu` và thấy.
Module này biến trạng thái thành cảnh báo chủ động.

NGUYÊN TẮC CHỌN QUY TẮC: chỉ cảnh báo những việc **cần người can thiệp**. Cảnh báo cho việc tự khỏi
(Redis chớp mạng 2 giây rồi nối lại) sẽ dạy người nhận bỏ qua cảnh báo — và họ sẽ bỏ qua cả cái quan
trọng. Vì vậy mọi ngưỡng ở đây đều là "kéo dài đủ lâu để không tự khỏi".

Phần đánh giá là hàm THUẦN (`evaluate`) nhận vào một bức ảnh trạng thái → kiểm thử được không cần DB.
"""

import logging
import os
from typing import Dict, List, Optional

from scripts.notify.base import (
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    Alert,
)

logger = logging.getLogger("notify.rules")

# Không có worker nào trong ngần này phút thì báo. Đủ dài để bỏ qua một lần restart bình thường
# (docker compose up -d --build mất khoảng 1–2 phút), đủ ngắn để phát hiện trong đêm.
NO_WORKER_MINUTES = int(os.getenv("ALERT_NO_WORKER_MINUTES", "5"))
# Hàng đợi sâu hơn ngần này thì báo — tồn đọng bất thường, có thể worker không kịp hoặc đang kẹt
QUEUE_DEPTH_ALERT = int(os.getenv("ALERT_QUEUE_DEPTH", "1000"))
# Số tài liệu trong hàng đợi chết đủ để coi là vấn đề hệ thống chứ không phải vài tệp hỏng lẻ tẻ
DEAD_LETTER_ALERT = int(os.getenv("ALERT_DEAD_LETTER", "10"))
# Dung lượng đĩa còn dưới ngần này GB thì báo — cao hơn ngưỡng từ chối nhận (DISK_MIN_FREE_GB)
# để còn thời gian xử lý TRƯỚC KHI hệ thống ngừng nhận tài liệu
DISK_WARN_GB = int(os.getenv("ALERT_DISK_WARN_GB", "30"))


# Quy tắc mà một WORKER không thể tự đánh giá — xem `evaluate(skip=...)`
WORKER_BLIND_SPOTS = frozenset({"no_worker"})


def evaluate(snapshot: Dict, skip: Optional[frozenset] = None) -> List[Alert]:
    """
    Sinh danh sách cảnh báo từ một bức ảnh trạng thái. Hàm THUẦN — không chạm DB, không gửi gì.

    `skip` bỏ qua một số quy tắc theo mã. Dùng cho **điểm mù của người quan sát**: một worker đang
    chạy thì không thể kết luận "không có worker nào" — chính sự tồn tại của nó bác bỏ điều đó. Nếu
    số đếm nhịp tim ra 0 trong khi worker đang chạy thì đó là mâu thuẫn dữ liệu Redis, không phải
    tình huống "hệ thống dừng"; báo động ở đó là báo động giả.

    Ai đánh giá được `no_worker`? Bên NGOÀI worker: API (`/api/v2/health/detailed`), bảng điều khiển,
    hoặc một bộ giám sát bên thứ ba. Đó là lý do hai trang đó vẫn hiển thị số worker độc lập — cảnh
    báo là lớp bổ sung, không thay thế việc quan sát.

    `snapshot` gồm (mọi khóa đều tùy chọn; thiếu khóa = không đánh giá quy tắc đó, KHÔNG phải = 0):
        workers_alive     int | None   None = đã thử đọc Redis nhưng thất bại
        queue_ready       int
        queue_dead        int
        disk_free_gb      float
        sla_breaches      int
        failed_batches    list[dict]

    Tách khỏi phần đọc DB có chủ đích: quy tắc cảnh báo là thứ dễ sai một cách âm thầm (báo nhầm,
    hoặc tệ hơn, không báo) và là thứ khó kiểm chứng nhất trên môi trường thật.
    """
    skip = skip or frozenset()
    alerts: List[Alert] = []

    # ── Không có worker nào (YC-TB-02) ──────────────────────────────
    #
    # ⚠️ PHẢI phân biệt BA trạng thái, và `dict.get()` gộp mất hai trong ba:
    #     khóa thiếu   → không thu thập được mục này, KHÔNG đánh giá (im lặng)
    #     giá trị None → đã thử đọc Redis nhưng thất bại → đáng báo
    #     giá trị 0    → đọc được, chắc chắn không có worker nào → đáng báo (mức cao nhất)
    #
    # Dùng `.get()` để quyết định sẽ biến mọi bức ảnh trạng thái thiếu khóa thành một cảnh báo giả
    # mức nghiêm trọng — đúng lỗi mà `test_thieu_khoa_thi_khong_danh_gia_quy_tac_do` bắt được.
    workers = snapshot.get("workers_alive")
    has_worker_info = "workers_alive" in snapshot and "no_worker" not in skip

    if has_worker_info and workers == 0:
        alerts.append(Alert(
            key="no_worker",
            title="Không có worker nào đang chạy",
            message=(
                "Hệ thống không có tiến trình xử lý nào. Mọi tài liệu sẽ nằm chờ vô thời hạn cho tới "
                "khi worker được khởi động lại — người dùng không thấy lỗi, chỉ thấy tài liệu không nhúc nhích."
            ),
            severity=SEVERITY_CRITICAL,
            detail={"số tài liệu đang chờ": snapshot.get("queue_ready", "không rõ")},
        ))
    # `None` = ĐÃ THỬ đọc Redis nhưng thất bại — khác hẳn 0, và cũng đáng báo (ADR-009 mục 6)
    elif has_worker_info and workers is None:
        alerts.append(Alert(
            key="redis_unreadable",
            title="Không đọc được trạng thái worker",
            message="Không kết nối được Redis để đếm worker. Hàng đợi có thể đang không hoạt động.",
            severity=SEVERITY_CRITICAL,
        ))

    # ── Đĩa sắp đầy (YC-TB-02) ──────────────────────────────────────
    disk_free = snapshot.get("disk_free_gb")
    if disk_free is not None and disk_free < DISK_WARN_GB:
        alerts.append(Alert(
            key="disk_low",
            title=f"Dung lượng đĩa còn {disk_free:.0f} GB",
            message=(
                f"Dưới ngưỡng cảnh báo {DISK_WARN_GB} GB. Khi xuống dưới ngưỡng an toàn, hệ thống sẽ "
                f"NGỪNG NHẬN tài liệu mới. Cần dọn dữ liệu cũ hoặc mở rộng ổ đĩa."
            ),
            severity=SEVERITY_CRITICAL if disk_free < DISK_WARN_GB / 2 else SEVERITY_WARNING,
            detail={"còn trống (GB)": round(disk_free, 1)},
        ))

    # ── Hàng đợi tồn đọng bất thường ────────────────────────────────
    queue_ready = snapshot.get("queue_ready")
    if queue_ready is not None and queue_ready >= QUEUE_DEPTH_ALERT:
        alerts.append(Alert(
            key="queue_deep",
            title=f"Hàng đợi tồn đọng {queue_ready} tài liệu",
            message=(
                f"Vượt ngưỡng {QUEUE_DEPTH_ALERT}. Có thể do một lô lớn đang chạy (bình thường) hoặc "
                f"worker không kịp xử lý. Kiểm tra số worker đang sống và thời gian xử lý trung bình."
            ),
            severity=SEVERITY_WARNING,
            detail={"đang chờ": queue_ready, "worker đang sống": workers},
        ))

    # ── Hàng đợi chết ───────────────────────────────────────────────
    dead = snapshot.get("queue_dead")
    if dead is not None and dead >= DEAD_LETTER_ALERT:
        alerts.append(Alert(
            key="dead_letter",
            title=f"{dead} tài liệu trong hàng đợi chết",
            message=(
                "Nhiều tài liệu đã hết lượt thử lại. Con số này thường chỉ ra một nguyên nhân CHUNG "
                "(cấu hình sai, dịch vụ phụ thuộc chết) chứ không phải vài tệp hỏng lẻ tẻ. "
                "Mở trang Tình trạng hàng đợi để xem lý do."
            ),
            severity=SEVERITY_WARNING,
            detail={"số tài liệu": dead},
        ))

    # ── Tồn đọng quá hạn SLA (YC-TB-03) ─────────────────────────────
    sla = snapshot.get("sla_breaches")
    if sla:
        alerts.append(Alert(
            key="sla_breach",
            title=f"{sla} tài liệu tồn đọng quá hạn",
            message=(
                "Có tài liệu nằm quá lâu ở một trạng thái. Phần lớn trường hợp là tài liệu chờ cán bộ "
                "duyệt — không gây lỗi nào nên rất dễ bị quên."
            ),
            severity=SEVERITY_WARNING,
            detail={"số tài liệu": sla},
        ))

    # ── Lô có tỉ lệ lỗi cao (YC-TB-03) ──────────────────────────────
    for batch in snapshot.get("failed_batches") or []:
        total = batch.get("total_files") or 0
        failed = batch.get("failed_files") or 0
        if total and failed / total > 0.3:
            alerts.append(Alert(
                key=f"batch_failing:{batch.get('id')}",
                title=f"Lô '{batch.get('name')}' có tỉ lệ lỗi cao",
                message=(
                    f"{failed}/{total} tài liệu thất bại ({failed * 100 // total}%). "
                    f"Tỉ lệ này thường chỉ ra vấn đề chung của cả lô — sai loại tài liệu, "
                    f"bản scan hỏng hàng loạt, hoặc cấu hình lược đồ không phù hợp."
                ),
                severity=SEVERITY_WARNING,
                detail={"lô": batch.get("name"), "thất bại": failed, "tổng": total},
            ))

    return alerts


def collect_snapshot(redis_client=None) -> Dict:
    """
    Thu thập trạng thái hiện tại để đưa vào `evaluate`. Mọi phần bọc riêng — một nguồn hỏng không
    được làm mất các quy tắc còn lại.

    Khóa thiếu nghĩa là "không đánh giá được quy tắc đó", KHÁC với giá trị 0.
    """
    import shutil

    snapshot: Dict = {}

    if redis_client is not None:
        try:
            from scripts.core import queue as jobqueue
            depth = jobqueue.depth(redis_client, os.getenv("REDIS_QUEUE", "digitization_jobs"))
            snapshot["queue_ready"] = depth.ready
            snapshot["queue_dead"] = depth.dead
        except Exception as e:  # noqa: BLE001
            logger.debug("Không đọc được độ sâu hàng đợi: %s", e)

        try:
            snapshot["workers_alive"] = sum(
                1 for _ in redis_client.scan_iter("worker:heartbeat:*", count=100))
        except Exception:  # noqa: BLE001
            snapshot["workers_alive"] = None      # None = không đọc được, khác 0

    try:
        usage = shutil.disk_usage(os.getenv("DIGITIZE_DATA_DIR", "/data/digitization/jobs"))
        snapshot["disk_free_gb"] = usage.free / (1024 ** 3)
    except Exception as e:  # noqa: BLE001
        logger.debug("Không đọc được dung lượng đĩa: %s", e)

    try:
        from scripts.core import dashboard
        snapshot["sla_breaches"] = dashboard.sla_breaches(limit=1)["tong_so"]
        snapshot["failed_batches"] = dashboard.active_batches()
    except Exception as e:  # noqa: BLE001
        logger.debug("Không đọc được số liệu tồn đọng: %s", e)

    return snapshot
