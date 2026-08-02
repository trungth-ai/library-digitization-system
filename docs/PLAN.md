# PLAN.md — Sprint đang chạy

> File này được `CLAUDE.md` và quy ước làm việc tham chiếu ("đọc PLAN.md trước khi thay đổi").
> **Phạm vi hẹp: chỉ việc của sprint hiện tại.** Tiến độ tổng thể xem `docs/STATUS.md`; lộ trình dài hạn
> xem `docs/ROADMAP.md`; quyết định kiến trúc ghi ở `docs/DECISIONS.md`.

**Cập nhật:** 29/07/2026 · **Giai đoạn:** GĐ 0 → GĐ 1 (hạn hồ sơ **30/7/2026** — còn 1 ngày)

---

## Sprint vừa xong: đa công cụ mô hình (ADR-007) ✅

| Việc | Kiểm chứng |
|---|---|
| Tách `name` (công cụ) khỏi `deployment` (chế độ) | 213 pytest |
| `TextGenProvider`: thêm công cụ mới = hiện thực một hàm `_complete` | test dựng công cụ mới bằng 5 dòng |
| Bảng đăng ký 18 công cụ (6 tại chỗ / 12 đám mây, có Kimi + Qwen) | `run_eval --list-providers` |
| vLLM + llama.cpp vào compose (profile riêng, không mở cổng) | `docker compose config` |
| Hai chốt an toàn cho YC-DR-03 | test từ chối cấu hình rò rỉ |

## Sprint vừa xong: nối pipeline + trả nợ chuẩn HPU (ADR-008) ✅

| Việc | Kiểm chứng |
|---|---|
| Worker trích metadata **qua lớp provider** (định tuyến + tin cậy + nhật ký) | 31 pytest + 23 kiểm chứng PG thật |
| Van lùi `USE_PROVIDER_LAYER=0` về đường cũ | pytest |
| Dự phòng chéo công cụ **chỉ trong cùng chế độ** | pytest (gồm ca từ chối vượt chế độ) |
| **Xóa mềm** giữ cả file + `restore` + `purge` tách riêng có audit | 39 kiểm chứng PG thật |
| `updated_at` + trigger cho `documents`/`metadata_fields` | PG thật |
| **YC-MS-07** đo thời gian/RAM/GPU + bảng `model_calls` | PG thật |
| **YC-MS-08** trang `/cong-cu` + `/api/v2/providers` | UI build exit 0 + 15 pytest |
| `/bao-cao` dùng API thật, bỏ dữ liệu mẫu | UI build exit 0 |
| Migration 001 cho DB đã tồn tại | áp 2 lần không lỗi, dữ liệu cũ nguyên vẹn |

**Nợ kỹ thuật đã trả:** `delete_job` hard delete → xóa mềm · thiếu `updated_at` · `utcnow()` deprecated ·
đoạn code chết trong `update_metadata` · sidebar toàn `href="#"` · `redis` import cứng làm worker không
test được · `src/core/responses.py` trong tài liệu là đường dẫn không tồn tại.

## Sprint vừa xong: chạy được trên máy chủ thật + theo dõi vận hành (ADR-009) ✅

| Việc | Kiểm chứng |
|---|---|
| Vừa máy chủ 4 CPU, hết xung đột cổng với Caddy trung tâm | `docker compose` chạy được |
| Client gọi API qua proxy same-origin (hết "Failed to fetch") | 17 kiểm chứng Next server thật |
| **Sửa lỗi `redis.exceptions.TimeoutError`** — BLPOP hết giờ không phải lỗi | 11 pytest |
| Nhịp tim worker → giao diện báo được "không có worker nào chạy" | pytest |
| Worker tự thử lại khi PostgreSQL chưa sẵn sàng (thay vì chết vòng vòng) | pytest |
| Bảng `system_events` + đo thời gian xử lý p50/p95 | 21 kiểm chứng PG thật |
| Trang `/cong-cu`: tình trạng từng thành phần + lỗi + thời gian xử lý | 17 kiểm chứng Next thật |
| Hiện lý do thật khi đẩy DSpace thất bại (6 bước, kèm phản hồi DSpace) | UI build exit 0 |
| **Sửa lỗi tải file ZIP** — `Content-Length` rỗng làm mất thân phản hồi (Caddy → 502) | 8 kiểm chứng Next thật, tái hiện được lỗi rồi sửa |

---

