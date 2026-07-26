#!/usr/bin/env python3
"""
Kiểm thử `DigitizationWorker.process_job` — đường xử lý tài liệu THẬT (ADR-008).

Đây là code rủi ro nhất trong lần nâng cấp: nó chạy trên hệ đang phục vụ. Test dùng Redis giả + DB giả
+ pipeline giả → chạy được không cần hạ tầng, và kiểm đúng những gì dễ sai khi nối lớp provider:
  - Tài liệu bình thường: trạng thái đi đúng chuỗi, metadata được lưu.
  - Tài liệu cần xem lại: vẫn 'completed' (OCR xong) nhưng có cờ để UI thấy.
  - Vi phạm độ nhạy cảm: job THẤT BẠI có mô tả + ghi bằng chứng từ chối cho kiểm toán.
  - Cờ USE_PROVIDER_LAYER=0: lùi được về đường cũ.

Chạy: pytest tests/test_worker_job.py -v
"""

import json
import pytest

from scripts.core.exceptions import SensitivityViolation


class _FakeRedis:
    """Redis giả: chỉ cần hset/publish cho luồng này."""

    def __init__(self):
        self.hashes = {}
        self.published = []

    def hset(self, name, mapping=None, **kwargs):
        self.hashes.setdefault(name, {}).update(mapping or {})

    def publish(self, channel, message):
        self.published.append((channel, message))


class _FakePipeline:
    """Pipeline giả: bỏ qua OCR, chỉ trả về summary như pipeline thật."""

    instances = []

    def __init__(self, config=None, claude_api_key=None, metadata_extractor=None):
        self.config = config
        self.metadata_extractor = metadata_extractor
        _FakePipeline.instances.append(self)

    def process(self, input_pdf, output_dir):
        return {"summary": {"status": "completed", "output_pdf": "/data/out/x.pdf"}}


class _DeniedPipeline(_FakePipeline):
    """Pipeline giả mô phỏng ràng buộc cứng độ nhạy cảm nổi lên từ tầng dưới."""

    def process(self, input_pdf, output_dir):
        raise SensitivityViolation(
            "Tài liệu độ nhạy cảm 'sensitive' không được xử lý bằng chế độ đám mây"
        )


class _FailingPipeline(_FakePipeline):
    def process(self, input_pdf, output_dir):
        return {"summary": {"status": "failed", "error": "Ghostscript lỗi"}}


@pytest.fixture
def worker(monkeypatch):
    """Worker với Redis giả, không mở DB pool, và mọi lời gọi DB được ghi lại."""
    import scripts.worker as w

    calls = {"status": [], "metadata": [], "audit": [], "extraction_info": []}

    monkeypatch.setattr(w.db, "update_document_status",
                        lambda job_id, status, **kw: calls["status"].append((job_id, status, kw)))
    monkeypatch.setattr(w.db, "save_metadata",
                        lambda job_id, md: calls["metadata"].append((job_id, md)))
    monkeypatch.setattr(w.audit, "log_action",
                        lambda action, **kw: calls["audit"].append((action, kw)))
    monkeypatch.setattr(w, "publish_job_event", lambda **kw: None)

    instance = w.DigitizationWorker(redis_client=_FakeRedis(), init_db=False)
    instance._test_calls = calls
    _FakePipeline.instances.clear()
    return instance


def _job(job_id="job-1", document_type="book"):
    return {
        "job_id": job_id, "filename": "sach.pdf", "input_file": "/in/sach.pdf",
        "output_dir": "/out/job-1", "document_type": document_type,
    }


def _patch_metadata_file(monkeypatch, metadata):
    """Giả file metadata.json mà pipeline ghi ra đĩa."""
    import scripts.worker as w
    monkeypatch.setattr(w.DigitizationWorker, "_read_metadata", lambda self, out_dir: metadata)


# =====================================================================
# 1. Đường bình thường
# =====================================================================

def test_job_thanh_cong_di_dung_chuoi_trang_thai(worker, monkeypatch):
    import scripts.worker as w
    monkeypatch.setattr(w, "DigitizationPipeline", _FakePipeline)
    monkeypatch.setattr(w, "USE_PROVIDER_LAYER", False)
    _patch_metadata_file(monkeypatch, [{"key": "dc.title", "value": "Sách A"}])

    worker.process_job(_job())

    statuses = [s for _, s, _ in worker._test_calls["status"]]
    assert statuses == ["ocr", "extracting", "exporting", "completed"]
    assert worker._test_calls["metadata"][0][1][0]["key"] == "dc.title"


