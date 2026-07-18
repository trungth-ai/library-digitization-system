#!/usr/bin/env python3
"""
SSE - Server-Sent Events via Redis Pub/Sub
Channel: "job_events"

Event format:
{
    "job_id":   "uuid",
    "status":   "ocr" | "extracting" | "completed" | "failed" | ...,
    "progress": 30,
    "filename": "book.pdf",
    "error":    null | "message"
}
"""

import json
import asyncio
import logging
from typing import AsyncGenerator

import redis.asyncio as aioredis

logger = logging.getLogger("sse")

REDIS_HOST  = __import__("os").getenv("REDIS_HOST", "redis")
REDIS_PORT  = int(__import__("os").getenv("REDIS_PORT", "6379"))

JOB_EVENTS_CHANNEL = "job_events"

# Heartbeat mỗi 15s để giữ kết nối, tránh proxy/load balancer timeout
HEARTBEAT_INTERVAL = 15


def _format_sse(data: dict, event: str = "job_update") -> str:
    """Chuyển dict thành SSE wire format"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _heartbeat() -> str:
    return ": heartbeat\n\n"


async def job_event_stream(job_id: str | None = None) -> AsyncGenerator[str, None]:
    """
    Async generator cho SSE endpoint.

    - job_id=None  → stream tất cả events (dùng cho bảng jobs list)
    - job_id=str   → chỉ stream events của 1 job cụ thể

    Tự động đóng stream khi job đạt terminal status
    (completed / failed / cancelled) nếu đang stream 1 job.
    """
    redis_client = aioredis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True
    )
    pubsub = redis_client.pubsub()

    try:
        await pubsub.subscribe(JOB_EVENTS_CHANNEL)
        logger.info(f"SSE client subscribed — job_id={job_id or 'ALL'}")

        # Gửi connected event để frontend biết stream đã sẵn sàng
        yield _format_sse({"type": "connected", "job_id": job_id}, event="connected")

        while True:
            # Dùng asyncio.wait_for để xen heartbeat định kỳ
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=HEARTBEAT_INTERVAL
                )
            except asyncio.TimeoutError:
                # Không có message → gửi heartbeat giữ kết nối
                yield _heartbeat()
                continue

            if message is None:
                # pubsub trả về None khi không có message mới
                await asyncio.sleep(0.1)
                continue

            # Parse event
            try:
                event_data = json.loads(message["data"])
            except (json.JSONDecodeError, KeyError):
                continue

            # Lọc theo job_id nếu cần
            if job_id and event_data.get("job_id") != job_id:
                continue

            yield _format_sse(event_data)

            # Đóng stream nếu job đã kết thúc (chỉ khi stream 1 job)
            if job_id:
                terminal_statuses = {"completed", "failed", "cancelled"}
                if event_data.get("status") in terminal_statuses:
                    logger.info(f"Job {job_id} reached terminal status, closing SSE stream")
                    yield _format_sse({"type": "done", "job_id": job_id}, event="done")
                    break

    except asyncio.CancelledError:
        # Client ngắt kết nối — bình thường
        logger.info(f"SSE client disconnected — job_id={job_id or 'ALL'}")
    except Exception as e:
        logger.error(f"SSE stream error: {e}")
        yield _format_sse({"type": "error", "message": str(e)}, event="error")
    finally:
        await pubsub.unsubscribe(JOB_EVENTS_CHANNEL)
        await pubsub.close()
        await redis_client.aclose()


def publish_job_event(redis_client, job_id: str, status: str,
                      progress: int, filename: str = "",
                      error: str = None) -> None:
    """
    Publish event đồng bộ — gọi từ worker.py (sync context).

    redis_client: redis.Redis instance (sync) đã có sẵn trong worker
    """
    event = {
        "job_id":   job_id,
        "status":   status,
        "progress": progress,
        "filename": filename,
        "error":    error,
    }
    try:
        redis_client.publish(JOB_EVENTS_CHANNEL, json.dumps(event, ensure_ascii=False))
    except Exception as e:
        logger.error(f"Failed to publish job event for {job_id}: {e}")