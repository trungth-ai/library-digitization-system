# DocuFlow HP — Bộ trường hợp kiểm thử đợt nâng cấp

> **Mở rộng** `docs/06_Ke_hoach_kiem_thu.docx` cho các yêu cầu mới trong `docs/UPGRADE_REQUIREMENTS.md`.
> Kế thừa nguyên tắc và định dạng của kế hoạch kiểm thử gốc.
>
> **Lập ngày:** 31/07/2026 · **Phiên bản:** 1.0
>
> ⚠️ **TRẠNG THÁI TÀI LIỆU: phần lớn trường hợp kiểm thử dưới đây CHƯA được chạy.**
> Đây chủ yếu là **kế hoạch**, không phải báo cáo kết quả. Ô "Trạng thái" chỉ được điền bằng
> **kết quả thật**, không bằng kỳ vọng. *(Giữ nguyên nguyên tắc mục I của kế hoạch gốc.)*
>
> **Đã chạy tính tới 01/08/2026** — thuộc đợt vá ba lỗ hổng N-01/N-02/N-03 (ADR-010/011/012):
>
> | Nhóm | Đã chạy đạt | Chưa chạy | Ghi chú |
> |---|---|---|---|
> | `KT-BU-01` (upload không chặn event loop) | ✅ | | pytest, có test tái hiện lỗi cũ |
> | `KT-BU-15/16/17/19/20/22/23` (hàng đợi tin cậy) | ✅ | | pytest với Redis giả đúng ngữ nghĩa |
> | `KT-QT-01/02/06/09/13/14/15/16` | ✅ | | pytest thuần + quét AST |
> | `KT-QT-03/04/05/10/11/12/17/18` | | ⏳ | **cần PostgreSQL thật + trình duyệt** |
> | `KT-KH-05/07/08` (không hồi quy) | ✅ | | 330 pytest, 0 hồi quy; UI build exit 0 |
> | `KT-HN-08` (thông lượng nạp) | | ⏳ | **cần đo thật** — ADR-010 nói rõ có thể giảm nhẹ |
> | Toàn bộ nhóm còn lại | | ⏳ | thuộc các sprint V1–V9 chưa bắt đầu |
>
> Môi trường đã chạy: máy dev Windows, Python 3.12, **không có PostgreSQL/Redis/fastapi** — nên mọi
> test là test logic thuần hoặc dùng lớp giả. Điều này **không thay thế** kiểm chứng trên môi trường
> thật; các ca đánh dấu ⏳ ở trên là phần bắt buộc phải chạy trước khi bật `AUTH_MODE=on`.

---

## 1. Nguyên tắc & quy ước

### 1.1 Kế thừa sáu nguyên tắc của kế hoạch kiểm thử gốc

1. **Đo trước, tuyên bố sau** — không con số nào vào hồ sơ khi chưa qua kiểm thử.
2. **Ghi rõ phương pháp và cỡ mẫu** — mỗi kết quả ghi: cỡ mẫu, cách chọn mẫu, ai đo, khi nào, phần cứng nào.
3. **Kết quả xấu vẫn ghi nhận** — không chọn lọc kết quả có lợi.
4. **Kiểm thử không hồi quy là bắt buộc** — hệ thống đang phục vụ người dùng thật.
5. **Kiểm thử chấp nhận do người dùng thật thực hiện** — đội tự nghiệm thu sản phẩm của mình là kiểm thử không có giá trị.
6. **Ưu tiên theo mức rủi ro** — bảo mật cao nhất, vì hậu quả không sửa được bằng bản vá.

### 1.2 Mã kiểm thử mới — không trùng với kế hoạch gốc

Kế hoạch gốc đã dùng: `KT-CN-01→31`, `KT-BM-01→15`, `KT-CX-01→10`, `KT-HN-01→07`, `KT-KH-01→04`,
`KT-PL-01→09`. Đợt này dùng **họ mã mới** để không xung đột, và **nối tiếp số** ở các họ sẵn có:

| Họ | Phạm vi | Số lượng |
|---|---|---|
| `KT-LG-xx` | Log hệ thống có cấu trúc | 12 |
| `KT-AN-xx` | Phân tích chi tiết kết quả AI | 14 |
| `KT-QT-xx` | Quản trị người dùng & phân quyền | 18 |
| `KT-NK-xx` | Nhật ký người dùng | 11 |
| `KT-BU-xx` | Nạp & xử lý khối lượng lớn | 26 |
| `KT-DB-xx` | Bảng điều khiển theo dõi công việc | 13 |
| `KT-RV-xx` | Không gian duyệt tài liệu | 12 |
| `KT-TB-xx` | Thông báo & cảnh báo | 8 |
| `KT-VH-xx` | Vận hành dài hạn | 10 |
| `KT-TK-xx` | Tích hợp & tài khoản dịch vụ | 6 |
| `KT-KH-05→09` | *(nối tiếp)* Không hồi quy cho từng sprint | 5 |
| `KT-BM-16→21` | *(nối tiếp)* Bảo mật cho tính năng mới | 6 |
| `KT-HN-08→11` | *(nối tiếp)* Hiệu năng khối lượng lớn | 4 |
| | **Tổng** | **145** |

### 1.3 Phân loại theo cách chạy

| Loại | Ý nghĩa | Bằng chứng nộp |
|---|---|---|
| **U** — Đơn vị | `pytest`, không cần DB/mạng | Đầu ra `pytest -q` |
| **TH** — Tích hợp | Cần PostgreSQL/Redis thật | Ảnh chụp truy vấn SQL + đầu ra |
| **E2E** | Qua trình duyệt / Next server thật | Ảnh chụp màn hình hoặc bản ghi Playwright |
| **TC** — Thủ công | Người thực hiện theo kịch bản | Biên bản có chữ ký người kiểm |
| **CN** — Chấp nhận | **Cán bộ sử dụng thật** thực hiện | Biên bản nghiệm thu |

### 1.4 Quy tắc bắt buộc khi ghi kết quả

- Ô "Trạng thái" chỉ nhận: `Đạt` / `Không đạt` / `Đạt có điều kiện (ghi rõ điều kiện)` / *(để trống nếu chưa chạy)*.
- Mọi con số ghi kèm **cỡ mẫu + phần cứng + ngày đo**. Ví dụ đúng: *"p95 = 4.230 ms, mẫu 500 tệp,
  máy chủ 4 CPU/8GB, đo 12/10/2026"*. Ví dụ **không dùng được**: *"nhanh hơn trước"*.
- Kiểm thử "Không đạt" **vẫn ghi vào tài liệu**, kèm số hiệu lỗi và hướng xử lý.

---

## 2. Bộ dữ liệu kiểm thử mới

Bổ sung cho BD-01→BD-05 của kế hoạch gốc. **Phải chuẩn bị xong trong V0** — thiếu bộ dữ liệu thì
không kiểm thử được và mọi con số về khối lượng lớn đều vô nghĩa.

