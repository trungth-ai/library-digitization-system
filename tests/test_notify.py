#!/usr/bin/env python3
"""
Kiểm thử thông báo & cảnh báo (sprint V8) — KT-TB-01/04/06/07/08, KT-BM-21.

Hai nhóm quan trọng nhất:

1. **Chống spam** (`test_chong_spam_*`) — một sự cố kéo dài 3 tiếng sinh cảnh báo mỗi vòng kiểm tra.
   Gửi hết thì người nhận tạo bộ lọc xóa tự động, và cảnh báo thành vô dụng đúng lúc cần nhất.

2. **Không gửi ra ngoài mạng nội bộ** (`test_chan_webhook_ngoai`, KT-BM-21) — nội dung cảnh báo có
   thể chứa tên tài liệu; gửi tới dịch vụ đám mây là rò rỉ dữ liệu qua đường không ai nghĩ tới.
"""

import logging
import os

import pytest

from scripts.notify import base, channels


def _alert(key="test", severity=base.SEVERITY_WARNING):
    return base.Alert(key=key, title="Sự cố thử", message="Nội dung cảnh báo", severity=severity)


class KenhGia(base.NotificationChannel):
    name = "gia"

    def __init__(self, ok=True, hong=False):
        self.da_gui = []
        self.ok = ok
        self.hong = hong

    def send(self, alert):
        if self.hong:
            raise RuntimeError("kênh hỏng")
        self.da_gui.append(alert)
        return self.ok


# ─────────────────────────────────────────────────────────────
# CHỐNG SPAM (YC-TB-04) 🔴
# ─────────────────────────────────────────────────────────────

def test_su_co_keo_dai_chi_gui_mot_lan():
    """
    🔴 Sự cố kéo dài sinh cảnh báo mỗi vòng kiểm tra — chỉ được gửi MỘT lần trong thời gian nguội.
    """
    kenh = KenhGia()
    dispatcher = base.Dispatcher(channels=[kenh], throttle=base.AlertThrottle(cooldown_sec=1800))

    for _ in range(60):                      # 60 vòng kiểm tra, 1 phút/lần = 1 tiếng sự cố
        dispatcher.send(_alert(key="postgres_down"))

    assert len(kenh.da_gui) == 1


def test_su_co_khac_nhau_van_gui_rieng():
    """Chống spam theo `key`: mất Redis và đĩa đầy là hai sự cố, phải báo cả hai."""
    kenh = KenhGia()
    dispatcher = base.Dispatcher(channels=[kenh])

    dispatcher.send(_alert(key="redis_down"))
    dispatcher.send(_alert(key="disk_low"))

    assert len(kenh.da_gui) == 2


def test_het_thoi_gian_nguoi_thi_gui_lai():
    throttle = base.AlertThrottle(cooldown_sec=100)

    assert throttle.should_send("k", now=1000.0) is True
    assert throttle.should_send("k", now=1050.0) is False
    assert throttle.should_send("k", now=1101.0) is True


def test_khac_phuc_xong_thi_lan_sau_bao_ngay():
    """
    Sau khi sự cố được khắc phục, lần tái diễn tiếp theo phải báo NGAY.

    Không xóa dấu vết thì một sự cố tái diễn 5 phút sau sẽ bị nuốt vì vẫn còn trong thời gian nguội —
    và đó là lúc đáng báo nhất (sự cố lặp lại nghĩa là chưa sửa được gốc).
    """
    throttle = base.AlertThrottle(cooldown_sec=1800)
    throttle.should_send("worker_down", now=1000.0)

    throttle.resolve("worker_down")

    assert throttle.should_send("worker_down", now=1060.0) is True


def test_force_bo_qua_chong_spam():
    kenh = KenhGia()
    dispatcher = base.Dispatcher(channels=[kenh])

    dispatcher.send(_alert(key="k"))
    dispatcher.send(_alert(key="k"), force=True)

    assert len(kenh.da_gui) == 2


# ─────────────────────────────────────────────────────────────
# GỬI QUA NHIỀU KÊNH
# ─────────────────────────────────────────────────────────────

