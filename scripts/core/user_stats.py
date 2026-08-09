#!/usr/bin/env python3
"""
Thống kê theo NGƯỜI DÙNG và theo TOÀN HỆ THỐNG (YC-TT).

VÌ SAO THÊM, TRONG KHI ĐÃ CÓ `dashboard.staff_workload`: hàm đó chỉ đếm hai hành động của việc
duyệt (`confirm`, `edit_field`) trong 7 ngày. Nó trả lời "hôm nay ai duyệt nhiều" — đủ để chia việc
hằng tuần, nhưng KHÔNG trả lời được ba câu hỏi khác mà quản trị viên thật sự cần:

  1. "Người này đã làm những gì trên hệ thống?" — kể cả tải lên, tải về, đẩy DSpace, đăng nhập.
  2. "Toàn Trung tâm tháng này ra sao?" — tổng theo hành động, số người hoạt động, đăng nhập hỏng.
  3. "Có dấu hiệu bất thường nào không?" — đăng nhập sai liên tục, bị từ chối quyền nhiều lần.

BỐN NGUỒN DỮ LIỆU, MỖI NGUỒN TRẢ LỜI MỘT LOẠI CÂU HỎI (xem `core/user_log.py`):
    documents      tài liệu ai tải lên, ai xác nhận  → khối lượng công việc
    audit_log      thao tác nghiệp vụ trên tài liệu   → làm gì với tài liệu nào
    user_activity  hành vi người dùng                 → đăng nhập, từ chối quyền, kết xuất
    ocr_runs       số trang                           → bối cảnh cho khối lượng

QUYẾT ĐỊNH QĐ-06 ĐƯỢC GIỮ NGUYÊN Ở ĐÂY: số liệu theo người là để CÂN ĐỐI CÔNG VIỆC, không phải
bảng xếp hạng thi đua. Vì vậy mọi hàm trả về số đếm đều kèm `ghi_chu` giải thích cách đọc, đặt
TRONG dữ liệu để giao diện không thể quên hiển thị.
"""

import logging
from typing import Dict, List, Optional

import scripts.db as db

logger = logging.getLogger("core.user_stats")

# Ghi chú BẮT BUỘC đi kèm mọi bảng số liệu theo người (QĐ-06).
GHI_CHU_CACH_DOC = (
    "Số liệu vận hành để cân đối công việc, KHÔNG phải bảng xếp hạng thi đua. "
    "Tài liệu có độ khó rất khác nhau — một công văn 2 trang và một khóa luận 200 trang đều tính "
    "là 1 tài liệu — nên số tài liệu không so sánh trực tiếp được giữa các cán bộ. "
    "Hãy đọc kèm cột số trang."
)


def _dict_cursor(conn):
    import psycopg2.extras
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _iso(rows: List[Dict], *fields: str) -> List[Dict]:
    """Đổi cột thời gian sang chuỗi ISO để JSON hóa được."""
    for row in rows:
        for field in fields:
            if row.get(field) is not None and hasattr(row[field], "isoformat"):
                row[field] = row[field].isoformat()
    return rows


# =====================================================================
# THEO TỪNG NGƯỜI DÙNG
# =====================================================================