| Bộ | Quy mô | Nội dung | Cách chuẩn bị | Dùng cho |
|---|---|---|---|---|
| **BD-06: Tải khối lượng lớn** | **500 tệp PDF** | Tài liệu thật đã số hóa của Trung tâm, đa dạng số trang (1–300) và dung lượng (0,1–200 MB) | Sao chép từ kho đã xử lý. **Không** tạo tệp giả — tệp giả không tái hiện đúng đặc tính OCR | `KT-BU`, `KT-HN-08→11` |
| **BD-07: Tài khoản & vai trò** | 8 tài khoản | 1 `admin`, 3 `librarian`, 2 `approver`, 1 `viewer`, 1 `service` (bị khóa) | Tạo trên môi trường thử. Mật khẩu lưu trong quản lý bí mật, **không** ghi vào tài liệu này | `KT-QT`, `KT-NK` |
| **BD-08: Tệp đầu vào xấu** | 15 tệp | 3 tệp trùng nhau hoàn toàn · 2 tệp PDF hỏng (cắt cụt) · 2 tệp đổi đuôi thành `.pdf` (thực chất ảnh/ZIP) · 2 tệp PDF có mật khẩu · 2 tệp 0 byte · 2 tệp > hạn mức · 1 ZIP có `zip-slip` (`../../etc/passwd`) · 1 tệp tên chứa dấu tiếng Việt và khoảng trắng | Tự tạo — đây là nhóm **duy nhất** được tạo giả, vì mục đích là kiểm thử biên | `KT-BU-04→10`, `KT-BM-20` |
| **BD-09: Đối chiếu độ chính xác vận hành** | ≥ 30 tài liệu/trường | Tài liệu đã được cán bộ duyệt và sửa metadata trong vận hành thật | Tích lũy tự nhiên sau khi V2 chạy ≥ 2 tuần | `KT-AN-06→09` |

> **BD-06 lưu ý về quyền riêng tư:** chọn tài liệu đã công khai hoặc thuộc nhóm "Công khai" theo
> lược đồ. Không đưa tài liệu nhóm "Nhạy cảm" vào bộ kiểm thử tải, vì bộ này có thể được sao chép
> qua nhiều môi trường thử.

---

## 3. KT-LG — Log hệ thống có cấu trúc *(V1)*

| Mã | Trường hợp kiểm thử | Các bước | Tiêu chí đạt | Loại | Trạng thái |
|---|---|---|---|---|---|
| KT-LG-01 | Log là JSON hợp lệ | Chạy API + worker, lấy 100 dòng log bất kỳ | 100/100 dòng `json.loads` thành công; có đủ `ts, level, logger, msg` | U | |
| KT-LG-02 | `request_id` sinh tự động | Gọi một endpoint không gửi `X-Request-Id` | Phản hồi có header `X-Request-Id`; grep giá trị đó ra ≥ 1 dòng log | TH | |
| KT-LG-03 | `request_id` từ ngoài được tôn trọng | Gọi API kèm `X-Request-Id: test-abc-123` | Log dùng đúng `test-abc-123`, không sinh mã mới | TH | |
| KT-LG-04 | `job_id` xuyên suốt vòng đời worker | Xử lý 1 tài liệu, grep `job_id` trong log worker | Ra đủ chuỗi: nhận việc → OCR → trích xuất → xuất → hoàn tất | TH | |
| KT-LG-05 | **Che bí mật (YC-BM-03)** | Cố ý ghi log chứa: `CLAUDE_API_KEY=sk-ant-xxx`, `password=abc123`, `Authorization: Bearer eyJ...`, cookie phiên | Tệp log chứa `***`; **grep toàn bộ thư mục log không ra chuỗi bí mật nào** | U | |
| KT-LG-06 | Dòng tổng kết mỗi request | Gọi 20 request gồm cả lỗi 400/404/500 | 20/20 có dòng tổng kết đủ: method, path, status, thời gian ms, actor | TH | |
| KT-LG-07 | Luân chuyển tệp log | Đặt `LOG_ROTATE_MB=1`, sinh > 3 MB log | Có tệp `.1`, `.2`; số tệp không vượt `LOG_ROTATE_KEEP`; ứng dụng không lỗi | TH | |
| KT-LG-08 | Dọn log theo tuổi | Tạo tệp log giả 30 ngày tuổi + `system_events` 100 ngày tuổi, chạy tác vụ dọn | Bản ghi quá hạn biến mất; bản ghi trong hạn còn **nguyên vẹn**; có dòng `system_events` ghi lại việc dọn và số lượng | TH | |
| KT-LG-09 | API xem log lọc đúng | `GET /api/v2/logs?job_id=<id>&level=error` | Chỉ trả log của job đó, mức `error`; có envelope `{status,data,message}` + `meta` phân trang | TH | |
| KT-LG-10 | API xem log không quét vô hạn | Tạo tệp log 500 MB, gọi API không kèm bộ lọc | Phản hồi trong thời gian chờ hợp lý; số dòng quét không vượt `LOG_SCAN_MAX_LINES` | TH | |
| KT-LG-11 | Trang `/nhat-ky-he-thong` | Mở trang, lọc theo mức `error`, dán một `request_id`, tải xuống đoạn log | Hiển thị đúng; tải xuống được tệp; **tiếng Việt hiển thị đúng dấu** | E2E | |
| KT-LG-12 | Van lùi `LOG_FORMAT=text` | Đặt `LOG_FORMAT=text`, khởi động lại | Log trở về đúng định dạng chữ thuần như trước V1; hệ thống chạy bình thường | TH | |

---

## 4. KT-AN — Phân tích chi tiết kết quả AI *(V2)*

| Mã | Trường hợp kiểm thử | Các bước | Tiêu chí đạt | Loại | Trạng thái |
|---|---|---|---|---|---|
| KT-AN-01 | Migration 003 an toàn | Chạy `003_ai_analytics.sql` **hai lần** trên bản sao dữ liệu thật | Không lỗi; số bản ghi `documents`, `model_calls`, `audit_log` **không đổi**; cột mới có mặt | TH | |
| KT-AN-02 | Ghi số token | Trích xuất 1 tài liệu bằng provider có báo token | `model_calls.prompt_tokens/completion_tokens/total_tokens` > 0 | TH | |
| KT-AN-03 | Công cụ không báo token không gây lỗi | Trích xuất bằng provider không trả thông tin token | Cột token = `NULL`; **không có ngoại lệ**; tài liệu vẫn xử lý xong | U | |
| KT-AN-04 | Chi tiết từng trường | Trích 1 tài liệu lược đồ Dublin Core (11 trường) | `model_call_fields` có đúng số dòng bằng số trường model trả về; giá trị khớp `metadata_fields` | TH | |
| KT-AN-05 | Chỉ số OCR | Xử lý 1 PDF 50 trang | `ocr_runs` có 1 dòng đủ: pages, dpi_pre/post, size_in/out, text_chars, duration_ms | TH | |
| KT-AN-06 | **Độ chính xác vận hành có cỡ mẫu** | Dựng 40 tài liệu đã duyệt, gọi `/api/v2/analytics/ai/accuracy` | Mỗi dòng có `sample_size`; trường có < `ACCURACY_MIN_SAMPLE` mẫu trả `"chưa đủ dữ liệu"`, **không trả %** | TH | |
| KT-AN-07 | Chuẩn hóa khi đối chiếu | Đặt giá trị AI `"Báo cáo  tổng kết"` (hai khoảng trắng), giá trị duyệt `"Báo cáo tổng kết"` | Tính là **đúng** — chuẩn hóa khoảng trắng theo công thức mục 1.3 kế hoạch gốc | U | |
| KT-AN-08 | Chuẩn hóa ngày tháng | Giá trị AI `01/03/2026`, giá trị duyệt `2026-03-01` | Tính là **đúng** — cùng ngày sau chuẩn hóa | U | |
| KT-AN-09 | Trường rỗng đúng cách | Tài liệu BD-04 (thiếu trường), AI trả rỗng, cán bộ cũng để rỗng | Tính là **đúng** (trả rỗng khi không có là đúng, bịa giá trị là sai) | U | |
| KT-AN-10 | Chi phí là số nguyên VNĐ | Xem báo cáo chi phí tháng | Giá trị là số nguyên; hiển thị `N.NNN.NNN đ`; chế độ tại chỗ = `0 đ` | TH | |
| KT-AN-11 | Prompt thô mặc định KHÔNG lưu | `AI_LOG_RAW=0`, trích 5 tài liệu | Không có tệp prompt/phản hồi nào; DB vẫn có `prompt_hash` | TH | |
| KT-AN-12 | Ghi truy vết lỗi không làm hỏng số hóa | Dựng `model_call_fields` không ghi được (thu quyền INSERT) | Tài liệu **vẫn xử lý xong** và lưu metadata; chỉ có dòng log lỗi | U | |
| KT-AN-13 | Trang `/phan-tich-ai` | Mở trang | Có ghi chú phương pháp *"đối chiếu với giá trị cán bộ đã duyệt"*; mọi % kèm cỡ mẫu; không có bảng rỗng trông như đã đo | E2E | |
| KT-AN-14 | Xuất Excel tiếng Việt | Xuất báo cáo độ chính xác | Mở bằng Excel trên Windows: **dấu tiếng Việt đúng**, ngày `DD/MM/YYYY`, tiền `N.NNN.NNN đ` | TC | |

