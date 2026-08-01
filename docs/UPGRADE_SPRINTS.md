# DocuFlow HP — Kế hoạch Sprint đợt nâng cấp (V0–V9)

> **Đây là phần CÁCH LÀM.** Yêu cầu (cái gì / vì sao): `docs/UPGRADE_REQUIREMENTS.md`.
> Kiểm thử: `docs/UPGRADE_TEST_CASES.md`. Lộ trình tổng: `docs/ROADMAP.md`.
>
> **Lập ngày:** 31/07/2026 · **Trạng thái:** đề xuất, chưa sprint nào bắt đầu.

---

## 0. Nguyên tắc chia sprint

Bốn ràng buộc quyết định cách chia dưới đây:

1. **Làm đến đâu dùng được đến đó.** Mỗi sprint kết thúc bằng một thứ cán bộ *mở ra dùng được*, không
   phải "hạ tầng đã sẵn sàng cho sprint sau". Nếu dự án dừng sau sprint bất kỳ, phần đã làm vẫn có giá trị.
2. **Không phá hệ đang chạy.** Hệ thống đang phục vụ thật. Mỗi sprint có bộ kiểm thử không hồi quy
   `KT-KH` phải chạy đạt **trước khi** coi là xong — không phải sau.
3. **Van lùi cho mọi thay đổi hành vi.** Đổi một biến môi trường là quay về hành vi cũ,
   **không cần build lại image**. Đây là mẫu đã dùng thành công ở ADR-008 (`USE_PROVIDER_LAYER`).
4. **Migration chỉ cộng, không trừ.** Chỉ `ADD COLUMN` / `CREATE TABLE`. Không `DROP`, không `ALTER TYPE`,
   không đổi tên. Chạy nhiều lần không lỗi. **Bắt buộc `pg_dump` trước mỗi lần chạy.**

### Định nghĩa "Hoàn thành" — áp dụng cho MỌI sprint

Một sprint chỉ được coi là xong khi **tất cả** các ô dưới đây được tích, có bằng chứng:

- [ ] Toàn bộ `KT-*` của sprint **đã chạy và đạt** — ghi kết quả thật, không ghi kỳ vọng
- [ ] `KT-KH` (không hồi quy) của sprint đạt: endpoint cũ, trang cũ, luồng số hóa vẫn chạy
- [ ] `python -m pytest tests/ -q` — không test nào hỏng so với trước sprint
- [ ] `cd ui && npm run build` — thoát mã 0
- [ ] Migration chạy được **hai lần liên tiếp** trên bản sao dữ liệu thật, không lỗi, dữ liệu cũ nguyên vẹn
- [ ] Van lùi đã **thử thật**: bật cờ về giá trị cũ → hành vi cũ trở lại
- [ ] Tài liệu cập nhật: `docs/PLAN.md`, `docs/STATUS.md`; ADR mới nếu có quyết định kiến trúc
- [ ] Mọi số hiệu năng có kèm **cỡ mẫu + phần cứng + ngày đo**
- [ ] Thông báo lỗi cho người dùng bằng **tiếng Việt có dấu**, đủ cụ thể để biết phải làm gì

---

## 1. Tổng quan — thứ tự và lý do

```
V0  Chuẩn bị           ██                       (2 ngày)   không code
V1  Nền log            ████                     (1 tuần)   độc lập
V2  Phân tích AI       ██████                   (1,5 tuần) cần V1 (request_id)
V3  Phân quyền         ████████                 (2 tuần)   ⚠️ rủi ro cao nhất
V4  Nhật ký người dùng ████                     (1 tuần)   cần V3 (danh tính)
V5  Nạp khối lượng lớn ██████                   (1,5 tuần) cần V3 (uploaded_by)
V6  Hàng đợi tin cậy   ██████                   (1,5 tuần) cần V5 (lô)
V7  Bảng điều khiển    ██████                   (1,5 tuần) cần V3+V5 (ai/lô nào)
V8  Duyệt + Cảnh báo   ██████                   (1,5 tuần) cần V3 (actor)
V9  Vận hành dài hạn   ████                     (1 tuần)   độc lập
                                        Tổng ≈ 13 tuần
```

### Vì sao thứ tự này, không phải thứ tự 1→4 bạn liệt kê

| Bạn xếp | Tôi xếp | Lý do đổi |
|---|---|---|
| 1. Log + AI analytics | **V1, V2** — giữ nguyên đầu tiên | Đúng: rẻ nhất, rủi ro thấp nhất, độc lập, và tạo nền `request_id` cho mọi sprint sau |
| 2. Khối lượng lớn | **V5, V6** — lùi xuống | Cần `uploaded_by` từ V3, và cần lô mới theo dõi được trên bảng điều khiển V7 |
| 3. Dashboard | **V7** — lùi xuống | "Theo dõi công việc" cần biết *việc của ai* (V3) và *lô nào* (V5) mới có nội dung thật |
| 4. Phân quyền | **V3** — đẩy lên | Ba lý do: (a) là **lỗ hổng bảo mật** đang tồn tại, không phải tính năng; (b) mở nút cho `YC-DR-04` — yêu cầu **BB của GĐ1**; (c) mọi nhật ký làm trước khi có danh tính đều phải sửa lại |

> **Điểm mấu chốt:** nếu làm dashboard (V7) trước phân quyền (V3), toàn bộ phần "việc của tôi",
> "năng suất theo cán bộ", "phân công" phải viết lại. Đó là làm hai lần cùng một việc.

### Xung đột lịch với lộ trình gốc — cần quyết định

`ROADMAP.md` đặt **GĐ1 tháng 8–9** (mốc Bán kết T9) và **GĐ2 tháng 10–11** (mốc Chung kết T11).
Đợt nâng cấp này chiếm 13 tuần trong cùng khoảng đó. Ba lựa chọn:

| Phương án | Nội dung | Đánh giá |
|---|---|---|
| **A. Chạy nối tiếp** | Xong GĐ1 rồi mới nâng cấp | An toàn nhưng V3 nằm sau Bán kết, mà `YC-DR-04` của GĐ1 lại **cần** V3 → GĐ1 không nghiệm thu đủ được |
| **B. Chạy song song** | Hai luồng cùng lúc | Cần ≥ 2 người viết mã. `YC-VH-02` của SRS vốn đã yêu cầu ≥ 2 người hiểu mã |
| **C. Đan xen ✅** | V1→V3 trước Bán kết (chúng đóng khoảng trống của GĐ1); V4→V9 sau, trong khung GĐ2 | **Khuyến nghị.** V2 còn tạo số liệu dùng ngay cho hồ sơ Bán kết |

Lịch dưới đây theo **phương án C**.