def per_user(days: int = 30) -> Dict:
    """
    Một dòng cho mỗi cán bộ: đã tải lên bao nhiêu, duyệt bao nhiêu, sửa bao nhiêu trường, đẩy
    DSpace bao nhiêu, và tổng số trang đã xử lý.

    Gộp từ `audit_log` theo `actor` chứ không theo `user_id`: `audit_log` giữ TÊN người thao tác
    tại thời điểm đó, nên nhật ký còn đọc được cả sau khi tài khoản bị xóa mềm — đúng mục đích của
    một sổ kiểm toán. Nối theo user_id sẽ làm bản ghi của người đã nghỉ việc biến mất khỏi báo cáo.
    """
    sql = """
        WITH thao_tac AS (
            SELECT actor,
                   COUNT(*) FILTER (WHERE action = 'upload')      AS so_tai_len,
                   COUNT(*) FILTER (WHERE action = 'confirm')     AS so_da_duyet,
                   COUNT(*) FILTER (WHERE action = 'edit_field')  AS so_truong_da_sua,
                   COUNT(*) FILTER (WHERE action = 'dspace_push') AS so_day_dspace,
                   COUNT(*) FILTER (WHERE action = 'delete')      AS so_da_xoa,
                   COUNT(DISTINCT document_id)                    AS so_tai_lieu_cham_toi,
                   MIN(created_at)                                AS lan_dau,
                   MAX(created_at)                                AS lan_cuoi
            FROM audit_log
            WHERE created_at > NOW() - (%(days)s || ' days')::interval
              AND actor IS NOT NULL
            GROUP BY actor
        ),
        so_trang AS (
            -- Số trang của những tài liệu người này ĐÃ XÁC NHẬN. Đây là bối cảnh bắt buộc theo
            -- QĐ-06: không có nó thì cột "số tài liệu" bị đọc sai thành năng suất.
            SELECT a.actor, COALESCE(SUM(o.pages), 0) AS so_trang
            FROM audit_log a
            JOIN ocr_runs o ON o.document_id = a.document_id
            WHERE a.action = 'confirm'
              AND a.created_at > NOW() - (%(days)s || ' days')::interval
              AND a.actor IS NOT NULL
            GROUP BY a.actor
        ),
        dang_nhap AS (
            SELECT username,
                   COUNT(*) FILTER (WHERE action = 'login' AND result = 'ok')  AS so_dang_nhap,
                   COUNT(*) FILTER (WHERE action = 'login_failed')             AS so_dang_nhap_hong,
                   COUNT(*) FILTER (WHERE result = 'denied')                   AS so_bi_tu_choi,
                   MAX(created_at) FILTER (WHERE action = 'login' AND result = 'ok')
                                                                               AS dang_nhap_gan_nhat
            FROM user_activity
            WHERE created_at > NOW() - (%(days)s || ' days')::interval
              AND username IS NOT NULL
            GROUP BY username
        )
        SELECT COALESCE(t.actor, d.username)              AS nguoi_dung,
               COALESCE(t.so_tai_len, 0)                  AS so_tai_len,
               COALESCE(t.so_da_duyet, 0)                 AS so_da_duyet,
               COALESCE(t.so_truong_da_sua, 0)            AS so_truong_da_sua,
               COALESCE(t.so_day_dspace, 0)               AS so_day_dspace,
               COALESCE(t.so_da_xoa, 0)                   AS so_da_xoa,
               COALESCE(t.so_tai_lieu_cham_toi, 0)        AS so_tai_lieu_cham_toi,
               COALESCE(p.so_trang, 0)                    AS so_trang,
               COALESCE(d.so_dang_nhap, 0)                AS so_dang_nhap,
               COALESCE(d.so_dang_nhap_hong, 0)           AS so_dang_nhap_hong,
               COALESCE(d.so_bi_tu_choi, 0)               AS so_bi_tu_choi,
               t.lan_dau, t.lan_cuoi, d.dang_nhap_gan_nhat
        FROM thao_tac t
        FULL OUTER JOIN dang_nhap d ON d.username = t.actor
        LEFT JOIN so_trang p ON p.actor = COALESCE(t.actor, d.username)
        WHERE COALESCE(t.actor, d.username) IS NOT NULL
        ORDER BY COALESCE(t.so_da_duyet, 0) DESC, COALESCE(t.so_tai_len, 0) DESC
    """

    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            try:
                cur.execute(sql, {"days": days})
                rows = [dict(r) for r in cur.fetchall()]
            except Exception as e:  # noqa: BLE001 — `ocr_runs` có thể chưa di trú (migration 005)
                conn.rollback()
                logger.info("Thống kê người dùng lùi về bản không có số trang: %s", e)
                rows = _per_user_khong_so_trang(cur, days)

    return {
        "so_ngay": days,
        "nguoi_dung": _iso(rows, "lan_dau", "lan_cuoi", "dang_nhap_gan_nhat"),
        "ghi_chu": GHI_CHU_CACH_DOC,
    }


