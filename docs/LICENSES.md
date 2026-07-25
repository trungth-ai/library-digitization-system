# Bảng đối chiếu giấy phép — DocuFlow HP (YC-PL-01, YC-PL-03)

> **Template cho hồ sơ dự thi.** Bốn yêu cầu YC-PL-01/02/03/04 phải hoàn thành **TRƯỚC khi ký Bản cam
> kết dự thi** (cam kết khẳng định sản phẩm không vi phạm SHTT).
>
> ⚠️ **Nguyên tắc SRS "giấy phép trước, hiệu năng sau" + "đo được mới tuyên bố":** các giá trị dưới đây
> là **THAM KHẢO**, PHẢI **xác minh với văn bản giấy phép gốc + đúng phiên bản đang dùng** rồi điền cột
> "Đã xác minh". Không tự khẳng định thay cho rà soát pháp lý (YC-PL-06). "Nguồn mở" KHÔNG đồng nghĩa
> "dùng thương mại thoải mái".

## 1. Mô hình AI (YC-PL-01, YC-PL-02)

> Chưa chốt model cụ thể (đúng nguyên tắc: rà giấy phép TRƯỚC khi tải/dùng). Điền sau khi rà.
> **KT-PL-02/03:** cùng một họ model, các cỡ khác nhau có thể có giấy phép KHÁC nhau — kiểm từng biến thể.
> Nếu là bản tinh chỉnh: truy tới model nền, kết luận theo giấy phép nghiêm ngặt hơn.

| Model | Phiên bản | Nhà phát hành | Giấy phép | Link văn bản gốc | Thương mại? | Điều kiện | Model nền | Đã xác minh |
|---|---|---|---|---|---|---|---|---|
| _(chưa chọn)_ | | | | | | | | ☐ |

**Ứng viên tham khảo (PHẢI rà từng biến thể trước khi dùng — đây KHÔNG phải kết luận):**
- Họ **Qwen** (Alibaba): nhiều bản Apache-2.0, nhưng một số cỡ có giấy phép riêng → kiểm từng bản.
- Họ **Llama** (Meta): "Llama Community License" — CÓ ràng buộc (không phải OSS thuần), giới hạn quy mô người dùng.
- Họ **Gemma** (Google): "Gemma Terms of Use" — có ràng buộc sử dụng.
- **Xiaomi MiMo** (vd `MiMo-7B-RL`): rà trên model card; cỡ 7B vừa hạ tầng hiện tại.
- **Kimi K2** (Moonshot): trọng số mở nhưng ~1000 tỉ tham số MoE → **không khả thi tại chỗ** với hạ tầng
  hiện tại; nếu dùng thì qua dịch vụ đám mây (rà mục 2b thay vì mục này).
- **DeepSeek**: 🔴 **CẢNH BÁO TRUY NGUỒN** — `deepseek-r1:7b/8b` phổ biến trên Ollama là bản **chưng cất
  (distill) từ Qwen hoặc Llama**, KHÔNG phải R1 thật. Giấy phép phải truy về **model nền** (nếu nền là
  Llama thì kèm ràng buộc Llama Community License), và hồ sơ **không được ghi "dùng DeepSeek-R1"**.
- Model tiếng Việt (**PhoGPT**, **Vistral**, **SeaLLM**...): rà kỹ, nhiều bản dựa trên nền có ràng buộc.
- Embedding (cho RAG - GĐ3): rà riêng model embedding (vd bge-m3, multilingual-e5...) — thường Apache/MIT nhưng phải xác minh.

## 2. Thành phần phần mềm nguồn mở (YC-PL-03)

> ⚠️ Cột "Giấy phép" là **giá trị thường gặp** — xác minh với phiên bản chính xác trong `requirements.txt`
> / `package.json` / image Docker đang dùng.

