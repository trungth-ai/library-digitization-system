# DocuFlow HP — Mô tả sản phẩm & Kiến trúc nâng cấp

> Tài liệu kỹ thuật (.md) tóm lược từ SRS `05_Dac_ta_yeu_cau_phan_mem.docx`. Khi có mâu thuẫn, SRS là nguồn chuẩn.
> Phiên bản: 1.0 — 07/2026.

## 1. Sản phẩm là gì

**DocuFlow HP** là nền tảng **số hóa và trích xuất dữ liệu tự động từ hồ sơ giấy**, đang vận hành
thật tại Trung tâm Thông tin Thư viện — Trường ĐH Quản lý và Công nghệ Hải Phòng (HPU) từ 2025.

Bài toán: thư viện/đơn vị hành chính có khối lượng lớn tài liệu giấy (sách, khóa luận, công văn).
Nhập liệu thủ công vừa chậm vừa sai sót. DocuFlow HP tự động: quét → OCR → trích xuất metadata có cấu
trúc → cán bộ duyệt → đưa vào kho số (DSpace) để lưu trữ và tra cứu.

### Giá trị cốt lõi
- **Tự động hóa nhập liệu**: giảm công sức biên mục thủ công.
- **Con người giữ quyền quyết định**: AI đề xuất, cán bộ duyệt — không tự ý ghi vào kho.
- **Chuẩn hóa metadata**: xuất đúng chuẩn Dublin Core để tích hợp DSpace.

## 2. Hiện trạng (ĐÃ VẬN HÀNH — tài sản lớn nhất của dự án)

| Thành phần | Công nghệ | Trạng thái |
|---|---|---|
| Giao diện web | Next.js | Đang vận hành |
| Máy chủ nghiệp vụ | FastAPI | Đang vận hành |
| Xử lý OCR | OCRmyPDF + Tesseract + Ghostscript (2 pha 150→120 DPI) | Đang vận hành |
| Trích xuất metadata | Mô hình đám mây (Claude), 16 trường Dublin Core cố định | Đang vận hành |
| Cơ sở dữ liệu | PostgreSQL 15 | Đang vận hành |
| Hàng đợi | Redis 7 | Đang vận hành |
| Tích hợp kho số | DSpace REST API | Đang vận hành |
| Phân quyền + nhật ký | 2 vai trò | Đang vận hành |
| Triển khai | Docker Compose | Đang vận hành |

### Ba hạn chế đã xác định (động lực nâng cấp)
1. **Lược đồ trích xuất cố định**: 16 trường Dublin Core mã hóa cứng — muốn xử lý loại tài liệu
   khác (vd công văn) phải sửa mã nguồn.
2. **Quy tắc chọn ngữ cảnh cố định**: lấy 8 trang đầu + 2 trang cuối, tối đa 6.000 ký tự — hợp với
   sách, vô nghĩa với công văn 1–3 trang.
3. **Phụ thuộc hoàn toàn mô hình đám mây**: không xử lý được tài liệu nhạy cảm, không chạy khi mất
   mạng, chi phí tăng tuyến tính theo khối lượng.

## 3. Mục tiêu nâng cấp

Chuyển hệ thống sang **kiến trúc hai chế độ** với **mô hình mở chạy tại chỗ**, bổ sung **lớp truy
hồi (RAG)** — giải quyết cả 3 hạn chế trên và mở ra khả năng khai thác dữ liệu sau số hóa.

### 3.1. Kiến trúc hai chế độ (Dual-mode)
```
                         ┌─────────────────────────┐
   Tài liệu  ──►  Định tuyến theo độ nhạy cảm (YC-DR)
                         └───────────┬─────────────┘
              Công khai │                    │ Nội bộ / Nhạy cảm
                        ▼                    ▼
              ┌──────────────────┐  ┌──────────────────────┐
              │ Công cụ ĐÁM MÂY  │  │ Công cụ TẠI CHỖ      │
              │ claude (mặc định)│  │ ollama (mặc định)    │
              │ openai · gemini  │  │ vllm · llamacpp      │
              │ azure · groq ... │  │ lmstudio · tgi       │
              └────────┬─────────┘  └──────────┬───────────┘
                       └──────────┬────────────┘
                        Lớp trừu tượng hóa mô hình (YC-MP)
                        — mọi phần hệ thống chỉ gọi qua đây —
```
Mỗi ô trên là **một dòng cấu hình**, không phải một lần viết lại mã: công cụ nào đảm nhiệm chế độ nào do
`CLOUD_PROVIDER`/`LOCAL_PROVIDER` quyết định (ADR-007). Nhờ vậy sản phẩm không khóa vào **bất kỳ** nhà
cung cấp nào — kể cả nhà cung cấp tại chỗ.
- **Chế độ đám mây**: giữ nguyên hành vi hiện tại cho tài liệu công khai (độ chính xác cao).
- **Chế độ tại chỗ**: mô hình mở chạy trong mạng nội bộ, xử lý tài liệu nhạy cảm, hoạt động cả khi
  ngắt Internet. **Mặc định an toàn**: không rõ độ nhạy cảm → dùng tại chỗ.
