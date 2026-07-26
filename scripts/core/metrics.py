#!/usr/bin/env python3
"""
Đo tài nguyên mỗi lần gọi model (YC-MS-07): thời gian, RAM, GPU nếu có.

VÌ SAO CẦN: so sánh Ollama vs vLLM vs llama.cpp không thể chỉ dựa vào độ chính xác — công cụ chính xác
nhất mà ngốn hết RAM máy chủ thì vẫn không dùng được trong vận hành. Trước đây harness chỉ đo thời gian,
phần tài nguyên phải ghi tay bằng `docker stats`.

RÀNG BUỘC: KHÔNG thêm phụ thuộc (không `psutil`) — giữ đúng nguyên tắc chạy được ở môi trường tối giản.
- RAM: đọc `/proc/self/status` (Linux, chính xác nhất) → `resource.getrusage` (POSIX) → None (Windows).
  Máy chủ chạy Linux nên đường chính luôn có số; máy dev Windows trả None và mọi thứ vẫn chạy.
- GPU: chỉ khi bật `METRICS_GPU=1` VÀ có `nvidia-smi`. Cố ý mặc định TẮT: gọi `nvidia-smi` mỗi lần
  trích xuất là chi phí vô ích khi máy không có GPU.
"""

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("core.metrics")


@dataclass
class ResourceSample:
    """Một mẫu đo tài nguyên. Trường nào không đo được thì None — KHÔNG bịa số 0."""
    latency_ms: int = 0
    rss_mb: Optional[float] = None
    gpu_mem_mb: Optional[float] = None


def read_rss_mb() -> Optional[float]:
    """Bộ nhớ thực (RSS) của tiến trình hiện tại, MB. None nếu nền tảng không cho đọc."""
    # Đường 1: /proc/self/status — Linux, đơn vị kB, đọc rẻ
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        pass

    # Đường 2: getrusage — POSIX. ru_maxrss là kB trên Linux, BYTE trên macOS.
    try:
        import resource
        import sys
        max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
        return round(max_rss / divisor, 1)
    except (ImportError, OSError, AttributeError):
        return None   # Windows: không có module resource → chấp nhận không có số


def read_gpu_mem_mb() -> Optional[float]:
    """Bộ nhớ GPU đang dùng (MB) qua nvidia-smi. Chỉ chạy khi METRICS_GPU=1."""
    if os.getenv("METRICS_GPU", "").strip() not in ("1", "true", "yes"):
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        # Nhiều GPU → cộng lại, vì model có thể trải trên nhiều card
        values = [float(v.strip()) for v in out.stdout.split("\n") if v.strip()]
        return round(sum(values), 1) if values else None
    except (FileNotFoundError, subprocess.SubprocessError, ValueError) as e:
        logger.debug("Không đọc được GPU memory: %s", e)
        return None


class measure:
    """
    Context manager đo một lần gọi model.

        with measure() as m:
            result = provider.extract_fields(...)
        m.sample.latency_ms, m.sample.rss_mb

    Đo RSS SAU lời gọi (đỉnh bộ nhớ thường ở đó), không đo delta: điều cần biết cho việc cấp phát
    máy chủ là "tiến trình phình tới đâu", không phải "tăng thêm bao nhiêu".
    """

    def __init__(self, with_gpu: bool = True):
        self.with_gpu = with_gpu
        self.sample = ResourceSample()
        self._t0 = 0.0

    def __enter__(self) -> "measure":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc) -> bool:
        self.sample.latency_ms = int((time.perf_counter() - self._t0) * 1000)
        self.sample.rss_mb = read_rss_mb()
        if self.with_gpu:
            self.sample.gpu_mem_mb = read_gpu_mem_mb()
        return False   # không nuốt ngoại lệ