## Đường găng tới hạn 30/7 ⏳ CẦN MÁY CHỦ

Phần lớn KHÔNG phải việc code.

| # | Việc | Ai | Chặn bởi |
|---|---|---|---|
| 1 | Deploy theo `docs/DEPLOY.md` — **chạy migration 001 trước** | 👤 người phụ trách | — |
| 2 | Tải model đã rà giấy phép, bật một công cụ tại chỗ | 👤 | (1) + `docs/LICENSES.md` mục 1 |
| 3 | Chuẩn bị BD-01 (30–50 công văn) + đáp án chuẩn | 👤 | — |
| 4 | `run_eval --providers claude,ollama` → bảng so sánh 2 chế độ | 👤 chạy, 🤖 đọc | (2)(3) |
| 5 | **Quay video ngắt Internet vẫn xử lý trọn 1 tài liệu** (KT-BM-01) | 👤 | (2) |
| 6 | Quét cổng từ ngoài chứng minh không mở cổng model (KT-BM-03) | 👤 | (1) |
| 7 | Hoàn tất bảng giấy phép + ý kiến pháp lý (YC-PL-04/06) | 👤 + pháp chế | — |

> ⚠️ Việc 5 và 6 là **bằng chứng cốt lõi** cho lập luận bảo mật — không thay được bằng mô tả kỹ thuật.
> Việc 7 phải xong **trước khi ký Bản cam kết**.
>
> 💡 Việc 5: dùng `llamacpp` (model là file `.gguf` đặt sẵn, container không gọi ra ngoài lúc khởi động).

### Kiểm tra sau khi deploy (thứ tự này)
```bash
# 1. Migration (BẮT BUỘC nếu volume postgres_data đã tồn tại)
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d library_digitization \
    < database/migrations/001_provider_layer_and_soft_delete.sql
# 2. Công cụ đã sẵn sàng chưa
docker compose exec api python -m scripts.eval.run_eval --health
# 3. Log worker phải có dòng "Lớp provider BẬT — công cụ ..."
docker compose logs worker | grep "Lớp provider"
# 4. Xử lý 1 tài liệu thử → mở /cong-cu xem có lượt gọi model, và:
docker compose exec postgres psql -U "$POSTGRES_USER" -d library_digitization \
    -c "SELECT provider, deployment, latency_ms, rss_mb, n_fields FROM model_calls ORDER BY id DESC LIMIT 5;"
```

---


## Sprint vừa xong: V5 nạp tài liệu khối lượng lớn (đường vào) ✅  *(02/08/2026)*

| Việc | Kiểm chứng |
|---|---|
| **YC-BU-02/03** Bỏ trần 10 tệp → hạn mức cấu hình theo *số tệp* và *tổng dung lượng*; khái niệm **lô** | migration 006 + 28 pytest |
| **YC-BU-04** Chống trùng SHA-256 — báo rõ trùng với tài liệu nào | hash đã có sẵn từ ADR-010 |
| **YC-BU-09** Kiểm tệp **thật sự là PDF** (chữ ký tệp), tệp rỗng, PDF có mật khẩu, tải lên đứt giữa chừng | pytest từng ca, mỗi ca một thông báo tiếng Việt riêng |
| **YC-BU-05** Kiểm dung lượng đĩa **trước khi** nhận byte nào | pytest |
| **YC-BU-07 🔴** Nạp từ ZIP — chống **zip-slip** và **zip bomb**, kiểm trên siêu dữ liệu trước khi giải nén | 14 pytest |
| **YC-BU-16** Tạm dừng / tiếp tục / hủy lô; tài liệu đang xử lý dở vẫn chạy xong | 5 pytest, gồm ca tạm dừng lâu không đẩy job vào hàng đợi chết |
| Trang `/lo` — nạp lô, theo dõi tiến độ, **liệt kê từng tệp bị bỏ qua kèm lý do** | UI build exit 0 |

**475 pytest PASS** · UI build exit 0. Endpoint nạp cũ **giữ nguyên** (ADR-003).

> ⚠️ **Cần chạy `database/migrations/006_batches.sql`** (sau 005). Trước khi chạy: `pg_dump`.

### Còn nợ của V5
- **Thư mục theo dõi** (`YC-BU-06`) và **upload chia mảnh** (`YC-BU-08`) chưa làm.
- Chưa đo `KT-HN-08` (thông lượng nạp 500 tệp) — cần bộ BD-06 và môi trường thật.

