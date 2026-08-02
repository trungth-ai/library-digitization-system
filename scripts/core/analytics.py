#!/usr/bin/env python3
"""
Phân tích chi tiết kết quả AI (YC-AN-05→08 — sprint V2).

Ý TƯỞNG CỐT LÕI: kế hoạch kiểm thử đo độ chính xác bằng bộ BD-01 — 30–50 tài liệu, đáp án chuẩn ghi
tay, rất tốn công và chỉ đo được một lần. Nhưng hệ đang chạy thật có sẵn một nguồn đáp án liên tục:
**giá trị cuối cùng mà cán bộ duyệt**. AI trả `"Bao cao tong ket"`, cán bộ sửa thành
`"Báo cáo tổng kết"` → đó là một điểm dữ liệu về độ chính xác, miễn phí, tích lũy mỗi ngày.

BA RÀNG BUỘC BẮT BUỘC để số liệu này trung thực (nếu bỏ, nó thành số liệu tự khen):

  1. **Luôn kèm cỡ mẫu.** Dưới `ACCURACY_MIN_SAMPLE` quan sát → trả `"chưa đủ dữ liệu"`, KHÔNG trả %.
     Một trường có 3 quan sát mà báo "100% chính xác" là con số gây hiểu nhầm nguy hiểm hơn là không
     có con số nào.
  2. **Nói rõ phương pháp trên giao diện.** Đây là đối chiếu với *giá trị cán bộ đã duyệt*, không
     phải với đáp án chuẩn độc lập — cán bộ cũng có thể bỏ sót. Là chỉ báo xu hướng, không thay thế BD-01.
  3. **Chuẩn hóa đúng công thức của kế hoạch kiểm thử mục 1.3**: bỏ khoảng trắng thừa, đồng nhất định
     dạng ngày. Trường không có trong tài liệu mà AI trả rỗng là ĐÚNG; bịa ra giá trị là SAI.

Phần so sánh là hàm THUẦN (`values_match`) nên kiểm thử được không cần DB.
"""

import logging
import os
import re
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional

import scripts.db as db

logger = logging.getLogger("core.analytics")

# Số quan sát tối thiểu trước khi được phép hiển thị tỉ lệ %. 30 là mức thường dùng để một tỉ lệ bắt
# đầu có ý nghĩa; cấu hình được vì mỗi Trung tâm có khối lượng khác nhau.
ACCURACY_MIN_SAMPLE = int(os.getenv("ACCURACY_MIN_SAMPLE", "30"))

INSUFFICIENT = "chưa đủ dữ liệu"

_DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d")


# ─────────────────────────────────────────────────────────────
# SO SÁNH GIÁ TRỊ — hàm thuần
# ─────────────────────────────────────────────────────────────

def normalize_value(value: Optional[str]) -> str:
    """
    Chuẩn hóa trước khi so sánh, theo công thức mục 1.3 kế hoạch kiểm thử.

    Gồm: chuẩn hóa Unicode (tiếng Việt có hai dạng tổ hợp), gộp khoảng trắng, bỏ khoảng trắng đầu
    cuối, hạ chữ thường. KHÔNG bỏ dấu — "Bao cao" và "Báo cáo" là hai giá trị KHÁC nhau, và việc AI
    trả về bản không dấu chính là một lỗi cần đếm.
    """
    if not value:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    return re.sub(r"\s+", " ", text).strip().lower()


def _parse_date(value: str) -> Optional[datetime]:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def values_match(ai_value: Optional[str], approved_value: Optional[str]) -> bool:
    """
    Giá trị AI trả về có khớp giá trị cán bộ đã duyệt không?

    Quy tắc (theo kế hoạch kiểm thử mục 1.3):
      - Cả hai rỗng → ĐÚNG. Trường không có trong tài liệu mà AI trả rỗng là hành vi đúng (YC-CF-05).
      - Một rỗng một có → SAI (bịa ra giá trị, hoặc bỏ sót).
      - Ngày tháng: so sánh sau khi phân tích, nên `01/03/2026` khớp `2026-03-01`.
      - Còn lại: so sánh sau chuẩn hóa khoảng trắng và chữ hoa/thường.
    """
    ai_norm = normalize_value(ai_value)
    approved_norm = normalize_value(approved_value)

    if not ai_norm and not approved_norm:
        return True
    if not ai_norm or not approved_norm:
        return False
    if ai_norm == approved_norm:
        return True

    ai_date, approved_date = _parse_date(ai_norm), _parse_date(approved_norm)
    return bool(ai_date and approved_date and ai_date == approved_date)