| Sprint | Tuần | Ngày (dự kiến) | Mốc liên quan |
|---|---|---|---|
| V0 | — | 03–04/8/2026 | |
| V1 | 1 | 05–11/8 | |
| V2 | 2–3 | 12–25/8 | Số liệu AI dùng cho hồ sơ Bán kết |
| V3 | 4–5 | 26/8–08/9 | Đóng `YC-DR-04` của GĐ1 |
| — | 6 | 09–15/9 | `AUTH_MODE=shadow` chạy quan sát · **Bán kết T9** |
| V4 | 7 | 16–22/9 | Bật `AUTH_MODE=on` |
| V5 | 8–9 | 23/9–06/10 | |
| V6 | 10–11 | 07–20/10 | |
| V7 | 12–13 | 21/10–03/11 | Dùng cho hồ sơ Chung kết |
| V8 | 14–15 | 04–17/11 | **Chung kết T11** |
| V9 | 16 | 18–24/11 | |

---

## V0 — Chuẩn bị *(2 ngày, không viết mã)*

**Vì sao có sprint này:** bốn việc dưới đây nếu bỏ qua sẽ làm hỏng các sprint sau, và cả bốn đều
không phải việc lập trình.

| # | Việc | Ai | Kết quả |
|---|---|---|---|
| 1 | Chốt 8 quyết định `QĐ-01`→`QĐ-08` (mục 12 của `UPGRADE_REQUIREMENTS.md`) | 👤 người phụ trách + 🤖 tư vấn | Biên bản chốt |
| 2 | Viết ADR-010→016 vào `docs/DECISIONS.md` cho các quyết định đã chốt | 🤖 | ADR có trong repo **trước khi** viết mã (theo quy ước dự án) |
| 3 | `pg_dump` dữ liệu thật + **khôi phục thử vào DB tạm** để chắc bản sao dùng được | 👤 | Bản sao đã kiểm chứng, không phải chỉ có tệp |
| 4 | Chuẩn bị bộ dữ liệu kiểm thử mới **BD-06/07/08** (xem `UPGRADE_TEST_CASES.md` mục 2) | 👤 | 500 PDF cho kiểm thử tải, danh sách tài khoản mẫu, tệp hỏng/trùng |

> ⚠️ **Việc 3 là điều kiện bắt buộc.** Từ V2 trở đi mỗi sprint đều có migration trên dữ liệu thật.
> Bản sao lưu chưa từng khôi phục thử thì chưa phải là bản sao lưu.

---

## V1 — Nền log có cấu trúc *(1 tuần)*

> **Sau sprint này dùng được gì:** quản trị viên mở `/nhat-ky-he-thong` trên trình duyệt, lọc log 24h
> qua, dán một `request_id` vào ô tìm kiếm và thấy toàn bộ chuỗi xử lý của request đó — thay vì SSH
> vào máy chủ chạy `docker compose logs | grep`.

**Yêu cầu:** `YC-LG-01` → `YC-LG-11` · **Kiểm thử:** `KT-LG-01` → `KT-LG-12`, `KT-KH-05`

### Việc

| # | Việc | Tệp | Ghi chú |
|---|---|---|---|
| 1 | `JsonFormatter` + `SecretRedactionFilter` + handler luân chuyển tệp | `scripts/core/logging_setup.py` *(mới)* | Bộ lọc che bí mật là **bắt buộc**, không tùy chọn — YC-BM-03 |
| 2 | `contextvars` cho `request_id` / `job_id` / `actor` | `scripts/core/context.py` *(mới)* | Một chỗ duy nhất; V3 sẽ điền `actor` thật vào đây mà không sửa nơi khác |
| 3 | Middleware sinh `request_id`, ghi dòng tổng kết, trả header `X-Request-Id` | `scripts/middleware/request_log.py` *(mới)* + `api.py` | Nhận `X-Request-Id` từ ngoài nếu có (để lần qua proxy Next) |
| 4 | Worker đặt `job_id` vào context suốt vòng đời một tài liệu | `scripts/worker.py` | Bọc quanh `process_job` |
| 5 | Chuyển proxy Next chuyển tiếp `X-Request-Id` | `ui/src/app/api/**/route.js` | Nối được log trình duyệt ↔ log API |
| 6 | Module dọn theo tuổi: tệp log, `system_events`, (sau này `user_activity`) | `scripts/core/retention.py` *(mới)* | **Trả nợ kỹ thuật đã ghi trong `PLAN.md`** |
| 7 | `GET /api/v2/logs` — lọc theo thời gian/mức/`request_id`/`job_id`/từ khóa, phân trang | `scripts/api.py` | Envelope HPU. Đọc ngược tệp JSONL, giới hạn cứng số dòng quét |
| 8 | Trang `/nhat-ky-he-thong` | `ui/src/app/nhat-ky-he-thong/page.jsx` *(mới)* | Gộp log ứng dụng + `system_events`; nút tải xuống đoạn đang xem |
| 9 | `GET /metrics` định dạng Prometheus | `scripts/api.py` | `YC-LG-11`, làm nếu còn thời gian |
| 10 | Cập nhật `.env.example` + `docs/DEPLOY.md` mục nhật ký | | Ghi rõ thư mục log cần gắn volume |

### Van lùi
`LOG_FORMAT=text` → về đúng định dạng log hiện tại. `LOG_TO_FILE=0` → chỉ ghi stdout như cũ.

### Rủi ro
| Rủi ro | Xử lý |
|---|---|
| Ghi tệp log làm đầy đĩa | Luân chuyển theo kích thước + `LOG_ROTATE_KEEP` + dọn theo tuổi ngay trong sprint này |
| API đọc log quét tệp lớn gây chậm | Giới hạn cứng số dòng quét (`LOG_SCAN_MAX_LINES`), đọc ngược từ cuối tệp, luôn có phân trang |
| Bộ lọc che bí mật bỏ sót mẫu mới | Kiểm thử `KT-LG-05` liệt kê từng mẫu; thêm mẫu là thêm một dòng cấu hình |

---

## V2 — Phân tích chi tiết kết quả AI *(1,5 tuần)*

> **Sau sprint này dùng được gì:** trang `/phan-tich-ai` trả lời được — *"Claude đúng bao nhiêu % trên
> trường `dc.title` trong 30 ngày qua, trên bao nhiêu mẫu?"*, *"tháng này tốn bao nhiêu tiền API?"*,
> *"tài liệu nào scan xấu cần quét lại?"*. Số liệu **tự tích lũy từ việc thật**, không cần chạy harness.

**Yêu cầu:** `YC-AN-01` → `YC-AN-11` · **Kiểm thử:** `KT-AN-01` → `KT-AN-14`, `KT-KH-06`

### Việc