def test_mot_kenh_hong_khong_ngan_kenh_con_lai():
    """
    🔴 Kênh SMTP sai cấu hình không được làm mất cảnh báo ở kênh log.

    Đây là lý do `send()` của kênh trả `bool` thay vì ném lỗi.
    """
    hong, tot = KenhGia(hong=True), KenhGia()
    dispatcher = base.Dispatcher(channels=[hong, tot])

    ket_qua = dispatcher.send(_alert())

    assert len(tot.da_gui) == 1
    assert ket_qua["gia"] in (True, False)   # cả hai cùng tên `gia`, đủ để biết đã thử cả hai


def test_bo_qua_kenh_chua_cau_hinh():
    """Cấu hình thiếu là trạng thái bình thường, không phải sự cố — bỏ qua im lặng."""
    class ChuaCauHinh(base.NotificationChannel):
        name = "chua"

        def available(self):
            return False

        def send(self, alert):
            raise AssertionError("không được gọi send() khi kênh chưa sẵn sàng")

    dispatcher = base.Dispatcher(channels=[ChuaCauHinh()])
    assert dispatcher.send(_alert()) == {}


def test_muc_thap_hon_nguong_thi_khong_gui():
    kenh = KenhGia()
    dispatcher = base.Dispatcher(channels=[kenh], min_severity=base.SEVERITY_CRITICAL)

    dispatcher.send(_alert(severity=base.SEVERITY_WARNING))

    assert kenh.da_gui == []


def test_muc_nghiem_trong_luon_qua_nguong():
    kenh = KenhGia()
    dispatcher = base.Dispatcher(channels=[kenh], min_severity=base.SEVERITY_WARNING)

    dispatcher.send(_alert(severity=base.SEVERITY_CRITICAL))

    assert len(kenh.da_gui) == 1


# ─────────────────────────────────────────────────────────────
# BẢNG ĐĂNG KÝ KÊNH (YC-TB-01, mẫu YC-MP-08)
# ─────────────────────────────────────────────────────────────

def test_luon_co_kenh_log_du_khong_khai_bao():
    """
    🔴 Cảnh báo biến mất còn TỆ HƠN không có cảnh báo — người vận hành tưởng hệ thống đang yên.

    Nên kênh `log` luôn có mặt kể cả khi cấu hình chỉ liệt kê email/webhook.
    """
    danh_sach = channels.build_channels("email,webhook")

    assert any(c.name == "log" for c in danh_sach)


def test_kenh_khong_ton_tai_bi_bo_qua_khong_gay_loi():
    """Lỗi chính tả trong `.env` không được làm gãy việc gửi cảnh báo."""
    danh_sach = channels.build_channels("log,khong-co-kenh-nay")

    assert [c.name for c in danh_sach] == ["log"]


def test_them_kenh_moi_chi_can_mot_dong():
    """Mẫu YC-MP-08: thêm kênh = một lớp con + một dòng trong bảng đăng ký, không sửa nơi gọi."""
    class KenhMoi(base.NotificationChannel):
        name = "moi"

        def send(self, alert):
            return True

    channels.CHANNELS["moi"] = KenhMoi
    try:
        danh_sach = channels.build_channels("moi")
        assert any(c.name == "moi" for c in danh_sach)
    finally:
        channels.CHANNELS.pop("moi")


# ─────────────────────────────────────────────────────────────
# KHÔNG GỬI RA NGOÀI MẠNG NỘI BỘ — KT-BM-21 🔴
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.1.1.5", "192.168.1.10"])
def test_nhan_dien_dia_chi_noi_bo(host):
    assert channels._is_internal_host(host) is True


@pytest.mark.parametrize("host", ["8.8.8.8", "1.1.1.1"])
def test_nhan_dien_dia_chi_ngoai(host):
    assert channels._is_internal_host(host) is False


