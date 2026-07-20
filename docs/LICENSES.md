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

## 3. Việc cần làm trước khi ký Bản cam kết (test plan KT-PL)
- [ ] **KT-PL-01/02/03** — Rà giấy phép mọi model + biến thể, điền bảng mục 1, kết luận rõ "dùng được / có điều kiện / không dùng được".
- [ ] **KT-PL-04** — Rà giấy phép mọi thành phần nguồn mở, đặc biệt **xác minh Ghostscript** (phiên bản + điều kiện) và **Redis** (phiên bản + license).
- [ ] **KT-PL-05** — Kết luận khả năng thương mại hóa; loại bỏ/thay thế thành phần "không dùng được".
- [ ] **YC-PL-04** — Văn bản xác định **quyền sở hữu mã nguồn** giữa Nhà trường và các tác giả (sản phẩm xây trong giờ làm việc, trên hạ tầng Nhà trường).
- [ ] **YC-PL-06** — Ý kiến pháp lý bằng văn bản về bảo vệ dữ liệu cá nhân / bí mật nhà nước (kỹ thuật KHÔNG thay thế được yêu cầu này).
- [ ] Tệp **ghi nhận nguồn** (attribution/NOTICE) theo yêu cầu từng giấy phép, kèm theo sản phẩm (YC-PL-05).

> 💡 Mẹo an toàn cho hồ sơ (SRS): nếu chưa rà xong model, **KHÔNG nêu tên model cụ thể** — nêu ở mức
> "mô hình mở có giấy phép cho phép thương mại, lựa chọn sau rà soát pháp lý" là đủ và an toàn hơn.
