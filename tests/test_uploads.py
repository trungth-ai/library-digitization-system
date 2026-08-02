#!/usr/bin/env python3
"""
Kiểm thử ghi tệp tải lên không chặn event loop (ADR-010, sửa lỗi N-03) — KT-BU-01.

Test quan trọng nhất ở đây là `test_khong_chan_event_loop`: nó **tái hiện đúng lỗi cũ**. Với bản
`shutil.copyfileobj` đồng bộ, tác vụ đếm nhịp song song sẽ không chạy được lần nào trong lúc ghi
tệp — đó chính là triệu chứng "SSE bị ngắt, request khác treo" ở production.

Không cần fastapi/redis: `scripts.core.uploads` là module thuần (xem docstring của nó).
"""

import asyncio
import hashlib
import shutil
import time

import pytest

from scripts.core import uploads


# ─────────────────────────────────────────────────────────────
# HỖ TRỢ: giả lập UploadFile của Starlette (chỉ cần .read)
# ─────────────────────────────────────────────────────────────

class FakeUpload:
    """Giả lập `UploadFile`: chỉ cần hàm `read(n)` bất đồng bộ, đúng phần `save_stream` dùng tới."""

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0
        self.read_calls = 0

    async def read(self, size: int) -> bytes:
        self.read_calls += 1
        chunk = self._data[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk


async def _offload_thread(fn, *args):
    """Giống `run_in_threadpool` của Starlette: chạy hàm chặn ở thread khác, nhường event loop."""
    return await asyncio.to_thread(fn, *args)


# ─────────────────────────────────────────────────────────────
# ĐÚNG DỮ LIỆU
# ─────────────────────────────────────────────────────────────

def test_ghi_dung_noi_dung_va_hash(tmp_path):
    """Nội dung ghi ra phải khớp từng byte, hash và dung lượng phải đúng."""
    data = b"%PDF-1.7\n" + bytes(range(256)) * 500          # ~128 KB
    dest = tmp_path / "tai_lieu.pdf"

    result = asyncio.run(uploads.save_stream(
        read=FakeUpload(data).read, destination=dest, chunk_size=4096,
    ))

    assert dest.read_bytes() == data
    assert result.size_bytes == len(data)
    assert result.sha256 == hashlib.sha256(data).hexdigest()


def test_ghi_theo_manh_thuc_su(tmp_path):
    """
    Phải ghi theo NHIỀU mảnh, không phải một lần.

    Nếu ai đó "tối ưu" thành đọc hết vào RAM rồi ghi một lượt thì test này hỏng — và đúng là phải
    hỏng: đọc cả tệp 200 MB vào RAM là một lỗi khác thay cho lỗi vừa sửa.
    """
    data = b"x" * (10 * 1024)
    dest = tmp_path / "a.pdf"

    result = asyncio.run(uploads.save_stream(
        read=FakeUpload(data).read, destination=dest, chunk_size=1024,
    ))

    assert result.chunks == 10


def test_tep_rong(tmp_path):
    """Tệp 0 byte không được làm hàm lỗi — hash là hash của chuỗi rỗng, có thể phát hiện được."""
    dest = tmp_path / "rong.pdf"

    result = asyncio.run(uploads.save_stream(read=FakeUpload(b"").read, destination=dest))

    assert dest.exists()
    assert result.size_bytes == 0
    assert result.chunks == 0
    assert result.sha256 == hashlib.sha256(b"").hexdigest()


def test_tu_tao_thu_muc_cha(tmp_path):
    """Thư mục chưa tồn tại thì tự tạo — nơi gọi không phải nhớ mkdir trước."""
    dest = tmp_path / "chua" / "co" / "b.pdf"

    asyncio.run(uploads.save_stream(read=FakeUpload(b"abc").read, destination=dest))

    assert dest.read_bytes() == b"abc"


def test_hash_file_khop_voi_save_stream(tmp_path):
    """
    `hash_file` (cho tệp đã nằm trên đĩa) phải cho cùng kết quả với `save_stream`.

    Hai đường nạp khác nhau (tải lên qua web vs. thư mục theo dõi) mà hash lệch nhau thì cơ chế
    chống trùng ở V5 sẽ bỏ sót — hai bản của cùng một tệp bị coi là khác nhau.
    """
    # Có tiếng Việt UTF-8 trong nội dung: hash phải tính trên byte, không qua giải mã văn bản
    data = b"%PDF-1.4 " + "Báo cáo tổng kết năm 2026".encode("utf-8")
    dest = tmp_path / "c.pdf"

    result = asyncio.run(uploads.save_stream(
        read=FakeUpload(data).read, destination=dest, chunk_size=8,
    ))

    assert uploads.hash_file(dest) == result.sha256


# ─────────────────────────────────────────────────────────────
# KHÔNG CHẶN EVENT LOOP — tái hiện lỗi N-03
# ─────────────────────────────────────────────────────────────

def test_khong_chan_event_loop(tmp_path):
    """
    KT-BU-01: trong lúc ghi tệp, event loop phải còn chạy được việc khác.

    Cách đo: chạy song song một tác vụ đếm nhịp mỗi 1ms. Nếu `save_stream` chặn event loop thì tác vụ
    đó không nhích được lần nào. Mỗi phép ghi ở đây bị làm chậm 5ms có chủ ý để mô phỏng đĩa thật —
    tổng 20 mảnh × 5ms = 100ms, đủ dài để tác vụ đếm nhịp phải chạy được nhiều lần.

    ⚠️ Test này CỐ TÌNH tái hiện lỗi cũ: nếu quay về `shutil.copyfileobj` đồng bộ, `ticks` sẽ là 0.
    """
    data = b"y" * (20 * 1024)
    dest = tmp_path / "lon.pdf"
    ticks = 0

    def _ghi_cham(buffer, hasher, chunk):
        time.sleep(0.005)                 # mô phỏng đĩa chậm
        uploads._write_and_hash(buffer, hasher, chunk)

    async def _offload_cham(fn, *args):
        # Bỏ qua `fn` mà gọi bản chậm: chỗ duy nhất cần làm chậm là phép ghi
        return await asyncio.to_thread(_ghi_cham, *args)

    async def scenario():
        nonlocal ticks

        async def dem_nhip():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.001)
                ticks += 1

        nhip = asyncio.create_task(dem_nhip())
        try:
            return await uploads.save_stream(
                read=FakeUpload(data).read, destination=dest,
                chunk_size=1024, offload=_offload_cham,
            )
        finally:
            nhip.cancel()

    result = asyncio.run(scenario())

    assert result.size_bytes == len(data)
    # Ghi mất ~100ms, nhịp 1ms → phải chạy được hàng chục lần. Lấy mốc thấp (5) để test không
    # dao động theo tốc độ máy, nhưng vẫn phân biệt dứt khoát với 0 của bản chặn event loop.
    assert ticks >= 5, f"event loop bị chặn trong lúc ghi tệp (chỉ chạy được {ticks} nhịp)"


def test_bang_chung_ban_dong_bo_chan_event_loop(tmp_path):
    """
    Chốt lại bằng phản chứng: bản ĐỒNG BỘ (`shutil.copyfileobj`) thì đếm nhịp KHÔNG chạy được.

    Không kiểm thử mã production — kiểm thử chính cái giả định làm nên ADR-010, để nếu sau này ai
    đọc lại còn thấy bằng chứng thay vì chỉ thấy lời khẳng định.
    """
    src = tmp_path / "src.bin"
    src.write_bytes(b"z" * (4 * 1024 * 1024))
    dest = tmp_path / "dest.bin"
    ticks = 0

    async def scenario():
        nonlocal ticks

        async def dem_nhip():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.001)
                ticks += 1

        nhip = asyncio.create_task(dem_nhip())
        try:
            # Đúng cách làm của bản cũ: đồng bộ, ngay trên event loop
            with src.open("rb") as fi, dest.open("wb") as fo:
                shutil.copyfileobj(fi, fo)
        finally:
            nhip.cancel()

    asyncio.run(scenario())

    assert dest.stat().st_size == 4 * 1024 * 1024
    assert ticks == 0, "bản đồng bộ lẽ ra phải chặn hoàn toàn event loop"
