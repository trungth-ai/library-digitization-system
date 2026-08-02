#!/usr/bin/env python3
"""
Các kênh gửi cảnh báo (YC-TB-01/06 — sprint V8).

🔴 YC-TB-06 — MỌI KÊNH PHẢI CHẠY ĐƯỢC KHI NGẮT INTERNET. Đây không phải chi tiết cấu hình mà là ràng
buộc kiến trúc: một hệ thống lấy khả năng air-gapped làm luận điểm chính mà cảnh báo lại đi qua dịch
vụ đám mây thì sẽ im lặng đúng lúc mất mạng — lúc cần cảnh báo nhất.

Vì vậy:
  • `email`   dùng SMTP **nội bộ của Nhà trường**, và có chốt cảnh báo nếu cấu hình trỏ ra ngoài.
  • `webhook` chỉ chấp nhận địa chỉ **nội mạng** (trừ khi được cho phép rõ ràng).
  • `log`     luôn có, không phụ thuộc mạng — kênh mặc định và là phương án cuối.

Dùng `urllib` của thư viện chuẩn cho webhook, không dùng `requests`: giữ air-gapped (không thêm phụ
thuộc phải tải trước khi ngắt mạng) — cùng lý do lớp provider dùng `urllib` (xem CLAUDE.md).
"""

import ipaddress
import json
import logging
import os
import socket
import urllib.error
import urllib.request
from typing import List, Optional
from urllib.parse import urlparse

from scripts.notify.base import Alert, NotificationChannel

logger = logging.getLogger("notify.channels")

WEBHOOK_TIMEOUT = int(os.getenv("ALERT_WEBHOOK_TIMEOUT", "10"))
SMTP_TIMEOUT = int(os.getenv("ALERT_SMTP_TIMEOUT", "15"))


def _is_internal_host(host: str) -> bool:
    """
    Địa chỉ này có nằm trong mạng nội bộ không?

    Phân giải tên miền rồi kiểm dải IP, chứ không so chuỗi: `alerts.internal.hpu.edu.vn` có thể trỏ
    ra Internet, còn `10.1.1.5` thì chắc chắn không. Không phân giải được → coi là NGOÀI (mặc định
    an toàn: thà chặn nhầm một địa chỉ hợp lệ còn hơn gửi dữ liệu ra ngoài mà không biết).
    """
    if not host:
        return False
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        for info in socket.getaddrinfo(host, None):
            address = ipaddress.ip_address(info[4][0])
            if not (address.is_private or address.is_loopback or address.is_link_local):
                return False
        return True
    except Exception:  # noqa: BLE001
        return False


class LogChannel(NotificationChannel):
    """
    Kênh mặc định: ghi cảnh báo vào log ứng dụng.

    Luôn khả dụng, không phụ thuộc mạng hay cấu hình. Là phương án cuối khi mọi kênh khác hỏng — và
    nhờ log JSON có cấu trúc (sprint V1), cảnh báo ở đây vẫn lọc và tra được.
    """

    name = "log"

    def send(self, alert: Alert) -> bool:
        level = logging.CRITICAL if alert.severity == "critical" else logging.WARNING
        logger.log(level, "CẢNH BÁO [%s] %s — %s", alert.key, alert.title, alert.message,
                   extra={"alert_key": alert.key, "alert_severity": alert.severity})
        return True


class EmailChannel(NotificationChannel):
    """
    Gửi email qua SMTP. PHẢI là máy chủ SMTP nội bộ để chạy được khi ngắt Internet (YC-TB-06).

    Không cấu hình đủ → `available()` trả `False` và kênh bị bỏ qua im lặng, thay vì báo lỗi ở mỗi
    lần gửi. Cấu hình thiếu là trạng thái bình thường (Trung tâm có thể chưa dùng email), không phải
    sự cố.
    """

    name = "email"

    def __init__(self):
        self.host = os.getenv("SMTP_HOST", "").strip()
        self.port = int(os.getenv("SMTP_PORT", "25"))
        self.user = os.getenv("SMTP_USER", "").strip()
        self.password = os.getenv("SMTP_PASSWORD", "")
        self.sender = os.getenv("ALERT_EMAIL_FROM", "").strip() or self.user
        self.recipients = [
            addr.strip() for addr in os.getenv("ALERT_EMAIL_TO", "").split(",") if addr.strip()
        ]
        self.use_tls = os.getenv("SMTP_USE_TLS", "0").strip() not in ("0", "false", "no", "")

    def available(self) -> bool:
        return bool(self.host and self.sender and self.recipients)

    def send(self, alert: Alert) -> bool:
        if not self.available():
            return False

        # Cảnh báo (không chặn) khi SMTP trỏ ra ngoài: hệ thống vẫn gửi được lúc có mạng, nhưng người
        # vận hành cần biết cảnh báo sẽ IM LẶNG đúng lúc mất mạng — chính lúc cần nó nhất.
        if not _is_internal_host(self.host):
            logger.warning(
                "SMTP_HOST='%s' KHÔNG thuộc mạng nội bộ — cảnh báo qua email sẽ không gửi được "
                "khi ngắt Internet (YC-TB-06). Cân nhắc dùng máy chủ thư nội bộ của Nhà trường.",
                self.host)

        try:
            import smtplib
            from email.message import EmailMessage

            message = EmailMessage()
            message["Subject"] = f"[DocuFlow HP] {alert.title}"
            message["From"] = self.sender
            message["To"] = ", ".join(self.recipients)
            message.set_content(alert.format_text())

            with smtplib.SMTP(self.host, self.port, timeout=SMTP_TIMEOUT) as smtp:
                if self.use_tls:
                    smtp.starttls()
                if self.user and self.password:
                    smtp.login(self.user, self.password)
                smtp.send_message(message)

            logger.info("Đã gửi cảnh báo '%s' qua email tới %d địa chỉ",
                        alert.key, len(self.recipients))
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("Gửi email cảnh báo thất bại: %s", e)
            return False