---

## 5. KT-QT — Quản trị người dùng & phân quyền *(V3)* 🔴 *ưu tiên cao nhất*

| Mã | Trường hợp kiểm thử | Các bước | Tiêu chí đạt | Loại | Trạng thái |
|---|---|---|---|---|---|
| KT-QT-01 | Mật khẩu được băm | Tạo tài khoản, truy vấn `SELECT * FROM users` | Không có cột nào chứa mật khẩu thô; hash có tiền tố thuật toán đã chốt (`QĐ-04`) | TH | |
| KT-QT-02 | Mật khẩu không lọt vào log | Đăng nhập, grep toàn bộ thư mục log tìm mật khẩu | **Không tìm thấy** mật khẩu ở bất kỳ tệp log nào (YC-BM-03) | TH | |
| KT-QT-03 | Đăng nhập & đăng xuất | Đăng nhập đúng → gọi `/api/v2/auth/me` → đăng xuất → gọi lại | Lần 1 trả thông tin người dùng; sau đăng xuất trả 401 | TH | |
| KT-QT-04 | Cookie phiên đúng thuộc tính | Kiểm header `Set-Cookie` | Có `HttpOnly`, `SameSite=Lax`; có `Secure` khi chạy HTTPS | TH | |
| KT-QT-05 | Thu hồi phiên có hiệu lực ngay | `admin` thu hồi phiên của người dùng B đang đăng nhập | Request kế tiếp của B trả 401 — **không chờ hết hạn** | TH | |
| KT-QT-06 | **Phân quyền cưỡng chế ở máy chủ** | Đăng nhập `viewer`, dùng `curl` gọi thẳng `DELETE /api/v2/jobs/{id}` (bỏ qua giao diện) | Trả **403**; tài liệu **không** bị xóa; có bản ghi `user_activity` với `result='denied'` | TH | |
| KT-QT-07 | Ẩn nút không phải cơ chế bảo vệ | Với mỗi vai trò: liệt kê nút bị ẩn trên giao diện, gọi thẳng API tương ứng | **100%** trả 403 — không nút ẩn nào mà API vẫn cho phép | TH | |
| KT-QT-08 | `librarian` không đẩy được DSpace | Đăng nhập `librarian`, gọi API đẩy DSpace | 403 kèm thông báo tiếng Việt rõ ràng | TH | |
| KT-QT-09 | **Không endpoint ghi nào bị bỏ sót** | Test tự động liệt kê mọi route POST/PUT/PATCH/DELETE của `api.py`, khẳng định từng route có dependency `require(...)` | **0** route ghi thiếu phân quyền. *(Test này hỏng khi thêm endpoint mới mà quên gắn — đó là mục đích)* | U | |
| KT-QT-10 | Khóa sau N lần sai | Sai mật khẩu 5 lần liên tiếp | Tài khoản khóa 15 phút; lần thứ 6 báo tiếng Việt rõ *còn bao lâu*; có `user_activity` | TH | |
| KT-QT-11 | Quản trị viên đầu tiên bắt buộc đổi mật khẩu | Khởi động lần đầu với `ADMIN_BOOTSTRAP_*`, đăng nhập | Bị buộc đổi mật khẩu trước khi làm được việc gì khác | E2E | |
| KT-QT-12 | Cookie qua được proxy Next | Đăng nhập trên giao diện, thao tác qua route proxy `ui/src/app/api/**` | Phiên giữ nguyên; **không** phải đăng nhập lại. *(Kiểm trên Next server thật, không chỉ FastAPI)* | E2E | |
| KT-QT-13 | `AUTH_MODE=off` không đổi hành vi | Đặt `off`, chạy bộ hồi quy `KT-KH-07` | Hệ thống hành xử **y hệt** trước V3 | TH | |
| KT-QT-14 | `AUTH_MODE=shadow` ghi nhận đúng | Đặt `shadow`, gọi API không kèm phiên | Request **được phục vụ**; có cảnh báo ghi rõ endpoint + IP + user-agent | TH | |
| KT-QT-15 | `AUTH_MODE=on` chặn thật | Đặt `on`, gọi API không kèm phiên | 401; thông báo tiếng Việt hướng dẫn đăng nhập | TH | |
| KT-QT-16 | Van lùi hoạt động | Từ `on` đổi về `shadow`, **không build lại image** | Hệ thống phục vụ lại request không xác thực trong vòng một lần khởi động lại container | TH | |
| KT-QT-17 | CLI cứu hộ mật khẩu quản trị | Chạy lệnh đặt lại mật khẩu từ trong container | Đăng nhập được bằng mật khẩu mới; có bản ghi `audit_log` về thao tác này | TC | |
| KT-QT-18 | Vô hiệu hóa thay vì xóa người dùng | Vô hiệu hóa 1 tài khoản đã có nhiều thao tác trong nhật ký | Không đăng nhập được nữa; **toàn bộ nhật ký cũ của họ vẫn truy được đầy đủ** | TH | |

---

## 6. KT-NK — Nhật ký người dùng *(V4)*