| Thành phần | Dùng ở | Giấy phép (tham khảo) | Thương mại? | Ghi chú / rủi ro | Đã xác minh |
|---|---|---|---|---|---|
| **Ghostscript** | Worker (nén PDF) | **AGPL-3.0** (bản GNU) hoặc Commercial (Artifex) | ⚠️ **Có điều kiện** | 🔴 **RỦI RO CAO** — AGPL copyleft mạnh: thương mại hóa có thể buộc công khai source hoặc **mua license Artifex**. SRS yêu cầu lưu ý riêng. Cân nhắc thay bằng công cụ nén khác (qpdf/mutool) nếu không mua được license. | ☐ |
| **Redis** | Hàng đợi + pub/sub | Redis ≤7.2: BSD-3; **≥7.4: RSALv2/SSPLv1** | ⚠️ **Xác minh** | 🟠 Redis **đổi license 2024** — không còn OSS thuần ở bản mới. Xác minh đúng phiên bản (`redis:7-alpine`); nếu vướng, cân nhắc **Valkey** (fork BSD do Linux Foundation). | ☐ |
| OCRmyPDF | Worker (OCR) | MPL-2.0 (tham khảo) | ✅ Thường được | Copyleft cấp file (nhẹ) | ☐ |
| Tesseract OCR | Worker (OCR) | Apache-2.0 (tham khảo) | ✅ Thường được | tessdata (vie/eng): kiểm license data | ☐ |
| PostgreSQL | CSDL | PostgreSQL License (tham khảo) | ✅ Thường được | Permissive (giống BSD/MIT) | ☐ |
| FastAPI | Backend | MIT (tham khảo) | ✅ Thường được | | ☐ |
| Uvicorn | Backend | BSD-3 (tham khảo) | ✅ Thường được | | ☐ |
| psycopg2 | Backend (DB driver) | LGPL-3.0 (tham khảo) | ✅ Thường được | LGPL — dùng như thư viện thường OK | ☐ |
| pypdf | Worker | BSD (tham khảo) | ✅ Thường được | | ☐ |
| anthropic SDK | Provider cloud | MIT (tham khảo) | ✅ Thường được | Dịch vụ Claude có điều khoản API riêng | ☐ |
| Next.js / React | Frontend | MIT (tham khảo) | ✅ Thường được | | ☐ |
| Docker Engine | Triển khai | Apache-2.0 (tham khảo) | ✅ Thường được | Docker Desktop có điều khoản riêng cho DN lớn | ☐ |
| **Ollama** | Model serving tại chỗ | MIT (tham khảo) | ✅ Thường được | License của Ollama ≠ license của MODEL chạy trên nó (rà mục 1) | ☐ |
| **vLLM** | Model serving tại chỗ (tùy chọn) | Apache-2.0 (tham khảo) | ✅ Thường được | Permissive. Image `vllm/vllm-openai` kéo theo CUDA runtime của NVIDIA — **điều khoản NVIDIA riêng**, xác minh nếu phân phối lại image | ☐ |
| **llama.cpp** | Model serving tại chỗ (tùy chọn) | MIT (tham khảo) | ✅ Thường được | Permissive. Model GGUF có giấy phép RIÊNG (rà mục 1) | ☐ |
| **HF text-generation-inference** | Model serving tại chỗ (tùy chọn) | ⚠️ **Xác minh theo phiên bản** | ⚠️ **Có điều kiện** | 🟠 TGI từng đổi sang **HFOILv1.0** (hạn chế thương mại) rồi quay lại Apache-2.0 — PHẢI kiểm đúng tag đang dùng | ☐ |
| **LM Studio** | Thử nghiệm trên máy trạm | ⚠️ **Nguồn đóng** | ⚠️ **Xác minh** | 🟠 Không phải OSS; điều khoản dùng trong tổ chức/thương mại phải đọc riêng. Chỉ dùng để thử, KHÔNG đưa vào vận hành | ☐ |

## 2b. Điều khoản dịch vụ mô hình ĐÁM MÂY (YC-PL-01, YC-BM)

> ⚠️ Với dịch vụ đám mây, **giấy phép phần mềm không phải câu hỏi chính** — câu hỏi chính là:
> *nội dung tài liệu gửi lên có bị lưu lại/dùng để huấn luyện không, lưu ở đâu, bao lâu?* Đây là vấn đề
> bảo vệ dữ liệu, không phải SHTT, và phải có ý kiến pháp lý bằng văn bản (YC-PL-06).
>
> Nhắc lại ràng buộc kỹ thuật đã cài trong sản phẩm: **chỉ tài liệu Công khai** được gửi tới nhóm này
> (YC-DR-03, không ghi đè được). Tài liệu Nội bộ/Nhạy cảm luôn xử lý tại chỗ.

