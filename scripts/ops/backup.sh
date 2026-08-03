#!/usr/bin/env bash
#
# Sao lưu DocuFlow HP (YC-VH-07 — sprint V9).
#
# VÌ SAO ĐÂY LÀ HẠNG MỤC KHÔNG ĐƯỢC HOÃN: YC-VH-05 là yêu cầu của SRS nhưng **chưa từng được hiện
# thực**. Hệ thống đang phục vụ thật, và phần dữ liệu giá trị nhất — các bản PDF đã OCR — là thứ
# không tái tạo được nếu bản giấy đã trả lại kho hoặc đã hư hỏng.
#
# 🔴 SAO LƯU CHƯA TỪNG KHÔI PHỤC THỬ THÌ CHƯA PHẢI LÀ SAO LƯU. Xem `restore-drill.sh` (YC-VH-08).
#
# Dùng:
#   scripts/ops/backup.sh                    # sao lưu vào $BACKUP_DIR
#   BACKUP_DIR=/mnt/nas/docuflow backup.sh   # nơi khác
#
# Đặt lịch (crontab trên máy chủ, 2 giờ sáng hằng ngày):
#   0 2 * * * cd /opt/docuflow && scripts/ops/backup.sh >> /var/log/docuflow-backup.log 2>&1

set -euo pipefail

# ── Cấu hình ────────────────────────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-/data/backups/docuflow}"
BACKUP_KEEP="${BACKUP_KEEP:-14}"
DIGITIZE_DATA_DIR="${DIGITIZE_DATA_DIR:-/data/digitization/jobs}"
COMPOSE="${COMPOSE:-docker compose}"

# ⚠️ KHÔNG đọc POSTGRES_USER/POSTGRES_DB từ shell của người chạy.
#
# Chúng nằm trong `.env` — thứ mà `docker compose` đọc, còn shell thì KHÔNG. Bản đầu của kịch bản này
# dùng `${POSTGRES_USER:-postgres}`, và trên máy chủ thật (user là `libraryuser`) nó lặng lẽ lùi về
# `postgres` rồi chết với "role postgres does not exist" — một bản sao lưu thất bại vì lý do trông
# như lỗi cấu hình PostgreSQL chứ không phải lỗi của kịch bản.
#
# Thay vào đó: khai triển biến BÊN TRONG container qua `sh -c`. Đúng do kiến trúc — giá trị lấy từ
# chính container đã được khởi tạo bằng nó, không thể lệch.
psql_in_container() {
    $COMPOSE exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" '"$*"
}

STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="$BACKUP_DIR/$STAMP"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
fail() { log "LỖI: $*"; exit 1; }

# ── Kiểm tra trước ──────────────────────────────────────────────────
# Kiểm dung lượng TRƯỚC khi bắt đầu: một bản sao lưu dở dang chiếm chỗ mà không dùng được là tình
# huống tệ nhất — vừa mất chỗ vừa không có bản sao.
mkdir -p "$TARGET"

available_kb="$(df -Pk "$BACKUP_DIR" | awk 'NR==2 {print $4}')"
needed_kb="$(du -sk "$DIGITIZE_DATA_DIR" 2>/dev/null | awk '{print $1}' || echo 0)"
if [ "$available_kb" -lt "$((needed_kb + 1048576))" ]; then
    fail "Không đủ dung lượng: cần ~$((needed_kb / 1024)) MB + 1 GB dự phòng, còn $((available_kb / 1024)) MB"
fi

log "Bắt đầu sao lưu vào $TARGET"

# ── 0. Kiểm nối được PostgreSQL TRƯỚC khi làm gì ────────────────────
# Thất bại ở đây phải nói rõ là "không nối được", chứ không để lộ ra dưới dạng một tệp dump 0 byte —
# đúng cái đã xảy ra khi kịch bản này còn đọc POSTGRES_USER từ shell.
if ! psql_in_container -At -c "SELECT 1" >/dev/null 2>&1; then
    fail "Không nối được PostgreSQL trong container. Kiểm tra: docker compose ps postgres"
fi

# ── 1. Cơ sở dữ liệu ────────────────────────────────────────────────
# `--format=custom` (nén sẵn, khôi phục chọn lọc được) thay vì SQL thuần: bản dump 5 GB dạng SQL rất
# chậm khi khôi phục và không cho phép khôi phục riêng một bảng khi cần đối chiếu.
log "Sao lưu PostgreSQL..."
if ! $COMPOSE exec -T postgres sh -c \
        'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
        > "$TARGET/database.dump"; then
    fail "pg_dump thất bại — KHÔNG có bản sao lưu cơ sở dữ liệu"
