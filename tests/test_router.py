#!/usr/bin/env python3
"""
Test định tuyến theo độ nhạy cảm (YC-DR). Chạy: pytest tests/test_router.py -v
"""

import pytest

from scripts.providers.router import resolve_mode, get_routed_provider, MODE_CLOUD, MODE_LOCAL
from scripts.providers.base import (
    ExtractionSchema, SENSITIVITY_PUBLIC, SENSITIVITY_INTERNAL, SENSITIVITY_SENSITIVE,
)
from scripts.core.exceptions import SensitivityViolation


def _schema(sensitivity, code="s"):
    return ExtractionSchema(code=code, document_type="x", fields=[], sensitivity=sensitivity)


# --- Công khai ---
def test_public_mac_dinh_cloud():
    assert resolve_mode(_schema(SENSITIVITY_PUBLIC)) == MODE_CLOUD

def test_public_co_the_chon_local():
    assert resolve_mode(_schema(SENSITIVITY_PUBLIC), "local") == MODE_LOCAL


# --- YC-DR-02: mặc định an toàn ---
def test_khong_ro_do_nhay_cam_ve_local():
    assert resolve_mode(_schema("")) == MODE_LOCAL
    assert resolve_mode(_schema("linh_tinh")) == MODE_LOCAL
    assert resolve_mode(_schema(None)) == MODE_LOCAL


# --- Nội bộ / Nhạy cảm: bắt buộc local ---
def test_internal_mac_dinh_local():
    assert resolve_mode(_schema(SENSITIVITY_INTERNAL)) == MODE_LOCAL

def test_sensitive_mac_dinh_local():
    assert resolve_mode(_schema(SENSITIVITY_SENSITIVE)) == MODE_LOCAL

def test_internal_chon_local_van_local():
    assert resolve_mode(_schema(SENSITIVITY_INTERNAL), "local") == MODE_LOCAL


# --- YC-DR-03: ràng buộc cứng — không ghi đè được ---
def test_internal_chon_cloud_bi_tu_choi():
    with pytest.raises(SensitivityViolation):
        resolve_mode(_schema(SENSITIVITY_INTERNAL), "cloud")

def test_sensitive_chon_cloud_bi_tu_choi():
    with pytest.raises(SensitivityViolation):
        resolve_mode(_schema(SENSITIVITY_SENSITIVE), "cloud")


# --- get_routed_provider ---
def test_routed_provider_public_cloud(monkeypatch):
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    provider, mode = get_routed_provider(_schema(SENSITIVITY_PUBLIC))
    assert mode == MODE_CLOUD and provider.name == "cloud"

def test_routed_provider_internal_local():
    provider, mode = get_routed_provider(_schema(SENSITIVITY_INTERNAL))
    assert mode == MODE_LOCAL and provider.name == "local"

def test_routed_provider_sensitive_cloud_bi_tu_choi():
    """Ràng buộc cứng chặn TRƯỚC khi tạo provider."""
    with pytest.raises(SensitivityViolation):
        get_routed_provider(_schema(SENSITIVITY_SENSITIVE), requested_mode="cloud")
