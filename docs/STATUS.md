# DocuFlow HP — Trạng thái nâng cấp & Bàn giao

> Cập nhật: 21/07/2026. Repo: `github.com/trungth-ai/library-digitization-system`.
> Số commit mới nhất: xem `git log --oneline`. Tài liệu này để kỹ sư tiếp quản (YC-VH-01) nắm nhanh:
> đã làm gì, cách kiểm chứng, còn gì — và **bắt đầu lần nâng cấp tiếp theo từ mục 4**.

## 1. Đã hoàn thành (kiểm chứng ở dev)

| GĐ | Hạng mục | Module | Kiểm chứng |
|---|---|---|---|
| 0 | Lớp trừu tượng hóa mô hình (cloud/local/generic) + factory | `scripts/providers/{base,cloud,local,factory,prompt}.py` | pytest + regression |
| 0 | Model serving Ollama (profile `local-ai`) | `docker-compose.yml` | `docs/LOCAL_MODE.md` |
| 0 | Harness đo đạc 2 chế độ | `scripts/eval/` | pytest + smoke CLI |
| 1 | Định tuyến độ nhạy cảm (ràng buộc cứng) | `scripts/providers/router.py` | pytest |
| 1 | Điểm tin cậy + chống ảo giác | `scripts/core/quality.py` | pytest |
| 2 | Audit log bất biến | `scripts/core/audit.py` + bảng `audit_log` | verify PostgreSQL |
| 2 | Báo cáo (chế độ / tỉ lệ sửa / throughput) | `scripts/core/reports.py` | verify psycopg2 + PG |
| 2 | Lược đồ cấu hình lưu DB | `scripts/core/schema_store.py` + bảng | verify PostgreSQL |
| 2 | Tích hợp API: endpoints reports/audit/schemas (envelope HPU) | `scripts/api.py` | psycopg2+PG + py_compile |
| 2 | UI dashboard `/bao-cao` + `/luoc-do` (design HPU, badge confidence/sensitivity) | `ui/src/app/`, `ui/src/components/hpu/` | verify preview trình duyệt |
| 3 | Chia đoạn theo cấu trúc (RAG) | `scripts/core/chunking.py` | pytest |
| — | **Deploy hardening** (font system, /api/health, .dockerignore, healthcheck, next.config, install.sh) | nhiều | **UI build exit 0 (không TLS flag)** |

**66 pytest PASS · 5 lần verify PostgreSQL 17 · 1 verify UI preview · UI build sạch.** Không hồi quy, không đụng pipeline production.

## 2. Cách kiểm chứng
```bash
python -m pytest tests/ -q                 # 66 passed (không cần DB/mạng)
cd ui && npm run build                     # UI build (KHÔNG cần TLS flag sau khi bỏ Google font)
# Verify DB (Windows, không cần Docker): initdb → Start-Process postgres.exe → psql -f database/init.sql
#   → psql/python verify (mẫu script ở scratchpad các phiên trước)
```

## 3. Còn lại — cần MÔI TRƯỜNG THẬT
| Việc | Cần gì | Ai |
|---|---|---|
| Wire router+quality+audit vào `worker` (chế độ tại chỗ dùng trong vận hành) | server (redis+postgres) | 🤖 code, verify server |
| Nối UI với API thật + trang upload/duyệt/jobs theo design HPU | backend chạy + trình duyệt | 🤖 verify preview |
| YC-RG embedding + tra cứu (GĐ3) | Ollama embedding + `pgvector` | 🤖 structure, số liệu cần env |
| Số liệu đo GĐ0 (KT-CX/KT-HN) cho hồ sơ | server + Ollama + BD-01 + đáp án chuẩn | 👤 bạn |
| Bảng giấy phép (YC-PL) + video ngắt mạng + văn bản pháp lý | rà soát + quay + pháp chế | 👤 bạn |

## 4. 🚀 Bước tiếp theo cho LẦN NÂNG CẤP TIẾP THEO
Thứ tự đề xuất (bắt đầu từ đây):

1. **[Ưu tiên hồ sơ]** Deploy lên server theo `docs/DEPLOY.md` → chạy `docs/EVAL.md` lấy bảng so sánh 2 chế độ; rà giấy phép (`docs/LICENSES.md`); quay video ngắt mạng.
2. **Tích hợp pipeline (GĐ1 vận hành):** wire `worker.py` gọi `router.get_routed_provider` + `quality.extract_with_quality` + `audit.log_action` thay cho `AIMetadataExtractor` trực tiếp. LÀM CÓ regression (KT-KH) + tách commit nhỏ. Định tuyến theo `schema.sensitivity` (mặc định an toàn).
3. **Nối UI ↔ API:** thay mock ở `/bao-cao`, `/luoc-do` bằng gọi endpoints `/api/v2/reports/*`, `/api/v2/schemas`, `/api/v2/audit`. Thêm màn upload + duyệt metadata (tô màu confidence dùng `ConfidenceBadge`).
4. **GĐ3 RAG:** bật `pgvector`; `embed()` của LocalProvider + bảng vector; truy hồi kết hợp (vector + toàn văn); dẫn nguồn bắt buộc (dùng offset từ `chunking.py`); phân quyền kết quả.
5. **Chuẩn hóa NEXT_PUBLIC build-args** cho UI image (xem `docs/DEPLOY.md` mục 4) khi deploy thật.

## 5. Bản đồ tài liệu (đọc theo nhu cầu)
- `CLAUDE.md` — điểm neo dự án (stack, quy tắc, ranh giới).
- `docs/PRODUCT.md` — mô tả sản phẩm + kiến trúc hai chế độ + RAG.
- `docs/REQUIREMENTS.md` — bảng yêu cầu YC-* + chuẩn HPU.
- `docs/ROADMAP.md` — lộ trình chia sprint (GĐ0-3).
- `docs/DECISIONS.md` — ADR-001..006 (quyết định kiến trúc).
- `docs/DEPLOY.md` — hướng dẫn triển khai + checklist.
- `docs/LOCAL_MODE.md` — bật chế độ tại chỗ (Ollama) + kiểm chứng ngắt mạng.
- `docs/EVAL.md` — đo số liệu 2 chế độ cho hồ sơ.
- `docs/LICENSES.md` — bảng đối chiếu giấy phép (cần hoàn tất trước khi ký cam kết).
- `docs/05_Dac_ta_yeu_cau_phan_mem.docx` / `06_Ke_hoach_kiem_thu.docx` — SRS + test plan (nguồn nghiệp vụ CHUẨN).

## 6. Nguyên tắc đã tuân thủ (SRS)
Bổ sung không viết lại · đo được mới tuyên bố · con người quyết định · mặc định an toàn · giấy phép trước ·
lớp trừu tượng viết trước. Mọi quyết định lớn ghi ở `docs/DECISIONS.md`.