| Dịch vụ | Dùng ở | Có huấn luyện trên dữ liệu gửi lên? | Thời gian lưu | Vùng dữ liệu | Đã xác minh |
|---|---|---|---|---|---|
| Anthropic Claude | provider `claude` (đang vận hành) | | | | ☐ |
| OpenAI | provider `openai` | | | | ☐ |
| Azure OpenAI | provider `azure_openai` | | | (chọn được vùng) | ☐ |
| Google Gemini | provider `gemini` | | | | ☐ |
| Moonshot AI (Kimi) | provider `moonshot`/`kimi` | | | ⚠️ Mặc định điểm cuối **quốc tế**; bản `.cn` lưu tại Trung Quốc | ☐ |
| Alibaba DashScope (Qwen) | provider `dashscope`/`qwen` | | | ⚠️ Mặc định **Singapore**; bản `.aliyuncs.com` lưu tại Trung Quốc | ☐ |
| OpenRouter / Groq / Together / DeepSeek / Mistral | provider tương ứng | ⚠️ **Rà từng nhà cung cấp** — cổng trung gian còn phụ thuộc nhà cung cấp phía sau | | | ☐ |

> 🔴 **Vùng dữ liệu là câu hỏi riêng, không lẫn với giấy phép.** Với nhà cung cấp có điểm cuối ở nhiều
> vùng (Moonshot, DashScope), việc chọn vùng nào là **quyết định của Nhà trường** và phải nằm trong ý
> kiến pháp lý (YC-PL-06), không phải mặc định kỹ thuật. Sản phẩm chỉ bảo đảm phần kỹ thuật: **tài liệu
> Nội bộ/Nhạy cảm không bao giờ đi tới bất kỳ điểm cuối đám mây nào** (YC-DR-03).

> 💡 Cách điền: đọc **Data Processing Addendum / API terms** của đúng gói dịch vụ đang mua (gói API
> thường khác gói tiêu dùng). Không suy luận từ tài liệu marketing.

## 3. Việc cần làm trước khi ký Bản cam kết (test plan KT-PL)
- [ ] **KT-PL-01/02/03** — Rà giấy phép mọi model + biến thể, điền bảng mục 1, kết luận rõ "dùng được / có điều kiện / không dùng được".
- [ ] **KT-PL-04** — Rà giấy phép mọi thành phần nguồn mở, đặc biệt **xác minh Ghostscript** (phiên bản + điều kiện) và **Redis** (phiên bản + license).
- [ ] **Mục 2b** — Rà điều khoản dữ liệu của MỌI dịch vụ đám mây thực sự bật trong `.env`. Dịch vụ không
      dùng thì ghi rõ "không sử dụng" — hồ sơ chỉ cần cam kết cho những gì sản phẩm thật sự gọi tới.
- [ ] **KT-PL-05** — Kết luận khả năng thương mại hóa; loại bỏ/thay thế thành phần "không dùng được".
- [ ] **YC-PL-04** — Văn bản xác định **quyền sở hữu mã nguồn** giữa Nhà trường và các tác giả (sản phẩm xây trong giờ làm việc, trên hạ tầng Nhà trường).
- [ ] **YC-PL-06** — Ý kiến pháp lý bằng văn bản về bảo vệ dữ liệu cá nhân / bí mật nhà nước (kỹ thuật KHÔNG thay thế được yêu cầu này).
- [ ] Tệp **ghi nhận nguồn** (attribution/NOTICE) theo yêu cầu từng giấy phép, kèm theo sản phẩm (YC-PL-05).

> 💡 Mẹo an toàn cho hồ sơ (SRS): nếu chưa rà xong model, **KHÔNG nêu tên model cụ thể** — nêu ở mức
> "mô hình mở có giấy phép cho phép thương mại, lựa chọn sau rà soát pháp lý" là đủ và an toàn hơn.