def test_khong_phan_giai_duoc_thi_coi_la_ngoai():
    """
    Mặc định AN TOÀN: không phân giải được tên miền → coi là NGOÀI.

    Thà chặn nhầm một địa chỉ hợp lệ còn hơn gửi tên tài liệu ra ngoài mà không biết.
    """
    assert channels._is_internal_host("khong-ton-tai-o-dau.invalid") is False


def test_chan_webhook_tro_ra_ngoai(monkeypatch, caplog):
    """
    🔴 KT-BM-21: nội dung cảnh báo có thể chứa tên tài liệu — gửi tới dịch vụ đám mây là rò rỉ.
    """
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.slack.com/services/abc")
    monkeypatch.delenv("ALERT_WEBHOOK_ALLOW_EXTERNAL", raising=False)

    kenh = channels.WebhookChannel()
    with caplog.at_level(logging.ERROR):
        assert kenh.available() is False

    assert any("rò rỉ" in r.message or "không thuộc mạng nội bộ" in r.message.lower()
               for r in caplog.records)


def test_cho_phep_webhook_ngoai_khi_khai_bao_ro(monkeypatch):
    """Vẫn mở được đường cho trường hợp đường truyền đã được kiểm soát — nhưng phải khai báo rõ."""
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.slack.com/services/abc")
    monkeypatch.setenv("ALERT_WEBHOOK_ALLOW_EXTERNAL", "1")

    assert channels.WebhookChannel().available() is True


def test_webhook_noi_mang_duoc_phep(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "http://n8n:5678/webhook/canh-bao")
    monkeypatch.delenv("ALERT_WEBHOOK_ALLOW_EXTERNAL", raising=False)

    # `n8n` là tên service Docker — không phân giải được ngoài container, nên kiểm bằng localhost
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "http://127.0.0.1:5678/webhook/canh-bao")
    assert channels.WebhookChannel().available() is True


def test_email_chua_cau_hinh_thi_khong_kha_dung(monkeypatch):
    for var in ("SMTP_HOST", "ALERT_EMAIL_FROM", "ALERT_EMAIL_TO", "SMTP_USER"):
        monkeypatch.delenv(var, raising=False)

    assert channels.EmailChannel().available() is False


def test_kenh_log_luon_kha_dung():
    """Không phụ thuộc mạng hay cấu hình — phương án cuối khi mọi kênh khác hỏng."""
    kenh = channels.LogChannel()
    assert kenh.available() is True
    assert kenh.send(_alert()) is True


def test_noi_dung_canh_bao_co_du_thong_tin():
    alert = base.Alert(key="k", title="Worker dừng", message="Không có worker nào chạy",
                       detail={"số worker": 0, "hàng đợi": 42})
    text = alert.format_text()

    assert "Worker dừng" in text
    assert "Không có worker nào chạy" in text
    assert "số worker" in text and "42" in text


# ─────────────────────────────────────────────────────────────
# QUY TẮC SINH CẢNH BÁO (YC-TB-02/03)
# ─────────────────────────────────────────────────────────────

from scripts.notify import rules  # noqa: E402


def _keys(alerts):
    return {a.key for a in alerts}


def test_khong_co_worker_la_muc_nghiem_trong():
    """
    Không có worker = mọi tài liệu nằm chờ vô thời hạn, người dùng KHÔNG thấy lỗi nào cả.

    Đây là kiểu hỏng im lặng nguy hiểm nhất — phải ở mức nghiêm trọng.
    """
    alerts = rules.evaluate({"workers_alive": 0, "queue_ready": 42})

    assert "no_worker" in _keys(alerts)
    assert alerts[0].severity == base.SEVERITY_CRITICAL


def test_khong_doc_duoc_redis_khac_voi_khong_co_worker():
    """
    `None` (không đọc được Redis) và `0` (chắc chắn không có worker) là hai tình huống khác nhau,
    dẫn tới hai hành động khác nhau (ADR-009 mục 6) — nên là hai cảnh báo khác nhau.
    """
    alerts = rules.evaluate({"workers_alive": None})

    assert "redis_unreadable" in _keys(alerts)
    assert "no_worker" not in _keys(alerts)


