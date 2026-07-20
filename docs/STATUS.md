# DocuFlow HP — Trạng thái nâng cấp & Bàn giao

> Cập nhật: 20/07/2026. Repo: `github.com/trungth-ai/library-digitization-system` (17 commit).
> Tài liệu này để bất kỳ kỹ sư nào tiếp quản (YC-VH-01) nắm được đã làm gì, cách kiểm chứng, còn gì.

## 1. Đã hoàn thành (backend modules, kiểm chứng ở dev)

| GĐ | Hạng mục | Module | Cách kiểm chứng |
|---|---|---|---|
| 0 | Lớp trừu tượng hóa mô hình (cloud/local/generic) + factory | `scripts/providers/{base,cloud,local,factory,prompt}.py` | `pytest` + regression |
| 0 | Model serving Ollama | `docker-compose.yml` (profile `local-ai`) | `docs/LOCAL_MODE.md` |
| 0 | Harness đo đạc 2 chế độ | `scripts/eval/` | `pytest` + smoke CLI |
| 1 | Định tuyến độ nhạy cảm (ràng buộc cứng) | `scripts/providers/router.py` | `pytest` |
| 1 | Điểm tin cậy + chống ảo giác | `scripts/core/quality.py` | `pytest` |
| 2 | Audit log bất biến | `scripts/core/audit.py` + `audit_log` | verify PostgreSQL |
| 2 | Báo cáo (theo chế độ / tỉ lệ sửa / throughput) | `scripts/core/reports.py` | verify PostgreSQL |
| 2 | Lược đồ cấu hình lưu DB | `scripts/core/schema_store.py` + bảng | verify PostgreSQL |
| 3 | Chia đoạn theo cấu trúc (RAG) | `scripts/core/chunking.py` | `pytest` |

**66 pytest PASS** + 4 lần kiểm chứng trên PostgreSQL 17. Không hồi quy, không đụng code production đang chạy.

## 2. Cách chạy kiểm thử

```bash
# Unit test (không cần DB/mạng)
pip install pytest
python -m pytest tests/ -q            # 66 passed

# Verify schema/audit/reports trên PostgreSQL tạm (Windows, không cần Docker)
#   xem mẫu ở các phiên trước: initdb → Start-Process postgres.exe → psql -f database/init.sql → psql -f verify_*.sql
```

## 3. Còn lại — CẦN MÔI TRƯỜNG THẬT (không verify được ở máy dev)

| Việc | Cần gì | Ai |
|---|---|---|
| **Tích hợp** module vào `worker`/`api.py` + endpoints envelope | server (redis + postgres) để chạy & verify | 🤖 code được, verify ở server |
| **UI**: dashboard báo cáo, tô màu confidence (YC-CF-04), màn quản trị lược đồ (YC-SC-05) | trình duyệt + Next.js dev server | 🤖 code + verify qua preview |
| **YC-RG** embedding + tra cứu (GĐ3) | Ollama embedding + `pgvector` | 🤖 structure, số liệu cần env |
| **Số liệu đo GĐ0** (KT-CX/KT-HN) cho hồ sơ | server + Ollama + BD-01 + đáp án chuẩn | 👤 bạn |
| **Bảng giấy phép** (YC-PL) + video ngắt mạng + văn bản pháp lý | rà soát + quay + pháp chế | 👤 bạn |

## 4. Khuyến nghị bước tiếp (ưu tiên theo hạn cuộc thi)

1. **Deploy bộ module lên server** (có Ollama) → chạy `docs/EVAL.md` lấy **bảng so sánh 2 chế độ** cho hồ sơ (hạn 30/7).
2. Rà giấy phép → điền `docs/LICENSES.md`; quay video ngắt mạng (`docs/LOCAL_MODE.md`).
3. Sau khi có môi trường: tích hợp vào pipeline/API + UI (làm có regression, verify qua preview).

## 5. Nguyên tắc đã tuân thủ (SRS)
Bổ sung không viết lại · đo được mới tuyên bố · con người quyết định · mặc định an toàn · giấy phép trước ·
lớp trừu tượng viết trước. Mọi quyết định lớn ghi ở `docs/DECISIONS.md` (ADR-001..005).