class WebhookChannel(NotificationChannel):
    """
    Gọi webhook nội mạng (n8n, Telegram bridge nội bộ, hệ thống giám sát của Nhà trường).

    🔴 CHẶN địa chỉ ngoài mạng nội bộ theo mặc định — không chỉ vì YC-TB-06 mà còn vì nội dung cảnh
    báo có thể chứa tên tài liệu. Gửi tên tài liệu nhạy cảm tới một dịch vụ đám mây là rò rỉ dữ liệu
    qua đường không ai nghĩ tới (KT-BM-21).
    """

    name = "webhook"

    def __init__(self):
        self.url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
        self.allow_external = os.getenv(
            "ALERT_WEBHOOK_ALLOW_EXTERNAL", "0").strip() not in ("0", "false", "no", "")

    def available(self) -> bool:
        if not self.url:
            return False

        host = urlparse(self.url).hostname or ""
        if not _is_internal_host(host) and not self.allow_external:
            logger.error(
                "ALERT_WEBHOOK_URL trỏ tới '%s' KHÔNG thuộc mạng nội bộ — kênh webhook bị TẮT. "
                "Nội dung cảnh báo có thể chứa tên tài liệu; gửi ra ngoài là rò rỉ dữ liệu. "
                "Đặt ALERT_WEBHOOK_ALLOW_EXTERNAL=1 nếu đường truyền đã được kiểm soát.", host)
            return False
        return True

    def send(self, alert: Alert) -> bool:
        payload = json.dumps({
            "key": alert.key, "title": alert.title, "message": alert.message,
            "severity": alert.severity, "detail": alert.detail or {},
            "source": "docuflow-hp",
        }, ensure_ascii=False).encode("utf-8")

        request = urllib.request.Request(
            self.url, data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=WEBHOOK_TIMEOUT) as response:
                ok = 200 <= response.status < 300
                if not ok:
                    logger.warning("Webhook trả về HTTP %s cho cảnh báo '%s'",
                                   response.status, alert.key)
                return ok
        except urllib.error.URLError as e:
            logger.error("Gọi webhook cảnh báo thất bại: %s", e)
            return False


# Bảng đăng ký — thêm kênh mới là thêm MỘT dòng ở đây (YC-TB-01, mẫu YC-MP-08)
CHANNELS = {
    "log": LogChannel,
    "email": EmailChannel,
    "webhook": WebhookChannel,
}


def build_channels(names: Optional[str] = None) -> List[NotificationChannel]:
    """
    Dựng danh sách kênh từ `ALERT_CHANNELS` (phân tách bằng dấu phẩy).

    LUÔN có kênh `log` kể cả khi không được liệt kê: nếu mọi kênh khác hỏng hoặc chưa cấu hình,
    cảnh báo vẫn phải để lại dấu vết ở đâu đó. Cảnh báo biến mất còn tệ hơn không có cảnh báo, vì
    người vận hành tưởng hệ thống đang yên.
    """
    raw = names if names is not None else os.getenv("ALERT_CHANNELS", "log")
    wanted = [n.strip().lower() for n in raw.split(",") if n.strip()]

    if "log" not in wanted:
        wanted.insert(0, "log")

    channels: List[NotificationChannel] = []
    for name in wanted:
        builder = CHANNELS.get(name)
        if builder is None:
            logger.warning("Kênh cảnh báo '%s' không tồn tại — bỏ qua "
                           "(hợp lệ: %s)", name, ", ".join(CHANNELS))
            continue
        channels.append(builder())

    return channels