| Mã | Trường hợp kiểm thử | Các bước | Tiêu chí đạt | Loại | Trạng thái |
|---|---|---|---|---|---|
| KT-NK-01 | **`user_activity` bất biến** | Thử `UPDATE user_activity SET ...` và `DELETE FROM user_activity` bằng tài khoản DB quản trị | Cả hai bị DB **từ chối** kèm thông báo của trigger | TH | |
| KT-NK-02 | Ghi đăng nhập thành công/thất bại | Đăng nhập đúng 1 lần, sai 3 lần từ 2 IP khác nhau | 4 bản ghi, đúng `result`, đúng IP từng lần | TH | |
| KT-NK-03 | Ghi bị từ chối quyền | `viewer` gọi API xóa | Bản ghi `action='delete'`, `result='denied'`, có `resource_id` | TH | |
| KT-NK-04 | Ghi truy cập dữ liệu nhạy cảm | Tải một tệp ZIP, kết xuất một báo cáo | Có bản ghi kèm `document_id` / loại báo cáo | TH | |
| KT-NK-05 | `actor` thật trong `audit_log` | Đăng nhập `librarian_a`, sửa một trường metadata | `audit_log.actor = 'librarian_a'` — **không còn** `'api'` | TH | |
| KT-NK-06 | Không còn `actor='api'` từ thao tác người | Sau 1 tuần chạy `AUTH_MODE=on`, truy vấn `audit_log WHERE actor='api'` | **0 bản ghi mới** kể từ ngày bật (bản ghi cũ giữ nguyên, không sửa) | TH | |
| KT-NK-07 | Lọc nhật ký người dùng | Lọc theo người + ngày + thao tác | Kết quả đúng; phân trang đúng; envelope HPU đủ `meta` | TH | |
| KT-NK-08 | Xuất Excel nhật ký | Xuất 10.000 dòng | Tệp mở được; tiếng Việt đúng; thời gian xuất ghi nhận kèm cỡ mẫu | TC | |
| KT-NK-09 | **Dòng thời gian một tài liệu** | Mở tài liệu đã qua: tải lên → OCR → trích xuất → sửa 2 trường → duyệt → đẩy DSpace | Một dòng thời gian duy nhất, đúng thứ tự, đủ 4 nguồn (`audit_log`, `user_activity`, `model_calls`, `ocr_runs`) | E2E | |
| KT-NK-10 | Phát hiện bất thường | Sai mật khẩu 10 lần trong 5 phút | Có `system_events` mức `warning` | TH | |
| KT-NK-11 | Dọn theo tuổi giữ đúng phần trong hạn | Tạo bản ghi 400 ngày + 100 ngày tuổi, chạy dọn (365 ngày) | Bản ghi 400 ngày mất, bản ghi 100 ngày **còn**; có ghi nhận số lượng đã dọn | TH | |

---

## 7. KT-BU — Nạp & xử lý khối lượng lớn *(V5, V6)*

### 7.1 Đường vào *(V5)*

| Mã | Trường hợp kiểm thử | Các bước | Tiêu chí đạt | Loại | Trạng thái |
|---|---|---|---|---|---|
| KT-BU-01 | **Ghi tệp không chặn API (sửa N-03)** | Mở SSE `/api/v2/jobs/stream` ở tab A; tab B tải tệp 200 MB | SSE tab A **không đứt**; request khác vẫn phản hồi trong lúc ghi đĩa | TH | |
| KT-BU-02 | Nạp 500 tệp một lần | Nạp toàn bộ BD-06 thành một lô | 500 tài liệu vào hàng đợi; lô có `total_files=500`; không lỗi | TH | |
| KT-BU-03 | Vượt hạn mức báo rõ ràng | Nạp vượt `MAX_BATCH_FILES` | Lỗi 400, thông báo **tiếng Việt** nói rõ hạn mức và số hiện tại | TH | |
| KT-BU-04 | Chống trùng bằng hash | Nạp 3 tệp trùng nhau (BD-08) | 1 tệp xử lý, 2 tệp bị bỏ qua kèm thông báo **trùng với tài liệu nào**; `skipped_files=2` | TH | |
| KT-BU-05 | Chế độ xử lý lại | Đặt `DEDUP_MODE=reprocess`, nạp lại tệp đã có | Tệp được xử lý lại; ghi rõ là bản xử lý lại | TH | |
| KT-BU-06 | Từ chối tệp không phải PDF | Nạp tệp ảnh đổi đuôi `.pdf` (BD-08) | Từ chối, nói rõ *lý do* (chữ ký tệp không phải PDF); không tốn OCR | U | |
| KT-BU-07 | Từ chối PDF hỏng / 0 byte / có mật khẩu | Nạp từng loại trong BD-08 | Mỗi loại có thông báo tiếng Việt riêng, đúng lý do | U | |
| KT-BU-08 | Tên tệp tiếng Việt có dấu | Nạp tệp `Báo cáo tổng kết năm 2026.pdf` | Xử lý bình thường; tên hiển thị đúng dấu; tải xuống đúng tên | TH | |
| KT-BU-09 | Đĩa gần đầy → từ chối an toàn | Giả lập dung lượng trống < `DISK_MIN_FREE_GB` | Từ chối nhận, có `system_events`; **hệ thống không chết**, tài liệu cũ không hỏng | TH | |
| KT-BU-10 | Nạp từ ZIP | Nạp ZIP 300 tệp | Tạo lô 300 tài liệu; cấu trúc thư mục thành gợi ý bộ sưu tập | TH | |
| KT-BU-11 | Thư mục theo dõi | Chép 100 tệp vào thư mục theo dõi | Trong ≤ 2 chu kỳ quét: tự tạo lô, tệp chuyển sang `_processed/` | TH | |
| KT-BU-12 | Giao diện nạp theo lô | Chọn 200 tệp trên trình duyệt, đặt tên lô, nạp | Thanh tiến độ tải chính xác; hiện danh sách bị bỏ qua **kèm lý do từng tệp** | E2E | |
| KT-BU-13 | Van lùi `BATCH_UPLOAD_V2=0` | Đặt `0`, dùng giao diện cũ | Đường nạp cũ (trần 10 tệp) hoạt động đúng như trước V5 | TH | |
| KT-BU-14 | Endpoint cũ không đổi | Gọi `/api/v1/process` và `/api/v2/batch-upload` như trước | Phản hồi **giữ nguyên định dạng cũ** (ADR-003) | TH | |

### 7.2 Hàng đợi & xử lý *(V6)*

| Mã | Trường hợp kiểm thử | Các bước | Tiêu chí đạt | Loại | Trạng thái |
|---|---|---|---|---|---|
| KT-BU-15 | **Không mất việc khi worker chết (sửa N-02)** 🔴 | Nạp 50 tài liệu; giữa lúc xử lý chạy `docker kill -s KILL` worker | **0 tài liệu bị mất.** Job đang dở quay lại hàng đợi và được xử lý xong. Tổng số hoàn tất = 50 | TH | |
| KT-BU-16 | Thu hồi việc mồ côi đúng thời hạn | Kill worker, đo thời gian tới khi job được nhận lại | ≤ 2 phút; có `system_events` `kind='job_reclaimed'` | TH | |
| KT-BU-17 | Không thu hồi nhầm job đang chạy | Worker A đang OCR tài liệu lớn (> 5 phút), bộ thu hồi chạy | Job **không** bị thu hồi khi nhịp tim còn sống; không xử lý hai lần | TH | |
| KT-BU-18 | Xử lý hai lần không tạo dữ liệu trùng | Ép xử lý lại một tài liệu đã xong | `metadata_fields` không có dòng trùng (nhờ `ON CONFLICT DO NOTHING`) | TH | |
| KT-BU-19 | Thử lại lỗi hạ tầng | Tắt Redis giữa chừng rồi bật lại | Job thử lại với khoảng lùi tăng dần; hoàn tất sau khi Redis trở lại | TH | |
| KT-BU-20 | Không thử lại lỗi tài liệu | Nạp PDF hỏng | Vào hàng đợi chết **ngay**, không thử lại 3 lần vô ích | TH | |
| KT-BU-21 | Hàng đợi chết có lý do đọc được | Xem `/api/v2/queue/dead` | Mỗi mục có lý do **tiếng Việt** đủ để biết phải làm gì | E2E | |
| KT-BU-22 | Chạy lại từ hàng đợi chết | Sửa nguyên nhân, bấm "Chạy lại" | Job chạy tiếp; **giữ nguyên `document_id`**; không tạo bản ghi mới | E2E | |
| KT-BU-23 | Ưu tiên hàng đợi | Nạp lô 500 (`low`), 10 giây sau tải 1 tệp lẻ (`high`) | Tệp lẻ được xử lý **trước** phần còn lại của lô | TH | |
| KT-BU-24 | Tạm dừng / tiếp tục lô | Tạm dừng lô đang chạy | Job đang chạy dở **vẫn xong**; job chưa bắt đầu thì dừng; "Tiếp tục" chạy lại đúng phần còn lại | TH | |
| KT-BU-25 | Kiểm soát tải | Đẩy hàng đợi vượt `QUEUE_MAX_DEPTH`, thử nạp thêm | Từ chối mềm kèm thông báo tiếng Việt nói rõ khi nào thử lại được; hệ thống **không sập** | TH | |
| KT-BU-26 | Đẩy DSpace theo lô phía máy chủ | Đẩy 100 item rồi **đóng trình duyệt** | Vẫn chạy tiếp tới hết; có bảng kết quả từng item với lý do lỗi cụ thể | E2E | |