---

## Sprint vừa xong: V2 phân tích chi tiết kết quả AI ✅  *(02/08/2026)*

| Việc | Kiểm chứng |
|---|---|
| **YC-AN-05 🔴** Độ chính xác **đo trên việc thật** — so giá trị AI với giá trị cán bộ đã duyệt | 15 pytest công thức so sánh (khoảng trắng, ngày tháng, rỗng, Unicode) |
| **Cỡ mẫu tối thiểu** — dưới 30 quan sát trả `null` + "chưa đủ dữ liệu", KHÔNG trả % | pytest chốt hành vi |
| **YC-AN-01/04** Token + chi phí **VNĐ số nguyên**; tại chỗ = 0 đ; chưa biết ≠ 0 đ | 13 pytest, gồm ca tỉ giá hỏng và đơn giá theo tiền tố tên model |
| **YC-AN-02** `model_call_fields` — kết quả từng trường + cờ `grounded` (chống ảo giác) | migration 005 + nối vào `extraction.py` |
| **YC-AN-03** `ocr_runs` — số trang **không có lớp text** = chỉ báo scan xấu cần quét lại | 14 pytest với trang giả |
| **YC-AN-08** Phát hiện suy giảm chất lượng (7 ngày so 30 ngày trước) | chỉ kết luận khi cả hai kỳ đủ mẫu |
| **YC-AN-10** Xuất bảng tính — XLSX nếu có `openpyxl`, không thì **CSV UTF-8 có BOM** | 15 pytest, gồm ca Excel hiển thị sai dấu tiếng Việt |
| **YC-AN-09** Trang `/phan-tich-ai` — ghi chú phương pháp đặt ngay đầu trang | UI build exit 0 |

**429 pytest PASS** · UI build exit 0. Van lùi: `AI_ANALYTICS_DETAIL=0` · `OCR_METRICS_ENABLED=0`.

> ⚠️ **Cần chạy `database/migrations/005_ai_analytics.sql`** (sau 004). Trước khi chạy: `pg_dump`.
> Số liệu độ chính xác **tích lũy dần** — chỉ có ý nghĩa sau khi cán bộ đã duyệt ≥ 30 tài liệu.

---

## Sprint vừa xong: V1 log có cấu trúc + V4 nhật ký người dùng ✅  *(01/08/2026)*

| Việc | Kiểm chứng |
|---|---|
| **YC-LG-01/04** Log JSON một dòng, có `request_id`/`job_id`/`actor`; middleware ghi tổng kết mỗi request | 27 pytest với handler dựng đúng như production |
| **YC-LG-05 🔴** Bộ lọc **che khóa API/mật khẩu** ở tầng logging — YC-BM-03 trước đây *không có cơ chế nào cưỡng chế* | 11 pytest gồm khóa Anthropic/Google/Groq/HF, `Bearer`, cookie phiên |
| **YC-LG-02/03** `contextvars` cho `request_id` (nhận `X-Request-Id` từ giao diện) và `job_id` xuyên suốt vòng đời một tài liệu | pytest ngữ cảnh lồng nhau |
| **YC-LG-06/07** Tệp JSONL luân chuyển + **dọn theo tuổi** — trả nợ "`system_events` sẽ lớn dần" | 17 pytest |
| **YC-NK-01→05** Bảng `user_activity` không sửa được; ghi đăng nhập/đăng xuất/sai mật khẩu/**bị từ chối quyền**/thiếu xác thực | migration 004 + pytest |
| **YC-NK-07** Dòng thời gian một tài liệu: gộp `audit_log` + `user_activity` + `model_calls` + `ocr_runs` | pytest |
| Endpoint `/api/v2/user-activity`, `/api/v2/jobs/{id}/timeline` | py_compile + test phân quyền |

**374 pytest PASS** · UI build exit 0. Van lùi: `LOG_FORMAT=text` · `USER_ACTIVITY_ENABLED=0`.

> ⚠️ **Cần chạy `database/migrations/004_user_activity.sql`** (sau 003). Trước khi chạy: `pg_dump`.
> `audit_log` **không** nằm trong danh sách bảng được dọn theo tuổi — có test chốt điều đó.

---

## Sprint vừa xong: VÁ BA LỖ HỔNG N-01/N-02/N-03 ✅  *(01/08/2026)*

