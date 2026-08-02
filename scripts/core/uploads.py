#!/usr/bin/env python3
"""
Ghi tệp tải lên theo mảnh, không chặn event loop, băm SHA-256 trong cùng lượt đọc (ADR-010).

VÌ SAO LÀ MODULE RIÊNG chứ không nằm trong `api.py`: `scripts/api.py` import `fastapi` và **mở kết nối
Redis ngay lúc import** (raise nếu không nối được), nên trên máy dev không cài hai gói đó thì không
import được → không kiểm thử được. Tách phần logic thuần ra đây, `api.py` chỉ tiêm `offload` vào.
Cùng lý do đã đưa `_redis_exception_classes()` ra mức module ở `worker.py` (ADR-009): **thứ gì cần
kiểm thử thì phải với tới được.**

LỖI ĐANG SỬA (N-03): `save_upload_file` cũ dùng `shutil.copyfileobj` đồng bộ bên trong `async def`,
nên ghi một tệp lớn xuống đĩa làm đóng băng toàn bộ API — SSE của mọi client bị ngắt, mọi request khác
treo. Đây là loại lỗi không ai báo vì nó biểu hiện thành "giao diện thỉnh thoảng chậm".
"""

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

# Đủ nhỏ để event loop mượt, đủ lớn để không tạo quá nhiều lượt chuyển thread.
DEFAULT_CHUNK_SIZE = 1024 * 1024


@dataclass
class UploadResult:
    """Kết quả ghi tệp. `chunks` để kiểm chứng ĐÃ ghi theo mảnh thật, không phải ghi một lần."""
    sha256: str
    size_bytes: int
    chunks: int


def _write_and_hash(buffer: Any, hasher: Any, chunk: bytes) -> None:
    """
    Ghi một mảnh và cập nhật hash — chạy TRONG thread pool.

    Gộp hai việc vào một lời gọi có chủ đích: `hashlib.update` trên mảnh 1 MB tốn vài ms CPU, đủ để
    không nên chạy trên event loop; mà tách thành hai lời gọi thread pool thì tốn thêm một lượt
    chuyển thread mà không được gì.
    """
    buffer.write(chunk)
    hasher.update(chunk)


async def _default_offload(fn: Callable, *args: Any) -> Any:
    """
    Đẩy việc chặn sang thread khác bằng thư viện chuẩn.

    `api.py` truyền `run_in_threadpool` của Starlette thay cho hàm này để dùng đúng thread pool có
    giới hạn của web server. Hàm này là mặc định cho CLI/script/kiểm thử.
    """
    return await asyncio.to_thread(fn, *args)


async def save_stream(
    read: Callable[[int], Awaitable[bytes]],
    destination: Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    offload: Optional[Callable[..., Awaitable[Any]]] = None,
) -> UploadResult:
    """
    Đọc từ `read` theo mảnh, ghi xuống `destination`, trả về hash + dung lượng.

    Tham số:
        read       — hàm bất đồng bộ `read(n) -> bytes` (khớp `UploadFile.read` của Starlette).
                     Trả về `b""` là hết tệp.
        offload    — hàm bất đồng bộ `offload(fn, *args)` để chạy phép ghi ngoài event loop.
                     `None` = dùng `asyncio.to_thread`.

    SHA-256 tính luôn ở đây vì đang mở đúng tệp đó rồi: lấy bây giờ là **miễn phí**, thêm sau sẽ tốn
    một lượt đọc toàn bộ tệp cho mỗi tài liệu. Dùng cho chống trùng tài liệu (YC-BU-04).
    """
    run = offload or _default_offload
    hasher = hashlib.sha256()
    total_bytes = 0
    chunks = 0

    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("wb") as buffer:
        while True:
            chunk = await read(chunk_size)
            if not chunk:
                break
            # Điểm nhường quyền cho event loop: đây chính là thứ bản cũ không có
            await run(_write_and_hash, buffer, hasher, chunk)
            total_bytes += len(chunk)
            chunks += 1

    return UploadResult(sha256=hasher.hexdigest(), size_bytes=total_bytes, chunks=chunks)


def hash_file(path: Path, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """
    Băm SHA-256 một tệp đã nằm trên đĩa (đồng bộ).

    Dùng cho tệp KHÔNG đi qua đường tải lên: thư mục theo dõi, giải nén ZIP, tài liệu cũ cần tính
    hash bù. Đường tải lên không dùng hàm này — ở đó hash đã có sẵn từ `save_stream`.
    """
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()
