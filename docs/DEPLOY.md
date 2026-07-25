# Hướng dẫn triển khai (Deploy) — DocuFlow HP

> Triển khai bằng Docker Compose (YC-VH-03: một lệnh). Đã rà deploy-readiness (commit `3c1de6c`):
> UI build không phụ thuộc Google Fonts, có `/api/health`, `.dockerignore` chặn secret, healthcheck sửa.

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
- ✅ Chạy được: postgres + redis + api (gồm endpoints reports/audit/schemas) + worker (pipeline hiện tại) + ui.
- ✅ Lớp provider đa công cụ (18 lựa chọn) — đổi bằng cấu hình, không sửa mã.
- ⏳ Chưa wire: worker CHƯA dùng router+quality+audit (vẫn trích như cũ) — sẽ tích hợp có regression (ADR-004).
  **Hệ quả khi deploy:** đổi `MODEL_PROVIDER` hiện chưa đổi hành vi của worker đang chạy; muốn đo thì
  dùng `run_eval` (mục 5) cho tới khi wire xong.
- ⏳ RAG (GĐ3): cần model embedding tại chỗ (vd `bge-m3`) + `pgvector` (chưa bật).

Xem thêm: `docs/STATUS.md` (tiến độ), `docs/PLAN.md` (sprint đang chạy),
`docs/LOCAL_MODE.md` (chọn công cụ + chọn model), `docs/EVAL.md` (đo số liệu).