def _per_user_khong_so_trang(cur, days: int) -> List[Dict]:
    """Bản lùi khi chưa có bảng `ocr_runs` — mất cột số trang, phần còn lại vẫn dùng được."""
    cur.execute("""
        SELECT actor                                       AS nguoi_dung,
               COUNT(*) FILTER (WHERE action = 'upload')      AS so_tai_len,
               COUNT(*) FILTER (WHERE action = 'confirm')     AS so_da_duyet,
               COUNT(*) FILTER (WHERE action = 'edit_field')  AS so_truong_da_sua,
               COUNT(*) FILTER (WHERE action = 'dspace_push') AS so_day_dspace,
               COUNT(*) FILTER (WHERE action = 'delete')      AS so_da_xoa,
               COUNT(DISTINCT document_id)                    AS so_tai_lieu_cham_toi,
               0 AS so_trang, 0 AS so_dang_nhap, 0 AS so_dang_nhap_hong, 0 AS so_bi_tu_choi,
               MIN(created_at) AS lan_dau, MAX(created_at) AS lan_cuoi,
               NULL::timestamptz AS dang_nhap_gan_nhat
        FROM audit_log
        WHERE created_at > NOW() - (%(days)s || ' days')::interval
          AND actor IS NOT NULL
        GROUP BY actor
        ORDER BY so_da_duyet DESC
    """, {"days": days})
    return [dict(r) for r in cur.fetchall()]


