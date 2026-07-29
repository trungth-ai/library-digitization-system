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


## Việc code còn nợ (chưa xếp sprint)

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
- **Đẩy DSpace đang thất bại trên máy chủ** — đã hiện lý do thật ở giao diện; chờ nguyên văn phản
  hồi của DSpace để xác định (nghi: DSpace 6 REST cho đọc công khai nhưng ghi cần
  `rest-dspace-token` chứ không chỉ cookie `JSESSIONID`).

## Định nghĩa "Hoàn thành" (mọi sprint)
- [ ] Không phá endpoint/UI đang chạy (KT-KH pass)
- [ ] Có kiểm thử KT-* tương ứng và **đã chạy đạt** (đo thật, không kỳ vọng)
- [ ] Tài liệu cập nhật (`PLAN.md` này + `DECISIONS.md` nếu có quyết định lớn)
- [ ] Số liệu ghi kèm cỡ mẫu + phương pháp