- **Nhiều công cụ cho mỗi chế độ**: thêm một công cụ nói giao thức tương thích OpenAI chỉ là thêm một
  dòng vào bảng đăng ký; công cụ có giao thức riêng thì thêm một lớp nhỏ (YC-MP-08). Điểm cuối khai báo
  "tại chỗ" được kiểm tra có thực sự nằm trong mạng nội bộ — chốt an toàn thứ hai cho YC-DR-03.
- **Ràng buộc cứng**: tài liệu Nội bộ/Nhạy cảm KHÔNG bao giờ ra đám mây, kể cả khi người dùng chọn
  thủ công (YC-DR-03).

### 3.2. Lược đồ trích xuất cấu hình được (YC-SC)
Lược đồ (schema) là **dữ liệu trong DB**, không phải mã nguồn. Quản trị viên tạo lược đồ mới (vd
công văn hành chính: số hiệu, ngày ban hành, cơ quan, độ mật, nơi nhận, người ký...) mà không cần
lập trình. Quy tắc chọn ngữ cảnh trở thành thuộc tính của lược đồ → sửa lỗ hổng "8 trang đầu/2 cuối".

### 3.3. Điểm tin cậy & chống ảo giác (YC-CF)
Mỗi trường trích xuất kèm **điểm tin cậy**; giao diện tô màu trường điểm thấp để cán bộ tập trung
kiểm tra. **Phát hiện giá trị bịa**: kiểm tra giá trị có thực sự xuất hiện trong văn bản gốc không —
nghiêm trọng với hồ sơ hành chính (một số hiệu bịa trông y hệt số hiệu thật).

### 3.4. Lớp truy hồi RAG (YC-RG)
- **RAG cho trích xuất**: truy hồi ví dụ đã duyệt (cùng lược đồ) đưa vào ngữ cảnh → "càng dùng càng chính xác".
- **RAG cho tra cứu**: hỏi bằng ngôn ngữ tự nhiên trên kho đã số hóa; **mọi câu trả lời bắt buộc dẫn
  nguồn** (tài liệu, trang, đoạn); không có nguồn → trả lời "không tìm thấy", không suy đoán.
- Dùng `pgvector` trên PostgreSQL hiện có (không thêm CSDL mới), embedding + sinh câu trả lời bằng mô
  hình mở tại chỗ.

### 3.5. Nhật ký kiểm toán & Báo cáo (YC-AU + yêu cầu bổ sung)
- **Audit log bất biến**: ghi mọi thao tác (tải lên, xử lý, sửa từng trường, xác nhận, đẩy DSpace)
  kèm ai/khi nào/giá trị cũ/mới/chế độ/mô hình. Không sửa/xóa được kể cả bởi quản trị viên → truy được trách nhiệm.
- **Log chi tiết vận hành**: mỗi lần gọi model ghi provider/model/version/thời gian xử lý (YC-MP-06).
- **Báo cáo**: theo chế độ xử lý (YC-DR-06), tỉ lệ trường bị sửa theo lược đồ (YC-CF-07), kết xuất
  nhật ký theo thời gian/người/tài liệu (YC-AU-05); dashboard thống kê throughput OCR, tỉ lệ thành công.

## 4. Đối tượng sử dụng
- **Cán bộ nghiệp vụ**: tải tài liệu, duyệt/hiệu chỉnh metadata, xác nhận đẩy DSpace.
- **Quản trị viên**: quản lý lược đồ, độ nhạy cảm, cấu hình model provider, xem báo cáo/kiểm toán.

## 5. Nguyên tắc thiết kế (từ SRS — chi phối mọi quyết định)
1. Bổ sung, không viết lại — hệ thống phải luôn tiếp tục chạy.
2. Con người giữ quyền quyết định.
3. Mặc định an toàn (không rõ → tại chỗ).
4. Đo được mới tuyên bố.
5. Giấy phép trước, hiệu năng sau.
6. Phạm vi theo nguồn lực thật (đội kiêm nhiệm).

Chi tiết yêu cầu: xem `REQUIREMENTS.md`. Lộ trình: xem `ROADMAP.md`.
