#!/usr/bin/env python3
"""
Test LocalProvider (mock HTTP, không cần Ollama thật) + factory chọn provider theo cấu hình.
Chạy: pytest tests/test_local_and_factory.py -v
"""

import json
import pytest

from scripts.providers.local import LocalProvider
from scripts.providers.factory import get_provider
from scripts.providers.base import ExtractionSchema, ModelProvider

BOOK_SCHEMA = ExtractionSchema(code="dublin_core", document_type="book")

CANNED = (
    '{"title":"Giáo trình CSDL","authors":["Phạm, E"],"subjects":["CSDL","SQL"],'
    '"abstract":"Tóm tắt.","type":"Book","language":"vi"}'
)


def test_local_extract_giong_build_metadata(monkeypatch):
    """extract_fields (mock Ollama trả JSON) → khớp _build_metadata trên cùng dict."""
    prov = LocalProvider(model="test-model")
    monkeypatch.setattr(prov, "_call_generate", lambda prompt: CANNED)

    result = prov.extract_fields("nội dung", BOOK_SCHEMA).to_metadata_list()

    # so khớp với parser dùng chung
    expected = prov._extractor._build_metadata(json.loads(CANNED))["metadata"]
    assert result == expected
    assert any(f["key"] == "dc.title" and f["value"] == "Giáo trình CSDL" for f in result)


def test_local_fallback_khi_loi_khong_mat_du_lieu(monkeypatch):
    """YC-MP-05: Ollama lỗi → fallback basic extraction, không ném ra ngoài, không mất dữ liệu."""
    prov = LocalProvider(model="test-model")

    def _boom(prompt):
        raise RuntimeError("Ollama chết")

    monkeypatch.setattr(prov, "_call_generate", _boom)
    result = prov.extract_fields("Tiêu đề tài liệu\nnội dung", BOOK_SCHEMA).to_metadata_list()

    # basic extraction luôn có dc.title + dc.type
    keys = [f["key"] for f in result]
    assert "dc.title" in keys and "dc.type" in keys


def test_local_embed(monkeypatch):
    prov = LocalProvider(model="test-embed")
    monkeypatch.setattr(prov, "_post_json", lambda path, payload: {"embedding": [0.1, 0.2, 0.3]})
    vecs = prov.embed(["a", "b"])
    assert vecs == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]


def test_local_health_khi_khong_co_ollama():
    """Không có Ollama chạy → health ready=False (không ném lỗi)."""
    prov = LocalProvider(base_url="http://localhost:59999")  # cổng chắc chắn không có
    h = prov.health()
    assert h.ready is False
    assert "không phản hồi" in h.detail.lower() or "ollama" in h.detail.lower()


# --- Factory (YC-MP-04) ---
# Lưu ý: `cloud`/`local` là BÍ DANH CHẾ ĐỘ; `name` giờ là tên CÔNG CỤ cụ thể (claude/ollama/...),
# còn chế độ triển khai nằm ở `deployment`.

def test_factory_chon_cloud(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "cloud")
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    monkeypatch.delenv("CLOUD_PROVIDER", raising=False)
    p = get_provider()
    assert isinstance(p, ModelProvider)
    assert p.name == "claude"
    assert p.deployment == "cloud"


def test_factory_chon_local(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_MODEL", "qwen2.5:7b")
    monkeypatch.delenv("LOCAL_PROVIDER", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    p = get_provider()
    assert p.name == "ollama"          # công cụ tại chỗ MẶC ĐỊNH, không phải chế độ
    assert p.deployment == "local"
    assert p.model == "qwen2.5:7b"     # tên biến cũ LOCAL_MODEL vẫn có hiệu lực


def test_factory_mac_dinh_la_cloud(monkeypatch):
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("CLOUD_PROVIDER", raising=False)
    p = get_provider()
    # mặc định giữ nguyên hành vi hiện tại: Claude trên đám mây
    assert p.name == "claude" and p.deployment == "cloud"


def test_factory_kind_khong_hop_le(monkeypatch):
    with pytest.raises(ValueError):
        get_provider(kind="cong-cu-khong-ton-tai")