def accuracy_percent(correct: int, total: int) -> Optional[float]:
    """
    Tỉ lệ đúng, làm tròn 1 chữ số. Trả `None` khi CHƯA ĐỦ MẪU — nơi gọi phải hiển thị "chưa đủ dữ liệu".

    Trả `None` thay vì 0 là có chủ đích: 0% và "chưa đo được" là hai điều hoàn toàn khác nhau.
    """
    if total < ACCURACY_MIN_SAMPLE:
        return None
    return round(correct * 100.0 / total, 1)


# ─────────────────────────────────────────────────────────────
# TRUY VẤN
# ─────────────────────────────────────────────────────────────

def _dict_cursor(conn):
    import psycopg2.extras
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def field_accuracy(date_from: Optional[str] = None, date_to: Optional[str] = None,
                   provider: Optional[str] = None) -> List[Dict]:
    """
    Độ chính xác theo TỪNG TRƯỜNG, đo trên việc thật (YC-AN-05).

    So `model_call_fields.value_preview` (AI trả về) với `metadata_fields.value` (giá trị hiện tại,
    tức là bản cán bộ đã duyệt/sửa). Chỉ tính tài liệu đã `completed` — tài liệu còn đang xử lý thì
    giá trị chưa phải là bản cuối.

    So sánh thực hiện bằng Python chứ không bằng SQL: quy tắc chuẩn hóa (ngày tháng, Unicode tiếng
    Việt) phải khớp CHÍNH XÁC công thức của kế hoạch kiểm thử, và trong Python thì kiểm thử được.
    """
    conditions = ["d.status = 'completed'"]
    params: list = []
    if date_from:
        conditions.append("f.created_at >= %s"); params.append(date_from)
    if date_to:
        conditions.append("f.created_at <= %s"); params.append(date_to)
    if provider:
        conditions.append("mc.provider = %s"); params.append(provider)

    sql = f"""
        SELECT f.field_key,
               f.value_preview          AS ai_value,
               m.value                  AS approved_value,
               mc.provider,
               mc.deployment
        FROM model_call_fields f
        JOIN model_calls mc ON mc.id = f.model_call_id
        JOIN documents   d  ON d.id  = f.document_id
        LEFT JOIN metadata_fields m
               ON m.document_id = f.document_id AND m.key = f.field_key
        WHERE {' AND '.join(conditions)}
    """

    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return _aggregate_accuracy(rows, key="field_key")


def provider_accuracy(date_from: Optional[str] = None,
                      date_to: Optional[str] = None) -> List[Dict]:
    """
    So sánh độ chính xác GIỮA CÁC CÔNG CỤ trên cùng khoảng thời gian (YC-AN-06).

    Đây là bảng số liệu cho hồ sơ dự thi mà **không cần chạy lại harness**: nó lấy từ việc thật của
    Trung tâm, nên phản ánh đúng loại tài liệu đang xử lý thay vì một tập mẫu chọn sẵn.
    """
    conditions = ["d.status = 'completed'"]
    params: list = []
    if date_from:
        conditions.append("f.created_at >= %s"); params.append(date_from)
    if date_to:
        conditions.append("f.created_at <= %s"); params.append(date_to)

    sql = f"""
        SELECT mc.provider || ' (' || mc.deployment || ')' AS nhom,
               f.value_preview AS ai_value,
               m.value         AS approved_value
        FROM model_call_fields f
        JOIN model_calls mc ON mc.id = f.model_call_id
        JOIN documents   d  ON d.id  = f.document_id
        LEFT JOIN metadata_fields m
               ON m.document_id = f.document_id AND m.key = f.field_key
        WHERE {' AND '.join(conditions)}
    """

    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return _aggregate_accuracy(rows, key="nhom")


def _aggregate_accuracy(rows: List[Dict], key: str) -> List[Dict]:
    """
    Gộp các quan sát thành tỉ lệ đúng theo nhóm. LUÔN trả kèm `sample_size`.

    Trường có ít mẫu vẫn xuất hiện trong kết quả (với `accuracy=None`): ẩn hẳn chúng đi sẽ tạo ấn
    tượng sai rằng mọi trường đều đã đo được.
    """
    buckets: Dict[str, Dict] = {}

    for row in rows:
        group = row.get(key) or "(không rõ)"
        bucket = buckets.setdefault(group, {"correct": 0, "total": 0, "provider": row.get("provider")})
        bucket["total"] += 1
        if values_match(row.get("ai_value"), row.get("approved_value")):
            bucket["correct"] += 1

    out = []
    for group, bucket in buckets.items():
        accuracy = accuracy_percent(bucket["correct"], bucket["total"])
        out.append({
            key: group,
            "so_dung": bucket["correct"],
            "sample_size": bucket["total"],
            # `None` = chưa đủ mẫu. Giao diện hiển thị "chưa đủ dữ liệu", KHÔNG hiển thị 0%.
            "do_chinh_xac": accuracy,
            "ghi_chu": INSUFFICIENT if accuracy is None else None,
            "provider": bucket.get("provider"),
        })

    # Sắp theo cỡ mẫu giảm dần: trường đo được nhiều nhất là trường đáng tin nhất, đưa lên trước
    return sorted(out, key=lambda r: (-r["sample_size"], r[key]))


