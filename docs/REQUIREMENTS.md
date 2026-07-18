# DocuFlow HP — Yêu cầu kỹ thuật

> Tóm lược có cấu trúc từ SRS `05_Dac_ta_yeu_cau_phan_mem.docx` (mục II–III), giữ nguyên mã **YC-***
> để truy vết. Tiêu chí nghiệm thu đầy đủ nằm trong SRS + `06_Ke_hoach_kiem_thu.docx`.
> Ưu tiên: **[BB]** Bắt buộc · **[NC]** Nên có · **[TT]** Có thì tốt.

## A. Yêu cầu chức năng (từ SRS)

### YC-MP — Lớp trừu tượng hóa mô hình  *(làm TRƯỚC tiên — giá trị lâu dài nhất)*
| Mã | Ưu tiên | Yêu cầu (rút gọn) |
|---|---|---|
| YC-MP-01 | BB | Giao diện chung cho model provider: `extract_fields(schema)`, `embed()`, `health()`. Toàn hệ thống chỉ gọi qua giao diện này |
| YC-MP-02 | BB | Provider đám mây — giữ nguyên hành vi hiện tại (không hồi quy) |
| YC-MP-03 | BB | Provider mô hình tại chỗ — gửi/nhận đúng định dạng trên ≥10 tài liệu thật |
| YC-MP-04 | BB | Đổi provider bằng cấu hình, không sửa mã, không biên dịch lại |
| YC-MP-05 | BB | Dự phòng: provider chính lỗi → tài liệu vào trạng thái lỗi có mô tả, không mất dữ liệu |
| YC-MP-06 | BB | **Log mỗi lần gọi model**: provider, tên model, phiên bản, thời gian xử lý |
| YC-MP-07 | NC | Chạy song song 2 provider để so sánh (chế độ đánh giá) |
| YC-MP-08 | BB | Giao diện đủ tổng quát: thêm công cụ mới chỉ viết 1 lớp hiện thực, không sửa giao diện |

### YC-MS — Công cụ phục vụ mô hình tại chỗ
| Mã | Ưu tiên | Yêu cầu |
|---|---|---|
| YC-MS-01 | BB | Thêm vào Docker Compose, chạy mạng nội bộ, **không mở cổng ra ngoài** |
| YC-MS-02 | BB | Mô hình lưu trên volume, không tải lại mỗi lần khởi động |
| YC-MS-03 | BB | Hoạt động hoàn toàn khi **ngắt Internet** (bằng chứng cốt lõi cho lập luận bảo mật) |
| YC-MS-04 | BB | Kiểm tra sẵn sàng trước khi đưa tài liệu vào xử lý |
| YC-MS-05 | BB | Cấu hình model khác nhau cho tác vụ khác nhau (trích xuất / embedding) |
| YC-MS-06 | BB | Thay công cụ bằng cấu hình, không sửa mã (phép thử chống khóa nhà cung cấp) |
| YC-MS-07 | NC | Đo & ghi tài nguyên: thời gian, RAM, GPU nếu có |
| YC-MS-08 | TT | Giao diện quản trị hiển thị công cụ/model đang dùng + tình trạng |

### YC-DR — Định tuyến theo độ nhạy cảm
| Mã | Ưu tiên | Yêu cầu |
|---|---|---|
| YC-DR-01 | BB | Mỗi lược đồ có độ nhạy cảm: Công khai / Nội bộ / Nhạy cảm (lưu DB) |
| YC-DR-02 | BB | Mặc định an toàn: không xác định được → chế độ tại chỗ |
| YC-DR-03 | BB | Nội bộ/Nhạy cảm **không bao giờ** ra đám mây, kể cả chọn thủ công (ràng buộc cứng, ghi log) |
| YC-DR-04 | BB | Chỉ quản trị viên đổi được độ nhạy cảm; mọi thay đổi ghi audit |
| YC-DR-05 | BB | Giao diện hiển thị rõ chế độ đang dùng cho tài liệu |
| YC-DR-06 | NC | **Báo cáo** định kỳ: tài liệu theo từng chế độ, phục vụ kiểm toán |