Ba vấn đề của hệ đang chạy, phát hiện khi rà mã cho đợt nâng cấp. Chi tiết quyết định: ADR-010/011/012.

| Việc | Kiểm chứng |
|---|---|
| **N-03** Ghi tệp tải lên theo mảnh, không chặn event loop; băm SHA-256 trong cùng lượt đọc (ADR-010) | 7 pytest, gồm test **tái hiện lỗi cũ** (bản đồng bộ = 0 nhịp event loop) |
| **N-02** Hàng đợi tin cậy `BLMOVE` + thu hồi việc mồ côi + thử lại có khoảng lùi + hàng đợi chết + 3 mức ưu tiên (ADR-011) | 47 pytest, gồm **KT-BU-15** kill worker giữa chừng → 0 job mất |
| **N-01** Danh tính & phân quyền: 4 vai trò, phiên trong PostgreSQL, ba nấc `AUTH_MODE`, khóa sau N lần sai (ADR-012) | 52 pytest, gồm **KT-QT-09** quét AST bắt endpoint ghi thiếu `require()` |
| Giao diện: trang `/dang-nhap`, `/quan-tri/nguoi-dung`, chuyển tiếp cookie qua 12 route proxy | UI build exit 0 |
| Sửa kèm: CORS `allow_origins=["*"]` + cookie (trình duyệt sẽ không gửi cookie) | test AST chặn tái diễn |
| Sửa kèm: `update_document_status` thêm `clear_error` — tài liệu thành công ở lần thử lại không mang lỗi cũ | pytest |
| Sửa kèm: mật khẩu chứa tên tiếng Việt **không dấu** giờ bị chặn (`strip_diacritics`) | pytest |

**330 pytest PASS** (224 cũ + 106 mới) · **0 hồi quy** · UI build exit 0.
Mặc định `AUTH_MODE=off` → **hành vi hệ thống KHÔNG đổi** sau khi cập nhật mã.

### ⚠️ Cần làm trước khi bật xác thực (theo thứ tự)

| # | Việc | Ai |
|---|---|---|
| 1 | `pg_dump` rồi chạy `database/migrations/003_users_rbac.sql` | 👤 |
| 2 | Đặt `ADMIN_BOOTSTRAP_USER`/`PASSWORD`, khởi động API, đăng nhập, **đổi mật khẩu**, rồi **xóa hai biến đó** | 👤 |
| 3 | Tạo tài khoản cho từng cán bộ + tập huấn (vẫn ở `AUTH_MODE=off`) | 👤 |
| 4 | `AUTH_MODE=shadow` → chạy **≥ 1 tuần**, theo dõi `system_events` `kind='auth_missing'` | 👤 |
| 5 | Chỉ bật `AUTH_MODE=on` khi **48 giờ liên tiếp không còn cảnh báo nào** | 👤 |

> Van lùi mọi lúc: `AUTH_MODE=off` · `QUEUE_MODE=blpop` — đổi biến môi trường, **không build lại image**.

### Việc còn nợ của phần vá này
- **Chưa kiểm chứng trên PostgreSQL thật**: `users`, `roles`, `role_permissions`, `user_sessions`
  mới chỉ chạy qua `py_compile` + test logic thuần. Cần chạy migration 003 trên bản sao dữ liệu thật
  (hai lần liên tiếp) và thử trọn luồng đăng nhập → thao tác → đăng xuất.
- **Chưa đo hiệu năng** `KT-HN-08` sau khi đổi cách ghi tệp — ADR-010 ghi rõ thông lượng một tệp đơn
  lẻ *có thể giảm nhẹ*; phải đo chứ không tuyên bố.
- ~~Nhật ký người dùng (`user_activity`)~~ **ĐÃ LÀM** ở sprint V1+V4 ngay sau đó (xem mục trên).
- **Giao diện** cho nhật ký người dùng (`/quan-tri/nhat-ky-nguoi-dung`) và dòng thời gian tài liệu
  chưa có — API đã sẵn (`/api/v2/user-activity`, `/api/v2/jobs/{id}/timeline`).

---

## Sprint kế tiếp: V0 — Chuẩn bị đợt nâng cấp 2  *(cập nhật 31/07/2026)*

Kế hoạch đầy đủ: `docs/UPGRADE_SPRINTS.md`. Yêu cầu: `docs/UPGRADE_REQUIREMENTS.md`.
Kiểm thử: `docs/UPGRADE_TEST_CASES.md`.

