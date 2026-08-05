# Lược đồ biên mục theo bộ mẫu HPU (7 loại tài liệu)

> Nguồn: 7 file `docs/Mau bien muc *.xlsx` (Trung tâm Thông tin Thư viện HPU, 08/2026).
> Tài liệu này **xác định các trường cần điền** cho từng loại tài liệu → seed vào `extraction_schemas`/`schema_fields`.

## 1. Phân loại 7 loại tài liệu

| # | Loại | `document_type` | `code` lược đồ | Chuẩn | `dc.type` |
|---|---|---|---|---|---|
| 1 | Sách | `book` | `sach` | Dublin Core | Book |
| 2 | Đề cương môn học | `de_cuong` | `de_cuong` | Dublin Core | Presentation |
| 3 | Khóa luận / Đồ án | `khoa_luan` | `khoa_luan` | Dublin Core | Thesis |
| 4 | Luận văn (Thạc sỹ) | `luan_van` | `luan_van` | Dublin Core | Thesis |
| 5 | Kỷ yếu hội thảo | `hoi_thao` | `hoi_thao` | Dublin Core | Presentation |
| 6 | Báo / Tạp chí NCKH | `bao_nckh` | `bao_nckh` | Dublin Core | Article |
| 7 | Công văn hành chính | `cong_van` | `cong_van` | Trường hành chính riêng | — |

Ba **nhóm cấu trúc trường** (Dublin Core):
- **Nhóm SÁCH** (sách, đề cương): có `contributor.editor`, `title.alternative`, `identifier.isbn`; *không* advisor/degree.
- **Nhóm LUẬN** (khóa luận, luận văn): có `contributor.advisor`, `description.degree`; *không* editor/alternative/isbn.
- **Nhóm BÀI VIẾT** (hội thảo, báo NCKH): có `contributor.advisor` (tùy), `description.degree` (loại bài); có `department`.

## 2. Nguồn dữ liệu mỗi trường (QUAN TRỌNG — chống ảo giác)
Không phải trường nào cũng để AI trích. Ba nguồn:
- 🤖 **AI trích** từ nội dung tài liệu (có điểm tin cậy, cán bộ duyệt).
- ⚙️ **Hệ thống** tự sinh từ file/PDF (không cần AI).
- 👤 **Người biên mục** nhập (AI KHÔNG được bịa).

| Trường | Nguồn | Ghi chú |
|---|---|---|
| `dc.identifier.other` (mã HPU2xxxxxx) | 👤 người | Mã kho thư viện gán khi nhập — **AI KHÔNG trích** (bịa mã là lỗi nghiêm trọng) |
| `dc.format.extent` (số trang, "161 tr.") | ⚙️ hệ thống | Đếm số trang từ PDF |
| `dc.size` (dung lượng, "124 MB") | ⚙️ hệ thống | Lấy từ kích thước file |
| `dc.format.mimetype` (`application/pdf`) | ⚙️ hệ thống | Cố định theo định dạng |
| `dc.type` (Book/Thesis/Article/Presentation) | ⚙️ theo lược đồ | Biết trước từ loại tài liệu, không cần đoán |
| `dc.title`, `dc.title.alternative` | 🤖 AI | |
| `dc.contributor.author/advisor/editor` | 🤖 AI | Định dạng "Họ, Tên" |
| `dc.publisher`, `dc.date.issued` | 🤖 AI | |
| `dc.subject` | 🤖 AI | 3-5 từ khóa |
| `dc.description.abstract` | 🤖 AI | |
| `dc.description.degree` | 🤖 AI | Đồ án / Thạc sỹ / Bài báo khoa học |
| `dc.language.iso` | 🤖 AI | vi / en |
| `dc.identifier.isbn` | 🤖 AI | Chỉ sách/đề cương |
| `dc.department` | 🤖 AI (gợi ý) | Khoa/Bộ môn — có thể gán theo collection |

## 3. Bảng trường chi tiết theo loại

