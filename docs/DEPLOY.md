# Hướng dẫn triển khai (Deploy) — DocuFlow HP

> Triển khai bằng Docker Compose (YC-VH-03: một lệnh). Đã rà deploy-readiness (commit `3c1de6c`):
> UI build không phụ thuộc Google Fonts, có `/api/health`, `.dockerignore` chặn secret, healthcheck sửa.

## 1. Yêu cầu
- Docker + Docker Compose trên server.
- (Tùy chọn) Ollama cho chế độ tại chỗ — chạy qua profile `local-ai`.

## 2. Các bước deploy

```bash
# 1) Kéo mã nguồn
git clone git@github.com:trungth-ai/library-digitization-system.git
cd library-digitization-system

# 2) Cấu hình backend — điền giá trị THẬT
cp .env.example .env
#   Sửa .env: CLAUDE_API_KEY, POSTGRES_PASSWORD, DSPACE_API_URL/TOKEN, DIGITIZE_DATA_DIR...

# 3) Cấu hình UI — QUAN TRỌNG (xem mục 4)
cp ui/.env.example ui/.env
#   Sửa NEXT_PUBLIC_OCR_API_URL = URL mà TRÌNH DUYỆT truy cập được (IP/domain server), KHÔNG phải 'api:8000'

# 4) Dựng & chạy (postgres, redis, api, worker, ui)
docker compose up -d --build

# 5) (Tùy chọn) Chế độ tại chỗ — thêm Ollama
docker compose --profile local-ai up -d
docker compose exec ollama ollama pull qwen2.5:7b   # chỉ mô hình đã rà giấy phép (docs/LICENSES.md)
```

## 3. Kiểm tra sau deploy
```bash
docker compose ps                       # tất cả service 'healthy'
curl http://localhost:8000/health       # API: {"status":"ok",...}
curl http://localhost:3000/api/health   # UI:  {"status":"ok","service":"ui"}
```
- PostgreSQL tự chạy `database/init.sql` khi khởi tạo volume LẦN ĐẦU (tạo bảng documents, job_statuses,
  metadata_fields, audit_log, extraction_schemas... + seed lookup).
- Nếu volume `postgres_data` đã tồn tại từ trước, init.sql KHÔNG chạy lại → phải migrate thủ công.

## 4. ⚠️ Lưu ý build-time cho UI (NEXT_PUBLIC_*)
Biến `NEXT_PUBLIC_*` được nhúng vào bundle **lúc build**, không phải runtime. `docker-compose.yml` hiện
truyền chúng ở `environment` (runtime) — đủ cho các route proxy `/api/*` (server-side), NHƯNG phần client
gọi trực tiếp FastAPI (SSE, một số fetch) cần giá trị **lúc build**. Hai cách:
- **Khuyến nghị:** build UI với biến đặt sẵn, ví dụ sửa service `ui` trong compose thêm:
  ```yaml
  build:
    context: ./ui
    args:
      NEXT_PUBLIC_OCR_API_URL: https://digitize.hpu.edu.vn   # URL trình duyệt truy cập được
      NEXT_PUBLIC_DSPACE_URL: https://lib.hpu.edu.vn
      NEXT_PUBLIC_SITE_URL: https://digitize.hpu.edu.vn
  ```
  và trong `ui/Dockerfile` (stage builder) khai báo `ARG` + `ENV` tương ứng trước `npm run build`.
- Hoặc để mọi lời gọi backend đi qua route proxy `/api/*` của Next.js (server-side dùng runtime env).

## 5. Sao lưu (YC-VH-05)
```bash
# DB metadata
docker compose exec postgres pg_dump -U "$POSTGRES_USER" -F c library_digitization > backup_$(date +%F).dump
# Dữ liệu số hóa: sao lưu volume ${DIGITIZE_DATA_DIR} (file scan + PDF + OCR) — KHÔNG chỉ backup DB
```

## 6. Trạng thái tích hợp
- ✅ Chạy được: postgres + redis + api (gồm endpoints reports/audit/schemas) + worker (pipeline hiện tại) + ui.
- ⏳ Chưa wire: worker CHƯA dùng router+quality+audit (vẫn trích như cũ) — sẽ tích hợp có regression (ADR-004).
- ⏳ RAG (GĐ3): cần Ollama embedding + `pgvector` (chưa bật).

Xem thêm: `docs/STATUS.md` (tiến độ), `docs/LOCAL_MODE.md` (chế độ tại chỗ), `docs/EVAL.md` (đo số liệu).
