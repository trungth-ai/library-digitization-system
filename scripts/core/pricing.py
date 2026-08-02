#!/usr/bin/env python3
"""
Tính chi phí mỗi lần gọi model (YC-AN-04 — sprint V2).

HAI QUY TẮC CHI PHỐI:

1. **Tiền là SỐ NGUYÊN, không bao giờ dấu phẩy động** (quy ước dự án). Đơn giá model rất nhỏ
   (vài USD trên MỘT TRIỆU token) nên tính bằng `float` rồi cộng dồn hàng nghìn lượt gọi sẽ tích lũy
   sai số. Ở đây tính bằng **micro-USD** (1 USD = 1.000.000) rồi quy sang **VNĐ nguyên**.

2. **Chế độ tại chỗ = 0 đồng.** Model chạy trên máy chủ Nhà trường không phát sinh chi phí theo lượt
   gọi. Điện và phần cứng là chi phí có thật nhưng không quy được về từng lượt gọi, nên gán 0 và nói
   rõ điều đó trên giao diện — gán một con số bịa ra sẽ vi phạm nguyên tắc "đo được mới tuyên bố".

Bảng đơn giá nằm ở đây chứ không trong mã gọi, và đọc đè được bằng tệp JSON (`MODEL_PRICING_FILE`):
đơn giá nhà cung cấp thay đổi theo thời gian, không nên phải sửa mã và build lại image mỗi lần.

Module THUẦN → kiểm thử được.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger("core.pricing")

# Tỉ giá quy đổi USD → VNĐ. Bắt buộc cấu hình; mặc định là một con số hợp lý để hệ thống chạy được
# ngay, nhưng báo cáo chi phí PHẢI ghi rõ tỉ giá đã dùng — nếu không, con số VNĐ không kiểm chứng được.
DEFAULT_USD_VND_RATE = 25000

# Đơn giá theo micro-USD cho MỘT TRIỆU token (đơn vị nhà cung cấp hay dùng), tách giá vào/ra.
# Số liệu tham khảo, phải đối chiếu lại với bảng giá chính thức trước khi dùng cho báo cáo tài chính.
_DEFAULT_PRICING: Dict[str, Dict[str, int]] = {
    # provider/model → {"in": micro-USD/1M token vào, "out": micro-USD/1M token ra}
    "claude:claude-sonnet-4":     {"in": 3_000_000,  "out": 15_000_000},
    "claude:claude-opus-4":       {"in": 15_000_000, "out": 75_000_000},
    "claude:claude-haiku-3-5":    {"in": 800_000,    "out": 4_000_000},
    "openai:gpt-4o":              {"in": 2_500_000,  "out": 10_000_000},
    "openai:gpt-4o-mini":         {"in": 150_000,    "out": 600_000},
    "gemini:gemini-1.5-pro":      {"in": 1_250_000,  "out": 5_000_000},
    "gemini:gemini-1.5-flash":    {"in": 75_000,     "out": 300_000},
}

# Chế độ tại chỗ: không có chi phí theo lượt gọi
LOCAL_DEPLOYMENT = "local"


@dataclass
class Cost:
    """Chi phí một lượt gọi. Cả hai trường đều là SỐ NGUYÊN."""
    micro_usd: int = 0
    vnd: int = 0
    # `False` khi không tìm được đơn giá — giao diện phải phân biệt "0 đồng vì chạy tại chỗ" với
    # "không biết vì chưa có đơn giá". Hai điều đó dẫn tới hai hành động khác nhau.
    known: bool = True

    def as_dict(self) -> Dict:
        return {"cost_micro_usd": self.micro_usd, "cost_vnd": self.vnd, "cost_known": self.known}


def usd_vnd_rate() -> int:
    """Tỉ giá quy đổi, số nguyên. Giá trị sai/thiếu → dùng mặc định kèm cảnh báo."""
    raw = os.getenv("USD_VND_RATE", "").strip()
    if not raw:
        return DEFAULT_USD_VND_RATE
    try:
        rate = int(float(raw))
        if rate <= 0:
            raise ValueError("tỉ giá phải dương")
        return rate
    except ValueError:
        logger.warning("USD_VND_RATE='%s' không hợp lệ → dùng mặc định %d", raw, DEFAULT_USD_VND_RATE)
        return DEFAULT_USD_VND_RATE


def load_pricing() -> Dict[str, Dict[str, int]]:
    """
    Bảng đơn giá: mặc định trong mã, đọc đè bằng tệp JSON nếu có `MODEL_PRICING_FILE`.

    Đọc đè thay vì thay thế: thêm một model mới vào tệp không làm mất đơn giá của các model khác.
    """
    pricing = dict(_DEFAULT_PRICING)

    path = os.getenv("MODEL_PRICING_FILE", "").strip()
    if not path:
        return pricing

    try:
        with open(path, encoding="utf-8") as f:
            override = json.load(f)
        for key, value in override.items():
            if isinstance(value, dict) and "in" in value and "out" in value:
                pricing[key] = {"in": int(value["in"]), "out": int(value["out"])}
            else:
                logger.warning("Bỏ qua đơn giá không hợp lệ cho '%s' trong %s", key, path)
    except Exception as e:  # noqa: BLE001 - đơn giá hỏng không được làm gãy việc số hóa
        logger.warning("Không đọc được bảng đơn giá '%s' (%s) → dùng bảng trong mã", path, e)

    return pricing


def _lookup(pricing: Dict[str, Dict[str, int]], provider: str,
            model: Optional[str]) -> Optional[Dict[str, int]]:
    """
    Tìm đơn giá theo `provider:model`, lùi dần về khớp tiền tố rồi về provider.

    Lùi dần vì tên model có hậu tố phiên bản/ngày (`claude-sonnet-4-20250514`) mà bảng đơn giá thì
    ghi theo họ model. Không lùi dần thì mỗi lần nhà cung cấp đổi hậu tố là mất đơn giá.
    """
    if model:
        exact = f"{provider}:{model}"
        if exact in pricing:
            return pricing[exact]
        for key, value in pricing.items():
            prefix = key.split(":", 1)[1] if ":" in key else key
            if key.startswith(f"{provider}:") and model.startswith(prefix):
                return value
    return pricing.get(provider)


def compute_cost(provider: str, deployment: str, model: Optional[str] = None,
                 prompt_tokens: Optional[int] = None,
                 completion_tokens: Optional[int] = None) -> Cost:
    """
    Chi phí một lượt gọi. Trả về `Cost` với micro-USD và VNĐ, cả hai là số nguyên.

    Các trường hợp trả `known=False` (không phải 0 đồng, mà là *chưa biết*):
      - công cụ không báo cáo số token;
      - chưa có đơn giá cho model này.
    """
    if deployment == LOCAL_DEPLOYMENT:
        return Cost(micro_usd=0, vnd=0, known=True)     # tại chỗ: chắc chắn 0, không phải "chưa biết"

    if not prompt_tokens and not completion_tokens:
        return Cost(known=False)

    rates = _lookup(load_pricing(), provider, model)
    if not rates:
        logger.debug("Chưa có đơn giá cho %s:%s — chi phí để trống", provider, model)
        return Cost(known=False)

    # Làm tròn xuống ở đơn vị micro-USD: sai số tối đa một phần triệu USD mỗi lượt gọi, không tích
    # lũy thành sai lệch đáng kể, và giữ được tính chất "chỉ dùng số nguyên".
    micro_usd = (
        (prompt_tokens or 0) * rates["in"] // 1_000_000
        + (completion_tokens or 0) * rates["out"] // 1_000_000
    )
    vnd = micro_usd * usd_vnd_rate() // 1_000_000

    return Cost(micro_usd=micro_usd, vnd=vnd, known=True)


def format_vnd(amount: Optional[int]) -> str:
    """
    Định dạng tiền theo quy ước dự án: `N.NNN.NNN đ` (dấu chấm ngăn nhóm nghìn).

    `None` → "chưa có số liệu", KHÔNG phải "0 đ": hiển thị 0 cho dữ liệu chưa biết là nói sai.
    """
    if amount is None:
        return "chưa có số liệu"
    return f"{amount:,.0f}".replace(",", ".") + " đ"
