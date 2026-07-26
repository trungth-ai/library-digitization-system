#!/usr/bin/env python3
"""
Kiểm thử dữ liệu cho giao diện quản trị công cụ mô hình (YC-MS-08) + bảng gộp tài nguyên (YC-MS-07).

Hai điều PHẢI đúng ở đây:
  1. KHÔNG lọt khóa API ra ngoài (YC-BM-03) — trang này liệt kê mọi nhà cung cấp, là chỗ dễ lộ nhất.
  2. Cấu hình sai phải thành THÔNG BÁO cho người quản trị, không thành lỗi 500 / trang trắng.

Chạy: pytest tests/test_provider_view.py -v
"""

import json
import pytest

from scripts.core.provider_view import build_provider_view, preset_to_dict, summarize_model_calls
from scripts.providers.registry import get_preset


# =====================================================================
# 1. Không lộ khóa API
# =====================================================================

def test_khong_bao_gio_tra_ve_gia_tri_khoa(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-khoa-that-khong-duoc-lo")
    data = preset_to_dict(get_preset("openai"))

    assert data["key_env"] == "OPENAI_API_KEY"
    assert data["key_configured"] is True      # chỉ nói ĐÃ ĐẶT, không nói đặt gì
    assert "sk-khoa-that-khong-duoc-lo" not in json.dumps(data)


def test_ca_view_day_du_cung_khong_lo_khoa(monkeypatch):
    """Kiểm cả cây dữ liệu, không chỉ một preset — đây là thứ thật sự đi qua HTTP."""
    for env in ("CLAUDE_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "MOONSHOT_API_KEY"):
        monkeypatch.setenv(env, f"secret-{env}")

    blob = json.dumps(build_provider_view(check_health=False), ensure_ascii=False)
    for env in ("CLAUDE_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "MOONSHOT_API_KEY"):
        assert f"secret-{env}" not in blob
        assert env in blob      # tên biến thì phải có, để người quản trị biết cần đặt gì


def test_bao_dung_khoa_chua_dat(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert preset_to_dict(get_preset("groq"))["key_configured"] is False


# =====================================================================
# 2. Cấu hình sai → thông báo, không phải lỗi 500
# =====================================================================

def test_cau_hinh_sai_tra_ve_thong_bao(monkeypatch):
    """Tên công cụ lạ trong MODEL_PROVIDER: trang quản trị vẫn phải dựng được."""
    monkeypatch.setenv("MODEL_PROVIDER", "cong-cu-khong-ton-tai")
    view = build_provider_view(check_health=False)

    assert "error" in view["current"]
    assert "không hợp lệ" in view["current"]["error"]
    assert view["available"], "danh sách công cụ vẫn phải hiện để người quản trị chọn lại"


def test_chot_an_toan_chan_thi_hien_ly_do(monkeypatch):
    """Điểm cuối công cộng đội lốt tại chỗ → hiện đúng lý do + cách sửa, không im lặng."""
    monkeypatch.setenv("MODEL_PROVIDER", "vllm")
    monkeypatch.setenv("VLLM_BASE_URL", "https://vllm-thue-ngoai.example.com/v1")
    monkeypatch.delenv("ALLOW_PUBLIC_LOCAL_ENDPOINT", raising=False)

    view = build_provider_view(check_health=False)
    assert "YC-DR-03" in view["current"]["error"]


def test_hien_cong_cu_cua_tung_che_do_va_chuoi_du_phong(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "claude")
    monkeypatch.setenv("CLOUD_PROVIDER", "claude")
    monkeypatch.setenv("LOCAL_PROVIDER", "vllm")
    monkeypatch.setenv("LOCAL_FALLBACK_PROVIDERS", "ollama,llamacpp")

    view = build_provider_view(check_health=False)
    assert view["modes"] == {"cloud": "claude", "local": "vllm"}
    assert view["fallback"]["local"] == ["ollama", "llamacpp"]


def test_co_tinh_trang_khi_bat_check_health(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "claude")
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)

    view = build_provider_view(check_health=True)
    assert view["current"]["ready"] is False
    assert "CLAUDE_API_KEY" in view["current"]["detail"]


def test_bo_check_health_thi_khong_co_truong_ready(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "claude")
    view = build_provider_view(check_health=False)
    assert "ready" not in view["current"]
    assert view["current"]["provider"] == "claude"


def test_liet_ke_du_ca_hai_che_do(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "claude")
    names = {p["name"] for p in build_provider_view(check_health=False)["available"]}
    assert {"ollama", "vllm", "llamacpp"} <= names       # tại chỗ
    assert {"claude", "moonshot", "dashscope"} <= names  # đám mây


# =====================================================================
# 3. Bảng gộp tài nguyên (YC-MS-07)
# =====================================================================

def _call(provider="ollama", deployment="local", latency=None, rss=None,
          status="success", error=None, fallback_from=None, n_fields=5):
    return {"provider": provider, "deployment": deployment, "latency_ms": latency,
            "rss_mb": rss, "status": status, "error": error,
            "fallback_from": fallback_from, "n_fields": n_fields}


def test_gop_theo_cong_cu():
    rows = [
        _call("ollama", latency=1000, rss=800.0),
        _call("ollama", latency=2000, rss=1200.5),
        _call("vllm", latency=300, rss=4000.0),
    ]
    out = summarize_model_calls(rows)

    assert out["total_calls"] == 3
    by_name = {a["provider"]: a for a in out["by_provider"]}
    assert by_name["ollama"]["calls"] == 2
    assert by_name["ollama"]["avg_latency_ms"] == 1500.0
    assert by_name["ollama"]["max_rss_mb"] == 1200.5      # RAM ĐỈNH, không phải trung bình
    assert by_name["vllm"]["avg_latency_ms"] == 300.0


def test_khong_bia_so_khi_chua_do_duoc():
    """Windows không đọc được RSS → phải là None, KHÔNG được thành 0 (0 nghĩa là 'đo được và bằng 0')."""
    out = summarize_model_calls([_call(latency=None, rss=None)])
    agg = out["by_provider"][0]
    assert agg["avg_latency_ms"] is None
    assert agg["max_rss_mb"] is None


def test_dem_loi_va_du_phong():
    rows = [
        _call(status="failed", error="máy chủ chết"),
        _call(status="fallback", fallback_from="vllm"),
        _call(),
    ]
    agg = summarize_model_calls(rows)["by_provider"][0]
    assert agg["calls"] == 3 and agg["failed"] == 1 and agg["fallbacks"] == 1


def test_cong_cu_ganh_viec_nhieu_nhat_len_dau():
    rows = [_call("vllm")] + [_call("ollama") for _ in range(3)]
    assert summarize_model_calls(rows)["by_provider"][0]["provider"] == "ollama"


def test_tach_rieng_cung_ten_khac_che_do():
    """Cùng tên công cụ nhưng dựng ở hai nơi → phải là hai dòng, vì dữ liệu đi hai đường khác nhau."""
    rows = [_call("vllm", deployment="local"), _call("vllm", deployment="cloud")]
    assert len(summarize_model_calls(rows)["by_provider"]) == 2


def test_danh_sach_rong():
    assert summarize_model_calls([]) == {"by_provider": [], "total_calls": 0}
