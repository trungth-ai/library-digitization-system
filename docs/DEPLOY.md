# Hướng dẫn triển khai (Deploy) — DocuFlow HP

> Triển khai bằng Docker Compose (YC-VH-03: một lệnh). Đã rà deploy-readiness (commit `3c1de6c`):
> UI build không phụ thuộc Google Fonts, có `/api/health`, `.dockerignore` chặn secret, healthcheck sửa.

## 0. ⚠️ Máy chủ trung tâm HPU — khớp cấu hình TRƯỚC khi `up`

Máy chủ đang chạy Caddy làm reverse proxy chung cho nhiều ứng dụng của trường. Ba thứ phải khớp,
nếu không `docker compose up` sẽ **fail** hoặc **làm chết ứng dụng khác**:

| Vấn đề | Triệu chứng | Cách khớp |
|---|---|---|
| **CPU vượt máy chủ** | `Error response from daemon: Range of CPUs is from 0.01 to 4.00` | `WORKER_REPLICAS × WORKER_CPUS` < tổng CPU. Máy 4 CPU: `WORKER_REPLICAS=1`, `WORKER_CPUS=2` |
| **Cổng 3000 đã bị chiếm** | UI không lên, hoặc `chat.hpu.edu.vn` chết | `UI_PORT=3200` (mặc định mới). **KHÔNG dùng 3000** |
| **Thiếu `LIBRARY_API_URL`** | `WARN The "LIBRARY_API_URL" variable is not set` | Đã có mặc định; copy lại `.env.example` để hết cảnh báo |

Cổng đã dùng trên máy chủ (theo Caddyfile): `3000` chat · `3003` hr · `3100` crm · `3955/3975/3976/3978/3979/3983` đào tạo · `5000` syllabus · `8100` mkt · `8181` decuong · `8800` mcp-lib.

Mặc định của compose sau khi sửa: **UI 3200, API 8000, PostgreSQL 5433, Redis 6380**, tất cả chỉ mở
trên `127.0.0.1` (Caddy chạy `network_mode: host` nên vẫn gọi được `localhost`). Muốn truy cập trực
tiếp từ máy khác khi gỡ lỗi: `BIND_ADDR=0.0.0.0`.

### Block Caddy cần thêm vào Caddyfile trung tâm

```caddyfile
sohoa.hpu.edu.vn {
    import tls_hpu
    encode zstd gzip
    request_body { max_size 512MB }

    handle /ocr-api/* {
        uri strip_prefix /ocr-api
        reverse_proxy localhost:8000 {
            import proxy_headers
            import proxy_timeout
            flush_interval -1        # SSE tiến độ OCR: không được buffer
        }
    }
    handle {
        reverse_proxy localhost:3200 {
            import proxy_headers
            import proxy_timeout
        }
    }
}
```

Backend đi theo **đường dẫn `/ocr-api`** trên cùng hostname, không dùng subdomain riêng: chứng chỉ
`hpu.edu.vn` là wildcard một cấp nên `api.sohoa.hpu.edu.vn` sẽ không khớp.

Áp dụng (kiểm cú pháp TRƯỚC khi reload — Caddy này đang phục vụ nhiều ứng dụng):
```bash
docker exec caddy caddy validate --config /etc/caddy/Caddyfile
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

Trong `.env` của app phải khớp tên miền:
```env
PUBLIC_BASE_URL=https://sohoa.hpu.edu.vn
PUBLIC_API_URL=https://sohoa.hpu.edu.vn/ocr-api
```
Đổi hai biến này thì **phải build lại UI** (`docker compose up -d --build ui`) — Next.js nhúng
`NEXT_PUBLIC_*` vào bundle lúc build, restart không có tác dụng.

## 1. Yêu cầu
- Docker + Docker Compose trên server.
- (Tùy chọn) Một công cụ mô hình tại chỗ — Ollama, vLLM hoặc llama.cpp, mỗi cái một profile riêng
  (mục 5). vLLM cần GPU NVIDIA để phát huy; hai cái còn lại chạy CPU.

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

# 5) (Tùy chọn) Chế độ tại chỗ — chọn MỘT công cụ (xem mục 5 để so sánh)
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
  metadata_fields, audit_log, extraction_schemas, model_calls... + seed lookup).
- Nếu volume `postgres_data` đã tồn tại từ trước, init.sql KHÔNG chạy lại → **phải chạy migration**.

### ⚠️ Migration BẮT BUỘC cho DB đã tồn tại

Bản nâng cấp này thêm cột/bảng mới (`documents.updated_at`, `needs_review`, `extraction_*`,
`metadata_fields.confidence`, bảng `model_calls`, trạng thái `deleted`). Trên máy chủ đã chạy, volume
`postgres_data` đã có → `init.sql` không chạy lại → code mới sẽ lỗi *"column does not exist"* nếu bỏ
qua bước này:

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d library_digitization \
    < database/migrations/001_provider_layer_and_soft_delete.sql
```

Migration idempotent (chạy lại nhiều lần không sao) và không xóa dữ liệu — đã kiểm chứng: áp 2 lần
liên tiếp không lỗi, tài liệu + metadata cũ nguyên vẹn, `updated_at` được điền theo `created_at`.