def for_user(username: str, days: int = 30) -> Dict:
    """
    Hồ sơ hoạt động của MỘT người: tổng theo hành động, phân bố theo ngày, loại tài liệu đã xử lý,
    và những thao tác gần nhất.

    "Phân bố theo ngày" là phần đáng giá nhất cho quản trị viên: một con số tổng không phân biệt
    được người làm đều mỗi ngày với người dồn tất cả vào buổi chiều cuối tháng — mà hai tình huống
    đó cần hai cách hỗ trợ hoàn toàn khác nhau.
    """
    ket_qua: Dict = {"nguoi_dung": username, "so_ngay": days}

    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            cur.execute("""
                SELECT action AS hanh_dong, COUNT(*) AS so_lan,
                       MAX(created_at) AS lan_cuoi
                FROM audit_log
                WHERE actor = %(username)s
                  AND created_at > NOW() - (%(days)s || ' days')::interval
                GROUP BY action
                ORDER BY so_lan DESC
            """, {"username": username, "days": days})
            ket_qua["theo_hanh_dong"] = _iso([dict(r) for r in cur.fetchall()], "lan_cuoi")

            cur.execute("""
                SELECT DATE(created_at) AS ngay, COUNT(*) AS so_thao_tac,
                       COUNT(*) FILTER (WHERE action = 'confirm') AS so_da_duyet
                FROM audit_log
                WHERE actor = %(username)s
                  AND created_at > NOW() - (%(days)s || ' days')::interval
                GROUP BY DATE(created_at)
                ORDER BY ngay DESC
            """, {"username": username, "days": days})
            ket_qua["theo_ngay"] = [
                {**dict(r), "ngay": r["ngay"].isoformat()} for r in cur.fetchall()
            ]

            # Loại tài liệu người này duyệt — cho biết ai đang gánh mảng nào
            cur.execute("""
                SELECT d.document_type AS loai, dt.label AS nhan, COUNT(*) AS so_tai_lieu
                FROM audit_log a
                JOIN documents      d  ON d.id = a.document_id
                JOIN document_types dt ON dt.code = d.document_type
                WHERE a.actor = %(username)s AND a.action = 'confirm'
                  AND a.created_at > NOW() - (%(days)s || ' days')::interval
                GROUP BY d.document_type, dt.label
                ORDER BY so_tai_lieu DESC
            """, {"username": username, "days": days})
            ket_qua["theo_loai_tai_lieu"] = [dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT action AS hanh_dong, result AS ket_qua, ip, created_at,
                       resource_type, resource_id
                FROM user_activity
                WHERE username = %(username)s
                  AND created_at > NOW() - (%(days)s || ' days')::interval
                ORDER BY created_at DESC
                LIMIT 50
            """, {"username": username, "days": days})
            ket_qua["hoat_dong_gan_nhat"] = _iso([dict(r) for r in cur.fetchall()], "created_at")

    ket_qua["ghi_chu"] = GHI_CHU_CACH_DOC
    return ket_qua


# =====================================================================
# TOÀN HỆ THỐNG (dành cho quản trị viên)
# =====================================================================

def admin_overview(days: int = 30) -> Dict:
    """
    Bức tranh toàn Trung tâm: khối lượng, ai đang hoạt động, và các dấu hiệu cần để mắt.

    `canh_bao` được tính SẴN ở đây thay vì để giao diện tự suy: một ngưỡng nằm trong mã giao diện
    sẽ lệch với ngưỡng của trang khác ngay lần chỉnh đầu tiên, và không kiểm thử được.
    """
    ket_qua: Dict = {"so_ngay": days}

    with db.get_conn() as conn:
        with _dict_cursor(conn) as cur:
            # -- Khối lượng --
            cur.execute("""
                SELECT COUNT(*)                                          AS so_tai_lieu,
                       COUNT(*) FILTER (WHERE status = 'completed')      AS so_hoan_thanh,
                       COUNT(*) FILTER (WHERE status = 'failed')         AS so_that_bai,
                       COUNT(*) FILTER (WHERE confirmed_at IS NOT NULL)  AS so_da_duyet,
                       COUNT(*) FILTER (WHERE needs_review)              AS so_can_xem_lai,
                       COUNT(*) FILTER (WHERE dspace_status = 'uploaded') AS so_da_len_dspace,
                       COUNT(DISTINCT uploaded_by)                       AS so_nguoi_tai_len
                FROM documents
                WHERE created_at > NOW() - (%(days)s || ' days')::interval
                  AND status <> 'deleted'
            """, {"days": days})
            ket_qua["khoi_luong"] = dict(cur.fetchone() or {})

            # -- Hoạt động theo hành động --
            cur.execute("""
                SELECT action AS hanh_dong, COUNT(*) AS so_lan,
                       COUNT(DISTINCT actor) AS so_nguoi
                FROM audit_log
                WHERE created_at > NOW() - (%(days)s || ' days')::interval
                GROUP BY action
                ORDER BY so_lan DESC
            """, {"days": days})
            ket_qua["theo_hanh_dong"] = [dict(r) for r in cur.fetchall()]

            # -- An ninh: đăng nhập hỏng và bị từ chối quyền --
            # Đây là phần quan trọng nhất của trang quản trị mà `staff_workload` không đụng tới.
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE action = 'login' AND result = 'ok')
                                                                       AS so_dang_nhap,
                       COUNT(*) FILTER (WHERE action = 'login_failed') AS so_dang_nhap_hong,
                       COUNT(*) FILTER (WHERE action = 'account_locked') AS so_khoa_tai_khoan,
                       COUNT(*) FILTER (WHERE result = 'denied')       AS so_bi_tu_choi,
                       COUNT(DISTINCT username) FILTER (WHERE action = 'login' AND result = 'ok')
                                                                       AS so_nguoi_hoat_dong,
                       COUNT(DISTINCT ip)                              AS so_dia_chi_ip
                FROM user_activity
                WHERE created_at > NOW() - (%(days)s || ' days')::interval
            """, {"days": days})
            an_ninh = dict(cur.fetchone() or {})
            ket_qua["an_ninh"] = an_ninh

            # Địa chỉ IP đăng nhập hỏng nhiều nhất — dấu hiệu dò mật khẩu
            cur.execute("""
                SELECT ip, COUNT(*) AS so_lan, MAX(created_at) AS lan_cuoi,
                       COUNT(DISTINCT username) AS so_tai_khoan_bi_thu
                FROM user_activity
                WHERE action = 'login_failed'
                  AND created_at > NOW() - (%(days)s || ' days')::interval
                  AND ip IS NOT NULL
                GROUP BY ip
                HAVING COUNT(*) >= 5
                ORDER BY so_lan DESC
                LIMIT 10
            """, {"days": days})
            ket_qua["ip_dang_nhap_hong"] = _iso([dict(r) for r in cur.fetchall()], "lan_cuoi")

            # -- Nhịp làm việc theo ngày --
            cur.execute("""
                SELECT DATE(created_at) AS ngay,
                       COUNT(*)                                    AS so_tai_lieu,
                       COUNT(*) FILTER (WHERE status = 'failed')   AS so_that_bai
                FROM documents
                WHERE created_at > NOW() - (%(days)s || ' days')::interval
                  AND status <> 'deleted'
                GROUP BY DATE(created_at)
                ORDER BY ngay DESC
            """, {"days": days})
            ket_qua["theo_ngay"] = [
                {**dict(r), "ngay": r["ngay"].isoformat()} for r in cur.fetchall()
            ]

    ket_qua["nguoi_dung"] = per_user(days)["nguoi_dung"]
    ket_qua["canh_bao"] = _canh_bao(ket_qua)
    ket_qua["ghi_chu"] = GHI_CHU_CACH_DOC
    return ket_qua


