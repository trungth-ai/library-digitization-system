# CLAUDE.md — DocuFlow HP (Library Digitization System)

> File này Claude Code tự đọc mỗi phiên. Đọc kèm `docs/PRODUCT.md`, `docs/ROADMAP.md`,
> `docs/DECISIONS.md` trước khi thay đổi lớn. Nguồn nghiệp vụ gốc: `docs/05_Dac_ta_yeu_cau_phan_mem.docx` (SRS) và `docs/06_Ke_hoach_kiem_thu.docx`.

## Loại app
Sản phẩm số hóa tài liệu **single-tenant** (một Nhà trường), stack SaaS về công nghệ nhưng
KHÔNG multi-tenant → áp dụng chuẩn HPU trừ `tenant-isolation`/RLS.

## Sản phẩm
**DocuFlow HP** — nền tảng số hóa và trích xuất dữ liệu tự động từ hồ sơ giấy, đang vận hành thật
tại Trung tâm Thông tin Thư viện HPU từ 2025. Quy trình: upload PDF → OCR (OCRmyPDF 2 pha 150→120 DPI)
→ trích xuất metadata bằng AI → cán bộ duyệt → đẩy lên DSpace.

**Mục tiêu nâng cấp** (dự thi Khởi nghiệp sáng tạo TP Hải Phòng 2026): kiến trúc **hai chế độ**
(đám mây + **tại chỗ/on-premise** với mô hình mở) + **lớp RAG** tra cứu. Xem `docs/ROADMAP.md`.

## Tech Stack
- **Backend**: Python 3.12, FastAPI, PostgreSQL 15 (psycopg2 pool), Redis 7 (queue + pub/sub), SSE.
- **Worker**: OCRmyPDF + Tesseract (vie+eng) + Ghostscript; trích metadata qua lớp model provider.
- **Frontend**: Next.js 16 (App Router), React 19, Tailwind 4.
- **AI**: hiện dùng Claude (cloud). Đang bổ sung provider tại chỗ (Ollama/vLLM) — xem ADR-002.
- **Tích hợp**: DSpace 6.3/7.x REST API.
- **Hạ tầng**: Docker Compose (postgres, redis, api, worker, ui + n8n/grafana/filebrowser tùy chọn).

## Cấu trúc thư mục (hiện tại → đích)
```
scripts/          # backend Python (api.py, worker.py, digitize.py, db.py, sse.py)
                  # → tái cấu trúc dần sang src/{core,routes,schemas,services,providers}
database/init.sql # schema PostgreSQL (đã tái tạo 07/2026)
ui/               # Next.js frontend
docker/           # Dockerfile.api, Dockerfile.worker
docs/             # SRS, test plan, tài liệu kỹ thuật (.md), roadmap
```

## Lệnh thường dùng
```bash
# Backend (local, cần PostgreSQL + Redis)
uvicorn scripts.api:app --reload --port 8000
python -m scripts.worker

# Frontend
cd ui && npm run dev     # Windows: đặt NEXT_TURBOPACK_EXPERIMENTAL_USE_SYSTEM_TLS_CERTS=1 khi build

# Toàn hệ thống
docker compose up -d --build
```

## Quy tắc BẮT BUỘC (theo chuẩn HPU + nguyên tắc SRS)
1. **API envelope** `{status, data, message}` (+ `meta` phân trang, `code`/`errors` khi lỗi) — qua
   `src/core/responses.py` (`success/error/paginated`). **Code mới** tuân thủ ngay; endpoint cũ
   (`/api/v1/process`, `/api/v2/*`) giữ nguyên để không phá UI đang chạy, di trú dần (ADR-003).
2. **Soft delete**: KHÔNG hard delete. Dùng `status`. (Hiện `delete_job` xóa cứng — cần sửa, xem ROADMAP.)
3. **Mọi bảng** có `id, created_at, updated_at, status`.
4. **Log chi tiết**: mỗi lần gọi model ghi provider/model/version/thời gian (YC-MP-06); audit log
   bất biến cho thao tác nghiệp vụ (YC-AU). Không ghi khóa API/mật khẩu ra log (YC-BM-03).
5. **UI**: palette HPU `#1e3a5f`, sidebar 240px, "confirm trước khi xóa, toast sau thao tác".
6. **Tiếng Việt** cho UI, thông báo lỗi cho người dùng, comment nghiệp vụ. Tên hàm/biến tiếng Anh snake_case.
7. **Commit**: tiếng Anh, conventional commits (feat/fix/docs/chore/refactor).

## Nguyên tắc chi phối (từ SRS — KHÔNG vi phạm)
- **Bổ sung, không viết lại**: hệ thống đang phục vụ thật; mọi thay đổi phải giữ nó tiếp tục chạy.
  Kiểm thử không hồi quy (KT-KH) là bắt buộc trước khi coi thay đổi là xong.
- **Con người giữ quyền quyết định**: không tự ghi vào hệ đích (DSpace) khi chưa có cán bộ xác nhận.
- **Mặc định an toàn**: không rõ độ nhạy cảm → xử lý tại chỗ, không đẩy ra đám mây.
- **Đo được mới tuyên bố**: không đưa con số chưa kiểm thử vào tài liệu/hồ sơ.
- **Giấy phép trước, hiệu năng sau**: rà giấy phép mô hình TRƯỚC khi tải về/dùng.
- **Lớp trừu tượng hóa mô hình viết TRƯỚC, chọn công cụ SAU** (YC-MP trước YC-MS).

## Ranh giới thực thi của Claude Code
- Làm việc trên bản local `D:\PROJECT\library-digitization-system` + commit lên GitHub (private).
- **KHÔNG deploy lên server production** (10.1.1.101) — việc deploy do người phụ trách quyết định.
- Test model tại chỗ cần Ollama + mô hình; nếu máy dev thiếu, viết code + test mock và ghi rõ cần chạy thật ở đâu.

## Tài liệu liên quan
- `docs/PRODUCT.md` — mô tả sản phẩm + kiến trúc nâng cấp
- `docs/REQUIREMENTS.md` — yêu cầu kỹ thuật (bảng YC-*) + chuẩn HPU
- `docs/ROADMAP.md` — lộ trình chia sprint
- `docs/DECISIONS.md` — ADR (quyết định kiến trúc)
- `docs/PLAN.md` — sprint đang chạy
