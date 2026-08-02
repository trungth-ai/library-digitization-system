# DocuFlow HP — Trạng thái nâng cấp & Bàn giao

> Cập nhật: 29/07/2026. Repo: `github.com/trungth-ai/library-digitization-system`.
> Số commit mới nhất: xem `git log --oneline`. Tài liệu này để kỹ sư tiếp quản (YC-VH-01) nắm nhanh:
> đã làm gì, cách kiểm chứng, còn gì — và **bắt đầu lần nâng cấp tiếp theo từ mục 4**.

## 1. Đã hoàn thành (kiểm chứng ở dev)

| GĐ | Hạng mục | Module | Kiểm chứng |
|---|---|---|---|
| 0 | Lớp trừu tượng hóa mô hình (cloud/local/generic) + factory | `scripts/providers/{base,cloud,local,factory,prompt}.py` | pytest + regression |
| 0 | **Nhiều công cụ mô hình** — bảng đăng ký 18 lựa chọn (6 tại chỗ / 12 đám mây, có Kimi + Qwen dịch vụ), tách `name`↔`deployment` (ADR-007) | `scripts/providers/{registry,textgen,openai_compat,gemini}.py` | pytest (95 test mock, không cần mạng) |
| 0 | Model serving tại chỗ: Ollama + **vLLM** + **llama.cpp** (3 profile riêng) | `docker-compose.yml` | `docs/LOCAL_MODE.md` |
| 0 | Harness đo đạc nhiều công cụ (`--providers claude,ollama,vllm`) | `scripts/eval/` | pytest + smoke CLI |
| 1 | Định tuyến độ nhạy cảm (ràng buộc cứng) | `scripts/providers/router.py` | pytest |
| 1 | **Worker dùng lớp provider** (ADR-008) — định tuyến + tin cậy + nhật ký gọi model; van lùi `USE_PROVIDER_LAYER=0` | `scripts/core/extraction.py`, `worker.py` | 31 pytest + PG thật |
| 1 | **Dự phòng chéo công cụ** cùng chế độ (không bao giờ tại chỗ → đám mây) | `scripts/providers/fallback.py` | pytest |
| 1 | **YC-MS-07** đo tài nguyên (thời gian/RAM/GPU) + bảng `model_calls` | `scripts/core/metrics.py`, `db.py` | PG thật |
| 1 | **YC-MS-08** trang quản trị công cụ/model + tình trạng | `/cong-cu`, `/api/v2/providers` | UI build + pytest |
| — | **Chuẩn HPU: xóa mềm** (giữ file), `updated_at` + trigger, `purge` tách riêng có audit | `db.py`, `init.sql`, migration 001 | 39 kiểm chứng PG thật |
| — | Nối `/bao-cao` vào API thật (bỏ dữ liệu mẫu) | `ui/src/app/bao-cao` | UI build exit 0 |
| — | **Theo dõi vận hành** (ADR-009): sửa lỗi Redis TimeoutError, bảng `system_events`, đo thời gian xử lý p50/p95, `/api/v2/health/detailed`, trang `/cong-cu` | `worker.py`, `db.py`, `api.py`, `ui/src/app/cong-cu` | 11 pytest + 21 PG thật + 17 Next thật |
| — | Client gọi API qua proxy same-origin (hết "Failed to fetch") + hiện lý do lỗi đẩy DSpace | `ui/src/app/api/ocr/*`, `page-client.jsx` | 17 kiểm chứng Next thật |
| 1 | Điểm tin cậy + chống ảo giác | `scripts/core/quality.py` | pytest |
| 2 | Audit log bất biến | `scripts/core/audit.py` + bảng `audit_log` | verify PostgreSQL |
| 2 | Báo cáo (chế độ / tỉ lệ sửa / throughput) | `scripts/core/reports.py` | verify psycopg2 + PG |
| 2 | Lược đồ cấu hình lưu DB | `scripts/core/schema_store.py` + bảng | verify PostgreSQL |
| 2 | Tích hợp API: endpoints reports/audit/schemas (envelope HPU) | `scripts/api.py` | psycopg2+PG + py_compile |
| 2 | UI dashboard `/bao-cao` + `/luoc-do` (design HPU, badge confidence/sensitivity) | `ui/src/app/`, `ui/src/components/hpu/` | verify preview trình duyệt |
| 3 | Chia đoạn theo cấu trúc (RAG) | `scripts/core/chunking.py` | pytest |
| — | **Deploy hardening** (font system, /api/health, .dockerignore, healthcheck, next.config, install.sh) | nhiều | **UI build exit 0 (không TLS flag)** |

