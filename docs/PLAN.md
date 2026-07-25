# PLAN.md — Sprint đang chạy

> File này được `CLAUDE.md` và quy ước làm việc tham chiếu ("đọc PLAN.md trước khi thay đổi").
> **Phạm vi hẹp: chỉ việc của sprint hiện tại.** Tiến độ tổng thể xem `docs/STATUS.md`; lộ trình dài hạn
> xem `docs/ROADMAP.md`; quyết định kiến trúc ghi ở `docs/DECISIONS.md`.

**Cập nhật:** 25/07/2026 · **Giai đoạn:** GĐ 0 (hạn hồ sơ **30/7/2026** — còn 5 ngày)

---

## Sprint hiện tại: 0A/0B mở rộng — đa công cụ mô hình ✅ ĐÃ XONG

**Mục tiêu:** gỡ nốt phần khóa nhà cung cấp còn sót trong lớp trừu tượng hóa, để "không khóa vào một
nhà cung cấp" là điều kiểm chứng được chứ không phải lời tuyên bố.

| Việc | Trạng thái | Kiểm chứng |
|---|---|---|
| Tách `name` (công cụ) khỏi `deployment` (chế độ) — ADR-007 | ✅ | 167 pytest |
| `TextGenProvider`: thêm công cụ mới = hiện thực một hàm `_complete` | ✅ | test dựng công cụ mới bằng 5 dòng |
| `OpenAICompatProvider` + `AzureOpenAIProvider` + `GeminiProvider` | ✅ | 95 test tầng provider |
| Bảng đăng ký 18 công cụ (6 tại chỗ / 12 đám mây) | ✅ | `run_eval --list-providers` |
| vLLM + llama.cpp vào compose (profile riêng, không mở cổng) | ✅ | `docker compose config` |
| Hai chốt an toàn cho YC-DR-03 (điểm cuối nội bộ + `LOCAL_PROVIDER`) | ✅ | test từ chối cấu hình rò rỉ |
| Kimi (Moonshot) + Qwen (DashScope) | ✅ | mỗi cái một dòng registry |

**DoD đã đạt:** đổi công cụ chỉ bằng biến môi trường; không hồi quy đường Claude (KT-KH); mọi test chạy
được khi ngắt mạng; tài liệu + ADR cập nhật.

---

## Sprint kế tiếp (đề xuất): số liệu thật cho hồ sơ ⏳ CẦN MÁY CHỦ

Đây là **đường găng** tới hạn 30/7, và phần lớn nằm ở môi trường thật chứ không ở code.

| # | Việc | Ai | Chặn bởi |
|---|---|---|---|
| 1 | Deploy lên server theo `docs/DEPLOY.md` | 👤 người phụ trách | — |
| 2 | Tải model đã rà giấy phép, bật một công cụ tại chỗ | 👤 | (1) + `docs/LICENSES.md` mục 1 |
| 3 | Chuẩn bị BD-01 (30–50 công văn) + đáp án chuẩn | 👤 | — |
| 4 | Chạy `run_eval --providers claude,ollama` → bảng so sánh 2 chế độ | 👤 chạy, 🤖 đọc | (2)(3) |
| 5 | **Quay video ngắt Internet vẫn xử lý trọn 1 tài liệu** (KT-BM-01) | 👤 | (2) |
| 6 | Quét cổng từ ngoài chứng minh không mở cổng model (KT-BM-03) | 👤 | (1) |
| 7 | Hoàn tất bảng giấy phép + ý kiến pháp lý (YC-PL-04/06) | 👤 + pháp chế | — |

> ⚠️ Việc 5 và 6 là **bằng chứng cốt lõi** cho lập luận bảo mật của hồ sơ — không thay thế được bằng
> mô tả kỹ thuật. Việc 7 phải xong **trước khi ký Bản cam kết**.
>
> 💡 Cho việc 5, `llamacpp` là lựa chọn thuyết phục nhất: model là file `.gguf` đặt sẵn, container không
> gọi ra ngoài lúc khởi động. `vllm` cần mạng ở lần đầu để tải model.

---

## Việc code còn nợ (chưa xếp sprint — xem `docs/STATUS.md` mục 3)

Không cái nào chặn hạn 30/7, nhưng cần xếp sớm sau đó:

- **GĐ1 — wire `worker.py`** dùng `router.get_routed_provider` + `quality` + `audit` thay cho gọi
  `AIMetadataExtractor` trực tiếp. Phải có regression (KT-KH), tách commit nhỏ. *(ADR-004 cố ý hoãn)*
- **Chính sách dự phòng chéo công cụ** (vLLM sập → Ollama?) — cần quyết định nghiệp vụ trước khi code.
- **YC-MS-07** đo tài nguyên (thời gian/RAM/GPU) mỗi lần gọi model — chưa có.
- **YC-MS-08** giao diện quản trị hiện công cụ/model + tình trạng — hiện chỉ có ở mức CLI.
- **Chuẩn HPU còn nợ:** `delete_job` đang **hard delete** (vi phạm quy tắc soft delete), thiếu
  `updated_at` cho `documents`.
- **Nối UI ↔ API thật** — `/bao-cao` và `/luoc-do` vẫn dùng dữ liệu mẫu.

## Định nghĩa "Hoàn thành" (mọi sprint)
- [ ] Không phá endpoint/UI đang chạy (KT-KH pass)
- [ ] Có kiểm thử KT-* tương ứng và **đã chạy đạt** (đo thật, không kỳ vọng)
- [ ] Tài liệu cập nhật (`PLAN.md` này + `DECISIONS.md` nếu có quyết định lớn)
- [ ] Số liệu ghi kèm cỡ mẫu + phương pháp