### 3.1 Nhóm SÁCH — `sach`, `de_cuong`
| DC key | Nhãn | Bắt buộc | Kiểu | Nguồn |
|---|---|---|---|---|
| dc.identifier.other | Mã tài liệu (HPU) | ✔ | text | 👤 |
| dc.title | Nhan đề | ✔ | text | 🤖 |
| dc.title.alternative | Nhan đề khác | | text | 🤖 |
| dc.contributor.author | Tác giả | ✔ | list | 🤖 |
| dc.contributor.editor | Biên tập/Chủ biên | | list | 🤖 |
| dc.publisher | Nhà xuất bản | | text | 🤖 |
| dc.date.issued | Năm xuất bản | | number | 🤖 |
| dc.subject | Từ khóa | ✔ | list | 🤖 |
| dc.description.abstract | Tóm tắt | | text | 🤖 |
| dc.identifier.isbn | ISBN | | text | 🤖 |
| dc.language.iso | Ngôn ngữ | | text | 🤖 |
| dc.department | Bộ sưu tập/Khoa | | text | 🤖 |
| dc.type | Loại (Book/Presentation) | ✔ | text | ⚙️ |
| dc.format.extent | Số trang | | text | ⚙️ |
| dc.size | Dung lượng | | text | ⚙️ |
| dc.format.mimetype | Định dạng | | text | ⚙️ |

### 3.2 Nhóm LUẬN — `khoa_luan`, `luan_van`
Như 3.1 nhưng **thay** `editor/alternative/isbn` **bằng**:
| DC key | Nhãn | Bắt buộc | Kiểu | Nguồn |
|---|---|---|---|---|
| dc.contributor.advisor | Người hướng dẫn | ✔ | list | 🤖 |
| dc.description.degree | Học vị/Loại (Đồ án·Thạc sỹ) | | text | 🤖 |
(giữ: identifier.other, title, author, publisher, date.issued, subject, abstract, language, department, type=Thesis, format.extent, size, format.mimetype)

### 3.3 Nhóm BÀI VIẾT — `hoi_thao`, `bao_nckh`
Như 3.2 (`advisor` tùy chọn, không bắt buộc) + `dc.description.degree` = loại bài ("Bài báo khoa học"); `dc.type` = Presentation (hội thảo) / Article (báo NCKH); `dc.publisher` = nơi tổ chức / tên tạp chí; `dc.department` = lĩnh vực (vd "600 - Công nghệ").

### 3.4 Công văn — `cong_van` (KHÔNG Dublin Core)
Bộ mẫu chi tiết hơn lược đồ hiện có — bổ sung các trường **in đậm**:
| Trường | Nhãn | Bắt buộc | Nguồn |
|---|---|---|---|
| so_hieu | Số, ký hiệu văn bản | ✔ | 🤖 |
| loai_van_ban | Loại văn bản | | 🤖 |
| ngay_ban_hanh | Ngày ban hành | | 🤖 |
| **don_vi_ban_hanh** | Đơn vị/bộ phận ban hành | | 🤖 |
| co_quan_ban_hanh | Cơ quan ban hành | ✔ | 🤖 |
| **noi_ban_hanh** | Nơi ban hành | | 🤖 |
| nguoi_ky | Người ký | | 🤖 |
| **chuc_vu_nguoi_ky** | Chức vụ người ký | | 🤖 |
| **nhan_de** | Nhan đề văn bản | | 🤖 |
| trich_yeu | Trích yếu nội dung | ✔ | 🤖 |
| tu_khoa (dc.subject) | Từ khóa | | 🤖 |
| so_trang | Số trang | | ⚙️ |
| dung_luong | Dung lượng tệp | | ⚙️ |

## 4. Quy tắc đặt tên tệp số hóa (từ mẫu công văn)
`[Năm]-[số ký hiệu]_[Trích yếu ngắn].pdf` — chữ không dấu, không khoảng trắng.
VD: `2026-562-KH-HT_Ke-hoach-nhap-hoc-sinh-vien-khoa-30.pdf`.

## 5. Ghi chú triển khai
- Seed 7 lược đồ vào `extraction_schemas` + `schema_fields` (thay lược đồ `dublin_core` generic cũ; giữ tương thích: `book`/`thesis` vẫn map được).
- Thêm `document_types`: `de_cuong, khoa_luan, luan_van, hoi_thao, bao_nckh` (đã có `book`, `cong_van`).
- Trường ⚙️/👤 (identifier.other, extent, size, mimetype) **loại khỏi prompt AI** — điền bởi hệ thống/người, tránh model bịa.