def cost_summary(date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict:
    """
    Tổng chi phí gọi model theo tháng và theo công cụ (YC-AN-04).

    Cộng dồn ở tầng SQL bằng số nguyên (`SUM` trên BIGINT) — không đưa qua dấu phẩy động ở bất kỳ
    khâu nào, kể cả khâu trung gian.
    """
    from scripts.core import pricing

    conditions, params = ["1=1"], []
    if date_from:
        conditions.append("created_at >= %s"); params.append(date_from)
    if date_to:
        conditions.append("created_at <= %s"); params.append(date_to)
    where = " AND ".join(conditions)

    sql_by_month = f"""
        SELECT to_char(created_at, 'YYYY-MM')          AS thang,
               COUNT(*)                                AS so_luot_goi,
               COALESCE(SUM(total_tokens), 0)          AS tong_token,
               COALESCE(SUM(cost_vnd), 0)              AS chi_phi_vnd,
               COUNT(*) FILTER (WHERE cost_vnd IS NULL AND deployment <> 'local')
                                                       AS luot_chua_biet_gia
        FROM model_calls
        WHERE {where}
        GROUP BY thang ORDER BY thang DESC
    """
    sql_by_provider = f"""
        SELECT provider, deployment,
               COUNT(*)                       AS so_luot_goi,
               COALESCE(SUM(total_tokens), 0) AS tong_token,
               COALESCE(SUM(cost_vnd), 0)     AS chi_phi_vnd
        FROM model_calls
        WHERE {where}
        GROUP BY provider, deployment ORDER BY chi_phi_vnd DESC
    """

    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute(sql_by_month, params)
            by_month = [dict(r) for r in cur.fetchall()]
            cur.execute(sql_by_provider, params)
            by_provider = [dict(r) for r in cur.fetchall()]

    for row in by_month + by_provider:
        row["chi_phi_hien_thi"] = pricing.format_vnd(row.get("chi_phi_vnd"))

    return {
        "theo_thang": by_month,
        "theo_cong_cu": by_provider,
        # Ghi rõ tỉ giá đã dùng: thiếu nó thì con số VNĐ không kiểm chứng lại được
        "ty_gia_usd_vnd": pricing.usd_vnd_rate(),
    }


def ocr_quality(date_from: Optional[str] = None, date_to: Optional[str] = None,
                limit: int = 100) -> Dict:
    """
    Chất lượng OCR (YC-AN-03): tổng quan + danh sách tài liệu scan xấu nên quét lại.

    `pages_without_text > 0` nghĩa là OCR chạy xong nhưng có trang không tạo được lớp text — ảnh quá
    mờ hoặc lệch. Biết sớm thì đề nghị quét lại, thay vì để tài liệu vào DSpace ở dạng không tra cứu được.
    """
    conditions, params = ["1=1"], []
    if date_from:
        conditions.append("o.created_at >= %s"); params.append(date_from)
    if date_to:
        conditions.append("o.created_at <= %s"); params.append(date_to)
    where = " AND ".join(conditions)

    sql_summary = f"""
        SELECT COUNT(*)                                          AS so_tai_lieu,
               COALESCE(SUM(pages), 0)                           AS tong_trang,
               COALESCE(SUM(pages_without_text), 0)              AS trang_khong_co_text,
               COUNT(*) FILTER (WHERE pages_without_text > 0)    AS tai_lieu_scan_xau,
               COALESCE(ROUND(AVG(duration_ms)), 0)              AS thoi_gian_tb_ms
        FROM ocr_runs o WHERE {where}
    """
    sql_bad = f"""
        SELECT o.document_id, d.filename, o.pages, o.pages_without_text,
               o.text_chars, o.duration_ms, o.created_at
        FROM ocr_runs o
        LEFT JOIN documents d ON d.id = o.document_id
        WHERE {where} AND o.pages_without_text > 0
        ORDER BY o.pages_without_text DESC, o.created_at DESC
        LIMIT %s
    """

    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute(sql_summary, params)
            summary = dict(cur.fetchone() or {})
            cur.execute(sql_bad, params + [limit])
            bad = [dict(r) for r in cur.fetchall()]

    for row in bad:
        if row.get("created_at"):
            row["created_at"] = row["created_at"].isoformat()
        # Tỉ lệ trang hỏng để xếp mức độ ưu tiên quét lại
        pages = row.get("pages") or 0
        row["ty_le_trang_hong"] = (
            round(row["pages_without_text"] * 100.0 / pages, 1) if pages else None)

    return {"tong_quan": summary, "tai_lieu_can_quet_lai": bad}


def quality_drift(days: int = 7, baseline_days: int = 30) -> Dict:
    """
    Phát hiện suy giảm chất lượng (YC-AN-08): so `days` ngày gần đây với `baseline_days` ngày trước đó.

    So sánh tỉ lệ tài liệu bị đánh dấu `needs_review`. Tăng đột biến nghĩa là một trong ba thứ đã đổi:
    model, loại tài liệu đầu vào, hoặc chất lượng scan — cả ba đều đáng biết sớm.

    Chỉ kết luận khi CẢ HAI kỳ đủ mẫu; thiếu mẫu thì nói rõ "chưa đủ dữ liệu" thay vì báo động giả.
    """
    sql = """
        SELECT
            COUNT(*) FILTER (WHERE created_at > NOW() - (%(recent)s || ' days')::interval)
                AS gan_day_tong,
            COUNT(*) FILTER (WHERE created_at > NOW() - (%(recent)s || ' days')::interval
                                   AND needs_review)
                AS gan_day_can_xem,
            COUNT(*) FILTER (WHERE created_at <= NOW() - (%(recent)s || ' days')::interval
                                   AND created_at > NOW() - (%(base)s || ' days')::interval)
                AS truoc_do_tong,
            COUNT(*) FILTER (WHERE created_at <= NOW() - (%(recent)s || ' days')::interval
                                   AND created_at > NOW() - (%(base)s || ' days')::interval
                                   AND needs_review)
                AS truoc_do_can_xem
        FROM documents
        WHERE status <> 'deleted'
    """
    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute(sql, {"recent": days, "base": days + baseline_days})
            row = dict(cur.fetchone() or {})

    gan_day_tong = row.get("gan_day_tong") or 0
    truoc_do_tong = row.get("truoc_do_tong") or 0

    if gan_day_tong < ACCURACY_MIN_SAMPLE or truoc_do_tong < ACCURACY_MIN_SAMPLE:
        return {
            "du_lieu_du": False,
            "ghi_chu": f"{INSUFFICIENT} (cần ít nhất {ACCURACY_MIN_SAMPLE} tài liệu mỗi kỳ)",
            "gan_day_tong": gan_day_tong, "truoc_do_tong": truoc_do_tong,
        }

    ty_le_gan_day = round((row["gan_day_can_xem"] or 0) * 100.0 / gan_day_tong, 1)
    ty_le_truoc_do = round((row["truoc_do_can_xem"] or 0) * 100.0 / truoc_do_tong, 1)
    chenh_lech = round(ty_le_gan_day - ty_le_truoc_do, 1)

    # Ngưỡng cảnh báo: tăng hơn 10 điểm phần trăm. Đặt ngưỡng tuyệt đối chứ không tương đối vì tỉ lệ
    # nền có thể rất thấp, khi đó "tăng gấp đôi" chỉ là dao động ngẫu nhiên.
    return {
        "du_lieu_du": True,
        "ty_le_can_xem_gan_day": ty_le_gan_day,
        "ty_le_can_xem_truoc_do": ty_le_truoc_do,
        "chenh_lech_diem_pt": chenh_lech,
        "canh_bao": chenh_lech > 10,
        "gan_day_tong": gan_day_tong, "truoc_do_tong": truoc_do_tong,
        "ghi_chu": (
            f"Tỉ lệ cần xem lại tăng {chenh_lech} điểm phần trăm so với kỳ trước"
            if chenh_lech > 10 else None
        ),
    }


METHOD_NOTE = (
    "Đối chiếu giá trị AI trả về với giá trị cán bộ đã duyệt — chỉ báo xu hướng trên việc thật, "
    "KHÔNG thay thế đối chiếu đáp án chuẩn của bộ dữ liệu kiểm thử BD-01. "
    f"Trường có dưới {ACCURACY_MIN_SAMPLE} quan sát không hiển thị tỉ lệ."
)