---

## 8. KT-DB — Bảng điều khiển theo dõi công việc *(V7)*

| Mã | Trường hợp kiểm thử | Các bước | Tiêu chí đạt | Loại | Trạng thái |
|---|---|---|---|---|---|
| KT-DB-01 | "Việc của tôi" đúng người | Đăng nhập 2 cán bộ khác nhau | Mỗi người chỉ thấy tài liệu liên quan **đến mình**; không lẫn của nhau | E2E | |
| KT-DB-02 | Số liệu khớp nguồn | Đối chiếu bảng điều khiển với `/api/v2/stats` và `/bao-cao` cùng thời điểm | **Không vênh số nào.** Vênh là không đạt — hai màn hình mâu thuẫn còn tệ hơn không có màn hình | TH | |
| KT-DB-03 | Không có worker → nói rõ | Tắt toàn bộ worker | Hiện cảnh báo "không có worker nào đang chạy", **không** hiện `0` im lặng | E2E | |
| KT-DB-04 | Tiến độ lô chính xác | Lô 100 tệp đang chạy | Số xong/lỗi/còn lại khớp DB; thanh tiến độ đúng tỉ lệ | TH | |
| KT-DB-05 | Cảnh báo SLA | Đặt ngưỡng 24h, dựng tài liệu tồn 30h | Xuất hiện trong danh sách quá hạn, hiện nổi bật, đếm đúng số lượng | TH | |
| KT-DB-06 | Cập nhật realtime | Mở bảng điều khiển, nạp tài liệu mới ở tab khác | Số liệu cập nhật **không cần tải lại trang** (qua SSE sẵn có) | E2E | |
| KT-DB-07 | Xu hướng hàng đợi | Xem biểu đồ 7 ngày | Dữ liệu từ `queue_samples`; chỉ ra được giờ cao điểm | E2E | |
| KT-DB-08 | Quyền xem năng suất cá nhân (`QĐ-06`) | Đăng nhập `librarian` xem thẻ năng suất | Chỉ thấy số của **chính mình**; `admin` thấy theo từng người | TH | |
| KT-DB-09 | Bộ lọc thời gian đồng bộ | Đổi bộ lọc sang "30 ngày" | **Mọi thẻ** cập nhật theo, không có thẻ nào giữ số cũ | E2E | |
| KT-DB-10 | Xuất Excel theo bộ lọc | Xuất với bộ lọc "7 ngày" | Tệp chứa đúng dữ liệu 7 ngày, tiếng Việt đúng, ngày `DD/MM/YYYY` | TC | |
| KT-DB-11 | Hiệu năng với dữ liệu lớn | Dựng 100.000 tài liệu, mở bảng điều khiển | Thời gian tải **ghi nhận kèm cỡ mẫu và phần cứng**; nếu vượt ngưỡng chấp nhận thì bật `daily_metrics` | TH | |
| KT-DB-12 | Không vẽ bảng rỗng | Môi trường sạch chưa có dữ liệu | Hiện "chưa có dữ liệu", **không** vẽ bảng/biểu đồ rỗng trông như đã đo | E2E | |
| KT-DB-13 | **Cán bộ thật dùng được** | Cán bộ Trung tâm dùng bảng điều khiển 1 tuần trong việc thật | Xác nhận trả lời được "hôm nay tôi phải làm gì" mà không cần hỏi ai | CN | |

---

## 9. KT-RV — Không gian duyệt tài liệu *(V8)*

| Mã | Trường hợp kiểm thử | Các bước | Tiêu chí đạt | Loại | Trạng thái |
|---|---|---|---|---|---|
| KT-RV-01 | Danh sách chờ duyệt | Mở `/duyet` | Chỉ hiện tài liệu `needs_review=true`; sắp theo ưu tiên & thời gian chờ | E2E | |
| KT-RV-02 | **Tô màu trường điểm thấp (YC-CF-04)** | Mở tài liệu có trường `confidence < 0.5` | Trường đó được tô màu phân biệt rõ; hiện điểm tin cậy; hiện **lý do cần xem lại** | E2E | |
| KT-RV-03 | Xem PDF cạnh metadata | Mở màn hình duyệt | PDF hiển thị bên trái, trường bên phải; cuộn PDF không mất vị trí form | E2E | |
| KT-RV-04 | Bàn phím tắt | Dùng phím tắt chuyển trường / chấp nhận / tài liệu tiếp | Hoạt động đúng; có bảng phím tắt xem được trong trang | E2E | |
| KT-RV-05 | Sửa trường ghi audit đúng người | Sửa `dc.title`, lưu | `audit_log`: `action='edit_field'`, `field_key='dc.title'`, đủ `old_value`/`new_value`, `actor` là **tên thật** | TH | |
| KT-RV-06 | Xác nhận trước khi đẩy DSpace | Thử đẩy DSpace một tài liệu **chưa xác nhận** | Bị chặn kèm thông báo tiếng Việt. *(Nguyên tắc SRS: con người giữ quyền quyết định)* | TH | |
| KT-RV-07 | Xác nhận ghi audit | Bấm Xác nhận | `audit_log` có `action='confirm'` với `actor` thật | TH | |
| KT-RV-08 | Duyệt hàng loạt có xác nhận | Chọn 20 tài liệu điểm cao, duyệt hàng loạt | Có hộp thoại xác nhận nói rõ số lượng; sau khi đồng ý ghi đủ 20 bản ghi audit | E2E | |
| KT-RV-09 | Thùng rác & phục hồi | Xóa mềm 1 tài liệu → mở `/thung-rac` → phục hồi | Tài liệu biến mất khỏi danh sách chính, xuất hiện ở thùng rác, phục hồi về đúng trạng thái cũ; **tệp không mất** | E2E | |
| KT-RV-10 | Xóa vĩnh viễn có chốt kiểm soát | `librarian` thử xóa vĩnh viễn; rồi `admin` thử | `librarian`: 403. `admin`: có **xác nhận hai bước** rồi mới xóa, có ghi audit | E2E | |
| KT-RV-11 | `/luoc-do` dùng dữ liệu thật | Mở `/luoc-do` | Hiện lược đồ từ `/api/v2/schemas`; **không còn dữ liệu mẫu** | E2E | |
| KT-RV-12 | **Cán bộ thật duyệt được** | Cán bộ duyệt ≥ 20 tài liệu thật trên trang mới | Xác nhận nhanh hơn hoặc bằng cách cũ; ghi lại nhận xét cải tiến | CN | |

---

## 10. KT-TB — Thông báo & cảnh báo *(V8)*

