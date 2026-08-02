#!/usr/bin/env bash
#
# Diễn tập khôi phục (YC-VH-08 — sprint V9).
#
# 🔴 LÝ DO TỒN TẠI: một bản sao lưu chưa từng được khôi phục thử **không phải là bản sao lưu** — nó
# là một tệp mà ta HY VỌNG dùng được. Rất nhiều tổ chức phát hiện bản dump của mình rỗng, cắt cụt,
# hoặc thiếu bảng đúng vào ngày cần tới nó.
#
# Kịch bản này khôi phục vào một cơ sở dữ liệu TẠM (không đụng dữ liệu thật) rồi ĐỐI CHIẾU số bản ghi
# với bản kê đã ghi lúc sao lưu. "Khôi phục thành công" phải nghĩa là số liệu khớp, không phải là
# "lệnh chạy xong mà không báo lỗi".
#
# Dùng:
#   scripts/ops/restore-drill.sh /data/backups/docuflow/20260802-020000
#
# Chạy ÍT NHẤT MỖI QUÝ và ghi kết quả vào docs/DEPLOY.md.

set -euo pipefail

BACKUP_PATH="${1:-}"
[ -n "$BACKUP_PATH" ] || { echo "Dùng: $0 <đường-dẫn-bản-sao-lưu>"; exit 1; }
[ -d "$BACKUP_PATH" ] || { echo "LỖI: không thấy thư mục $BACKUP_PATH"; exit 1; }

POSTGRES_USER="${POSTGRES_USER:-postgres}"
DRILL_DB="${DRILL_DB:-library_digitization_drill}"
COMPOSE="${COMPOSE:-docker compose}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "=== DIỄN TẬP KHÔI PHỤC ==="
log "Bản sao lưu: $BACKUP_PATH"
log "Cơ sở dữ liệu tạm: $DRILL_DB (KHÔNG đụng dữ liệu thật)"
log ""

[ -f "$BACKUP_PATH/database.dump" ] || { log "LỖI: thiếu database.dump"; exit 1; }

# ── 1. Dựng CSDL tạm ────────────────────────────────────────────────
# Tên khác hẳn CSDL thật, và luôn DROP trước để lần diễn tập trước không làm sai kết quả lần này.
log "Tạo cơ sở dữ liệu tạm..."
$COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -c "DROP DATABASE IF EXISTS $DRILL_DB;" >/dev/null
$COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -c "CREATE DATABASE $DRILL_DB;" >/dev/null

# ── 2. Khôi phục ────────────────────────────────────────────────────
log "Khôi phục bản dump..."
if ! $COMPOSE exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$DRILL_DB" --no-owner \
        < "$BACKUP_PATH/database.dump"; then
    log "❌ KHÔI PHỤC THẤT BẠI — bản sao lưu này KHÔNG dùng được"
    exit 1
fi

# ── 3. Đối chiếu số bản ghi ─────────────────────────────────────────
# Đây là phần làm cho diễn tập có giá trị. Không đối chiếu thì chỉ biết "pg_restore không báo lỗi",
# mà pg_restore vẫn trả về 0 khi khôi phục một cơ sở dữ liệu rỗng.
log ""
log "Đối chiếu số bản ghi với bản kê lúc sao lưu:"

sai_lech=0
while IFS='=' read -r bang mong_doi; do
    case "$bang" in
        documents|metadata_fields|audit_log|model_calls) ;;
        *) continue ;;
    esac

    thuc_te="$($COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d "$DRILL_DB" -At \
                -c "SELECT COUNT(*) FROM $bang;" 2>/dev/null | tr -d '[:space:]')"

    if [ "$thuc_te" = "$mong_doi" ]; then
        log "  ✅ $bang: $thuc_te"
    else
        log "  ❌ $bang: mong đợi $mong_doi, khôi phục được $thuc_te"
        sai_lech=$((sai_lech + 1))
    fi
done < "$BACKUP_PATH/manifest.txt"

# ── 4. Kiểm tra tệp tài liệu ────────────────────────────────────────
if [ -f "$BACKUP_PATH/documents.tar.gz" ]; then
    log ""
    log "Kiểm tra tệp nén tài liệu..."
    if tar -tzf "$BACKUP_PATH/documents.tar.gz" >/dev/null 2>&1; then
        so_pdf="$(tar -tzf "$BACKUP_PATH/documents.tar.gz" | grep -c '\.pdf$' || true)"
        log "  ✅ Tệp nén đọc được, chứa $so_pdf tệp PDF"
    else
        log "  ❌ Tệp nén HỎNG — không giải nén được"
        sai_lech=$((sai_lech + 1))
    fi
else
    log "  ⚠️  Không có documents.tar.gz trong bản sao lưu này"
fi

# ── 5. Dọn ──────────────────────────────────────────────────────────
log ""
log "Xóa cơ sở dữ liệu tạm..."
$COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -c "DROP DATABASE IF EXISTS $DRILL_DB;" >/dev/null

# ── Kết luận ────────────────────────────────────────────────────────
log ""
if [ "$sai_lech" -eq 0 ]; then
    log "✅ DIỄN TẬP ĐẠT — bản sao lưu này khôi phục được và số liệu khớp."
    log "   Ghi kết quả (ngày, người chạy, bản sao lưu nào) vào docs/DEPLOY.md."
    exit 0
else
    log "❌ DIỄN TẬP KHÔNG ĐẠT — $sai_lech hạng mục sai lệch."
    log "   ĐỪNG tin vào bản sao lưu này. Kiểm tra lại kịch bản sao lưu ngay."
    exit 1
fi