| # | Việc | Tệp | Ghi chú |
|---|---|---|---|
| 1 | Migration 003: mở rộng `model_calls` + tạo `model_call_fields`, `ocr_runs` | `database/migrations/003_ai_analytics.sql` *(mới)* + `database/init.sql` | **Chỉ ADD COLUMN / CREATE TABLE.** Cập nhật cả `init.sql` để cài mới cũng đúng |
| 2 | Provider trả về số token khi công cụ có báo cáo | `scripts/providers/base.py` (mở rộng kiểu trả về), `openai_compat.py`, `cloud.py`, `gemini.py` | ⚠️ **KHÔNG sửa hợp đồng `_complete`** — thêm trường tùy chọn, công cụ không báo token thì để `NULL` |
| 3 | Bảng đơn giá + tính chi phí (số nguyên micro-USD và **số nguyên VNĐ**) | `scripts/core/pricing.py` *(mới)* | Đơn giá trong tệp cấu hình, không mã cứng; tại chỗ = 0 |
| 4 | Ghi `model_call_fields` khi trích xuất | `scripts/core/extraction.py` | Bọc `try/except` — theo đúng mẫu `extraction.py:255`, lỗi truy vết **không được** làm hỏng số hóa |
| 5 | Thu chỉ số OCR và ghi `ocr_runs` | `scripts/digitize.py`, `scripts/worker.py` | Lấy từ đầu ra OCRmyPDF + `pypdf`; `pages_without_text` là chỉ báo scan xấu |
| 6 | Đối chiếu độ chính xác trên việc thật (`YC-AN-05`) | `scripts/core/analytics.py` *(mới)* | So `model_call_fields.value_preview` với `metadata_fields.value` hiện tại; chuẩn hóa khoảng trắng + ngày **đúng công thức mục 1.3 kế hoạch kiểm thử** |
| 7 | Endpoint: `/api/v2/analytics/ai/{accuracy,cost,providers,fields,ocr-quality}` | `scripts/api.py` | Envelope HPU. **Bắt buộc trả kèm `sample_size`** trong mọi phản hồi có % |
| 8 | Xuất Excel | `scripts/core/export_excel.py` *(mới)* | `openpyxl`; UTF-8; ngày `DD/MM/YYYY`; tiền `N.NNN.NNN đ` |
| 9 | Trang `/phan-tich-ai` | `ui/src/app/phan-tich-ai/page.jsx` *(mới)* | **Dưới 30 mẫu: hiện "chưa đủ dữ liệu", KHÔNG hiện %** |
| 10 | Phát hiện suy giảm chất lượng (`YC-AN-08`) | `scripts/core/analytics.py` | So 7 ngày với 30 ngày trước; ghi `system_events` mức `warning` |

### Ràng buộc bắt buộc

> **Mọi tỉ lệ % phải đi kèm cỡ mẫu, trên giao diện và trong API.** Trang phải ghi rõ phương pháp:
> *"Đối chiếu với giá trị cán bộ đã duyệt — chỉ báo xu hướng, không thay thế đối chiếu đáp án chuẩn
> BD-01."* Đây là ràng buộc của nguyên tắc SRS "đo được mới tuyên bố", không phải tùy chọn hiển thị.

### Van lùi
`AI_ANALYTICS_DETAIL=0` → không ghi `model_call_fields`/`ocr_runs`, hệ thống chạy đúng như trước.
`AI_LOG_RAW` mặc định `0` — không lưu prompt/phản hồi thô.

### Rủi ro
| Rủi ro | Xử lý |
|---|---|
| `model_call_fields` phình nhanh (11 dòng/tài liệu) | 500 tài liệu/ngày ≈ 5.500 dòng/ngày — chấp nhận được; `value_preview` cắt ngắn (mặc định 200 ký tự); có thời hạn lưu |
| Sửa lớp provider làm hồi quy đường Claude | `KT-KH-06` chạy nguyên bộ test provider hiện có (95 test mock) trước khi merge |
| Số liệu độ chính xác bị hiểu là đáp án chuẩn | Ghi chú phương pháp bắt buộc trên giao diện; ngưỡng cỡ mẫu tối thiểu |

---

## V3 — Danh tính & phân quyền ⚠️ *(2 tuần — sprint rủi ro cao nhất)*

> **Sau sprint này dùng được gì:** cán bộ có tài khoản riêng, đăng nhập bằng tài khoản đó, và
> `audit_log` ghi **tên thật** thay vì `'api'`. Quản trị viên tạo/khóa tài khoản trên giao diện.
> Hệ thống **vẫn chạy y như cũ** cho tới khi chủ động bật nấc chặn.

**Yêu cầu:** `YC-QT-01` → `YC-QT-12` · **Kiểm thử:** `KT-QT-01` → `KT-QT-18`, `KT-BM-16` → `KT-BM-19`, `KT-KH-07`

### Chia làm hai nửa

**Nửa đầu (tuần 1) — xây, không bật:**

| # | Việc | Tệp |
|---|---|---|
| 1 | Migration 004: `users`, `roles`, `role_permissions`, `user_sessions` + seed 4 vai trò | `database/migrations/004_users_rbac.sql` *(mới)* + `init.sql` |
| 2 | Băm & kiểm mật khẩu (`QĐ-04`), chính sách độ mạnh, khóa sau N lần sai | `scripts/core/passwords.py` *(mới)* |
| 3 | Interface xác thực cắm được + hiện thực `local` (`YC-QT-10`) | `scripts/auth/base.py`, `scripts/auth/local.py` *(mới)* |
| 4 | Quản lý phiên trong PostgreSQL (`QĐ-02`), thu hồi được | `scripts/auth/sessions.py` *(mới)* |
| 5 | `POST /api/v2/auth/{login,logout}`, `GET /api/v2/auth/me` | `scripts/api.py` |
| 6 | Dependency `require(permission)` — **cưỡng chế ở máy chủ** | `scripts/auth/deps.py` *(mới)* |
| 7 | Khởi tạo quản trị viên đầu tiên từ biến môi trường, bắt buộc đổi mật khẩu | `scripts/auth/bootstrap.py` *(mới)* |
| 8 | Lệnh CLI đặt lại mật khẩu quản trị (cứu hộ khi mất mật khẩu, có ghi audit) | `scripts/auth/cli.py` *(mới)* |

**Nửa sau (tuần 2) — gắn vào, chạy nấc `shadow`:**