**224 pytest PASS · 83 kiểm chứng trên PostgreSQL 17 thật · 34 kiểm chứng route/trang trên Next server thật · UI build exit 0.**
Không hồi quy đường Claude (KT-KH có test chốt). ⚠️ Lần này **CÓ thay đổi pipeline** (ADR-008) —
van lùi `USE_PROVIDER_LAYER=0`; DB đã tồn tại **phải chạy cả `001_*.sql` và `002_monitoring.sql`**
trong `database/migrations/`.

## 2. Cách kiểm chứng
```bash
python -m pytest tests/ -q                 # 224 passed (không cần DB/mạng)
python -m scripts.eval.run_eval --list-providers   # bảng công cụ mô hình khả dụng
python -m scripts.eval.run_eval --health           # kiểm tra sẵn sàng (YC-MS-04)
cd ui && npm run build                     # UI build (KHÔNG cần TLS flag sau khi bỏ Google font)
# Verify DB thật (Windows, không cần Docker):
#   initdb -D <dir> -U postgres --auth-local=trust && pg_ctl -D <dir> -o "-p 55432" start
#   createdb -p 55432 -U postgres library_digitization
#   psql -p 55432 -U postgres -d library_digitization -f database/init.sql
#   → rồi chạy kiểm chứng tầng db.py + chuỗi trích xuất (xem docs/DECISIONS.md ADR-008)
```

## 3. Còn lại — cần MÔI TRƯỜNG THẬT
| Việc | Cần gì | Ai |
|---|---|---|
| Trang thùng rác/phục hồi + trang duyệt tài liệu `needs_review` trên UI (API đã có) | trình duyệt | 🤖 |
| YC-RG embedding + tra cứu (GĐ3) | model embedding tại chỗ (vd `bge-m3`) + `pgvector` | 🤖 structure, số liệu cần env |
| Số liệu đo GĐ0 (KT-CX/KT-HN) cho hồ sơ | server + ≥1 công cụ tại chỗ + BD-01 + đáp án chuẩn | 👤 bạn |
| **Chọn công cụ tại chỗ cho GĐ1 bằng số liệu** (ollama vs vllm vs llamacpp) | server + `run_eval --providers` | 👤 bạn chạy, 🤖 đọc kết quả |
| Bảng giấy phép (YC-PL) + video ngắt mạng + văn bản pháp lý | rà soát + quay + pháp chế | 👤 bạn |

## 3b. ✅ ĐÃ VÁ BA LỖ HỔNG (01/08/2026)

| # | Lỗ hổng | Bản vá | ADR | Kiểm chứng |
|---|---|---|---|---|
| **N-01** | Backend **không có xác thực nào**; `actor` là query param → YC-AU-02 không thỏa mãn | 4 vai trò + phiên trong PostgreSQL + ba nấc `AUTH_MODE=off→shadow→on`; `require()` trên mọi endpoint ghi; khóa sau 5 lần sai; CLI cứu hộ mật khẩu | ADR-012 | 52 pytest, gồm **KT-QT-09** quét AST bắt endpoint ghi thiếu phân quyền |
| **N-02** | `BLPOP` làm **mất job** khi worker chết giữa lúc OCR | `BLMOVE` + danh sách đang-xử-lý + thu hồi việc mồ côi theo nhịp tim + thử lại có khoảng lùi + hàng đợi chết + 3 mức ưu tiên | ADR-011 | 47 pytest, gồm **KT-BU-15** kill worker → **0 job mất** |
| **N-03** | Upload đồng bộ trong `async def` → **chặn event loop**, SSE đứt | Ghi theo mảnh qua thread pool + băm SHA-256 cùng lượt đọc | ADR-010 | 7 pytest, gồm test **tái hiện lỗi cũ** (bản đồng bộ = 0 nhịp) |

**330 pytest PASS** (224 cũ + 106 mới) · **0 hồi quy** · UI build exit 0.
Mặc định `AUTH_MODE=off` + `QUEUE_MODE=reliable` → cập nhật mã **không đổi hành vi** với người dùng.

Ba sửa lỗi kèm theo, phát hiện trong lúc vá: CORS `allow_origins=["*"]` không dùng được cùng cookie ·
`update_document_status` không xóa được `error_message` cũ khi thử lại thành công · mật khẩu chứa tên
tiếng Việt **không dấu** không bị chặn.

**Chưa kiểm chứng trên PostgreSQL thật** — xem `docs/PLAN.md` mục "Việc còn nợ của phần vá này".

## 4. 🚀 Bước tiếp theo cho LẦN NÂNG CẤP TIẾP THEO