Kiểm tra sau khi chạy:
```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d library_digitization -c \
  "SELECT count(*) FROM information_schema.columns WHERE table_name='documents' AND column_name IN ('updated_at','needs_review');"
# Kỳ vọng: 2
```

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

## 5. Chọn công cụ mô hình khi deploy

Mặc định `MODEL_PROVIDER=cloud` → Claude, **giữ nguyên hành vi hệ đang chạy**. Không phải sửa gì nếu
chưa muốn đổi. Xem danh sách và biến môi trường từng công cụ cần:

```bash
docker compose exec api python -m scripts.eval.run_eval --list-providers
```

Bật một công cụ tại chỗ (chỉ **một** cái tại một thời điểm để không tranh RAM/GPU):

```bash
docker compose --profile local-ai up -d            # Ollama    — CPU, dựng nhanh nhất
docker compose --profile local-ai-vllm up -d       # vLLM      — cần GPU, thông lượng cao
docker compose --profile local-ai-llamacpp up -d   # llama.cpp — CPU, nhẹ nhất, air-gapped tuyệt đối
```

rồi đặt trong `.env`:

```env
MODEL_PROVIDER=local     # bật định tuyến theo chế độ
LOCAL_PROVIDER=vllm      # công cụ đảm nhiệm chế độ tại chỗ
CLOUD_PROVIDER=claude    # công cụ đảm nhiệm chế độ đám mây
```

**Kiểm tra sẵn sàng trước khi đưa tài liệu vào xử lý** (YC-MS-04) — báo cả trường hợp máy chủ sống
nhưng **chưa tải model**, và trả **mã thoát 1** nếu chưa sẵn sàng (dùng được trong script):

```bash
docker compose exec api python -m scripts.eval.run_eval --health
```

```bash
docker compose exec api python -m scripts.eval.run_eval --health --providers claude,ollama,vllm
```

### ⚠️ Hai chốt an toàn có thể làm deploy DỪNG (đúng thiết kế)

Cả hai bảo vệ ràng buộc cứng YC-DR-03 (tài liệu Nội bộ/Nhạy cảm không ra đám mây):

1. Provider khai báo `local` nhưng điểm cuối **không thuộc dải mạng nội bộ** → từ chối khởi tạo. Sửa
   `<TÊN>_BASE_URL` về địa chỉ nội bộ, hoặc khai `<TÊN>_DEPLOYMENT=cloud` nếu đó thực sự là dịch vụ
   ngoài, hoặc đặt `ALLOW_PUBLIC_LOCAL_ENDPOINT=1` nếu đường truyền đã được kiểm soát (VPN/đường riêng).
2. `LOCAL_PROVIDER` lại là một công cụ đám mây (vd `groq`) → mọi tài liệu nhạy cảm bị **từ chối xử lý**.

Thông báo lỗi tiếng Việt nêu rõ cả ba cách xử lý — đọc log `api`/`worker` khi container không lên.

## 6. Sao lưu (YC-VH-05)
```bash
# DB metadata
docker compose exec postgres pg_dump -U "$POSTGRES_USER" -F c library_digitization > backup_$(date +%F).dump
# Dữ liệu số hóa: sao lưu volume ${DIGITIZE_DATA_DIR} (file scan + PDF + OCR) — KHÔNG chỉ backup DB
```

## 7. Trạng thái tích hợp
- ✅ Chạy được: postgres + redis + api (gồm endpoints reports/audit/schemas/providers) + worker + ui.
- ✅ Lớp provider đa công cụ (18 lựa chọn) — đổi bằng cấu hình, không sửa mã.
- ✅ **Worker đã dùng lớp provider** (ADR-008): định tuyến theo độ nhạy cảm + điểm tin cậy + nhật ký
  gọi model. Đổi `MODEL_PROVIDER`/`LOCAL_PROVIDER` giờ đổi thật hành vi xử lý tài liệu.
  Van lùi: `USE_PROVIDER_LAYER=0` → về đường cũ bám Claude, không cần build lại image.
- ✅ Xóa mềm: nút xóa chỉ đặt `status='deleted'`, giữ file + metadata. Xóa vật lý phải gọi rõ
  `DELETE /api/v2/jobs/{id}?purge=true`.
- ✅ Trang **Công cụ mô hình** (`/cong-cu`) hiện công cụ/model đang dùng + tình trạng + số liệu tài nguyên.
- ⏳ RAG (GĐ3): cần model embedding tại chỗ (vd `bge-m3`) + `pgvector` (chưa bật).
- ⏳ UI chưa có: thùng rác/nút phục hồi, trang duyệt riêng tài liệu `needs_review` (API đã sẵn:
  `GET /api/v2/jobs?needs_review=true`, `POST /api/v2/jobs/{id}/restore`).

Xem thêm: `docs/STATUS.md` (tiến độ), `docs/PLAN.md` (sprint đang chạy),
`docs/LOCAL_MODE.md` (chọn công cụ + chọn model), `docs/EVAL.md` (đo số liệu).