| Mã | Trường hợp kiểm thử | Các bước | Tiêu chí đạt | Loại | Trạng thái |
|---|---|---|---|---|---|
| KT-TB-01 | Cảnh báo không còn worker | Tắt toàn bộ worker > ngưỡng | Cảnh báo gửi qua kênh đã cấu hình, nội dung tiếng Việt nói rõ sự cố | TH | |
| KT-TB-02 | Cảnh báo mất Redis/PostgreSQL | Tắt Redis | Có cảnh báo; khi Redis trở lại có thông báo đã khắc phục | TH | |
| KT-TB-03 | Cảnh báo đĩa thấp | Giả lập đĩa dưới ngưỡng | Có cảnh báo trước khi hệ thống từ chối nhận tài liệu | TH | |
| KT-TB-04 | **Chống spam cảnh báo** | Duy trì sự cố 30 phút | **Không** gửi mỗi phút; gộp theo quy tắc đã cấu hình; có thông báo khi khắc phục | TH | |
| KT-TB-05 | Cảnh báo lô xong | Chạy xong một lô | Người tạo lô nhận được thông báo, có số liệu tổng kết (xong/lỗi/bỏ qua) | TH | |
| KT-TB-06 | **Cảnh báo chạy khi ngắt Internet** | Ngắt Internet, dựng sự cố | Cảnh báo vẫn gửi được qua SMTP nội bộ / webhook nội mạng (YC-BM-02) | TC | |
| KT-TB-07 | Thêm kênh mới = một lớp | Viết một kênh giả (mock) | Thêm kênh **không phải sửa** lớp gọi (đúng mẫu YC-MP-08) | U | |
| KT-TB-08 | Tắt cảnh báo | `ALERTS_ENABLED=0` | Không gửi cảnh báo nào; hệ thống chạy bình thường | TH | |

---

## 11. KT-VH — Vận hành dài hạn *(V9)*

| Mã | Trường hợp kiểm thử | Các bước | Tiêu chí đạt | Loại | Trạng thái |
|---|---|---|---|---|---|
| KT-VH-01 | Sao lưu tự động chạy đúng lịch | Đợi qua một chu kỳ | Có tệp sao lưu mới; số bản giữ lại đúng `BACKUP_KEEP` | TC | |
| KT-VH-02 | **Khôi phục thử thành công** 🔴 | Khôi phục bản sao lưu vào DB tạm, đối chiếu số bản ghi từng bảng | Số bản ghi khớp 100%; ứng dụng chạy được trên DB khôi phục. *(Sao lưu chưa khôi phục thử thì chưa phải sao lưu)* | TC | |
| KT-VH-03 | Sao lưu gồm cả tệp tài liệu | Kiểm nội dung bản sao lưu | Có cả DB và thư mục tài liệu; khôi phục ra mở được PDF | TC | |
| KT-VH-04 | Dọn tệp trung gian | Tạo tệp trung gian quá hạn, chạy dọn | Tệp quá hạn mất; **PDF kết quả và tệp gốc còn nguyên** | TH | |
| KT-VH-05 | Purge cần phê duyệt | `librarian` thử purge; `admin` thử purge | `librarian`: 403. `admin`: có xác nhận + ghi audit + `audit_log` **vẫn giữ** lịch sử tài liệu đã purge | TH | |
| KT-VH-06 | CI chạy tự động | Đẩy một commit | GitHub Actions chạy `pytest` + `npm run build`; hỏng test thì báo đỏ | TH | |
| KT-VH-07 | E2E 5 luồng chính | Chạy bộ Playwright | 5/5 luồng đạt: đăng nhập, nạp, duyệt, đẩy DSpace, xem báo cáo | E2E | |
| KT-VH-08 | E2E bắt được lỗi tải tệp | Tái hiện lỗi `Content-Length` rỗng (commit `3663eaf`) | Bộ E2E **phát hiện được** lỗi này nếu tái xuất hiện | E2E | |
| KT-VH-09 | Trang trợ giúp theo vai trò | Đăng nhập từng vai trò, mở `/tro-giup` | Nội dung tiếng Việt phù hợp vai trò | E2E | |
| KT-VH-10 | **Người thứ hai tiếp quản được** | Kỹ sư chưa từng làm dự án đọc tài liệu và triển khai từ đầu | Triển khai thành công **không cần hỏi** người viết mã (YC-VH-01/02) | CN | |

---

## 12. KT-TK — Tích hợp & tài khoản dịch vụ *(V9)*

| Mã | Trường hợp kiểm thử | Các bước | Tiêu chí đạt | Loại | Trạng thái |
|---|---|---|---|---|---|
| KT-TK-01 | API key băm khi lưu | Tạo key, truy vấn bảng `api_keys` | DB **không** chứa key dạng thô; key hiện **đúng một lần** khi tạo | TH | |
| KT-TK-02 | Thu hồi key có hiệu lực ngay | Thu hồi key đang dùng | Request kế tiếp bằng key đó trả 401 | TH | |
| KT-TK-03 | Phạm vi quyền của key | Key chỉ có quyền nạp tài liệu, thử gọi API xóa | 403; có ghi `user_activity` | TH | |
| KT-TK-04 | Key hết hạn | Đặt key hết hạn hôm qua | 401 kèm lý do "khóa đã hết hạn" | TH | |
| KT-TK-05 | Webhook khi lô xong | Đăng ký webhook nội mạng, chạy một lô | Nhận được gọi lại, nội dung đủ thông tin lô | TH | |
| KT-TK-06 | Giới hạn tần suất | Gọi vượt ngưỡng | 429 kèm thông báo khi nào gọi lại được | TH | |

---

## 13. KT-KH — Không hồi quy *(bắt buộc mỗi sprint)*

> **Đây là nhóm quan trọng nhất về mặt rủi ro.** Hệ thống đang phục vụ người dùng thật. Một sprint
> làm hỏng chức năng đang chạy là thất bại, dù tính năng mới có tốt đến đâu.
> Chạy **trước khi** coi sprint là xong, không phải sau.

| Mã | Sprint | Trường hợp kiểm thử | Tiêu chí đạt | Trạng thái |
|---|---|---|---|---|
| KT-KH-05 | V1 | Log mới không đổi hành vi nghiệp vụ | Xử lý trọn 1 tài liệu (nạp → OCR → trích xuất → sửa → đẩy DSpace) cho kết quả **giống hệt** trước V1; 224 pytest cũ vẫn đạt | |
| KT-KH-06 | V2 | Lớp provider không hồi quy | Toàn bộ test provider hiện có đạt; trích xuất Dublin Core cho **cùng kết quả** trên BD-02; `/bao-cao` và `/cong-cu` hiển thị đúng như trước | |
| KT-KH-07 | V3 | Phân quyền ở `AUTH_MODE=off` không đổi gì | Mọi endpoint cũ, mọi trang cũ hành xử **y hệt** trước V3; UI build exit 0; SSE hoạt động | |
| KT-KH-08 | V5, V6 | Đường nạp và hàng đợi cũ còn dùng được | `/api/v1/process` + `/api/v2/batch-upload` giữ nguyên định dạng phản hồi; `QUEUE_MODE=blpop` chạy đúng như trước | |
| KT-KH-09 | V7, V8, V9 | Trang cũ không bị ảnh hưởng | `/`, `/bao-cao`, `/cong-cu`, `/luoc-do` chạy đúng; số liệu **không vênh** với bảng điều khiển mới | |

**Kịch bản hồi quy chuẩn (chạy cho mọi `KT-KH-xx`):**