### YC-SC — Lược đồ trích xuất cấu hình được  *(ranh giới sản phẩm ↔ dịch vụ)*
| Mã | Ưu tiên | Yêu cầu |
|---|---|---|
| YC-SC-01 | BB | Lược đồ là dữ liệu (danh sách trường, kiểu, mô tả, bắt buộc) trong DB; thêm mới không sửa mã |
| YC-SC-02 | BB | Chuyển lược đồ Dublin Core hiện tại thành 1 lược đồ, giữ nguyên hành vi (không hồi quy) |
| YC-SC-03 | BB | Lược đồ công văn hành chính: số hiệu, ngày, cơ quan, loại VB, trích yếu, độ khẩn, độ mật, nơi nhận, người ký |
| YC-SC-04 | BB | Quy tắc chọn ngữ cảnh là thuộc tính của lược đồ, không phải hằng số trong mã |
| YC-SC-05 | BB | Giao diện cho quản trị viên tạo/sửa lược đồ mà không cần lập trình |
| YC-SC-06/07 | NC | Nhân bản / xuất / nhập lược đồ (chia sẻ giữa đơn vị) |
| YC-SC-08 | TT | Thư viện lược đồ mẫu (≥3) |

### YC-CF — Điểm tin cậy & kiểm soát chất lượng
| Mã | Ưu tiên | Yêu cầu |
|---|---|---|
| YC-CF-01 | BB | Điểm tin cậy cho từng trường |
| YC-CF-02 | BB | Kiểm tra tính hợp lệ đầu ra (định dạng, đủ trường bắt buộc, đúng kiểu) |
| YC-CF-03 | BB | Thử lại khi đầu ra không hợp lệ, tối đa N lần (cấu hình) → chuyển xử lý thủ công |
| YC-CF-04 | BB | Giao diện tô màu trường điểm thấp |
| YC-CF-05 | BB | **Phát hiện giá trị bịa**: kiểm giá trị có trong văn bản gốc không (chống ảo giác) |
| YC-CF-06 | NC | Ngưỡng tin cậy cấu hình theo lược đồ |
| YC-CF-07 | NC | **Thống kê/báo cáo**: tỉ lệ trường bị cán bộ sửa, theo trường & lược đồ |

### YC-RG — Lớp truy hồi (RAG)
| Mã | Ưu tiên | Yêu cầu |
|---|---|---|
| YC-RG-01 | BB | `pgvector` trên PostgreSQL hiện có, không thêm CSDL mới |
| YC-RG-02 | BB | Embedding bằng mô hình mở tại chỗ (không cần Internet) |
| YC-RG-03 | BB | Chia đoạn theo cấu trúc văn bản, không theo số ký tự cố định |
| YC-RG-04 | BB | Truy hồi ví dụ đã duyệt (cùng lược đồ) đưa vào ngữ cảnh trích xuất |
| YC-RG-05 | BB | Chỉ truy hồi trong cùng đơn vị/lược đồ — cách ly dữ liệu |
| YC-RG-06 | BB | Giao diện hỏi bằng ngôn ngữ tự nhiên trên kho |
| YC-RG-07 | BB | Truy hồi kết hợp: vector + toàn văn |
| YC-RG-08 | BB | **Mọi câu trả lời bắt buộc dẫn nguồn**; không có nguồn → "không tìm thấy" |
| YC-RG-09 | BB | Sinh câu trả lời bằng mô hình mở tại chỗ (chạy khi ngắt mạng) |
| YC-RG-10 | BB | Kết quả tra cứu tuân theo phân quyền (kể cả trong đoạn dẫn nguồn) |

### YC-AU — Nhật ký kiểm toán  *("log chi tiết" — trọng tâm yêu cầu bổ sung)*
| Mã | Ưu tiên | Yêu cầu |
|---|---|---|
| YC-AU-01 | BB | Ghi mọi thao tác: tải lên, xử lý, sửa từng trường, xác nhận, đẩy DSpace |
| YC-AU-02 | BB | Ghi rõ: ai, khi nào, thao tác gì, giá trị cũ, giá trị mới |
| YC-AU-03 | BB | **Bất biến**: không sửa/xóa được kể cả bởi quản trị viên |
| YC-AU-04 | BB | Ghi chế độ xử lý + tên/phiên bản model cho mỗi tài liệu |
| YC-AU-05 | NC | **Kết xuất báo cáo** theo thời gian/người dùng/tài liệu |
| YC-AU-06 | NC | Thời hạn lưu cấu hình được, mặc định không xóa |