fi

db_size="$(stat -c %s "$TARGET/database.dump" 2>/dev/null || stat -f %z "$TARGET/database.dump")"
[ "$db_size" -gt 1024 ] || fail "Bản dump quá nhỏ ($db_size byte) — nhiều khả năng lỗi"
log "Đã sao lưu cơ sở dữ liệu ($((db_size / 1024 / 1024)) MB)"

# ── 2. Tệp tài liệu ─────────────────────────────────────────────────
# Đây là phần KHÔNG tái tạo được. Cơ sở dữ liệu mất thì còn tài liệu để xử lý lại; tài liệu mất thì
# phải đi tìm lại bản giấy.
log "Sao lưu tệp tài liệu từ $DIGITIZE_DATA_DIR..."
if [ -d "$DIGITIZE_DATA_DIR" ]; then
    tar -czf "$TARGET/documents.tar.gz" -C "$(dirname "$DIGITIZE_DATA_DIR")" \
        "$(basename "$DIGITIZE_DATA_DIR")" || fail "Nén tệp tài liệu thất bại"
    log "Đã sao lưu tệp tài liệu"
else
    log "CẢNH BÁO: không thấy thư mục $DIGITIZE_DATA_DIR — bỏ qua phần tệp"
fi

# ── 3. Cấu hình ─────────────────────────────────────────────────────
# KHÔNG sao lưu `.env` (chứa khóa API và mật khẩu). Chỉ ghi lại DANH SÁCH TÊN biến để khi khôi phục
# còn biết cần điền những gì — giá trị thật lấy từ nơi quản lý bí mật của Nhà trường.
if [ -f .env ]; then
    grep -oE '^[A-Z_]+=' .env | tr -d '=' > "$TARGET/env-keys.txt" 2>/dev/null || true
    log "Đã ghi danh sách tên biến môi trường (KHÔNG chứa giá trị)"
fi

# ── 4. Bản kê để kiểm chứng ─────────────────────────────────────────
# Ghi số bản ghi từng bảng: đây là căn cứ đối chiếu khi diễn tập khôi phục (YC-VH-08). Không có nó
# thì "khôi phục thành công" chỉ là "lệnh chạy xong mà không báo lỗi".
log "Ghi bản kê số bản ghi..."
psql_in_container -At -c "\"
    SELECT 'documents=' || COUNT(*) FROM documents
    UNION ALL SELECT 'metadata_fields=' || COUNT(*) FROM metadata_fields
    UNION ALL SELECT 'audit_log=' || COUNT(*) FROM audit_log
    UNION ALL SELECT 'model_calls=' || COUNT(*) FROM model_calls;
\"" > "$TARGET/manifest.txt" 2>/dev/null || log "CẢNH BÁO: không ghi được bản kê"

# Bản kê rỗng làm diễn tập khôi phục thành nghi thức trống rỗng: không có gì để đối chiếu thì
# `restore-drill.sh` sẽ báo ĐẠT dù bản dump có vấn đề.
[ -s "$TARGET/manifest.txt" ] || log "CẢNH BÁO: bản kê RỖNG — diễn tập khôi phục sẽ không đối chiếu được gì"

{
    echo "created_at=$(date -Iseconds)"
    echo "database_bytes=$db_size"
} >> "$TARGET/manifest.txt"

# ── 5. Dọn bản cũ ───────────────────────────────────────────────────
# Dọn SAU KHI bản mới đã hoàn tất: dọn trước rồi sao lưu thất bại là mất cả bản cũ lẫn bản mới.
log "Giữ lại $BACKUP_KEEP bản gần nhất..."
cd "$BACKUP_DIR"
ls -1dt */ 2>/dev/null | tail -n "+$((BACKUP_KEEP + 1))" | while read -r old; do
    log "  xóa bản cũ: $old"
    rm -rf "$old"
done

log "HOÀN TẤT. Bản sao lưu: $TARGET"
log ""
log "⚠️  NHẮC: bản sao lưu chưa từng khôi phục thử thì chưa phải là bản sao lưu."
log "    Chạy diễn tập ít nhất mỗi quý:  scripts/ops/restore-drill.sh $TARGET"
