#!/usr/bin/env python3
"""
Ngữ cảnh của một request / một job — `request_id`, `job_id`, `actor` (YC-LG-02/03 — sprint V1).

VÌ SAO DÙNG `contextvars` CHỨ KHÔNG TRUYỀN THAM SỐ: `actor` cần có mặt ở tầng ghi nhật ký kiểm toán,
tầng gọi model, tầng truy vấn — truyền qua tham số nghĩa là sửa chữ ký của hàng chục hàm và mỗi hàm
mới lại là một cơ hội quên. Đặt vào ngữ cảnh MỘT LẦN ở tầng ngoài cùng (middleware / vòng lặp worker)
thì mọi tầng bên trong lấy được mà không phải biết gì về nhau.

`contextvars` an toàn với asyncio: mỗi task có bản sao riêng, nên hai request chạy song song không
giẫm lên giá trị của nhau — điều mà biến toàn cục hay `threading.local` không bảo đảm dưới async.

Module THUẦN: không import fastapi/psycopg2 → kiểm thử được, và worker (không có fastapi) dùng chung.
"""

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

# Giá trị mặc định là None chứ không phải chuỗi rỗng: "chưa đặt" khác với "đặt bằng rỗng", và khi
# ghi log ta muốn phân biệt được hai điều đó.
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_job_id: ContextVar[Optional[str]] = ContextVar("job_id", default=None)
_actor: ContextVar[Optional[str]] = ContextVar("actor", default=None)


def new_request_id() -> str:
    """
    Sinh mã request mới, ngắn gọn để người vận hành còn đọc/gõ lại được.

    16 ký tự hex (64 bit) là đủ: mục đích là tra cứu trong nhật ký, không phải chống đoán.
    """
    return uuid.uuid4().hex[:16]


# ── Đọc ───────────────────────────────────────────────────────

def get_request_id() -> Optional[str]:
    return _request_id.get()


def get_job_id() -> Optional[str]:
    return _job_id.get()


def get_actor() -> Optional[str]:
    return _actor.get()


def snapshot() -> dict:
    """Toàn bộ ngữ cảnh hiện tại, bỏ trường chưa đặt — dùng để gắn vào dòng log JSON."""
    return {
        key: value
        for key, value in (
            ("request_id", _request_id.get()),
            ("job_id", _job_id.get()),
            ("actor", _actor.get()),
        )
        if value is not None
    }


# ── Ghi ───────────────────────────────────────────────────────

def set_request_id(value: Optional[str]) -> None:
    _request_id.set(value)


def set_actor(value: Optional[str]) -> None:
    _actor.set(value)


def set_job_id(value: Optional[str]) -> None:
    _job_id.set(value)


@contextmanager
def request_context(request_id: Optional[str] = None,
                    actor: Optional[str] = None) -> Iterator[str]:
    """
    Đặt ngữ cảnh cho một request, tự khôi phục giá trị cũ khi thoát.

    Khôi phục bằng token của `contextvars` thay vì đặt lại về None: nếu có ngữ cảnh lồng nhau (một
    request gọi một tiến trình con) thì đặt về None sẽ xóa mất ngữ cảnh của tầng ngoài.
    """
    rid = request_id or new_request_id()
    token_request = _request_id.set(rid)
    token_actor = _actor.set(actor)
    try:
        yield rid
    finally:
        _request_id.reset(token_request)
        _actor.reset(token_actor)


@contextmanager
def job_context(job_id: str, actor: Optional[str] = None) -> Iterator[str]:
    """
    Đặt ngữ cảnh cho toàn bộ vòng đời xử lý một tài liệu trong worker (YC-LG-03).

    Nhờ nó, grep một `job_id` ra được đủ chuỗi OCR → trích xuất → xuất, thay vì phải lần theo dấu
    thời gian giữa nhiều tài liệu đang chạy song song.
    """
    token_job = _job_id.set(job_id)
    token_actor = _actor.set(actor)
    try:
        yield job_id
    finally:
        _job_id.reset(token_job)
        _actor.reset(token_actor)


def clear() -> None:
    """Xóa toàn bộ ngữ cảnh. Chủ yếu cho kiểm thử — mã production nên dùng context manager."""
    _request_id.set(None)
    _job_id.set(None)
    _actor.set(None)