def _canh_bao(data: Dict) -> List[Dict]:
    """
    Những điều đáng để mắt, viết thành câu tiếng Việt.

    Trả về danh sách rỗng khi mọi thứ bình thường — KHÔNG bịa ra cảnh báo cho đủ chỗ trên màn hình.
    Một bảng cảnh báo lúc nào cũng có gì đó sẽ nhanh chóng bị bỏ qua, kể cả khi nó nói thật.
    """
    canh_bao: List[Dict] = []
    an_ninh = data.get("an_ninh") or {}
    khoi_luong = data.get("khoi_luong") or {}

    hong = int(an_ninh.get("so_dang_nhap_hong") or 0)
    thanh_cong = int(an_ninh.get("so_dang_nhap") or 0)
    # Ngưỡng kép (số tuyệt đối VÀ tỉ lệ): chỉ dùng tỉ lệ thì một hệ thống mới với 1 lần đăng nhập
    # hỏng trên 2 lần thử sẽ báo động; chỉ dùng số tuyệt đối thì hệ thống lớn không bao giờ báo.
    if hong >= 20 and hong > thanh_cong * 0.2:
        canh_bao.append({
            "muc": "canh_bao",
            "noi_dung": f"{hong} lần đăng nhập thất bại trong kỳ — kiểm tra danh sách IP bên dưới",
        })

    if data.get("ip_dang_nhap_hong"):
        top = data["ip_dang_nhap_hong"][0]
        if int(top.get("so_tai_khoan_bi_thu") or 0) >= 3:
            canh_bao.append({
                "muc": "nguy_hiem",
                "noi_dung": (f"Địa chỉ {top['ip']} thử đăng nhập vào "
                             f"{top['so_tai_khoan_bi_thu']} tài khoản khác nhau — dấu hiệu dò mật khẩu"),
            })

    tu_choi = int(an_ninh.get("so_bi_tu_choi") or 0)
    if tu_choi >= 10:
        canh_bao.append({
            "muc": "thong_tin",
            "noi_dung": (f"{tu_choi} lần bị từ chối quyền — có thể cán bộ đang thiếu quyền cần thiết "
                         f"cho công việc, xem lại phân vai"),
        })

    can_xem = int(khoi_luong.get("so_can_xem_lai") or 0)
    hoan_thanh = int(khoi_luong.get("so_hoan_thanh") or 0)
    if hoan_thanh and can_xem > hoan_thanh * 0.3:
        canh_bao.append({
            "muc": "canh_bao",
            "noi_dung": (f"{can_xem}/{hoan_thanh} tài liệu bị đánh dấu cần xem lại (trên 30%) — "
                         f"chất lượng trích xuất đang giảm, xem trang Phân tích AI"),
        })

    that_bai = int(khoi_luong.get("so_that_bai") or 0)
    tong = int(khoi_luong.get("so_tai_lieu") or 0)
    if tong and that_bai > tong * 0.1:
        canh_bao.append({
            "muc": "nguy_hiem",
            "noi_dung": f"{that_bai}/{tong} tài liệu xử lý thất bại (trên 10%) — kiểm tra nhật ký worker",
        })

    return canh_bao