| # | Việc | Tệp |
|---|---|---|
| 9 | Gắn `require(...)` vào **mọi** endpoint ghi; đọc theo vai trò | `scripts/api.py` |
| 10 | Xử lý ba nấc `AUTH_MODE=off\|shadow\|on` | `scripts/auth/deps.py` |
| 11 | Điền `actor` thật vào context V1 → `audit_log`/`model_calls` tự có tên thật | `scripts/core/context.py`, `scripts/core/audit.py` |
| 12 | Trang đăng nhập DocuFlow (**tách bạch** với đăng nhập DSpace hiện có) | `ui/src/app/dang-nhap/page.jsx` *(mới)* |
| 13 | Trang `/quan-tri/nguoi-dung` — tạo/sửa/khóa/đổi vai trò/đặt lại mật khẩu/xem phiên | `ui/src/app/quan-tri/nguoi-dung/page.jsx` *(mới)* |
| 14 | Sidebar hiện mục theo quyền; ẩn nút không có quyền (**tiện ích, không phải bảo vệ**) | `ui/src/components/hpu/HpuLayout.jsx` |
| 15 | Chuyển tiếp cookie phiên qua các route proxy Next | `ui/src/app/api/**/route.js` |

### Cảnh báo quan trọng về giao diện

`ui/src/components/LoginForm.jsx` hiện là **đăng nhập DSpace**, không phải đăng nhập DocuFlow.
Hai thứ khác nhau và phải giữ khác nhau — trộn vào một chỗ sẽ làm cán bộ nhầm mật khẩu nào dùng ở đâu.
Đặt tên rõ trên giao diện: *"Đăng nhập DocuFlow"* và *"Kết nối DSpace"*.

### Quy trình bật — ba nấc, không được rút gọn

```
Nấc 1  AUTH_MODE=off      Triển khai. Hành vi KHÔNG ĐỔI. Tạo tài khoản, tập huấn cán bộ.
Nấc 2  AUTH_MODE=shadow   Không chặn, nhưng ghi cảnh báo mỗi request thiếu xác thực,
                          kèm endpoint + IP + user-agent.
                          → Chạy ≥ 1 TUẦN. Đọc nhật ký, sửa hết chỗ còn sót.
                          → Điều kiện sang nấc 3: 0 cảnh báo trong 48 giờ liên tiếp.
Nấc 3  AUTH_MODE=on       Chặn thật. Lùi về `shadow` bất cứ lúc nào bằng một biến.
```

> **Không rút gọn nấc 2.** Không ai biết hết những chỗ đang gọi API: có thể có script cá nhân, luồng
> n8n, hay tab trình duyệt cán bộ mở từ tuần trước. Nấc `shadow` biến câu hỏi "còn sót chỗ nào?"
> từ phỏng đoán thành dữ liệu đọc được.

### Van lùi
`AUTH_MODE=off` → hệ thống hành xử đúng như trước sprint. Không cần build lại, không cần rollback DB
(bảng mới không ảnh hưởng đường cũ).

### Rủi ro
| Rủi ro | Xử lý |
|---|---|
| Bật chặn làm gián đoạn công việc thật | Ba nấc + điều kiện định lượng để chuyển nấc |
| Mất mật khẩu quản trị → khóa cả hệ thống | CLI cứu hộ (việc 8), tài liệu hóa trong `DEPLOY.md`, thao tác có ghi audit |
| Bỏ sót một endpoint ghi khi gắn `require(...)` | `KT-QT-09` **liệt kê tự động** mọi route POST/PUT/PATCH/DELETE và khẳng định từng route có dependency — test hỏng khi thêm endpoint mới mà quên gắn |
| Cookie không qua được proxy Next | `KT-QT-12` kiểm trên Next server thật, không chỉ trên FastAPI |

---

## V4 — Nhật ký người dùng *(1 tuần)*

> **Sau sprint này dùng được gì:** quản trị viên tra được *"cán bộ A hôm 15/9 đã làm gì"*, thấy các
> lần đăng nhập sai, và mở một tài liệu ra là thấy **dòng thời gian đầy đủ**: ai tải lên, model nào
> trích, ai sửa trường gì, ai duyệt, ai đẩy DSpace.

**Yêu cầu:** `YC-NK-01` → `YC-NK-09` · **Kiểm thử:** `KT-NK-01` → `KT-NK-11`

### Việc