```bash
# 1. Kiểm thử tự động
python -m pytest tests/ -q                  # phải không kém số test đạt trước sprint
cd ui && npm run build                      # thoát mã 0

# 2. Luồng nghiệp vụ đầu-cuối trên BD-02 (thủ công, 1 tài liệu)
#    Nạp → theo dõi SSE → OCR xong → metadata có → sửa 1 trường → tải ZIP → đẩy DSpace
#    Đối chiếu: metadata giống kết quả cũ đã được cán bộ duyệt

# 3. Kiểm tra dữ liệu cũ nguyên vẹn (sau mỗi migration)
SELECT COUNT(*) FROM documents;      -- so với số trước migration
SELECT COUNT(*) FROM audit_log;
SELECT COUNT(*) FROM metadata_fields;
SELECT COUNT(*) FROM model_calls;

# 4. Van lùi: đặt cờ về giá trị cũ → xác nhận hành vi cũ trở lại
```

---

## 14. KT-BM — Bảo mật cho tính năng mới *(nối tiếp KT-BM-15 của kế hoạch gốc)*

> Nhóm ưu tiên **cao nhất** theo nguyên tắc 6 — lỗi ở đây không sửa được sau khi đã xảy ra.

| Mã | Trường hợp kiểm thử | Các bước | Tiêu chí đạt | Loại | Trạng thái |
|---|---|---|---|---|---|
| KT-BM-16 | Tính năng mới chạy khi ngắt Internet | Ngắt Internet, thử: đăng nhập, nạp lô, duyệt, xem bảng điều khiển, nhận cảnh báo | **Tất cả hoạt động.** Không thành phần mới nào cần Internet (YC-BM-02) | TC | |
| KT-BM-17 | Không lộ bí mật trong log & API | Grep toàn bộ tệp log + phản hồi API tìm: khóa API, mật khẩu, hash mật khẩu, token phiên, API key | **0 kết quả** (YC-BM-03) | TH | |
| KT-BM-18 | Chống IDOR trên endpoint mới | Đăng nhập người dùng A, truy cập tài nguyên của B bằng id trực tiếp | Trả **404, không phải 403** (không tiết lộ sự tồn tại); có ghi `user_activity` | TH | |
| KT-BM-19 | Tài liệu nhạy cảm vẫn không ra đám mây | Nạp lô có tài liệu nhóm "Nhạy cảm" (BD-05) qua đường nạp **mới** | Ràng buộc cứng YC-DR-03 vẫn hiệu lực trên đường nạp mới; có bản ghi từ chối | TH | |
| KT-BM-20 | **Chống `zip-slip`** | Nạp ZIP chứa mục `../../etc/passwd` (BD-08) | Bị từ chối; **không tệp nào** được ghi ngoài thư mục đích; có ghi nhật ký | U | |
| KT-BM-21 | Kênh cảnh báo không rò dữ liệu ra ngoài | Kiểm cấu hình cảnh báo + giám sát lưu lượng khi gửi | Chỉ gửi tới đích nội mạng đã cấu hình; **nội dung cảnh báo không chứa nội dung tài liệu** | TC | |

---

## 15. KT-HN — Hiệu năng khối lượng lớn *(nối tiếp KT-HN-07)*

> **Không đặt ngưỡng trước khi đo** (YC-PC-02/03). Các ô "Tiêu chí đạt" dưới đây định nghĩa
> *phải đo được cái gì*, không định nghĩa *phải đạt con số nào*. Con số điền sau khi đo thật.

| Mã | Trường hợp kiểm thử | Các bước | Tiêu chí đạt | Loại | Trạng thái |
|---|---|---|---|---|---|
| KT-HN-08 | Thông lượng nạp | Nạp 500 tệp BD-06, đo thời gian từ lúc bấm tới khi tệp cuối vào hàng đợi | Ghi: thời gian, MB/s, phần cứng, **cỡ mẫu 500**. API vẫn phản hồi trong suốt quá trình | TH | |
| KT-HN-09 | Thông lượng xử lý theo số worker | Chạy hết BD-06 với 1, 2, 3 worker | Bảng: worker → tài liệu/giờ, CPU, RAM. **Thay bảng ước lượng trong `docker-compose.yml:161`** bằng số đo thật | TH | |
| KT-HN-10 | Chạy dài không rò rỉ bộ nhớ | Chạy liên tục 8 giờ | RAM worker không tăng đơn điệu; không container nào bị OOM | TH | |
| KT-HN-11 | Bảng điều khiển với dữ liệu lớn | 100.000 tài liệu, 1 triệu dòng `user_activity` | Ghi thời gian tải từng thẻ kèm cỡ mẫu; xác định có cần bật `daily_metrics` không | TH | |

---

## 16. Ma trận truy vết YC ↔ KT ↔ Sprint

> Nguyên tắc của kế hoạch kiểm thử gốc: **mỗi yêu cầu phải có ít nhất một trường hợp kiểm thử.**
> Bảng này để kiểm tra không yêu cầu nào bị bỏ sót.

