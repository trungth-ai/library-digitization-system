#!/usr/bin/env python3
"""
Kiểm thử nạp từ ZIP (sprint V5) — KT-BU-10, KT-BM-20.

Ba nhóm rủi ro của việc giải nén tệp do người dùng cung cấp, mỗi nhóm một khối test:
zip-slip (ghi đè tệp hệ thống), zip bomb (làm đầy đĩa), và nội dung không hợp lệ.
"""

import zipfile
from pathlib import Path

import pytest

from scripts.core import ingest_zip

PDF_BYTES = b"%PDF-1.7\n" + b"noi dung tai lieu " * 50


def _tao_zip(path: Path, muc: dict) -> Path:
    """`muc` = {tên_trong_zip: nội_dung_bytes}"""
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in muc.items():
            archive.writestr(name, content)
    return path


# ─────────────────────────────────────────────────────────────
# GIẢI NÉN BÌNH THƯỜNG
# ─────────────────────────────────────────────────────────────

def test_giai_nen_cac_tep_pdf(tmp_path):
    zip_path = _tao_zip(tmp_path / "lo.zip", {
        "a.pdf": PDF_BYTES, "b.pdf": PDF_BYTES,
    })

    result = ingest_zip.extract_pdfs(zip_path, tmp_path / "ra")

    assert result.ok
    assert len(result.entries) == 2
    assert all(e.path.exists() for e in result.entries)


def test_giu_ten_thu_muc_lam_goi_y_bo_suu_tap(tmp_path):
    """
    Cán bộ thường nén theo cấu trúc thư mục — thông tin đó có ích cho phân loại.

    Chỉ là GỢI Ý: con người vẫn quyết định bộ sưu tập (nguyên tắc SRS).
    """
    zip_path = _tao_zip(tmp_path / "lo.zip", {"Cong van 2026/Quy 1/a.pdf": PDF_BYTES})

    result = ingest_zip.extract_pdfs(zip_path, tmp_path / "ra")

    assert result.entries[0].folder == "Cong van 2026/Quy 1"
    assert result.entries[0].filename == "a.pdf"


def test_ten_tep_tieng_viet_trong_zip(tmp_path):
    zip_path = _tao_zip(tmp_path / "lo.zip", {"Báo cáo tổng kết.pdf": PDF_BYTES})

    result = ingest_zip.extract_pdfs(zip_path, tmp_path / "ra")

    assert len(result.entries) == 1
    assert result.entries[0].filename == "Báo cáo tổng kết.pdf"


def test_ten_trung_nhau_khong_ghi_de(tmp_path):
    """Hai thư mục cùng chứa `bao-cao.pdf` — ghi đè lặng lẽ là mất một tài liệu."""
    zip_path = _tao_zip(tmp_path / "lo.zip", {
        "thu-muc-1/bao-cao.pdf": PDF_BYTES,
        "thu-muc-2/bao-cao.pdf": PDF_BYTES + b"khac",
    })

    result = ingest_zip.extract_pdfs(zip_path, tmp_path / "ra")

    assert len(result.entries) == 2
    assert len({e.path for e in result.entries}) == 2, "hai tệp phải ghi ra hai đường dẫn khác nhau"


def test_bo_qua_tep_khong_phai_pdf_kem_ly_do(tmp_path):
    """Nạp 300 tệp mà chỉ báo "30 tệp lỗi" là vô dụng — phải nói rõ từng tệp vì sao."""
    zip_path = _tao_zip(tmp_path / "lo.zip", {
        "tot.pdf": PDF_BYTES,
        "anh.jpg": b"\xff\xd8\xff\xe0anh",
        "gia.pdf": b"\xff\xd8\xff\xe0day la anh doi ten",
    })

    result = ingest_zip.extract_pdfs(zip_path, tmp_path / "ra")

    assert len(result.entries) == 1
    assert len(result.skipped) == 2
    ly_do = {s["code"] for s in result.skipped}
    assert "not_pdf_extension" in ly_do
    assert "not_pdf_content" in ly_do


def test_tep_gia_bi_xoa_khoi_dia(tmp_path):
    """Tệp không dùng được không được để lại trên đĩa — nó sẽ tích lũy và không ai dọn."""
    ra = tmp_path / "ra"
    zip_path = _tao_zip(tmp_path / "lo.zip", {"gia.pdf": b"\xff\xd8\xff\xe0anh"})

    ingest_zip.extract_pdfs(zip_path, ra)

    assert list(ra.glob("*.pdf")) == []


# ─────────────────────────────────────────────────────────────
# CHỐNG ZIP-SLIP 🔴
# ─────────────────────────────────────────────────────────────

