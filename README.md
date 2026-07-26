# DocuFlow HP — Hệ thống số hóa tài liệu

Nền tảng số hóa và trích xuất dữ liệu tự động từ hồ sơ giấy, **đang vận hành thật** tại Trung tâm Thông
tin Thư viện Trường Đại học Quản lý và Công nghệ Hải Phòng từ 2025.

```
Upload PDF → OCR (OCRmyPDF 2 pha 150→120 DPI) → trích metadata bằng AI → cán bộ duyệt → đẩy lên DSpace
```

**Đang nâng cấp** (dự thi Khởi nghiệp sáng tạo TP Hải Phòng 2026): kiến trúc **hai chế độ**
(đám mây + tại chỗ với mô hình mở) và **lớp RAG** tra cứu.

## Bắt đầu nhanh

```bash
cp .env.example .env        # điền CLAUDE_API_KEY, POSTGRES_PASSWORD, DSPACE_*...
cp ui/.env.example ui/.env  # NEXT_PUBLIC_OCR_API_URL = URL TRÌNH DUYỆT truy cập được
docker compose up -d --build
```

Chi tiết + lưu ý build-time của UI: [`docs/DEPLOY.md`](docs/DEPLOY.md).

Chạy lẻ khi phát triển:

```bash
uvicorn scripts.api:app --reload --port 8000
python -m scripts.worker
cd ui && npm run dev
python -m pytest tests/ -q          # 213 test, không cần DB/mạng
```

## Chọn công cụ mô hình

Hệ thống **không khóa vào nhà cung cấp nào**. Đổi công cụ chỉ bằng một biến môi trường, không sửa mã:

```bash
python -m scripts.eval.run_eval --list-providers    # xem 18 lựa chọn + biến cần đặt
python -m scripts.eval.run_eval --health            # kiểm tra công cụ đã sẵn sàng chưa
```

| Chế độ | Công cụ |
|---|---|
| **Tại chỗ** — dữ liệu không ra khỏi trường | `ollama`, `vllm`, `llamacpp`, `lmstudio`, `tgi`, `ollama_openai` |
| **Đám mây** — chỉ tài liệu Công khai | `claude` (mặc định), `openai`, `azure_openai`, `gemini`, `moonshot`/`kimi`, `dashscope`/`qwen`, `groq`, `openrouter`, `together`, `deepseek`, `mistral`, `openai_compat` |

Model chạy trên công cụ đó là chuyện khác (Qwen, Xiaomi MiMo, Llama, model tiếng Việt...) — xem
[`docs/LOCAL_MODE.md`](docs/LOCAL_MODE.md) mục 1b.

> **Ràng buộc cứng:** tài liệu Nội bộ/Nhạy cảm **không bao giờ** đi ra đám mây, kể cả khi người dùng
> chọn thủ công (YC-DR-03). Không rõ độ nhạy cảm → mặc định xử lý tại chỗ.

## Kiến trúc

```
scripts/
  api.py worker.py digitize.py db.py sse.py    # backend đang vận hành
  core/        responses, exceptions, audit, quality, chunking, reports, schema_store
  providers/   lớp trừu tượng hóa mô hình — mọi lời gọi model đi qua đây
  eval/        harness đo độ chính xác nhiều công cụ
database/init.sql   ui/   docker/   docs/   tests/
```

Backend Python 3.12 + FastAPI + PostgreSQL 15 + Redis 7 · Worker OCRmyPDF/Tesseract (vie+eng) ·
Frontend Next.js 16 + React 19 + Tailwind 4 · Tích hợp DSpace 6.3/7.x.

## Tài liệu

| File | Nội dung |
|---|---|
| [`docs/PRODUCT.md`](docs/PRODUCT.md) | Mô tả sản phẩm + kiến trúc hai chế độ + RAG |
| [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) | Bảng yêu cầu YC-* + chuẩn HPU |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Lộ trình 4 giai đoạn chia sprint |
| [`docs/PLAN.md`](docs/PLAN.md) | Sprint đang chạy |
| [`docs/STATUS.md`](docs/STATUS.md) | **Bàn giao**: đã làm gì, kiểm chứng thế nào, còn gì |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | ADR — quyết định kiến trúc (mới nhất ở đầu) |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Triển khai + checklist + sao lưu |
| [`docs/LOCAL_MODE.md`](docs/LOCAL_MODE.md) | Chọn/bật công cụ + chọn model + kiểm chứng ngắt mạng |
| [`docs/EVAL.md`](docs/EVAL.md) | Đo độ chính xác cho hồ sơ dự thi |
| [`docs/LICENSES.md`](docs/LICENSES.md) | Đối chiếu giấy phép — **phải hoàn tất trước khi ký cam kết** |

Nguồn nghiệp vụ chuẩn: `docs/05_Dac_ta_yeu_cau_phan_mem.docx` (SRS) và `docs/06_Ke_hoach_kiem_thu.docx`.

## Nguyên tắc phát triển

- **Bổ sung, không viết lại** — hệ thống đang phục vụ thật; kiểm thử không hồi quy (KT-KH) là bắt buộc.
- **Con người giữ quyền quyết định** — không tự ghi vào DSpace khi chưa có cán bộ xác nhận.
- **Mặc định an toàn** — không rõ độ nhạy cảm thì xử lý tại chỗ.
- **Đo được mới tuyên bố** — không đưa con số chưa kiểm thử vào tài liệu/hồ sơ.
- **Giấy phép trước, hiệu năng sau** — rà giấy phép model TRƯỚC khi tải về.

## Giấy phép & liên hệ

Sản phẩm nội bộ của Nhà trường, mã nguồn ở repo riêng tư. Quyền sở hữu mã nguồn và giấy phép các thành
phần đang được rà soát — xem [`docs/LICENSES.md`](docs/LICENSES.md) (YC-PL-04/06 chưa hoàn tất).

Liên hệ: Trung tâm Thông tin Thư viện HPU — `trungth@hpu.edu.vn`.