| Yêu cầu | Kiểm thử | Sprint |
|---|---|---|
| YC-LG-01, 02, 03 | KT-LG-01, 02, 03, 04 | V1 |
| YC-LG-04 | KT-LG-06 | V1 |
| YC-LG-05 | KT-LG-05, KT-BM-17 | V1 |
| YC-LG-06 | KT-LG-07 | V1 |
| YC-LG-07 | KT-LG-08, KT-NK-11, KT-VH-04 | V1, V4, V9 |
| YC-LG-08 | KT-LG-09, KT-LG-10 | V1 |
| YC-LG-09 | KT-LG-11 | V1 |
| YC-LG-10, 11 | KT-LG-12 *(van lùi)*, kiểm thủ công `/metrics` | V1 |
| YC-AN-01 | KT-AN-02, KT-AN-03 | V2 |
| YC-AN-02 | KT-AN-04 | V2 |
| YC-AN-03 | KT-AN-05 | V2 |
| YC-AN-04 | KT-AN-10 | V2 |
| YC-AN-05 | KT-AN-06, 07, 08, 09 | V2 |
| YC-AN-06 | KT-AN-13 | V2 |
| YC-AN-07 | KT-AN-11 | V2 |
| YC-AN-08 | KT-AN-13 | V2 |
| YC-AN-09 | KT-AN-13 | V2 |
| YC-AN-10 | KT-AN-14 | V2 |
| YC-AN-11 | KT-AN-12 | V2 |
| YC-QT-01 | KT-QT-01, KT-QT-02 | V3 |
| YC-QT-02 | KT-QT-03, 04, 05 | V3 |
| YC-QT-03 | KT-QT-06, 07, 08, 09 | V3 |
| YC-QT-04 | KT-QT-13, 14, 15, 16 | V3 |
| YC-QT-05 | KT-QT-11 | V3 |
| YC-QT-06 | KT-QT-10 | V3 |
| YC-QT-07 | KT-QT-11, KT-QT-17 | V3 |
| YC-QT-08 | KT-QT-18 | V3 |
| YC-QT-09, 10 | KT-QT-07, KT-TB-07 *(mẫu cắm được)* | V3 |
| YC-QT-11 | KT-NK-05, KT-NK-06 | V3, V4 |
| YC-NK-01 | KT-NK-01 | V4 |
| YC-NK-02 | KT-NK-02 | V4 |
| YC-NK-03 | KT-NK-03, KT-QT-06 | V4 |
| YC-NK-04 | KT-NK-04 | V4 |
| YC-NK-05 | KT-NK-07 | V4 |
| YC-NK-06 | KT-NK-08 | V4 |
| YC-NK-07 | KT-NK-09 | V4 |
| YC-NK-08 | KT-NK-10 | V4 |
| YC-NK-09 | KT-NK-11 | V4 |
| YC-BU-01 | KT-BU-01, KT-HN-08 | V5 |
| YC-BU-02 | KT-BU-02, KT-BU-03 | V5 |
| YC-BU-03 | KT-BU-02, KT-DB-04 | V5, V7 |
| YC-BU-04 | KT-BU-04, KT-BU-05 | V5 |
| YC-BU-05 | KT-BU-09 | V5 |
| YC-BU-06 | KT-BU-11 | V5 |
| YC-BU-07 | KT-BU-10, KT-BM-20 | V5 |
| YC-BU-08 | *(cần bổ sung khi làm)* | V5 |
| YC-BU-09 | KT-BU-06, 07, 08 | V5 |
| YC-BU-10 | *(profile tùy chọn — kiểm thủ công)* | V5 |
| YC-BU-11 | **KT-BU-15** | V6 |
| YC-BU-12 | KT-BU-16, KT-BU-17 | V6 |
| YC-BU-13 | KT-BU-19, 20, 21 | V6 |
| YC-BU-14 | KT-BU-22 | V6 |
| YC-BU-15 | KT-BU-23 | V6 |
| YC-BU-16 | KT-BU-24 | V6 |
| YC-BU-17 | KT-BU-25 | V6 |
| YC-BU-18 | KT-DB-04, KT-DB-06 | V6, V7 |
| YC-BU-19 | KT-BU-26 | V6 |
| YC-BU-20 | KT-HN-09 | V6 |
| YC-DB-01 | KT-DB-01 | V7 |
| YC-DB-02 | KT-DB-02, KT-DB-03 | V7 |
| YC-DB-03 | KT-DB-04 | V7 |
| YC-DB-04 | KT-DB-05 | V7 |
| YC-DB-05 | KT-DB-08 | V7 |
| YC-DB-06 | KT-DB-07 | V7 |
| YC-DB-07 | KT-DB-09 | V7 |
| YC-DB-08 | KT-DB-10 | V7 |
| YC-DB-09 | KT-DB-11, KT-HN-11 | V7 |
| YC-DB-10 | *(kiểm thủ công trên màn hình lớn)* | V7 |
| YC-RV-01 | KT-RV-01 | V8 |
| YC-RV-02 | KT-RV-02, KT-RV-03 | V8 |
| YC-RV-03 | KT-RV-04 | V8 |
| YC-RV-04 | KT-RV-05, 06, 07 | V8 |
| YC-RV-05 | KT-RV-09, KT-RV-10 | V8 |
| YC-RV-06 | KT-RV-08 | V8 |
| YC-RV-07 | KT-DB-01 | V8 |
| YC-RV-08 | KT-RV-11 | V8 |
| YC-TB-01 | KT-TB-07 | V8 |
| YC-TB-02 | KT-TB-01, 02, 03 | V8 |
| YC-TB-03 | KT-TB-05 | V8 |
| YC-TB-04 | KT-TB-04 | V8 |
| YC-TB-05 | *(cần bổ sung khi làm)* | V8 |
| YC-TB-06 | KT-TB-06, KT-BM-21 | V8 |
| YC-VH-07 | KT-VH-01, KT-VH-03 | V9 |
| YC-VH-08 | KT-VH-02 | V9 |
| YC-VH-09 | KT-VH-04, KT-VH-05 | V9 |
| YC-VH-10 | KT-VH-06 | V9 |
| YC-VH-11 | KT-VH-07, KT-VH-08 | V9 |
| YC-VH-12 | KT-VH-09 | V9 |
| YC-TK-01 | KT-TK-01, KT-TK-02, KT-TK-04 | V9 |
| YC-TK-02 | KT-TK-03 | V9 |
| YC-TK-03 | KT-TK-05 | V9 |
| YC-TK-04 | KT-TK-06 | V9 |
| YC-TK-05 | *(rà tài liệu)* | V9 |

**Kiểm tra độ phủ:** 78 yêu cầu · 74 có kiểm thử cụ thể · 4 ghi rõ *"cần bổ sung khi làm"* hoặc
*"kiểm thủ công"* — phải điền trước khi bắt đầu sprint tương ứng, theo đúng nguyên tắc *mỗi yêu cầu
có ít nhất một trường hợp kiểm thử*.

---

## 17. Cổng nghiệm thu theo sprint

Sprint chỉ được coi là xong khi **tất cả** kiểm thử của nó đạt. Ô "Kết quả" điền bằng số thật khi chạy.

| Sprint | Kiểm thử bắt buộc | Kiểm thử ưu tiên cao 🔴 | Kết quả |
|---|---|---|---|
| V1 | KT-LG-01→12, KT-KH-05 | KT-LG-05 *(che bí mật)* | ___/13 |
| V2 | KT-AN-01→14, KT-KH-06 | KT-AN-01 *(migration an toàn)*, KT-AN-06 *(cỡ mẫu)* | ___/15 |
| V3 | KT-QT-01→18, KT-BM-16→18, KT-KH-07 | KT-QT-06, KT-QT-09, KT-QT-16 *(van lùi)* | ___/22 |
| V4 | KT-NK-01→11 | KT-NK-01 *(bất biến)*, KT-NK-06 | ___/11 |
| V5 | KT-BU-01→14, KT-BM-19, KT-BM-20, KT-HN-08, KT-KH-08 | KT-BU-01 *(sửa N-03)*, KT-BM-20 *(zip-slip)* | ___/18 |
| V6 | KT-BU-15→26, KT-HN-09, KT-HN-10 | **KT-BU-15** *(sửa N-02 — không mất dữ liệu)* | ___/14 |
| V7 | KT-DB-01→13, KT-HN-11 | KT-DB-02 *(số không vênh)*, KT-DB-13 *(chấp nhận)* | ___/14 |
| V8 | KT-RV-01→12, KT-TB-01→08, KT-BM-21 | KT-RV-06 *(chưa duyệt không đẩy)*, KT-RV-12 *(chấp nhận)* | ___/21 |
| V9 | KT-VH-01→10, KT-TK-01→06, KT-KH-09 | KT-VH-02 *(khôi phục thử)*, KT-VH-10 *(bàn giao)* | ___/17 |

---

## 18. Kiểm thử chấp nhận — do cán bộ sử dụng thật

> Nguyên tắc 5: *"Đội tự nghiệm thu sản phẩm của mình là kiểm thử không có giá trị."*

| Mã | Nội dung | Người thực hiện | Điều kiện đạt |
|---|---|---|---|
| KT-DB-13 | Dùng bảng điều khiển trong việc thật 1 tuần | Cán bộ Trung tâm | Trả lời được "hôm nay tôi phải làm gì" mà không cần hỏi ai |
| KT-RV-12 | Duyệt ≥ 20 tài liệu thật trên trang `/duyet` | Cán bộ nghiệp vụ | Không chậm hơn cách cũ; ghi lại nhận xét cải tiến |
| KT-QT-17 | Quản trị viên tự tạo và phân quyền tài khoản mới | Quản trị viên (không phải lập trình viên) | Làm được **không cần lập trình viên hỗ trợ** |
| KT-VH-10 | Kỹ sư chưa từng làm dự án triển khai từ đầu | Người thứ hai (YC-VH-02) | Triển khai thành công chỉ bằng tài liệu |
| KT-BU-02 | Nạp lô 500 tài liệu thật trong công việc | Cán bộ Trung tâm | Hoàn tất không cần trợ giúp kỹ thuật |

**Biên bản nghiệm thu phải ghi:** ai thực hiện · ngày · số tài liệu/thao tác thực tế · vướng mắc gặp
phải · kết luận đạt/không đạt · chữ ký. Không có biên bản thì kiểm thử chấp nhận coi như chưa chạy.
