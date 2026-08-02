#!/usr/bin/env python3
"""
Log JSON có cấu trúc + che bí mật + luân chuyển tệp (YC-LG-01/04/05/06 — sprint V1).

BA VẤN ĐỀ ĐANG SỬA:
  1. `logging.basicConfig` định dạng chữ thuần (`api.py`, `worker.py`) → không lọc/tổng hợp được,
     và không có cách nào nối các dòng log của cùng một request.
  2. **YC-BM-03 ("không ghi khóa API/mật khẩu ra log") không có cơ chế nào cưỡng chế** — hiện chỉ
     dựa vào việc lập trình viên nhớ. Một dòng `logger.debug(config)` là đủ để rò khóa Claude.
  3. Log chỉ nằm trong container, bị cắt vòng → mất bằng chứng đúng lúc cần điều tra.

Bộ lọc che bí mật gắn ở TẦNG LOGGING, không phải ở nơi gọi: nơi gọi thì có hàng trăm chỗ và mỗi chỗ
mới là một cơ hội quên; tầng logging chỉ có một. Đây là khác biệt giữa "quy ước" và "cơ chế".

Module THUẦN (chỉ dùng thư viện chuẩn) → kiểm thử được, và worker dùng chung với API.
"""

import json
import logging
import logging.handlers
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.core import context

# Trường chuẩn của mỗi dòng log — cố định để công cụ phân tích không phải đoán
_RESERVED = frozenset(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}

MASK = "***"

# ─────────────────────────────────────────────────────────────
# CHE BÍ MẬT (YC-BM-03)
# ─────────────────────────────────────────────────────────────

# Mẫu nhận diện bí mật. Ưu tiên bắt SÓT còn hơn bắt NHẦM: che nhầm một giá trị vô hại chỉ gây khó
# chịu, còn để lọt một khóa API là sự cố bảo mật không thu hồi được sau khi log đã bị sao chép.
# ⚠️ THỨ TỰ QUAN TRỌNG: mẫu Bearer/Basic phải đứng TRƯỚC mẫu `khóa=giá_trị` chung. Nếu ngược lại,
# `Authorization: Bearer eyJ...` sẽ khớp mẫu chung và che mất chữ "Bearer" — để lộ nguyên token phía
# sau. Đúng lỗi mà `test_che_gan_khoa_gia_tri` bắt được.
_SECRET_PATTERNS: List[re.Pattern] = [
    # Khóa API theo tiền tố nhà cung cấp (Anthropic, OpenAI, Google, Groq, HuggingFace)
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{8,})"),
    re.compile(r"\b(AIza[A-Za-z0-9_\-]{10,})"),
    re.compile(r"\b(gsk_[A-Za-z0-9_\-]{8,})"),
    re.compile(r"\b(hf_[A-Za-z0-9]{8,})"),
    # Header Authorization dạng Bearer/Basic — PHẢI trước mẫu chung bên dưới
    re.compile(r"\b((?:Bearer|Basic)\s+)([A-Za-z0-9._\-+/=]{8,})"),
    # gán khóa=giá trị: api_key=..., password: ..., "token": "..."
    # `['\"]?\s*` sau tên khóa để bắt được cả dạng JSON `{"token": "..."}` — dạng hay gặp nhất khi
    # ai đó log nguyên một payload hoặc một dict cấu hình.
    re.compile(
        r"((?:api[_\-]?key|apikey|secret|password|passwd|pwd|token|authorization|cookie|"
        r"session|credential)s?['\"]?\s*[=:]\s*)(['\"]?)([^\s'\"&,;}\]]{4,})",
        re.IGNORECASE,
    ),
]


def redact(text: str) -> str:
    """
    Che mọi bí mật nhận ra được trong một chuỗi.

    Giữ lại phần TÊN (`api_key=`) và chỉ che phần GIÁ TRỊ: người đọc log vẫn biết được "có khóa API ở
    đây" — thông tin cần cho việc gỡ lỗi — mà không đọc được khóa.
    """
    if not text:
        return text

    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 3:
            text = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)
        elif pattern.groups == 2:
            text = pattern.sub(lambda m: f"{m.group(1)}{MASK}", text)
        else:
            text = pattern.sub(MASK, text)
    return text


