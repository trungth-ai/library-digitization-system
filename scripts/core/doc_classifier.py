#!/usr/bin/env python3
"""
Đoán LOẠI TÀI LIỆU (YC-SC-09) — để cán bộ không phải chọn tay từng tệp.

VÌ SAO CẦN: 7 lược đồ biên mục (sách, đề cương, khóa luận, luận văn, hội thảo, báo NCKH, công văn)
chỉ dùng đúng khi loại tài liệu chọn đúng. Bắt cán bộ chọn tay cho từng tệp trong lô 500 tệp là
việc không ai làm nổi — mà chọn sai thì trích xuất theo sai lược đồ, sai từ gốc.

HAI TẦNG, RẺ TRƯỚC ĐẮT SAU:
  1. `suggest_from_filename` — ngay khi chọn tệp, chưa OCR. Miễn phí, chạy được ở trình duyệt lẫn
     máy chủ. Đủ đúng với tên tệp đặt theo quy ước ("KL_NguyenVanA.pdf", "CV 123-QD.pdf").
  2. `suggest_from_text`     — sau OCR, đọc nội dung thật. Vẫn miễn phí (đối sánh từ khóa).
  3. `classify_with_model`   — CHỈ khi hai tầng trên không đủ tự tin. Tốn một lượt gọi model, nên
     không gọi cho mọi tài liệu.

VÌ SAO ĐỐI SÁNH TỪ KHÓA TRƯỚC, KHÔNG GỌI MODEL NGAY:
  - Chạy được khi ngắt mạng (nguyên tắc "mặc định an toàn" — tài liệu nội bộ không ra đám mây).
  - Kiểm thử được không cần dịch vụ ngoài → CI bắt được hồi quy.
  - Không tốn chi phí trên mỗi tài liệu của lô hàng nghìn tệp.
  - Giải thích được: trả về ĐÚNG những từ đã khớp, nên cán bộ kiểm tra được vì sao máy đoán vậy —
    một điểm số trần trụi thì không ai dám tin.

CHỮ CÓ DẤU: OCR tiếng Việt rất hay mất dấu ("luận văn" → "luan van"). Mọi đối sánh đều làm trên bản
ĐÃ BỎ DẤU của cả văn bản lẫn mẫu, nên bản quét xấu vẫn nhận ra được.

Kết quả LUÔN là GỢI Ý. Con người giữ quyền quyết định (nguyên tắc SRS) — không ở đâu trong hệ thống
loại tài liệu đoán được tự động đẩy tài liệu sang DSpace mà không có xác nhận của cán bộ.
"""

import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("core.doc_classifier")

# Mã loại tài liệu dùng khi cán bộ chọn "để hệ thống tự đoán".
AUTO = "auto"

# Loại dùng khi không đoán được gì. 'book' là loại mặc định LỊCH SỬ của hệ đang chạy — giữ nguyên để
# tài liệu không đoán được vẫn đi đúng đường cũ, không hồi quy (KT-KH).
FALLBACK_TYPE = "book"

# Điểm tối thiểu để coi là "có bằng chứng thật", chứ không phải một từ khóa lẻ đi lạc.
MIN_SCORE = float(os.getenv("CLASSIFY_MIN_SCORE", "3.0"))

# Dưới ngưỡng này thì mới đáng gọi model (tầng 3). Đặt cao thì tốn tiền, đặt thấp thì đoán ẩu.
MODEL_CONFIDENCE_THRESHOLD = float(os.getenv("CLASSIFY_MODEL_THRESHOLD", "0.55"))

# Số ký tự đầu văn bản dùng để đoán loại. Dấu hiệu loại tài liệu nằm ở bìa/trang đầu; đọc cả tài
# liệu chỉ làm loãng điểm số vì phần thân bài loại nào cũng giống nhau.
PROBE_CHARS = int(os.getenv("CLASSIFY_PROBE_CHARS", "4000"))


# =====================================================================
# CHUẨN HÓA
# =====================================================================