| # | Việc | Tệp | Ghi chú |
|---|---|---|---|
| 1 | Migration 005: `user_activity` **append-only** (trigger chặn UPDATE/DELETE/TRUNCATE) | `database/migrations/005_user_activity.sql` *(mới)* | Dùng lại đúng hàm `prevent_audit_mutation()` đã có trong `init.sql` |
| 2 | Module ghi hoạt động, không ném lỗi ra ngoài | `scripts/core/user_log.py` *(mới)* | Cùng nguyên tắc `audit.py:55` |
| 3 | Ghi tự động: đăng nhập/đăng xuất/sai mật khẩu/khóa/hết phiên/**bị từ chối quyền** | `scripts/auth/*`, `scripts/auth/deps.py` | 403 là tín hiệu an ninh quan trọng nhất — không được bỏ sót |
| 4 | Ghi truy cập dữ liệu nhạy cảm: xem tài liệu nội bộ/nhạy cảm, tải tệp, kết xuất báo cáo | `scripts/api.py` | |
| 5 | `GET /api/v2/user-activity` — lọc người/thao tác/thời gian/IP/kết quả, phân trang | `scripts/api.py` | |
| 6 | Trang `/quan-tri/nhat-ky-nguoi-dung` + xuất Excel | `ui/src/app/quan-tri/nhat-ky-nguoi-dung/page.jsx` *(mới)* | Dùng lại `export_excel.py` từ V2 |
| 7 | **Dòng thời gian một tài liệu** — gộp `audit_log` + `user_activity` + `model_calls` + `ocr_runs` | `scripts/core/timeline.py` *(mới)*, `ui/src/components/DocumentTimeline.jsx` *(mới)* | Hạng mục giá trị cao, công sức thấp |
| 8 | Phát hiện bất thường: nhiều lần sai mật khẩu, đăng nhập ngoài giờ, kết xuất lượng lớn | `scripts/core/user_log.py` | Ghi `system_events` mức `warning`; V8 sẽ gửi cảnh báo |
| 9 | Nối `user_activity` vào bộ dọn theo tuổi của V1 | `scripts/core/retention.py` | 365 ngày mặc định (`QĐ-08`) |

### Việc kèm theo — trả một món nợ cũ

`update_metadata` hiện dùng DELETE+INSERT nên trigger `AFTER UPDATE` không kích hoạt →
`metadata_history` **gần như trống** (đã ghi chú trong `init.sql` và `PLAN.md`). Sprint này ghi lịch
sử ở **tầng ứng dụng** khi sửa metadata, vì lúc này mới có `actor` thật để ghi vào `changed_by`.
Làm sớm hơn thì chỉ ghi được `changed_by='system'` — vô nghĩa.

### Van lùi
`USER_ACTIVITY_ENABLED=0` → ngừng ghi, hệ thống chạy bình thường.

---

## V5 — Nạp tài liệu khối lượng lớn: đường vào *(1,5 tuần)*

> **Sau sprint này dùng được gì:** cán bộ chọn 500 file (hoặc thả một ZIP, hoặc chép vào thư mục theo
> dõi), đặt tên lô, bấm một lần. File trùng bị nhận ra và bỏ qua. Trong lúc tải, các tab khác **không
> bị treo** — sửa lỗi N-03.

**Yêu cầu:** `YC-BU-01` → `YC-BU-10` · **Kiểm thử:** `KT-BU-01` → `KT-BU-14`, `KT-HN-08`, `KT-KH-08`

### Việc

| # | Việc | Tệp | Ghi chú |
|---|---|---|---|
| 1 | **Sửa N-03:** ghi tệp qua `run_in_threadpool`, đọc theo mảnh, tính SHA-256 trong lúc ghi | `scripts/api.py:142` | Một lượt đọc: vừa ghi vừa băm, không đọc tệp hai lần |
| 2 | Migration 006: `batches` + cột mới của `documents` (`batch_id`, `file_hash`, `file_size`, `page_count`, `priority`, `attempts`, `uploaded_by`, `assigned_to`) | `database/migrations/006_batches.sql` *(mới)* + `init.sql` | |
| 3 | Bỏ trần 10 file → hạn mức cấu hình theo *số tệp* và *tổng dung lượng* | `scripts/api.py:266` | Thông báo tiếng Việt nói rõ hạn mức và số hiện tại |
| 4 | Chống trùng SHA-256: trùng → bỏ qua + báo trùng với tài liệu nào (cấu hình cho phép xử lý lại) | `scripts/db.py`, `scripts/api.py` | Index đã thiết kế ở mục 7.4 tài liệu yêu cầu |
| 5 | Kiểm tra tệp thật sự là PDF (chữ ký tệp `%PDF-`), không hỏng, không mã hóa; đếm số trang | `scripts/core/file_check.py` *(mới)* | Từ chối sớm rẻ hơn nhiều so với để OCR chạy rồi mới hỏng |
| 6 | Kiểm tra dung lượng đĩa trước khi nhận; dưới ngưỡng → từ chối + ghi `system_events` | `scripts/api.py` | |
| 7 | `POST /api/v2/batches` (nạp nhiều tệp), `GET /api/v2/batches`, `GET /api/v2/batches/{id}` | `scripts/api.py` | Envelope HPU, phân trang `?page&per_page` |
| 8 | Nạp từ ZIP: giải nén phía máy chủ, chống `zip-slip`, giữ cấu trúc thư mục làm gợi ý bộ sưu tập | `scripts/core/ingest_zip.py` *(mới)* | ⚠️ Bắt buộc chặn đường dẫn thoát thư mục |
| 9 | Thư mục theo dõi: quét định kỳ, tự tạo lô, chuyển tệp đã nhận sang `_processed/` | `scripts/ingest_watcher.py` *(mới)* | Dùng chung thư mục với FileBrowser đã có trong compose |
| 10 | Giao diện nạp theo lô: đặt tên lô, chọn nhiều tệp/thư mục, hiện tiến độ tải, danh sách bị bỏ qua kèm lý do | `ui/src/components/BatchUploader.jsx` *(mới)* | Thay `OCRUploader` khi bật cờ; giữ thành phần cũ làm van lùi |
| 11 | Upload chia mảnh (`YC-BU-08`) | `scripts/api.py`, `ui/src/lib/upload.js` *(mới)* | Làm nếu còn thời gian; ưu tiên thấp hơn việc 1–10 |

### Van lùi
`BATCH_UPLOAD_V2=0` → giao diện và endpoint cũ (trần 10 file) hoạt động như trước.
Endpoint `/api/v1/process` và `/api/v2/batch-upload` **giữ nguyên, không đụng vào** (ADR-003).

### Rủi ro
| Rủi ro | Xử lý |
|---|---|
| Nạp 500 file làm đầy đĩa giữa chừng | Việc 6 kiểm tra trước; ngưỡng cấu hình; ghi `system_events` để V8 cảnh báo |
| Giải nén ZIP độc hại ghi đè tệp hệ thống (`zip-slip`) | Kiểm tra đường dẫn từng mục **trước khi** ghi; `KT-BM-20` |
| Băm SHA-256 làm chậm nạp | Băm trong cùng lượt đọc khi ghi đĩa, chạy trong thread pool — không cộng thêm lượt I/O |

---

## V6 — Hàng đợi tin cậy & mở rộng *(1,5 tuần)*

> **Sau sprint này dùng được gì:** khởi động lại máy chủ giữa lúc chạy lô 500 file — **không mất một
> tài liệu nào**. Job lỗi được thử lại, hết lượt thì vào hàng đợi chết có lý do đọc được, bấm một nút
> chạy lại. Tài liệu lẻ cán bộ đang chờ không bị kẹt sau lô chạy đêm.

**Yêu cầu:** `YC-BU-11` → `YC-BU-20` · **Kiểm thử:** `KT-BU-15` → `KT-BU-26`, `KT-HN-09`, `KT-HN-10`

### Việc

| # | Việc | Tệp | Ghi chú |
|---|---|---|---|
| 1 | **Sửa N-02:** `BLMOVE` sang `worker:<id>:processing`, xóa khỏi đó khi hoàn tất | `scripts/worker.py:223` | `BLMOVE` là nguyên tử — job **luôn** ở đúng một chỗ |
| 2 | Ba hàng đợi ưu tiên `high`/`normal`/`low`, worker đọc theo thứ tự | `scripts/worker.py`, `scripts/api.py` | |
| 3 | Bộ thu hồi việc mồ côi: worker hết nhịp tim → trả job về hàng đợi + `system_events` | `scripts/core/reclaimer.py` *(mới)* | Chạy trong worker rảnh; nhịp tim đã có sẵn từ ADR-009 |
| 4 | Thử lại có khoảng lùi tăng dần + đếm `attempts` + hàng đợi chết có lý do | `scripts/worker.py`, `scripts/db.py` | Phân biệt lỗi **hạ tầng** (thử lại) với lỗi **tài liệu** (không thử lại, vô ích) |
| 5 | `GET /api/v2/queue/dead` + `POST /api/v2/queue/dead/{id}/retry` + chạy lại cả lô | `scripts/api.py` | Chạy lại **giữ nguyên `document_id`**, không tạo bản ghi mới |
| 6 | Tạm dừng / tiếp tục / hủy lô | `scripts/api.py`, `scripts/worker.py` | Job đang chạy dở vẫn chạy xong — dừng giữa OCR là lãng phí |
| 7 | Kiểm soát tải: hàng đợi vượt ngưỡng → từ chối mềm việc nạp mới | `scripts/api.py` | Thông báo tiếng Việt nói rõ khi nào thử lại được |
| 8 | Lấy mẫu độ sâu hàng đợi mỗi phút vào `queue_samples` (migration 007) | `scripts/core/reclaimer.py`, `database/migrations/007_queue_samples.sql` *(mới)* | Nguồn dữ liệu cho biểu đồ xu hướng của V7 |
| 9 | Đẩy DSpace theo lô **ở phía máy chủ** | `scripts/api.py`, `scripts/worker.py` | Đóng trình duyệt vẫn chạy tiếp |
| 10 | **Đo thông lượng thật** trên BD-06 (500 tệp) với 1/2/3 worker → thay bảng khuyến nghị ước lượng trong `docker-compose.yml:161` | `docs/DEPLOY.md` | Ghi kèm cỡ mẫu + cấu hình phần cứng + ngày đo |

### Van lùi
`QUEUE_MODE=blpop` → về đúng cơ chế hàng đợi hiện tại. `QUEUE_PRIORITY=0` → một hàng đợi như cũ.

### Rủi ro
| Rủi ro | Xử lý |
|---|---|
| Đổi cơ chế hàng đợi gây lỗi ở đường đang chạy | Van lùi `QUEUE_MODE`; chạy `reliable` ở dev một tuần trước khi lên máy chủ; `KT-BU-15` tái hiện được ca worker bị `kill -9` |
| Bộ thu hồi trả về job **đang chạy thật** → xử lý hai lần | Chỉ thu hồi khi khóa nhịp tim đã hết hạn (TTL 60s) **và** không có tiến triển; job phải **idempotent** — ghi metadata dùng `ON CONFLICT DO NOTHING` (đã có sẵn trong `init.sql`) |
| Thử lại vô hạn với tài liệu hỏng | Trần `MAX_ATTEMPTS`; lỗi tài liệu (PDF hỏng) **không** thử lại |

---

## V7 — Bảng điều khiển theo dõi công việc *(1,5 tuần)*

> **Sau sprint này dùng được gì:** đăng nhập vào là thấy ngay *"3 tài liệu chờ bạn duyệt, 2 tài liệu
> của bạn bị lỗi, lô Công văn T10 còn 47 file"*. Quản lý thấy việc đang tắc ở đâu và tài liệu nào tồn quá hạn.

**Yêu cầu:** `YC-DB-01` → `YC-DB-10` · **Kiểm thử:** `KT-DB-01` → `KT-DB-13`

### Việc

| # | Việc | Tệp |
|---|---|---|
| 1 | Truy vấn tổng hợp cho bảng điều khiển | `scripts/core/dashboard.py` *(mới)* |
| 2 | `GET /api/v2/dashboard/{summary,my-work,queue,batches,sla,workload}` | `scripts/api.py` |
| 3 | Ngưỡng SLA cấu hình theo trạng thái + truy vấn tài liệu quá hạn | `scripts/core/dashboard.py`, `.env.example` |
| 4 | Trang `/bang-dieu-khien` — **trang mặc định sau khi đăng nhập** | `ui/src/app/bang-dieu-khien/page.jsx` *(mới)* |
| 5 | Thẻ "Việc của tôi" + cập nhật realtime qua SSE sẵn có | `ui/src/components/dashboard/*` *(mới)* |
| 6 | Biểu đồ xu hướng hàng đợi từ `queue_samples` (V6) | `ui/src/components/dashboard/QueueChart.jsx` *(mới)* |
| 7 | Năng suất theo cán bộ — **áp đúng `QĐ-06`** về ai được xem | `scripts/core/dashboard.py`, giao diện |
| 8 | Bộ lọc thời gian dùng chung + xuất Excel | giao diện + `export_excel.py` (V2) |
| 9 | Bảng `daily_metrics` + tác vụ tổng hợp hàng đêm (migration 008) | `database/migrations/008_daily_metrics.sql` *(mới)*, `scripts/core/rollup.py` *(mới)* |
| 10 | Bổ sung sidebar: bảng điều khiển, duyệt, nhật ký, quản trị (thay các mục `href=null` hiện tại) | `ui/src/components/hpu/HpuLayout.jsx` |

### Nguyên tắc hiển thị (kế thừa từ `/bao-cao`)
Không vẽ bảng rỗng trông như đã đo. Backend chưa chạy → hiện lý do. Chưa có dữ liệu → nói rõ
"chưa có dữ liệu". Không có worker nào → nói rõ, không hiện `0` im lặng.

### Van lùi
Trang mới, không đụng `/bao-cao` và `/cong-cu`. Không cần van lùi ngoài việc gỡ mục sidebar.

---

## V8 — Không gian duyệt + Thông báo *(1,5 tuần)*

> **Sau sprint này dùng được gì:** cán bộ duyệt tài liệu trên màn hình hai cột — PDF bên trái, metadata
> bên phải, **trường điểm tin cậy thấp được tô màu** — thay vì sửa trong bảng. Worker chết lúc 2h sáng
> thì có người được báo ngay.

**Yêu cầu:** `YC-RV-01` → `YC-RV-08`, `YC-TB-01` → `YC-TB-06` · **Kiểm thử:** `KT-RV-01` → `KT-RV-12`, `KT-TB-01` → `KT-TB-08`

### Việc — phần duyệt

| # | Việc | Tệp | Ghi chú |
|---|---|---|---|
| 1 | Trang `/duyet` — danh sách `needs_review`, sắp theo ưu tiên & thời gian chờ | `ui/src/app/duyet/page.jsx` *(mới)* | **API đã có từ tháng 7**, chỉ thiếu trang |
| 2 | Màn hình duyệt hai cột, tô màu trường điểm thấp (`YC-CF-04`) | `ui/src/app/duyet/[jobId]/page.jsx` *(mới)* | Dùng lại `ConfidenceBadge` đã có |
| 3 | Bàn phím tắt (chuyển trường, chấp nhận, tài liệu tiếp) | như trên | Cán bộ duyệt hàng trăm tài liệu/tuần — phím tắt tiết kiệm thật |
| 4 | Nút Xác nhận → `audit_log` action `confirm` với `actor` thật; **chưa xác nhận thì không đẩy DSpace được** | `scripts/api.py` | Hiện thực hóa nguyên tắc SRS "con người giữ quyền quyết định" |
| 5 | Trang thùng rác `/thung-rac` + phục hồi + xóa vĩnh viễn (chỉ `admin`, xác nhận hai bước) | `ui/src/app/thung-rac/page.jsx` *(mới)* | API `restore`/`purge` đã có |
| 6 | Duyệt hàng loạt tài liệu điểm tin cậy cao (có xác nhận rõ ràng) | | `YC-RV-06` |
| 7 | Phân công tài liệu cho cán bộ (`assigned_to` từ V5) | | `YC-RV-07` |
| 8 | Nối `/luoc-do` vào `/api/v2/schemas` — **bỏ dữ liệu mẫu** | `ui/src/app/luoc-do/page.jsx` | Trả nợ đã ghi trong `PLAN.md` |

### Việc — phần cảnh báo

| # | Việc | Tệp | Ghi chú |
|---|---|---|---|
| 9 | Interface kênh thông báo + hiện thực `log`, `email` (SMTP nội bộ), `webhook` | `scripts/notify/{base,log,email,webhook}.py` *(mới)* | Cùng mẫu YC-MP-08: thêm kênh = viết một lớp |
| 10 | Quy tắc cảnh báo hạ tầng: không còn worker, mất Redis/PG, đĩa thấp, hàng đợi vượt ngưỡng | `scripts/core/alerts.py` *(mới)* | Đọc `system_events` đã có |
| 11 | Cảnh báo nghiệp vụ: lô xong, lô tỉ lệ lỗi cao, tài liệu quá hạn SLA | `scripts/core/alerts.py` | |
| 12 | Gộp + giới hạn tần suất chống spam | `scripts/core/alerts.py` | Sự cố kéo dài gửi **một lần**, không gửi mỗi phút |
| 13 | Tùy chọn nhận cảnh báo theo người dùng | migration 009 + giao diện | |

> ⚠️ **`YC-TB-06`:** mọi kênh cảnh báo phải chạy được khi **ngắt Internet** — SMTP nội bộ hoặc webhook
> nội mạng. Không phụ thuộc dịch vụ đám mây (YC-BM-02). Kiểm thử `KT-BM-21`.

### Van lùi
`ALERTS_ENABLED=0`. Trang duyệt là trang mới, không đụng luồng cũ trên `/`.

---

## V9 — Vận hành dài hạn & Tích hợp *(1 tuần)*

> **Sau sprint này dùng được gì:** dữ liệu được sao lưu tự động **và đã khôi phục thử thành công**.
> Đĩa không âm thầm đầy lên. n8n gọi API bằng khóa riêng thay vì tài khoản người.

**Yêu cầu:** `YC-VH-07` → `YC-VH-12`, `YC-TK-01` → `YC-TK-05` · **Kiểm thử:** `KT-VH-01` → `KT-VH-10`, `KT-TK-01` → `KT-TK-06`

### Việc

| # | Việc | Tệp | Ghi chú |
|---|---|---|---|
| 1 | Sao lưu tự động `pg_dump` + thư mục tài liệu, giữ N bản, kiểm tra toàn vẹn | `scripts/ops/backup.sh` *(mới)*, `docker-compose.yml` | `YC-VH-05` là yêu cầu SRS **chưa từng được hiện thực** |
| 2 | **Diễn tập khôi phục có tài liệu hóa** — khôi phục vào DB tạm, đối chiếu số bản ghi | `docs/DEPLOY.md` | Sao lưu chưa khôi phục thử thì chưa phải sao lưu |
| 3 | Dọn tệp trung gian trong `/data/digitization/jobs` theo tuổi | `scripts/core/retention.py` | Nối vào bộ dọn của V1 |
| 4 | Purge tài liệu xóa mềm quá N ngày — **cần `admin` phê duyệt** + ghi audit | `scripts/api.py` | Không tự động xóa dữ liệu nghiệp vụ |
| 5 | Tài khoản dịch vụ + API key (băm khi lưu, hiện một lần, thu hồi được, có hạn) | `scripts/auth/api_keys.py` *(mới)*, migration 010 | |
| 6 | Phạm vi quyền cho từng key + giới hạn tần suất | `scripts/auth/deps.py` | |
| 7 | Webhook ra ngoài khi tài liệu/lô xong | `scripts/notify/webhook.py` (V8) | Cho n8n tự động hóa bước sau |
| 8 | CI GitHub Actions: `pytest` + `npm run build` mỗi push | `.github/workflows/ci.yml` *(mới)* | 224 test hiện chỉ chạy khi ai đó nhớ chạy |
| 9 | E2E Playwright 5 luồng chính | `tests/e2e/*` *(mới)* | Lỗi `Content-Length` (commit `3663eaf`) thuộc loại chỉ E2E mới bắt được |
| 10 | Trang trợ giúp tiếng Việt theo vai trò (`YC-VH-04`) | `ui/src/app/tro-giup/page.jsx` *(mới)* | |

---

## 2. Tổng hợp thay đổi cơ sở dữ liệu

| Migration | Sprint | Nội dung | Loại |
|---|---|---|---|
| `003_ai_analytics.sql` | V2 | Mở rộng `model_calls`; tạo `model_call_fields`, `ocr_runs` | ADD / CREATE |
| `004_users_rbac.sql` | V3 | `users`, `roles`, `role_permissions`, `user_sessions` | CREATE |
| `005_user_activity.sql` | V4 | `user_activity` + trigger bất biến | CREATE |
| `006_batches.sql` | V5 | `batches`; thêm 8 cột cho `documents` | ADD / CREATE |
| `007_queue_samples.sql` | V6 | `queue_samples`; `dead_letter_jobs` | CREATE |
| `008_daily_metrics.sql` | V7 | `daily_metrics` | CREATE |
| `009_notification_prefs.sql` | V8 | `notification_preferences`, `alert_history` | CREATE |
| `010_api_keys.sql` | V9 | `api_keys` | CREATE |

**Không có migration nào `DROP` hay `ALTER TYPE`.** Mỗi migration phải:
chạy được hai lần liên tiếp không lỗi · cập nhật song song vào `database/init.sql` để cài mới cũng
đúng · có phần ghi chú tiếng Việt giải thích *vì sao* thêm bảng/cột đó.

---

## 3. Tổng hợp biến môi trường mới

| Biến | Mặc định | Sprint | Ý nghĩa |
|---|---|---|---|
| `LOG_FORMAT` | `json` | V1 | `text` = van lùi về định dạng cũ |
| `LOG_LEVEL` | `INFO` | V1 | |
| `LOG_DIR`, `LOG_ROTATE_MB`, `LOG_ROTATE_KEEP` | `/data/logs`, `100`, `10` | V1 | |
| `LOG_RETENTION_DAYS` | `14` | V1 | Log kỹ thuật |
| `SYSTEM_EVENTS_RETENTION_DAYS` | `90` | V1 | |
| `AI_ANALYTICS_DETAIL` | `1` | V2 | `0` = không ghi chi tiết từng trường |
| `AI_LOG_RAW` | `0` | V2 | Lưu prompt/phản hồi thô (riêng tư — mặc định tắt) |
| `USD_VND_RATE` | *(bắt buộc đặt)* | V2 | Quy đổi chi phí sang VNĐ nguyên |
| `ACCURACY_MIN_SAMPLE` | `30` | V2 | Dưới ngưỡng: hiện "chưa đủ dữ liệu" thay vì % |
| `AUTH_MODE` | `off` | V3 | `off` → `shadow` → `on` |
| `AUTH_BACKEND` | `local` | V3 | `local` \| `ldap` \| `oidc` |
| `ADMIN_BOOTSTRAP_USER`, `ADMIN_BOOTSTRAP_PASSWORD` | — | V3 | Chỉ dùng lần khởi tạo đầu |
| `SESSION_TTL_HOURS`, `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCK_MINUTES` | `12`, `5`, `15` | V3 | |
| `REQUIRE_SEPARATE_APPROVER` | `0` | V3 | Chốt bốn mắt (`QĐ-05`) |
| `USER_ACTIVITY_ENABLED`, `USER_ACTIVITY_RETENTION_DAYS` | `1`, `365` | V4 | |
| `BATCH_UPLOAD_V2` | `1` | V5 | `0` = van lùi về đường nạp cũ |
| `MAX_BATCH_FILES`, `MAX_BATCH_MB` | `500`, `5000` | V5 | |
| `DEDUP_MODE` | `skip` | V5 | `skip` \| `reprocess` |
| `DISK_MIN_FREE_GB` | `20` | V5 | Ngưỡng từ chối nhận |
| `WATCH_FOLDER`, `WATCH_INTERVAL_SEC` | *(tắt)*, `60` | V5 | |
| `QUEUE_MODE` | `reliable` | V6 | `blpop` = van lùi |
| `QUEUE_PRIORITY` | `1` | V6 | |
| `MAX_ATTEMPTS`, `RETRY_BACKOFF_SEC` | `3`, `30` | V6 | |
| `QUEUE_MAX_DEPTH` | `2000` | V6 | Ngưỡng kiểm soát tải |
| `SLA_HOURS_*` | *(theo trạng thái)* | V7 | Ngưỡng tài liệu tồn quá hạn |
| `ALERTS_ENABLED`, `ALERT_CHANNELS` | `1`, `log` | V8 | `log,email,webhook` |
| `SMTP_*` | — | V8 | SMTP **nội bộ** (YC-BM-02) |
| `BACKUP_CRON`, `BACKUP_KEEP` | `0 2 * * *`, `14` | V9 | |
| `JOB_FILES_RETENTION_DAYS` | `90` | V9 | Dọn tệp trung gian |

Mọi biến trên phải được ghi vào `.env.example` **kèm chú thích tiếng Việt** ngay trong sprint tương ứng.

---

## 4. Điều kiện đi tiếp giữa các sprint

Không bắt đầu sprint sau khi sprint trước chưa qua cổng:

| Cổng | Điều kiện |
|---|---|
| **V1 → V2** | Log JSON chạy ở dev ≥ 3 ngày; bộ lọc che bí mật đã kiểm bằng `KT-LG-05`; dọn theo tuổi chạy đúng |
| **V2 → V3** | Migration 003 chạy được hai lần trên bản sao dữ liệu thật; toàn bộ test provider cũ vẫn đạt |
| **V3 → V4** | **`AUTH_MODE=shadow` chạy ≥ 1 tuần với 0 cảnh báo trong 48h cuối**; CLI cứu hộ mật khẩu đã thử thật |
| **V4 → V5** | `AUTH_MODE=on` đã bật ở máy chủ thật ≥ 3 ngày không sự cố |
| **V5 → V6** | Nạp thử BD-06 (500 tệp) thành công; chống trùng đúng; đĩa không đầy |
| **V6 → V7** | Kiểm thử `kill -9` worker giữa chừng: **không mất tài liệu nào** (`KT-BU-15`) |
| **V7 → V8** | Bảng điều khiển khớp số với `/api/v2/stats` và `/bao-cao` (không được vênh) |
| **V8 → V9** | Cán bộ thật đã duyệt ≥ 20 tài liệu trên trang `/duyet` và xác nhận dùng được (kiểm thử chấp nhận) |

---

## 5. Nếu phải cắt phạm vi

SRS cảnh báo rủi ro lớn nhất là **ôm quá phạm vi**. Thứ tự cắt khi thiếu thời gian — cắt từ dưới lên:

| Ưu tiên | Sprint | Cắt được? |
|---|---|---|
| 🔴 Không cắt | **V3** (phân quyền) | Lỗ hổng bảo mật + chặn `YC-DR-04` của GĐ1 |
| 🔴 Không cắt | **V6** (hàng đợi tin cậy) | Đang **mất dữ liệu** khi worker chết |
| 🟠 Giữ | **V1**, **V5** | Nền tảng cho phần còn lại; rẻ |
| 🟠 Giữ | **V8 phần duyệt** | API đã trả tiền rồi, chỉ thiếu trang — tỉ lệ giá trị/công sức cao nhất |
| 🟡 Cắt được phần NC | **V2**, **V4**, **V7** | Giữ phần BB, bỏ `YC-AN-06/07/08`, `YC-NK-07/08`, `YC-DB-05/06/09/10` |
| 🟢 Hoãn được | **V9**, **V8 phần cảnh báo** | Trừ sao lưu `YC-VH-07` — cái này **không hoãn được** |

> **Ngoại lệ:** `YC-VH-07` (sao lưu tự động) tuy nằm ở V9 nhưng **không được hoãn**. Nếu phải cắt V9,
> hãy kéo riêng việc sao lưu lên bất kỳ sprint nào trước đó. Chạy hệ thống thật không có sao lưu là
> rủi ro không tương xứng với công sức bỏ ra để làm nó (nửa ngày).

---

## 6. Cập nhật tài liệu khi chạy sprint

Mỗi sprint kết thúc phải cập nhật:

- **`docs/PLAN.md`** — sprint đang chạy, việc còn nợ (phạm vi hẹp, chỉ sprint hiện tại)
- **`docs/STATUS.md`** — bảng "đã hoàn thành" + cách kiểm chứng + số test đạt
- **`docs/DECISIONS.md`** — ADR mới nếu có quyết định kiến trúc phát sinh
- **`docs/UPGRADE_TEST_CASES.md`** — điền **kết quả thật** vào cột Trạng thái (không điền kỳ vọng)
- **`.env.example`** — biến mới kèm chú thích tiếng Việt
- **`docs/DEPLOY.md`** — bước triển khai mới, migration cần chạy, van lùi