> 📌 **Cập nhật 31/07/2026 — đã có kế hoạch nâng cấp đợt 2 đầy đủ.** Đọc theo thứ tự:
> `docs/UPGRADE_REQUIREMENTS.md` (yêu cầu + 3 vấn đề nghiêm trọng phát hiện khi rà mã) →
> `docs/UPGRADE_SPRINTS.md` (9 sprint V1–V9) → `docs/UPGRADE_TEST_CASES.md` (145 trường hợp kiểm thử).
>
> ✅ **Ba lỗ hổng N-01/N-02/N-03 ĐÃ VÁ** (01/08/2026) — xem mục 3b ở trên. Việc còn lại của V0:
> chốt các quyết định `QĐ-01/02/03/04/07/08` còn treo, sao lưu + **khôi phục thử**, chuẩn bị BD-06/07/08.
> (`QĐ-05` và `QĐ-06` đã được người phụ trách chốt ngày 31/07 — xem ADR-012.)

Thứ tự đề xuất trước đây (vẫn đúng cho phần hồ sơ dự thi, chạy song song với V0–V3):

1. **[Ưu tiên hồ sơ]** Deploy lên server theo `docs/DEPLOY.md` → chạy `docs/EVAL.md` lấy bảng so sánh 2 chế độ; rà giấy phép (`docs/LICENSES.md`); quay video ngắt mạng.
2. ~~Tích hợp pipeline~~ **ĐÃ XONG** (ADR-008). Khi deploy: chạy migration 001 trước, theo dõi log
   worker xem dòng "Lớp provider BẬT", rồi xử lý 1 tài liệu thử và kiểm `/cong-cu` + `model_calls`.
3. **UI còn nợ:** trang duyệt tài liệu `needs_review` (dùng `ConfidenceBadge` tô màu trường điểm thấp)
   + thùng rác/phục hồi. API đã sẵn: `GET /api/v2/jobs?needs_review=true`,
   `POST /api/v2/jobs/{id}/restore`. `/luoc-do` vẫn còn dữ liệu mẫu.
4. **GĐ3 RAG:** bật `pgvector`; `embed()` của provider tại chỗ + bảng vector; truy hồi kết hợp (vector + toàn văn); dẫn nguồn bắt buộc (dùng offset từ `chunking.py`); phân quyền kết quả. Đặt `<TÊN>_EMBED_MODEL` để dùng model embedding chuyên dụng thay vì model sinh văn bản (YC-MS-05).
5. **Chuẩn hóa NEXT_PUBLIC build-args** cho UI image (xem `docs/DEPLOY.md` mục 4) khi deploy thật.

## 5. Bản đồ tài liệu (đọc theo nhu cầu)
- `README.md` — điểm vào: sản phẩm, bắt đầu nhanh, chọn công cụ mô hình, bản đồ tài liệu.
- `CLAUDE.md` — điểm neo dự án (stack, quy tắc, ranh giới).
- `docs/PLAN.md` — sprint đang chạy + việc code còn nợ.
- `docs/PRODUCT.md` — mô tả sản phẩm + kiến trúc hai chế độ + RAG.
- `docs/REQUIREMENTS.md` — bảng yêu cầu YC-* + chuẩn HPU.
- `docs/ROADMAP.md` — lộ trình chia sprint (GĐ0-3 + GĐ2B nhánh nâng cấp).
- `docs/UPGRADE_REQUIREMENTS.md` — **yêu cầu nâng cấp đợt 2** (log, AI analytics, khối lượng lớn,
  dashboard, phân quyền, nhật ký người dùng + 4 nhóm đề xuất). Có mục "3 vấn đề nghiêm trọng".
- `docs/UPGRADE_SPRINTS.md` — 9 sprint V1–V9: việc, DoD, van lùi, cổng đi tiếp, thứ tự cắt phạm vi.
- `docs/UPGRADE_TEST_CASES.md` — 145 trường hợp kiểm thử + ma trận truy vết YC ↔ KT ↔ Sprint.
- `docs/DECISIONS.md` — ADR-001..009 (quyết định kiến trúc).
- `docs/DEPLOY.md` — hướng dẫn triển khai + checklist.
- `docs/LOCAL_MODE.md` — chọn/bật công cụ mô hình (Ollama, vLLM, llama.cpp...) + kiểm chứng ngắt mạng.
- `docs/EVAL.md` — đo số liệu 2 chế độ cho hồ sơ.
- `docs/LICENSES.md` — bảng đối chiếu giấy phép (cần hoàn tất trước khi ký cam kết).
- `docs/05_Dac_ta_yeu_cau_phan_mem.docx` / `06_Ke_hoach_kiem_thu.docx` — SRS + test plan (nguồn nghiệp vụ CHUẨN).

## 6. Nguyên tắc đã tuân thủ (SRS)
Bổ sung không viết lại · đo được mới tuyên bố · con người quyết định · mặc định an toàn · giấy phép trước ·
lớp trừu tượng viết trước. Mọi quyết định lớn ghi ở `docs/DECISIONS.md`.