def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt + hạ chữ thường, để bản quét mất dấu vẫn khớp được mẫu."""
    if not text:
        return ""
    # đ/Đ không phải là 'd' + dấu tổ hợp nên NFD không tách được — phải thay tay trước
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", without_marks).lower()


def _norm(text: str) -> str:
    """Bỏ dấu + gộp mọi khoảng trắng về một dấu cách: xuống dòng giữa cụm từ không được cắt cụm."""
    return re.sub(r"\s+", " ", strip_accents(text))


# =====================================================================
# BỘ DẤU HIỆU THEO LOẠI
# =====================================================================
#
# Trọng số theo mức ĐẶC TRƯNG, không theo mức phổ biến:
#   5.0 — gần như chỉ loại này mới có ("cong hoa xa hoi chu nghia viet nam" ⇒ công văn)
#   3.0 — dấu hiệu mạnh nhưng loại khác cũng có thể có
#   1.5 — dấu hiệu yếu, chỉ có nghĩa khi cộng dồn với dấu hiệu khác
#
# Viết mẫu CÓ DẤU cho người đọc; `_compile` sẽ bỏ dấu khi nạp module.

_SIGNALS_RAW: Dict[str, List[Tuple[str, float]]] = {
    "cong_van": [
        ("cộng hòa xã hội chủ nghĩa việt nam", 5.0),
        ("độc lập - tự do - hạnh phúc", 5.0),
        ("độc lập tự do hạnh phúc", 5.0),
        ("kính gửi", 3.0),
        ("nơi nhận", 3.0),
        ("v/v", 3.0),
        ("số:", 1.5),
        ("ký thay", 1.5),
        ("tm. ", 1.5),
        ("kt. ", 1.5),
        ("quyết định", 1.5),
        ("thông báo", 1.5),
    ],
    "luan_van": [
        ("luận văn thạc sĩ", 5.0),
        ("luận văn thạc sỹ", 5.0),
        ("luận án tiến sĩ", 5.0),
        ("luận án tiến sỹ", 5.0),
        ("người hướng dẫn khoa học", 3.0),
        ("học viên cao học", 3.0),
        ("chuyên ngành", 1.5),
        ("mã số", 1.5),
        ("luận văn", 1.5),
    ],
    "khoa_luan": [
        ("khóa luận tốt nghiệp", 5.0),
        ("đồ án tốt nghiệp", 5.0),
        ("khoá luận tốt nghiệp", 5.0),
        ("sinh viên thực hiện", 3.0),
        ("giảng viên hướng dẫn", 3.0),
        ("khóa luận", 1.5),
        ("đồ án", 1.5),
        ("lớp", 1.5),
        ("mã sinh viên", 1.5),
    ],
    "de_cuong": [
        ("đề cương chi tiết học phần", 5.0),
        ("đề cương môn học", 5.0),
        ("đề cương chi tiết môn học", 5.0),
        ("chuẩn đầu ra của học phần", 3.0),
        ("số tín chỉ", 3.0),
        ("điều kiện tiên quyết", 3.0),
        ("mã học phần", 3.0),
        ("học phần", 1.5),
        ("hình thức đánh giá", 1.5),
    ],
    "hoi_thao": [
        ("kỷ yếu hội thảo", 5.0),
        ("hội thảo khoa học", 5.0),
        ("kỷ yếu hội nghị", 5.0),
        ("hội nghị khoa học", 3.0),
        ("ban tổ chức hội thảo", 3.0),
        ("báo cáo tham luận", 3.0),
        ("tham luận", 1.5),
        ("kỷ yếu", 1.5),
    ],
    "bao_nckh": [
        ("tạp chí khoa học", 5.0),
        ("issn", 3.0),
        ("doi:", 3.0),
        ("ngày nhận bài", 3.0),
        ("ngày phản biện", 3.0),
        ("tóm tắt:", 1.5),
        ("abstract", 1.5),
        ("keywords", 1.5),
        ("tài liệu tham khảo", 1.5),
        ("tạp chí", 1.5),
    ],
    "sach": [
        ("nhà xuất bản", 3.0),
        ("isbn", 3.0),
        ("chịu trách nhiệm xuất bản", 3.0),
        ("chủ biên", 3.0),
        ("tái bản", 3.0),
        ("in lần thứ", 1.5),
        ("lời nói đầu", 1.5),
        ("mục lục", 1.5),
        ("giáo trình", 1.5),
    ],
}

# Dấu hiệu riêng cho TÊN TỆP: cán bộ đặt tên viết tắt, không viết cả cụm.
# Tách riêng vì "cv" trong tên tệp nghĩa là công văn, còn "cv" giữa nội dung thì thường là chữ lạc.
_FILENAME_SIGNALS_RAW: Dict[str, List[Tuple[str, float]]] = {
    "cong_van": [("cong van", 5.0), ("cv_", 3.0), ("cv-", 3.0), ("qd_", 3.0),
                 ("quyet dinh", 3.0), ("thong bao", 3.0), ("tb_", 1.5)],
    "luan_van": [("luan van", 5.0), ("luanvan", 5.0), ("lv_", 3.0), ("lv-", 3.0),
                 ("thac si", 3.0), ("thac sy", 3.0), ("cao hoc", 3.0)],
    "khoa_luan": [("khoa luan", 5.0), ("khoaluan", 5.0), ("do an", 5.0), ("doan_", 3.0),
                  ("kl_", 3.0), ("kl-", 3.0), ("datn", 5.0), ("tot nghiep", 3.0)],
    "de_cuong": [("de cuong", 5.0), ("decuong", 5.0), ("dc_", 3.0), ("hoc phan", 3.0),
                 ("mon hoc", 3.0)],
    "hoi_thao": [("hoi thao", 5.0), ("hoithao", 5.0), ("ky yeu", 5.0), ("kyyeu", 5.0),
                 ("hoi nghi", 3.0), ("ht_", 1.5)],
    "bao_nckh": [("tap chi", 5.0), ("tapchi", 5.0), ("nckh", 5.0), ("bai bao", 3.0),
                 ("journal", 3.0), ("tc_", 1.5)],
    "sach": [("sach", 5.0), ("giao trinh", 5.0), ("giaotrinh", 5.0), ("isbn", 3.0),
             ("book", 3.0)],
}


def _compile(raw: Dict[str, List[Tuple[str, float]]]) -> Dict[str, List[Tuple[str, float]]]:
    """Bỏ dấu mọi mẫu MỘT LẦN lúc nạp module — không bỏ dấu lại trên từng tài liệu."""
    return {code: [(_norm(pattern), weight) for pattern, weight in patterns]
            for code, patterns in raw.items()}


_SIGNALS = _compile(_SIGNALS_RAW)
_FILENAME_SIGNALS = _compile(_FILENAME_SIGNALS_RAW)

# Nhãn tiếng Việt để hiện trong giao diện và ghi log. Khớp `document_types.label` trong DB;
# giữ bản sao ở đây để đoán được loại kể cả khi chưa kết nối DB.
TYPE_LABELS: Dict[str, str] = {
    "sach": "Sách",
    "de_cuong": "Đề cương môn học",
    "khoa_luan": "Khóa luận / Đồ án",
    "luan_van": "Luận văn thạc sỹ",
    "hoi_thao": "Kỷ yếu hội thảo",
    "bao_nckh": "Báo / Tạp chí NCKH",
    "cong_van": "Công văn",
}

# Danh sách loại đoán được, thứ tự ổn định (phục vụ kiểm thử và hiển thị)
KNOWN_TYPES: Tuple[str, ...] = tuple(TYPE_LABELS)


# =====================================================================
# KẾT QUẢ
# =====================================================================

@dataclass
class Suggestion:
    """
    Một gợi ý loại tài liệu.

    `evidence` là phần quan trọng nhất với người dùng: cán bộ nhìn thấy máy đoán "Luận văn" VÌ đã
    thấy cụm "luận văn thạc sĩ" và "người hướng dẫn khoa học" thì mới có cơ sở để đồng ý hay bác bỏ.
    """
    document_type: str = FALLBACK_TYPE
    confidence: float = 0.0
    source: str = "none"                 # filename | text | model | none
    evidence: List[str] = field(default_factory=list)
    scores: Dict[str, float] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return TYPE_LABELS.get(self.document_type, self.document_type)

    @property
    def confident(self) -> bool:
        """Đủ chắc để dùng thẳng, không cần hỏi model."""
        return self.confidence >= MODEL_CONFIDENCE_THRESHOLD

    def reason_vi(self) -> str:
        """Câu giải thích tiếng Việt cho giao diện."""
        if self.document_type == FALLBACK_TYPE and self.source == "none":
            return "Chưa đủ dấu hiệu để đoán loại tài liệu"
        if self.source == "model":
            return f"Model nhận định đây là {self.label}"
        nguon = "tên tệp" if self.source == "filename" else "nội dung tài liệu"
        if not self.evidence:
            return f"Đoán từ {nguon}"
        return f"Đoán từ {nguon}, thấy: " + ", ".join(f"“{e}”" for e in self.evidence[:4])

    def to_dict(self) -> Dict:
        return {
            "document_type": self.document_type,
            "label": self.label,
            "confidence": round(self.confidence, 2),
            "source": self.source,
            "evidence": self.evidence,
            "reason": self.reason_vi(),
        }


# =====================================================================
# CHẤM ĐIỂM
# =====================================================================

def _score(normalized: str,
           signals: Dict[str, List[Tuple[str, float]]]) -> Tuple[Dict[str, float], Dict[str, List[str]]]:
    """
    Chấm điểm từng loại trên văn bản ĐÃ chuẩn hóa.

    Mỗi mẫu tính ĐIỂM MỘT LẦN dù xuất hiện bao nhiêu lần: tài liệu 300 trang lặp "mục lục" 40 lần
    không vì thế mà "sách hơn" một cuốn sách nhắc một lần. Đếm số lần sẽ khiến điểm số phụ thuộc
    vào ĐỘ DÀI tài liệu thay vì loại tài liệu.
    """
    scores: Dict[str, float] = {}
    evidence: Dict[str, List[str]] = {}

    for code, patterns in signals.items():
        total = 0.0
        hits: List[Tuple[str, float]] = []
        for pattern, weight in patterns:
            if pattern and pattern in normalized:
                total += weight
                hits.append((pattern, weight))
        if total > 0:
            scores[code] = total
            # Dấu hiệu mạnh nhất lên trước — cán bộ đọc dòng giải thích thấy ngay lý do chính
            evidence[code] = [p for p, _ in sorted(hits, key=lambda x: -x[1])]

    return scores, evidence


def _to_suggestion(scores: Dict[str, float], evidence: Dict[str, List[str]],
                   source: str) -> Suggestion:
    """
    Chuyển điểm số thành gợi ý có độ tin cậy.

    Độ tin cậy = ƯU THẾ × ĐỘ MẠNH:
      - ƯU THẾ  (top / tổng điểm): loại này có nổi bật hơn các loại khác không? Một tài liệu ăn điểm
        đều cả 7 loại thì dù điểm cao vẫn không đáng tin.
      - ĐỘ MẠNH (top / 2·MIN_SCORE): có đủ bằng chứng tuyệt đối không? Một tài liệu chỉ khớp đúng
        một từ khóa yếu sẽ có ưu thế 1.0 (vì các loại khác 0 điểm) nhưng rõ ràng không đáng tin.
    Nhân hai thành phần lại thì phải THỎA MÃN CẢ HAI mới được điểm cao — đúng với trực giác
    "vừa rõ ràng hơn các loại khác, vừa có bằng chứng chắc".
    """
    if not scores:
        return Suggestion(source="none")

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top_code, top_score = ranked[0]

    if top_score < MIN_SCORE:
        # Có dấu vết nhưng quá mỏng: trả về loại đoán để tham khảo, độ tin cậy thấp để không ai
        # dùng thẳng, và KHÔNG che giấu là đã thấy gì.
        return Suggestion(document_type=top_code, confidence=round(top_score / (2 * MIN_SCORE), 2),
                          source=source, evidence=evidence.get(top_code, []), scores=scores)

    uu_the = top_score / sum(scores.values())
    do_manh = min(1.0, top_score / (2 * MIN_SCORE))
    confidence = round(uu_the * do_manh, 2)

    return Suggestion(document_type=top_code, confidence=confidence, source=source,
                      evidence=evidence.get(top_code, []), scores=scores)


# =====================================================================
# TẦNG 1 — TÊN TỆP (chưa OCR, miễn phí)
# =====================================================================

def suggest_from_filename(filename: str) -> Suggestion:
    """Đoán loại tài liệu từ tên tệp. Dùng ngay lúc cán bộ chọn tệp, trước khi tải lên."""
    if not filename:
        return Suggestion(source="none")

    # Bỏ phần mở rộng và đổi mọi dấu ngăn cách thành dấu cách: "KL_Nguyen-Van.A.pdf" → "kl nguyen van a"
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", filename)
    normalized = _norm(re.sub(r"[_\-.]+", " ", stem))
    # Giữ thêm bản có gạch dưới để các mẫu tiền tố kiểu "kl_" vẫn khớp được
    raw_normalized = _norm(stem)

    scores, evidence = _score(f"{normalized} {raw_normalized}", _FILENAME_SIGNALS)
    return _to_suggestion(scores, evidence, source="filename")


# =====================================================================
# TẦNG 2 — NỘI DUNG SAU OCR (miễn phí)
# =====================================================================

def suggest_from_text(text: str, filename: str = "") -> Suggestion:
    """
    Đoán loại tài liệu từ nội dung đã OCR, có cộng thêm dấu hiệu tên tệp.

    Tên tệp cộng vào với trọng số GIẢM (một nửa): tên tệp là ý định của người đặt tên, nội dung là
    sự thật của tài liệu. Khi hai nguồn mâu thuẫn thì nội dung phải thắng — nhưng khi nội dung mờ
    (bản quét xấu, OCR ra ít chữ) thì tên tệp vẫn kéo được về đúng hướng.
    """
    normalized = _norm(text or "")[:PROBE_CHARS]
    scores, evidence = _score(normalized, _SIGNALS)

    if filename:
        name_suggestion = suggest_from_filename(filename)
        for code, value in name_suggestion.scores.items():
            scores[code] = scores.get(code, 0.0) + value * 0.5
            if code not in evidence:
                evidence[code] = []
            evidence[code].extend(
                f"tên tệp: {e}" for e in name_suggestion.evidence[:2]
                if f"tên tệp: {e}" not in evidence[code]
            )

    return _to_suggestion(scores, evidence, source="text")


# =====================================================================
# TẦNG 3 — HỎI MODEL (chỉ khi hai tầng trên không đủ tự tin)
# =====================================================================

def classify_with_model(text: str, provider) -> Optional[Suggestion]:
    """
    Hỏi model loại tài liệu, qua ĐÚNG giao diện `ModelProvider.extract_fields` sẵn có.

    KHÔNG thêm phương thức mới vào `ModelProvider`: dựng một lược đồ MỘT TRƯỜNG rồi tái dùng đường
    trích xuất chuẩn. Nhờ vậy mọi công cụ mô hình (Claude, Ollama, vLLM…) đều đoán loại được ngay
    mà không phải sửa lớp nào — đúng phép thử YC-MP-08 "thêm công cụ = viết thêm một lớp".

    Trả về None khi model không dùng được: đoán loại là việc PHỤ, không được làm hỏng số hóa.
    """
    from scripts.providers.base import ExtractionSchema, SchemaField

    danh_sach = ", ".join(f"{code} ({label})" for code, label in TYPE_LABELS.items())
    schema = ExtractionSchema(
        code="_phan_loai",
        name="Phân loại tài liệu",
        document_type="phan_loai",
        fields=[SchemaField(
            key="loai_tai_lieu",
            label=f"Loại tài liệu — CHỈ trả về đúng một mã trong: {danh_sach}",
            required=True,
        )],
        context_strategy="first8_last2",
    )

    try:
        result = provider.extract_fields((text or "")[:PROBE_CHARS], schema)
    except Exception as e:  # noqa: BLE001 — đoán loại hỏng không được làm hỏng job
        logger.warning("Hỏi model loại tài liệu thất bại: %s", e)
        return None

    for f in getattr(result, "fields", []) or []:
        if f.key != "loai_tai_lieu":
            continue
        # Model hay trả kèm nhãn ("sach (Sách)") hoặc thừa dấu — dò mã hợp lệ trong chuỗi trả về
        answer = _norm(str(f.value or ""))
        for code in KNOWN_TYPES:
            if code.replace("_", " ") in answer.replace("_", " "):
                return Suggestion(document_type=code,
                                  confidence=f.confidence if f.confidence is not None else 0.6,
                                  source="model", evidence=[str(f.value)])
        logger.info("Model trả loại không nhận ra: %r", f.value)

    return None


# =====================================================================
# ĐIỀU PHỐI
# =====================================================================

def is_auto(document_type: Optional[str]) -> bool:
    """Cán bộ có chọn 'để hệ thống tự đoán' không? Rỗng cũng coi là tự đoán."""
    return not document_type or str(document_type).strip().lower() in (AUTO, "", "tu_dong")


def classify(text: str, filename: str = "", provider=None) -> Suggestion:
    """
    Đoán loại tài liệu, leo thang từ rẻ tới đắt.

    Chỉ gọi model khi đối sánh từ khóa không đủ tự tin VÀ có provider truyền vào. Lô hàng nghìn tệp
    đặt tên theo quy ước sẽ không tốn lượt gọi model nào.
    """
    suggestion = suggest_from_text(text, filename=filename)
    if suggestion.confident or provider is None:
        return suggestion

    tu_model = classify_with_model(text, provider)
    if tu_model is None:
        return suggestion

    # Model và từ khóa cùng kết luận → cộng hưởng, tin hơn hẳn từng nguồn riêng lẻ
    if tu_model.document_type == suggestion.document_type:
        tu_model.confidence = max(tu_model.confidence, min(1.0, suggestion.confidence + 0.3))
        tu_model.evidence = suggestion.evidence + tu_model.evidence
    return tu_model
