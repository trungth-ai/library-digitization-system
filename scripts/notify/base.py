#!/usr/bin/env python3
"""
Interface kênh thông báo + chống spam cảnh báo (YC-TB-01/04 — sprint V8).

VẤN ĐỀ THẬT MÀ MODULE NÀY GIẢI: `system_events` đã ghi nhận sự cố từ ADR-009, nhưng **không ai được
báo**. Worker chết lúc 2 giờ sáng thì 8 giờ sáng mới có người phát hiện — cả một đêm xử lý mất trắng.

CHỐNG SPAM LÀ PHẦN QUAN TRỌNG KHÔNG KÉM VIỆC GỬI. Một sự cố kéo dài (mất PostgreSQL 3 tiếng) sẽ sinh
cảnh báo mỗi vòng lặp kiểm tra. Gửi hết thì hộp thư ngập 180 thư giống nhau, và hệ quả thực tế là
người nhận tạo bộ lọc xóa tự động — cảnh báo trở thành vô dụng đúng lúc cần nhất.

Module THUẦN: không import fastapi/psycopg2/smtplib ở mức module → kiểm thử được.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger("notify.base")

# Mức nghiêm trọng — quyết định kênh nào nhận
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

_SEVERITY_ORDER = {SEVERITY_INFO: 0, SEVERITY_WARNING: 1, SEVERITY_CRITICAL: 2}


@dataclass
class Alert:
    """Một cảnh báo. `key` là danh tính để gộp — hai cảnh báo cùng `key` là cùng một sự cố."""
    key: str
    title: str
    message: str
    severity: str = SEVERITY_WARNING
    detail: Optional[Dict] = None

    def format_text(self) -> str:
        """Nội dung dạng chữ thuần — dùng cho log và thân email."""
        lines = [self.title, "", self.message]
        if self.detail:
            lines.append("")
            lines.extend(f"  {k}: {v}" for k, v in self.detail.items())
        return "\n".join(lines)


class NotificationChannel:
    """
    Interface kênh thông báo. Thêm kênh mới = viết một lớp con + một dòng trong `channels.CHANNELS`.

    `send` KHÔNG được ném lỗi ra ngoài: một kênh hỏng (SMTP sai cấu hình) không được ngăn các kênh
    còn lại gửi, và tuyệt đối không được làm gãy nghiệp vụ đang gọi tới.
    """

    name = "base"

    def send(self, alert: Alert) -> bool:
        """Gửi cảnh báo. Trả `True` nếu gửi được."""
        raise NotImplementedError

    def available(self) -> bool:
        """Kênh này đã cấu hình đủ để dùng chưa? Chưa đủ thì bỏ qua, không báo lỗi mỗi lần gửi."""
        return True


class AlertThrottle:
    """
    Chống spam: mỗi `key` chỉ gửi lại sau `cooldown` giây (YC-TB-04).

    Trạng thái giữ TRONG BỘ NHỚ tiến trình, không lưu DB. Đánh đổi có chủ đích: restart tiến trình sẽ
    gửi lại một lần cho sự cố đang diễn ra — điều đó CHẤP NHẬN ĐƯỢC (thậm chí có ích: nó xác nhận sự
    cố vẫn còn sau khi restart), còn thêm một bảng và một truy vấn cho mỗi cảnh báo thì không đáng.

    `resolve()` xóa dấu vết để khi sự cố tái diễn về sau, cảnh báo được gửi ngay chứ không phải chờ
    hết thời gian nguội.
    """

    def __init__(self, cooldown_sec: Optional[int] = None):
        self.cooldown = cooldown_sec if cooldown_sec is not None else int(
            os.getenv("ALERT_COOLDOWN_SEC", "1800"))
        self._last_sent: Dict[str, float] = {}

    def should_send(self, key: str, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        last = self._last_sent.get(key)
        if last is not None and now - last < self.cooldown:
            return False
        self._last_sent[key] = now
        return True

    def resolve(self, key: str) -> None:
        """Sự cố đã khắc phục — lần tái diễn tiếp theo sẽ được báo ngay."""
        self._last_sent.pop(key, None)

    def reset(self) -> None:
        self._last_sent.clear()


@dataclass
class Dispatcher:
    """
    Gửi cảnh báo qua tất cả kênh đã bật, có chống spam.

    Kênh nào cũng được thử độc lập: một kênh hỏng không ngăn kênh còn lại. Đây là lý do `send` của
    kênh trả `bool` thay vì ném lỗi.
    """
    channels: List[NotificationChannel] = field(default_factory=list)
    throttle: AlertThrottle = field(default_factory=AlertThrottle)
    min_severity: str = SEVERITY_WARNING

    def send(self, alert: Alert, force: bool = False) -> Dict[str, bool]:
        """
        Gửi một cảnh báo. Trả `{tên_kênh: gửi_được}`; rỗng nếu bị chặn bởi chống spam hoặc mức thấp.
        """
        if _SEVERITY_ORDER.get(alert.severity, 1) < _SEVERITY_ORDER.get(self.min_severity, 1):
            return {}

        if not force and not self.throttle.should_send(alert.key):
            logger.debug("Bỏ qua cảnh báo '%s' — đang trong thời gian nguội", alert.key)
            return {}

        results: Dict[str, bool] = {}
        for channel in self.channels:
            if not channel.available():
                continue
            try:
                results[channel.name] = channel.send(alert)
            except Exception as e:  # noqa: BLE001 - một kênh hỏng không ngăn kênh còn lại
                logger.error("Kênh '%s' gửi cảnh báo thất bại: %s", channel.name, e)
                results[channel.name] = False

        return results

    def resolve(self, key: str) -> None:
        self.throttle.resolve(key)