## B. Yêu cầu phi chức năng (từ SRS)
- **YC-PC (Hiệu năng)**: chế độ đám mây không suy giảm sau khi thêm lớp trừu tượng (YC-PC-01); đo &
  ghi thời gian chế độ tại chỗ trên phần cứng thật, **không đặt ngưỡng trước khi đo** (YC-PC-02/03).
- **YC-BM (Bảo mật)**: tài liệu nhạy cảm không rời mạng nội bộ (YC-BM-01); chạy đủ khi ngắt Internet
  (YC-BM-02); không ghi khóa API/mật khẩu ra log (YC-BM-03); phân quyền cho mọi chức năng mới kể cả
  RAG (YC-BM-04); công cụ model không mở cổng ra ngoài (YC-BM-05).
- **YC-PL (Pháp lý/Giấy phép)**: bảng đối chiếu giấy phép mọi model AI (YC-PL-01) & thành phần nguồn
  mở (YC-PL-03, lưu ý Ghostscript); chỉ dùng model cho phép thương mại (YC-PL-02); văn bản xác định
  quyền sở hữu mã nguồn (YC-PL-04) — **xong TRƯỚC khi ký Bản cam kết dự thi**.
- **YC-VH (Vận hành)**: tài liệu hóa đủ để người khác tiếp quản (YC-VH-01); ≥2 người hiểu mã (YC-VH-02);
  triển khai bằng 1 lệnh (YC-VH-03); hướng dẫn tiếng Việt (YC-VH-04); sao lưu/khôi phục (YC-VH-05);
  giám sát + cảnh báo (YC-VH-06).

## C. Chuẩn HPU áp dụng (từ ecosystem hpu-dev)
| Chuẩn | Áp dụng cho DocuFlow HP |
|---|---|
| API envelope `{status,data,message}` + `success/error/paginated` | **Code mới** tuân thủ; endpoint cũ giữ tương thích, di trú dần (ADR-003) |
| URL `/api/v1/{resource}` kebab số nhiều, JSON snake_case, phân trang `?page&per_page` | Áp cho API mới (documents, schemas, audit, reports) |
| Cột bắt buộc mọi bảng: `id, created_at, updated_at, status` | Bổ sung `updated_at` cho `documents`; áp cho bảng mới |
| Soft delete (`status`, không hard delete) + endpoint `/{id}/restore` | Sửa `delete_job` (đang xóa cứng) |
| Design system `#1e3a5f`, sidebar 240px, badge trạng thái, confirm-trước-xóa | Nâng cấp UI Next.js dần |
| Docker: healthcheck `service_healthy`, non-root user, caddy-docker-proxy labels, backup pg_dump | Chuẩn hóa `docker-compose.yml` + Dockerfile |
| KHÔNG áp dụng: `tenant-isolation`/RLS/`organization_id` | Vì single-tenant (một Nhà trường) |

> Bảo mật chống IDOR (không `db.get(Model, id)` trần) và trả 404-không-403 vẫn áp dụng cho endpoint
> truy cập tài liệu theo id, dù không multi-tenant.

## D. Nhóm "Báo cáo & Log chi tiết" (yêu cầu bổ sung — gom để triển khai)
1. **Structured logging** (nền tảng): log JSON có `request_id`/`job_id` tương quan; middleware log mọi
   request (method, path, status, thời gian); không lộ secret (YC-BM-03).
2. **Model-call log** (YC-MP-06): provider/model/version/latency mỗi lần trích xuất — lưu bảng riêng.
3. **Audit log bất biến** (YC-AU): bảng append-only, chặn UPDATE/DELETE bằng trigger + phân quyền DB.
4. **Báo cáo/Dashboard**: throughput OCR theo thời gian, tỉ lệ thành công/thất bại, tài liệu theo chế
   độ (YC-DR-06), tỉ lệ trường bị sửa (YC-CF-07), kết xuất kiểm toán (YC-AU-05) — có xuất Excel.