def test_chan_zip_slip_khong_ghi_ra_ngoai_thu_muc(tmp_path):
    """
    🔴 KT-BM-20: mục tên `../../../thoat.pdf` KHÔNG được ghi ra ngoài thư mục đích.

    Hai lớp bảo vệ cùng chặn ca này: `check_filename` từ chối tên chứa `..`, và
    `safe_extract_path` kiểm đường dẫn đã phân giải. Test khẳng định kết quả cuối: không có tệp nào
    xuất hiện bên ngoài.
    """
    ngoai = tmp_path / "ngoai"
    ngoai.mkdir()
    ra = tmp_path / "ra"

    zip_path = tmp_path / "doc.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("../../ngoai/thoat.pdf", PDF_BYTES)
        archive.writestr("binh-thuong.pdf", PDF_BYTES)

    result = ingest_zip.extract_pdfs(zip_path, ra)

    assert list(ngoai.iterdir()) == [], "🔴 tệp đã thoát ra ngoài thư mục đích"
    assert len(result.entries) == 1
    assert result.entries[0].filename == "binh-thuong.pdf"

    # Mục độc hại phải bị TỪ CHỐI RÕ RÀNG, không được âm thầm nhận dưới tên đã cắt đường dẫn.
    # Bản đầu chỉ ghi theo tên tệp nên tệp không thoát ra được — an toàn, nhưng an toàn nhờ tình cờ:
    # không có dấu vết nào cho biết vừa nhận một tệp nén có ý đồ.
    assert len(result.skipped) == 1
    assert result.skipped[0]["code"] == "unsafe_path"


def test_moi_tep_giai_nen_deu_nam_trong_thu_muc_dich(tmp_path):
    ra = tmp_path / "ra"
    zip_path = _tao_zip(tmp_path / "lo.zip", {
        "a/b/c/sau.pdf": PDF_BYTES, "ngay.pdf": PDF_BYTES,
    })

    result = ingest_zip.extract_pdfs(zip_path, ra)

    for entry in result.entries:
        assert entry.path.resolve().is_relative_to(ra.resolve())


# ─────────────────────────────────────────────────────────────
# CHỐNG ZIP BOMB 🔴
# ─────────────────────────────────────────────────────────────

def test_chan_zip_bomb_ty_le_nen_bat_thuong(tmp_path):
    """
    🔴 Tệp nén 1 MB giải nén thành 10 GB sẽ làm đầy đĩa.

    Kiểm trên SIÊU DỮ LIỆU trước khi ghi byte nào — phát hiện sau khi đã ghi 10 GB thì đĩa đã đầy.
    """
    zip_path = tmp_path / "bom.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bom.pdf", b"\x00" * (20 * 1024 * 1024))   # nén cực tốt

    hop_le, ly_do = ingest_zip.inspect(zip_path)

    assert hop_le is False
    assert "tỉ lệ nén" in ly_do


def test_chan_qua_nhieu_muc(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_zip, "MAX_ENTRIES", 3)
    zip_path = _tao_zip(tmp_path / "lo.zip", {f"{i}.pdf": PDF_BYTES for i in range(5)})

    hop_le, ly_do = ingest_zip.inspect(zip_path)

    assert hop_le is False
    assert "5 mục" in ly_do and "3" in ly_do


def test_chan_vuot_dung_luong_sau_giai_nen(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_zip, "MAX_UNCOMPRESSED_MB", 0)
    zip_path = _tao_zip(tmp_path / "lo.zip", {"a.pdf": PDF_BYTES})

    hop_le, ly_do = ingest_zip.inspect(zip_path)

    assert hop_le is False
    assert "giải nén" in ly_do


def test_zip_bi_chan_thi_khong_ghi_gi_ra_dia(tmp_path, monkeypatch):
    """Từ chối phải xảy ra TRƯỚC khi ghi — đây là toàn bộ ý nghĩa của việc kiểm siêu dữ liệu."""
    monkeypatch.setattr(ingest_zip, "MAX_ENTRIES", 1)
    ra = tmp_path / "ra"
    zip_path = _tao_zip(tmp_path / "lo.zip", {"a.pdf": PDF_BYTES, "b.pdf": PDF_BYTES})

    result = ingest_zip.extract_pdfs(zip_path, ra)

    assert result.ok is False
    assert not ra.exists() or list(ra.iterdir()) == []


# ─────────────────────────────────────────────────────────────
# TỆP HỎNG
# ─────────────────────────────────────────────────────────────

def test_zip_hong_bao_loi_tieng_viet(tmp_path):
    tep = tmp_path / "hong.zip"
    tep.write_bytes(b"day khong phai zip")

    hop_le, ly_do = ingest_zip.inspect(tep)

    assert hop_le is False
    assert "hỏng" in ly_do or "ZIP" in ly_do


def test_zip_rong_khong_gay_loi(tmp_path):
    zip_path = _tao_zip(tmp_path / "rong.zip", {})

    result = ingest_zip.extract_pdfs(zip_path, tmp_path / "ra")

    assert result.ok
    assert result.entries == []