class SecretRedactionFilter(logging.Filter):
    """
    Che bí mật trong MỌI bản ghi log, bất kể ai ghi và ghi kiểu gì.

    Che ở `record.msg` và `record.args` TRƯỚC khi định dạng: nếu chỉ che chuỗi đã định dạng thì các
    handler khác (vd handler ghi ra tệp riêng) vẫn nhận được bản gốc chưa che.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _redact_value(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(_redact_value(a) for a in record.args)

        return True      # luôn cho bản ghi đi tiếp — đây là bộ lọc để SỬA, không phải để chặn


def _redact_value(value: Any) -> Any:
    return redact(value) if isinstance(value, str) else value


# ─────────────────────────────────────────────────────────────
# ĐỊNH DẠNG JSON (YC-LG-01)
# ─────────────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """
    Mỗi dòng log là một object JSON hợp lệ, có `request_id`/`job_id`/`actor` lấy từ ngữ cảnh.

    Ngữ cảnh được lấy tại thời điểm ĐỊNH DẠNG chứ không phải lúc gọi `logger.info`: hai thời điểm này
    nằm trong cùng một task nên giá trị như nhau, và làm cách này thì nơi gọi không phải biết gì về
    `contextvars`.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(context.snapshot())

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        # Trường bổ sung do nơi gọi truyền qua `extra={...}`
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value if _json_safe(value) else repr(value)

        # `ensure_ascii=False` để tiếng Việt đọc được trực tiếp trong tệp log, không thành \uXXXX
        return json.dumps(payload, ensure_ascii=False, default=str)


def _json_safe(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, type(None), list, dict))


# ─────────────────────────────────────────────────────────────
# THIẾT LẬP
# ─────────────────────────────────────────────────────────────

def configure(service: str, level: Optional[str] = None,
              log_format: Optional[str] = None,
              log_dir: Optional[str] = None) -> logging.Logger:
    """
    Thiết lập logging cho một tiến trình (`api` hoặc `worker`). Gọi MỘT LẦN lúc khởi động.

    Van lùi `LOG_FORMAT=text` khôi phục đúng định dạng chữ thuần đang dùng — nếu ai đó quen đọc log
    cũ thấy JSON khó chịu thì đổi một biến là xong, không phải chờ bản vá.

    Bộ lọc che bí mật gắn cho MỌI handler, kể cả ở chế độ `text`: đây là yêu cầu bảo mật (YC-BM-03),
    không phải một tùy chọn hiển thị.
    """
    level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    log_format = (log_format or os.getenv("LOG_FORMAT", "json")).lower()

    root = logging.getLogger()
    root.setLevel(level)

    # Gỡ handler cũ: `logging.basicConfig` ở đầu api.py/worker.py đã gắn một cái, để lại sẽ log đúp
    for handler in list(root.handlers):
        root.removeHandler(handler)

    if log_format == "text":
        formatter: logging.Formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    else:
        formatter = JsonFormatter()

    redaction = SecretRedactionFilter()

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.addFilter(redaction)
    root.addHandler(stream)

    directory = log_dir if log_dir is not None else os.getenv("LOG_DIR", "")
    if directory:
        file_handler = _build_file_handler(directory, service, formatter, redaction)
        if file_handler:
            root.addHandler(file_handler)

    logging.getLogger(service).debug("Logging đã thiết lập: định dạng=%s, mức=%s", log_format, level)
    return logging.getLogger(service)


def _build_file_handler(directory: str, service: str, formatter: logging.Formatter,
                        redaction: logging.Filter):
    """
    Handler ghi tệp JSONL có luân chuyển. Lỗi thì bỏ qua, KHÔNG làm tiến trình không khởi động được.

    Ghi tệp là tiện ích vận hành; không ghi được (thiếu quyền, chưa gắn volume) thì vẫn còn stdout —
    dừng cả API vì không mở được tệp log là đánh đổi sai.
    """
    try:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path / f"{service}.jsonl",
            maxBytes=int(float(os.getenv("LOG_ROTATE_MB", "100")) * 1024 * 1024),
            backupCount=int(os.getenv("LOG_ROTATE_KEEP", "10")),
            encoding="utf-8",
        )
        handler.setFormatter(formatter)
        handler.addFilter(redaction)
        return handler
    except Exception as e:  # noqa: BLE001
        logging.getLogger(service).warning(
            "Không ghi được log ra thư mục '%s' (%s) — chỉ ghi stdout", directory, e)
        return None