**V0 không viết mã** — bốn việc, bỏ qua sẽ làm hỏng các sprint sau:

| # | Việc | Ai |
|---|---|---|
| 1 | Chốt 8 quyết định `QĐ-01→08` (phiên đăng nhập, băm mật khẩu, hạ tầng log, bốn mắt, ai xem năng suất, đường nạp chính, thời hạn lưu) | 👤 + 🤖 tư vấn |
| 2 | Viết ADR-010→016 vào `DECISIONS.md` cho các quyết định đã chốt — **trước khi** viết mã | 🤖 |
| 3 | `pg_dump` dữ liệu thật **và khôi phục thử vào DB tạm** | 👤 |
| 4 | Chuẩn bị BD-06 (500 PDF), BD-07 (8 tài khoản), BD-08 (15 tệp đầu vào xấu) | 👤 |

> ⚠️ **Ba vấn đề của hệ đang chạy** phát hiện khi rà mã (chi tiết ở `UPGRADE_REQUIREMENTS.md` mục 0):
> **N-01** không có xác thực ở backend → `YC-AU-02` hiện không thỏa mãn (sửa ở V3) ·
> **N-02** `BLPOP` (`worker.py:223`) mất job khi worker chết (sửa ở V6) ·
> **N-03** `save_upload_file` (`api.py:142`) chặn event loop (sửa ở V5).

## Việc code còn nợ (chưa xếp sprint)

> Các mục dưới đây **đã được xếp sprint** trong `docs/UPGRADE_SPRINTS.md`: trang duyệt `needs_review`
> + thùng rác → **V8** · `/luoc-do` nối API thật → **V8** · `metadata_history` ghi ở tầng ứng dụng →
> **V4** (chờ có `actor` thật) · dọn `system_events` theo tuổi → **V1**.

- **UI:** trang duyệt tài liệu `needs_review` (tô màu trường điểm thấp bằng `ConfidenceBadge`) và
  thùng rác/phục hồi. API đã sẵn: `GET /api/v2/jobs?needs_review=true`,
  `POST /api/v2/jobs/{id}/restore`, `DELETE /api/v2/jobs/{id}?purge=true`.
- **`/luoc-do`** vẫn dùng dữ liệu mẫu — nối vào `/api/v2/schemas`.
- **GĐ3 RAG:** bật `pgvector`; dùng `embed()` của provider tại chỗ với model embedding chuyên dụng
  (`<TÊN>_EMBED_MODEL`, vd `bge-m3` — YC-MS-05); truy hồi kết hợp; dẫn nguồn bắt buộc.
- **`metadata_history`** hiện ít được ghi vì `update_metadata` dùng DELETE+INSERT nên trigger
  `AFTER UPDATE` không kích hoạt (đã ghi chú trong `init.sql`). Muốn có lịch sử đầy đủ thì chuyển sang
  câu `UPDATE`, hoặc ghi lịch sử ở tầng ứng dụng.
- **Chuẩn hóa `NEXT_PUBLIC` build-args** cho UI image (xem `docs/DEPLOY.md` mục 4).
- **Dọn `system_events` theo tuổi** — bảng sẽ lớn dần, chưa có cơ chế xóa bản ghi cũ. Chưa gấp
  (mỗi sự kiện là một dòng nhỏ, và chỉ ghi khi ĐỔI trạng thái) nhưng cần trước khi chạy dài hạn.
- ~~Đẩy DSpace thất bại~~ **ĐÃ TÌM RA VÀ SỬA**: không phải vấn đề quyền DSpace như tôi nghi ban đầu.
  Route proxy tải file đặt `Content-Length: ''` (FastAPI dùng `StreamingResponse` nên không gửi
  header này) → thân ZIP bị mất, Caddy trả 502. Đã tái hiện được lỗi ở máy dev rồi sửa và kiểm lại.
  **Cần thử lại trên máy chủ để xác nhận bước đẩy DSpace chạy trọn.**

## Định nghĩa "Hoàn thành" (mọi sprint)
- [ ] Không phá endpoint/UI đang chạy (KT-KH pass)
- [ ] Có kiểm thử KT-* tương ứng và **đã chạy đạt** (đo thật, không kỳ vọng)
- [ ] Tài liệu cập nhật (`PLAN.md` này + `DECISIONS.md` nếu có quyết định lớn)
- [ ] Số liệu ghi kèm cỡ mẫu + phương pháp
