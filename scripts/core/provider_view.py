#!/usr/bin/env python3
"""
Dữ liệu hiển thị cho giao diện quản trị công cụ mô hình (YC-MS-08).

VÌ SAO TÁCH RA KHỎI `api.py`: logic ở đây có hai thứ dễ sai và phải kiểm được — (1) tuyệt đối không
để lọt khóa API ra ngoài (YC-BM-03), (2) cấu hình sai phải hiện thành thông báo cho người quản trị
chứ không thành lỗi 500. Đặt trong api.py thì chỉ test được khi có FastAPI + HTTP; đặt ở đây thì test
bằng unit test thuần, chạy được cả khi ngắt mạng.

`api.py` chỉ còn gọi `build_provider_view()` rồi bọc envelope.
"""

import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger("core.provider_view")


def preset_to_dict(preset) -> Dict:
    """
    Mô tả một lựa chọn công cụ cho UI.

    CHỈ trả TÊN biến chứa khóa và việc nó đã được đặt hay chưa — KHÔNG BAO GIỜ trả giá trị khóa.
    Giao diện quản trị cần biết "đã cấu hình chưa", không cần biết khóa là gì.
    """
    return {
        "name": preset.name,
        "label": preset.label,
        "deployment": preset.deployment,
        "base_url": preset.base_url,
        "default_model": preset.default_model,
        "key_env": preset.key_env,
        "key_configured": bool(preset.key_env and os.getenv(preset.key_env)),
        "note": preset.note,
    }


def build_provider_view(check_health: bool = True) -> Dict:
    """
    Toàn bộ dữ liệu cho trang "Công cụ mô hình": công cụ đang dùng + tình trạng, công cụ của từng
    chế độ, chuỗi dự phòng, và danh sách lựa chọn.

    Không ném lỗi: cấu hình sai trả về `current.error` để UI hiện được thông báo tiếng Việt.
    """
    from scripts.providers import fallback
    from scripts.providers.factory import get_provider, resolve_provider_name
    from scripts.providers.registry import list_presets

    view: Dict = {
        "current": None,
        "modes": {
            "cloud": resolve_provider_name("cloud"),
            "local": resolve_provider_name("local"),
        },
        "fallback": fallback.describe_chain(),
        "available": [preset_to_dict(p) for p in list_presets()],
    }

    try:
        provider = get_provider()
        current = provider.describe()
        if check_health:
            health = provider.health()
            current["ready"] = health.ready
            current["detail"] = health.detail
        view["current"] = current
    except ValueError as e:
        # Cấu hình sai: thiếu điểm cuối, tên công cụ lạ, hoặc chốt an toàn "local nhưng điểm cuối
        # công cộng" đã chặn. Đây là thông tin người quản trị CẦN THẤY, không phải lỗi hệ thống.
        logger.warning("Cấu hình công cụ mô hình không dùng được: %s", e)
        view["current"] = {"error": str(e)}
    except Exception as e:  # noqa: BLE001 - trang quản trị không được trắng vì một provider lạ
        logger.error("Không dựng được thông tin provider: %s", e)
        view["current"] = {"error": f"Không đọc được cấu hình công cụ: {e}"}

    return view


def summarize_model_calls(rows: List[Dict]) -> Dict:
    """
    Gộp nhật ký gọi model theo công cụ (YC-MS-07): số lần gọi, thời gian trung bình, RAM đỉnh.

    Dùng cho bảng so sánh công cụ trong hồ sơ — số liệu lấy từ vận hành THẬT, không phải từ harness
    chạy riêng. Trường nào chưa đo được (vd RAM trên Windows) thì để None, KHÔNG bịa 0.
    """
    by_provider: Dict[str, Dict] = {}
    for r in rows:
        key = f"{r.get('provider')}/{r.get('deployment')}"
        agg = by_provider.setdefault(key, {
            "provider": r.get("provider"), "deployment": r.get("deployment"),
            "calls": 0, "failed": 0, "fallbacks": 0, "total_latency_ms": 0,
            "latency_samples": 0, "max_rss_mb": None, "total_fields": 0,
        })
        agg["calls"] += 1
        if r.get("status") == "failed" or r.get("error"):
            agg["failed"] += 1
        if r.get("fallback_from"):
            agg["fallbacks"] += 1
        if r.get("latency_ms") is not None:
            agg["total_latency_ms"] += r["latency_ms"]
            agg["latency_samples"] += 1
        if r.get("rss_mb") is not None:
            agg["max_rss_mb"] = max(agg["max_rss_mb"] or 0, r["rss_mb"])
        agg["total_fields"] += r.get("n_fields") or 0

    out = []
    for agg in by_provider.values():
        samples = agg.pop("latency_samples")
        total = agg.pop("total_latency_ms")
        agg["avg_latency_ms"] = round(total / samples, 1) if samples else None
        agg["avg_fields"] = round(agg["total_fields"] / agg["calls"], 1) if agg["calls"] else 0
        out.append(agg)

    # Nhiều lần gọi nhất lên trước — đó là công cụ đang gánh việc thật
    out.sort(key=lambda a: a["calls"], reverse=True)
    return {"by_provider": out, "total_calls": sum(a["calls"] for a in out)}