# =====================================================================
# ĐỘ CHÍNH XÁC CỦA VIỆC ĐOÁN LOẠI (YC-SC-09)
# =====================================================================

def classification_accuracy(days: int = 30) -> Dict:
    """
    Máy đoán loại tài liệu đúng bao nhiêu phần trăm — đo trên VIỆC THẬT, không phải tập mẫu.

    Đáp án chuẩn là loại mà CÁN BỘ ĐÃ XÁC NHẬN (`document_type` sau khi duyệt); dự đoán là
    `detected_type`. Nguồn đáp án này miễn phí và tích lũy mỗi ngày — đúng nguyên tắc SRS
    "đo được mới tuyên bố": không có bảng này thì không được phép nói bộ đoán loại chính xác bao nhiêu.

    Chỉ tính tài liệu ĐÃ ĐƯỢC XÁC NHẬN: tài liệu chưa ai xem thì `document_type` vẫn đang là giá trị
    máy đặt, so với chính nó sẽ ra 100% — một con số đẹp và hoàn toàn vô nghĩa.
    """
    sql = """
        SELECT COUNT(*)                                                  AS tong_so,
               COUNT(*) FILTER (WHERE detected_type = document_type)     AS so_dung,
               ROUND(AVG(detected_confidence)::numeric, 3)               AS tin_cay_tb
        FROM documents
        WHERE detected_type IS NOT NULL
          AND confirmed_at IS NOT NULL
          AND created_at > NOW() - (%(days)s || ' days')::interval
    """
    sql_theo_loai = """
        SELECT detected_type                                         AS may_doan,
               document_type                                         AS can_bo_chot,
               COUNT(*)                                              AS so_lan
        FROM documents
        WHERE detected_type IS NOT NULL
          AND confirmed_at IS NOT NULL
          AND detected_type <> document_type
          AND created_at > NOW() - (%(days)s || ' days')::interval
        GROUP BY detected_type, document_type
        ORDER BY so_lan DESC
        LIMIT 20
    """

    try:
        with db.get_conn() as conn:
            with _dict_cursor(conn) as cur:
                cur.execute(sql, {"days": days})
                tong = dict(cur.fetchone() or {})
                cur.execute(sql_theo_loai, {"days": days})
                nham_lan = [dict(r) for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001 — chưa chạy migration 010 thì nói rõ, không trả 0%
        logger.info("Chưa đo được độ chính xác đoán loại: %s", e)
        return {"so_ngay": days, "chua_do_duoc": True,
                "ly_do": "Chưa chạy migration 010_doc_classification.sql"}

    tong_so = int(tong.get("tong_so") or 0)
    so_dung = int(tong.get("so_dung") or 0)

    return {
        "so_ngay": days,
        "tong_so": tong_so,
        "so_dung": so_dung,
        # None (không phải 0) khi chưa có mẫu nào: "chưa đo được" và "đoán sai hết" là hai chuyện
        # hoàn toàn khác nhau, và hiển thị 0% khi chưa có dữ liệu là nói dối bằng con số.
        "ty_le_dung": round(so_dung * 100.0 / tong_so, 1) if tong_so else None,
        "tin_cay_tb": float(tong["tin_cay_tb"]) if tong.get("tin_cay_tb") is not None else None,
        "nham_lan_thuong_gap": nham_lan,
        "ghi_chu": (
            "Đo trên tài liệu cán bộ ĐÃ xác nhận — loại cán bộ chốt là đáp án chuẩn. "
            "Bảng «nhầm lẫn thường gặp» cho biết nên bổ sung dấu hiệu nào vào "
            "scripts/core/doc_classifier.py."
        ),
    }