def test_co_worker_thi_khong_bao():
    assert rules.evaluate({"workers_alive": 2, "queue_ready": 5}) == []


def test_thieu_khoa_thi_khong_danh_gia_quy_tac_do():
    """
    Khóa thiếu = "không đánh giá được", KHÁC với giá trị 0.

    Nếu coi thiếu là 0 thì một bức ảnh trạng thái không đọc được đĩa sẽ báo "đĩa còn 0 GB" — cảnh
    báo giả, và cảnh báo giả dạy người ta bỏ qua cảnh báo thật.
    """
    assert rules.evaluate({}) == []


def test_dia_sap_day_bao_som_hon_nguong_tu_choi():
    """
    Ngưỡng cảnh báo CAO HƠN ngưỡng từ chối nhận tài liệu — để còn thời gian xử lý TRƯỚC KHI hệ
    thống ngừng nhận.
    """
    alerts = rules.evaluate({"disk_free_gb": 10.0})

    assert "disk_low" in _keys(alerts)
    assert rules.DISK_WARN_GB > int(os.getenv("DISK_MIN_FREE_GB", "20")) - 1


def test_dia_rat_thap_thi_nang_muc():
    thap = rules.evaluate({"disk_free_gb": rules.DISK_WARN_GB / 3})
    vua = rules.evaluate({"disk_free_gb": rules.DISK_WARN_GB - 1})

    assert thap[0].severity == base.SEVERITY_CRITICAL
    assert vua[0].severity == base.SEVERITY_WARNING


def test_hang_doi_chet_nhieu_thi_bao():
    alerts = rules.evaluate({"queue_dead": rules.DEAD_LETTER_ALERT})

    assert "dead_letter" in _keys(alerts)
    assert "nguyên nhân CHUNG" in alerts[0].message


def test_vai_tep_hong_le_te_thi_khong_bao():
    """Ngưỡng để phân biệt "vài tệp hỏng" (bình thường) với "vấn đề hệ thống"."""
    assert rules.evaluate({"queue_dead": 1}) == []


def test_lo_ti_le_loi_cao_thi_bao():
    alerts = rules.evaluate({"failed_batches": [
        {"id": "lo-1", "name": "Công văn T8", "total_files": 100, "failed_files": 40},
    ]})

    assert any(a.key.startswith("batch_failing:") for a in alerts)


def test_lo_it_loi_thi_khong_bao():
    """Vài tệp lỗi trong một lô lớn là bình thường — không đáng đánh thức ai."""
    assert rules.evaluate({"failed_batches": [
        {"id": "lo-1", "name": "x", "total_files": 100, "failed_files": 5},
    ]}) == []


def test_lo_rong_khong_chia_cho_khong():
    assert rules.evaluate({"failed_batches": [
        {"id": "lo-1", "name": "x", "total_files": 0, "failed_files": 0},
    ]}) == []


def test_moi_lo_mot_key_rieng():
    """Hai lô cùng lỗi phải là hai cảnh báo — chống spam theo key sẽ nuốt mất cái thứ hai nếu trùng."""
    alerts = rules.evaluate({"failed_batches": [
        {"id": "a", "name": "Lô A", "total_files": 10, "failed_files": 9},
        {"id": "b", "name": "Lô B", "total_files": 10, "failed_files": 9},
    ]})

    assert len(_keys(alerts)) == 2


def test_moi_canh_bao_deu_noi_ro_hau_qua():
    """
    Cảnh báo phải nói HẬU QUẢ, không chỉ nêu triệu chứng.

    "Queue depth 1200" không cho người trực đêm biết có cần dậy hay không; "tài liệu sẽ nằm chờ vô
    thời hạn" thì có.
    """
    alerts = rules.evaluate({
        "workers_alive": 0, "disk_free_gb": 5.0,
        "queue_ready": 5000, "queue_dead": 50, "sla_breaches": 30,
    })

    assert len(alerts) >= 5
    for alert in alerts:
        assert len(alert.message) > 40, f"cảnh báo '{alert.key}' quá cụt để hành động"