def test_lop_provider_duoc_tiem_vao_pipeline(worker, monkeypatch):
    """USE_PROVIDER_LAYER bật → pipeline PHẢI nhận ProviderMetadataExtractor, không phải None."""
    import scripts.worker as w
    from scripts.core.extraction import ProviderMetadataExtractor

    monkeypatch.setattr(w, "DigitizationPipeline", _FakePipeline)
    monkeypatch.setattr(w, "USE_PROVIDER_LAYER", True)
    _patch_metadata_file(monkeypatch, [])

    worker.process_job(_job())

    injected = _FakePipeline.instances[0].metadata_extractor
    assert isinstance(injected, ProviderMetadataExtractor)
    assert injected.document_id == "job-1"      # để ghi audit + model_calls đúng tài liệu
    assert injected.actor == "worker"


def test_cờ_tat_thi_lui_ve_duong_cu(worker, monkeypatch):
    """Van an toàn vận hành: USE_PROVIDER_LAYER=0 → không tiêm gì, pipeline dùng AIMetadataExtractor."""
    import scripts.worker as w
    monkeypatch.setattr(w, "DigitizationPipeline", _FakePipeline)
    monkeypatch.setattr(w, "USE_PROVIDER_LAYER", False)
    _patch_metadata_file(monkeypatch, [])

    worker.process_job(_job())
    assert _FakePipeline.instances[0].metadata_extractor is None


def test_loai_tai_lieu_duoc_truyen_vao_config(worker, monkeypatch):
    import scripts.worker as w
    monkeypatch.setattr(w, "DigitizationPipeline", _FakePipeline)
    monkeypatch.setattr(w, "USE_PROVIDER_LAYER", False)
    _patch_metadata_file(monkeypatch, [])

    worker.process_job(_job(document_type="cong_van"))
    assert _FakePipeline.instances[0].config.document_type == "cong_van"


# =====================================================================
# 2. Tài liệu cần cán bộ xem lại (YC-CF-03/04)
# =====================================================================

def test_can_xem_lai_thi_van_completed_nhung_co_co(worker, monkeypatch):
    """
    OCR đã xong nên status là 'completed'; chất lượng trích xuất là chuyện khác → cờ riêng.
    Gộp hai thứ vào status sẽ khiến cán bộ tưởng tài liệu lỗi và xử lý lại OCR vô ích.
    """
    import scripts.worker as w

    class _WithReview(_FakePipeline):
        def __init__(self, **kw):
            super().__init__(**kw)
            if self.metadata_extractor is not None:
                self.metadata_extractor.last_run = {
                    "needs_review": True, "review_note": "Trường điểm tin cậy thấp: dc.publisher",
                    "provider": "ollama", "mode": "local", "model": "qwen2.5:7b",
                    "n_fields": 3, "latency_ms": 1200,
                }

    monkeypatch.setattr(w, "DigitizationPipeline", _WithReview)
    monkeypatch.setattr(w, "USE_PROVIDER_LAYER", True)
    _patch_metadata_file(monkeypatch, [{"key": "dc.title", "value": "Sách A"}])

    worker.process_job(_job())

    assert [s for _, s, _ in worker._test_calls["status"]][-1] == "completed"
    job_hash = worker.redis.hashes["job:job-1"]
    assert job_hash["needs_review"] == "1"
    assert "dc.publisher" in job_hash["review_note"]


# =====================================================================
# 3. Ràng buộc cứng độ nhạy cảm (YC-DR-03)
# =====================================================================

def test_vi_pham_do_nhay_cam_job_that_bai_co_mo_ta(worker, monkeypatch):
    import scripts.worker as w
    monkeypatch.setattr(w, "DigitizationPipeline", _DeniedPipeline)
    monkeypatch.setattr(w, "USE_PROVIDER_LAYER", True)

    worker.process_job(_job())

    job_id, status, kw = worker._test_calls["status"][-1]
    assert status == "failed"
    assert "ràng buộc độ nhạy cảm" in kw["error_message"].lower() or \
           "Từ chối" in kw["error_message"]


def test_vi_pham_do_nhay_cam_ghi_bang_chung_kiem_toan(worker, monkeypatch):
    """KT-BM-06: phải có bằng chứng từ chối trong audit, không chỉ trong log file."""
    import scripts.worker as w
    from scripts.core import audit

    monkeypatch.setattr(w, "DigitizationPipeline", _DeniedPipeline)
    monkeypatch.setattr(w, "USE_PROVIDER_LAYER", True)

    worker.process_job(_job())

    actions = [a for a, _ in worker._test_calls["audit"]]
    assert audit.ACTION_ROUTE_DENIED in actions


def test_loi_thuong_van_ghi_audit_va_khong_lam_worker_chet(worker, monkeypatch):
    import scripts.worker as w
    monkeypatch.setattr(w, "DigitizationPipeline", _FailingPipeline)
    monkeypatch.setattr(w, "USE_PROVIDER_LAYER", False)

    worker.process_job(_job())   # KHÔNG được ném ra ngoài, vòng lặp worker phải sống

    job_id, status, kw = worker._test_calls["status"][-1]
    assert status == "failed" and "Ghostscript" in kw["error_message"]
    assert worker._test_calls["audit"], "lỗi xử lý cũng phải để lại dấu vết kiểm toán"
