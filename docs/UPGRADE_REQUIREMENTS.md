# DocuFlow HP — Bản mô tả yêu cầu NÂNG CẤP (đợt 2, 08–11/2026)

> **Phạm vi tài liệu này:** yêu cầu cho đợt nâng cấp *vận hành & quản trị*, bổ sung vào
> `docs/REQUIREMENTS.md` (yêu cầu gốc từ SRS). Tài liệu này trả lời **CÁI GÌ / VÌ SAO**.
> — Chia sprint và cách làm: `docs/UPGRADE_SPRINTS.md`
> — Bộ trường hợp kiểm thử: `docs/UPGRADE_TEST_CASES.md`
> — Lộ trình tổng: `docs/ROADMAP.md`
>
> **Ngày lập:** 31/07/2026 · **Căn cứ:** rà soát mã nguồn thực tế tại commit `50dd3bd` +
> `docs/05_Dac_ta_yeu_cau_phan_mem.docx` (SRS) + `docs/06_Ke_hoach_kiem_thu.docx` (kế hoạch kiểm thử).
>
> **Trạng thái:** *đề xuất* — chưa hạng mục nào được lập trình. Mọi con số hiệu năng trong tài liệu này
> là **ngưỡng cần đo**, không phải kết quả đã đo (nguyên tắc "đo được mới tuyên bố").

---

## 0. Tóm tắt cho người quyết định

Đợt nâng cấp này gồm **6 nhóm bạn yêu cầu** + **4 nhóm tôi đề xuất thêm**, tổng **78 yêu cầu** mã
`YC-*`, chia **9 sprint** trong ~12 tuần. Nguyên tắc xuyên suốt giữ nguyên: *bổ sung không viết lại*,
*làm đến đâu dùng được đến đó*, *đo được mới tuyên bố*.

| # | Nhóm | Mã | Vì sao cần | Sprint |
|---|---|---|---|---|
| 1 | Log hệ thống có cấu trúc | `YC-LG` | Lỗi hiện chỉ nằm trong log container, bị cắt vòng, phải SSH mới đọc được | V1 |
| 2 | Phân tích chi tiết kết quả AI | `YC-AN` | Biết model nào đúng bao nhiêu %, tốn bao nhiêu tiền — **đo trên việc thật**, không chỉ trên tập mẫu | V2 |
| 3 | Danh tính & phân quyền | `YC-QT` | **Đang không có xác thực nào** → 3 yêu cầu BB của SRS không thể thỏa mãn | V3 |
| 4 | Nhật ký người dùng | `YC-NK` | Truy được ai làm gì, phát hiện truy cập bất thường | V4 |
| 5 | Nạp tài liệu khối lượng lớn | `YC-BU` | Trần 10 file/lần; upload chặn API; hàng đợi mất việc khi worker chết | V5, V6 |
| 6 | Bảng điều khiển theo dõi công việc | `YC-DB` | Cán bộ không biết "việc của tôi hôm nay là gì", quản lý không biết ai đang tồn việc | V7 |
| 7 | *(đề xuất)* Không gian duyệt tài liệu | `YC-RV` | API đã có từ tháng 7 nhưng **chưa có giao diện** — cán bộ không dùng được | V8 |
| 8 | *(đề xuất)* Thông báo & cảnh báo | `YC-TB` | Worker chết lúc 2h sáng, 8h sáng mới có người phát hiện | V8 |
| 9 | *(đề xuất)* Vận hành dài hạn | `YC-VH-07→12` | Chưa có sao lưu tự động, chưa có cơ chế dọn dữ liệu cũ | V9 |
| 10 | *(đề xuất)* Tích hợp & tài khoản dịch vụ | `YC-TK` | n8n/hệ thống khác cần gọi API mà không dùng tài khoản người | V9 |

### Ba vấn đề nghiêm trọng phát hiện khi rà mã nguồn

Đây **không phải yêu cầu mới** — là lỗi/thiếu sót của hệ đang chạy, cần sửa trong đợt này.

| # | Vấn đề | Bằng chứng | Hậu quả thực tế | Xử lý ở |
|---|---|---|---|---|
| **N-01** | **Không có xác thực ở backend.** Toàn bộ `scripts/api.py` không có một `Depends`/middleware xác thực nào. `actor` là query param mặc định `"api"` | `api.py:703`, `api.py:743` | Bất kỳ ai vào được mạng nội bộ đều xóa/sửa được tài liệu; nhật ký kiểm toán ghi `actor='api'` nên **YC-AU-02 "ghi rõ ai" hiện KHÔNG thỏa mãn** dù bảng `audit_log` đã đúng | **V3** |
| **N-02** | **Hàng đợi mất việc.** `redis.blpop` lấy job RA khỏi hàng đợi trước khi xử lý; không có ack, không có visibility timeout | `worker.py:223` | Worker bị kill/OOM/restart giữa chừng → job biến mất im lặng. Tài liệu treo mãi ở "Chờ xử lý", không ai biết. Ở lô 500 file, xác suất gặp là gần như chắc chắn | **V6** |
| **N-03** | **Upload chặn API.** `save_upload_file` dùng `shutil.copyfileobj` **đồng bộ** bên trong `async def` | `api.py:142`, `api.py:206`, `api.py:257` | Ghi một file lớn xuống đĩa làm đóng băng toàn bộ event loop: SSE ngắt, mọi request khác treo. Càng tải nhiều file càng nặng | **V5** |

> ⚠️ N-01 là vấn đề **bảo mật**, không phải tiện ích. Theo nguyên tắc "ưu tiên kiểm thử theo mức rủi ro"
> của kế hoạch kiểm thử (mục 1.1), nhóm bảo mật được ưu tiên cao nhất vì *hậu quả không sửa được bằng
> bản vá*. Đây là lý do sprint phân quyền (V3) đứng trước phần khối lượng lớn và dashboard, dù bạn liệt
> kê chúng ở thứ tự 2 và 3.

---

## 1. Hiện trạng — đã có gì, thiếu gì

> **Cập nhật 09/08/2026.** Các bảng trong mục 1 là ảnh chụp hiện trạng **lúc lập đề xuất nâng cấp**
> (tháng 7/2026) — giữ nguyên để còn đọc được lý do vì sao làm đợt này. Từ đó tới nay các sprint
> V1–V9 đã lấp phần lớn ô ❌; xem `docs/STATUS.md` để biết trạng thái hiện tại.
>
> Ba nhóm yêu cầu **thêm mới sau đề xuất gốc**, đã hiện thực xong:
> - **YC-BU-21** — nạp tự động từ thư mục Google Drive (mục 7.1)
> - **YC-SC-09→14** — đoán loại tài liệu tự động (mục 9.4b)
> - **YC-TT-01→08** — thống kê theo người dùng & quản trị (mục 9.4c)

Rà tại commit `50dd3bd`. Cột "Có" nghĩa là **đã chạy được**, không phải "đã lên kế hoạch".

### 1.1 Ghi nhận & nhật ký

| Hạng mục | Có | Chi tiết / thiếu |
|---|---|---|
| `audit_log` bất biến | ✅ | `init.sql` mục 7b — trigger chặn UPDATE/DELETE/TRUNCATE. **Nhưng** cột `actor` không có nguồn tin cậy (N-01) |
| `model_calls` | ✅ | provider, deployment, model, version, latency, rss, gpu, attempts, n_fields, fallback, status |
| `system_events` | ✅ | Sự cố hạ tầng (ADR-009). **Thiếu:** cơ chế dọn theo tuổi (đã ghi nợ ở `PLAN.md`) |
| `metadata_fields.confidence` | ✅ | Điểm tin cậy từng trường, có index cho trường < 0.5 |
| `documents.duration_ms`, `stage_timings` | ✅ | Thời gian từng chặng dạng JSONB |
| Log ứng dụng có cấu trúc | ❌ | `logging.basicConfig` định dạng chữ thuần (`api.py:45`, `worker.py:26`). Không JSON, không tương quan được request |
| `request_id` / `job_id` xuyên suốt | ❌ | Không lần được một request qua nhiều tầng |
| Middleware ghi log mỗi request | ❌ | Không biết endpoint nào chậm, endpoint nào lỗi nhiều |
| Che khóa bí mật trong log | ❌ | YC-BM-03 yêu cầu nhưng **không có cơ chế nào cưỡng chế** — hiện chỉ dựa vào lập trình viên nhớ |
| Xem log trên giao diện | ❌ | Phải SSH vào máy chủ chạy `docker compose logs` |
| Số token / chi phí mỗi lần gọi | ❌ | Không biết một tháng tốn bao nhiêu tiền API |
| Kết quả AI ở mức TỪNG TRƯỜNG | ❌ | Chỉ lưu `n_fields` (đếm), không lưu model trả về gì cho từng trường |
| Chỉ số chất lượng OCR | ❌ | Không biết tài liệu nào scan xấu, bao nhiêu trang không có lớp text |
| `metadata_history` | ⚠️ | Bảng có, trigger có, nhưng `update_metadata` dùng DELETE+INSERT nên trigger `AFTER UPDATE` **hầu như không kích hoạt** (đã ghi chú trong `init.sql`) |

### 1.2 Nạp & xử lý tài liệu

| Hạng mục | Có | Chi tiết / thiếu |
|---|---|---|
| Upload 1 file | ✅ | `POST /api/v1/process` |
| Upload nhiều file | ⚠️ | `POST /api/v2/batch-upload` — **trần cứng 10 file** (`api.py:266`), ghi đĩa đồng bộ (N-03) |
| Hàng đợi Redis | ⚠️ | Danh sách + BLPOP. Không ack, không thử lại, không ưu tiên, không hàng đợi chết (N-02) |
| Nhân bản worker | ⚠️ | `WORKER_REPLICAS` trong compose, chỉnh tay. Không tự co giãn, không có khuyến nghị đo được |
| Khái niệm "lô" (batch) | ❌ | Không có bảng `batches`. Tải 300 file lên là 300 job rời rạc, không theo dõi được như một mẻ việc |
| Chống trùng tài liệu | ❌ | Tải cùng một file 2 lần → xử lý 2 lần, tốn OCR và tạo bản ghi trùng trong DSpace |
| Nạp từ thư mục / ZIP / thư mục theo dõi | ❌ | `FolderSelector.jsx` chỉ chọn thư mục ở trình duyệt, vẫn tải từng file |
| Upload tiếp tục được khi đứt mạng | ❌ | Đứt giữa chừng → tải lại từ đầu |
| Kiểm soát tải (backpressure) | ❌ | Không kiểm tra dung lượng đĩa, không giới hạn độ sâu hàng đợi → có thể làm đầy đĩa máy chủ |
| Tạm dừng / hủy / chạy lại một lô | ❌ | `job_statuses` có mã `cancelled` nhưng **không có endpoint nào đặt được trạng thái đó** |
| Đẩy DSpace theo lô | ⚠️ | UI có nút đẩy hàng loạt nhưng gọi tuần tự từng item từ trình duyệt |

### 1.3 Theo dõi & báo cáo

| Hạng mục | Có | Chi tiết / thiếu |
|---|---|---|
| `/bao-cao` | ✅ | Thống kê OCR, theo chế độ, trường bị sửa, thông lượng 7 ngày (dữ liệu thật) |
| `/cong-cu` | ✅ | Tình trạng thành phần, công cụ mô hình, sự kiện hệ thống, thời gian xử lý p50/p95 |
| SSE realtime | ✅ | `/api/v2/jobs/stream` |
| `workers_alive` | ✅ | Đếm nhịp tim — phân biệt "đang chạy" với "không có worker nào" |
| "Việc của tôi" | ❌ | Không có khái niệm người dùng nên không có khái niệm việc của ai |
| Độ sâu hàng đợi theo thời gian | ❌ | Chỉ có số hiện tại (`queue_length`), không có lịch sử → không thấy giờ cao điểm |
| Năng suất theo cán bộ | ❌ | Không đo được ai duyệt bao nhiêu tài liệu/ngày |
| SLA / tài liệu tồn quá hạn | ❌ | Tài liệu nằm chờ duyệt 3 tuần không ai biết |
| Xuất Excel | ❌ | Mọi báo cáo chỉ xem trên màn hình |
| Trang duyệt tài liệu `needs_review` | ❌ | **API đã có từ tháng 7** (`GET /api/v2/jobs?needs_review=true`) nhưng chưa có giao diện |
| Thùng rác / phục hồi | ❌ | API đã có (`POST /api/v2/jobs/{id}/restore`), chưa có giao diện |
| `/luoc-do` | ⚠️ | Còn dùng dữ liệu mẫu, chưa nối `/api/v2/schemas` |

### 1.4 Người dùng & phân quyền

| Hạng mục | Có | Chi tiết |
|---|---|---|
| Bảng `users` | ❌ | Không tồn tại |
| Đăng nhập vào DocuFlow | ❌ | `LoginForm.jsx` đăng nhập vào **DSpace**, không phải vào DocuFlow. Là proxy tới DSpace REST |
| Vai trò / quyền | ❌ | Không có |
| Phiên đăng nhập | ❌ | Không có |
| Nhật ký đăng nhập | ❌ | Không có |
| Khóa tài khoản sau N lần sai | ❌ | Không có |

> **Hệ quả pháp lý — cần lưu ý cho hồ sơ dự thi:** SRS yêu cầu YC-DR-04 *"chỉ quản trị viên đổi được
> độ nhạy cảm"* và YC-RG-10 *"kết quả tra cứu tuân theo phân quyền"*. Cả hai **không thể hiện thực**
> khi chưa có khái niệm người dùng. Nếu hồ sơ tuyên bố đã có hai yêu cầu này thì là tuyên bố sai.

---

## 2. Nguyên tắc thiết kế cho đợt nâng cấp

Kế thừa từ SRS, thêm 3 nguyên tắc riêng cho đợt này:

1. **Bổ sung không viết lại** *(kế thừa)* — hệ đang phục vụ thật tại Trung tâm Thông tin Thư viện.
   Mọi endpoint/trang hiện có phải tiếp tục chạy. Kiểm thử không hồi quy `KT-KH` là điều kiện tiên quyết.
2. **Đo được mới tuyên bố** *(kế thừa)* — mọi số hiệu năng đi kèm cỡ mẫu + phần cứng + ngày đo.
3. **Con người giữ quyền quyết định** *(kế thừa)* — tự động hóa không được tự đẩy dữ liệu vào DSpace.
4. **Mỗi sprint kết thúc bằng một thứ dùng được** *(mới)* — không có sprint nào chỉ "chuẩn bị hạ tầng".
   Nếu dừng dự án sau bất kỳ sprint nào, phần đã làm vẫn có giá trị sử dụng độc lập.
5. **Bật dần, có van lùi** *(mới)* — mọi thay đổi hành vi lớn đi kèm biến môi trường tắt/bật được mà
   **không cần build lại image**, theo đúng mẫu `USE_PROVIDER_LAYER` đã dùng thành công ở ADR-008.
6. **Không lưu cái không cần** *(mới)* — nhật ký chi tiết rất dễ phình. Mỗi loại log phải có thời hạn
   lưu và cơ chế dọn **được thiết kế cùng lúc với lúc tạo ra nó**, không để nợ lại.

### 2.1 Bốn lớp nhật ký — ranh giới rõ ràng

Đây là quyết định thiết kế cốt lõi của nhóm YC-LG. Trộn bốn loại vào một bảng là sai lầm khó sửa về sau.

| Lớp | Nơi lưu | Nội dung | Bất biến | Thời hạn lưu | Ai đọc |
|---|---|---|---|---|---|
| **Kiểm toán nghiệp vụ** | `audit_log` (đã có) | Thao tác trên tài liệu: tải lên, xử lý, sửa trường, xác nhận, đẩy DSpace | ✅ trigger chặn | Mặc định vĩnh viễn (YC-AU-06) | Thanh tra, quản lý |
| **Hành vi người dùng** | `user_activity` (mới) | Đăng nhập, đăng xuất, sai mật khẩu, bị từ chối quyền, xem, tìm kiếm, kết xuất | ✅ trigger chặn | 365 ngày (cấu hình) | Quản trị viên |
| **Sự cố hạ tầng** | `system_events` (đã có) | Mất Redis/PostgreSQL, worker lỗi, công cụ mô hình không dùng được | ❌ | 90 ngày (cấu hình) | Kỹ sư vận hành |
| **Chi tiết kỹ thuật** | Tệp JSONL + luân chuyển | Mỗi dòng log của tiến trình, kèm `request_id`/`job_id` | ❌ | 14 ngày (cấu hình) | Kỹ sư khi gỡ lỗi |

**Vì sao chi tiết kỹ thuật KHÔNG vào PostgreSQL:** một request tạo 5–20 dòng log; 500 tài liệu/ngày
sinh hàng chục nghìn dòng. Đẩy vào PG làm phình cơ sở dữ liệu nghiệp vụ, làm chậm sao lưu, và không
đem lại giá trị tra cứu tương xứng. Tệp JSONL + `grep`/API đọc tệp là đủ, và giữ được tính air-gapped
(không cần Elasticsearch/Loki). Ai muốn dùng Loki/Grafana thì bật profile tùy chọn — xem `QĐ-03`.

### 2.2 Chuẩn HPU áp dụng cho mã nguồn mới

Toàn bộ mã của đợt này là **mã mới** → tuân thủ chuẩn HPU ngay từ đầu, không di trú dần:

- Envelope `{status, data, message}` qua `scripts/core/responses.py` (+ `meta` phân trang, `code`/`errors` khi lỗi).
- URL `/api/v2/{resource}` kebab-case số nhiều, JSON snake_case, phân trang `?page&per_page`.
- Mọi bảng mới có đủ `id, created_at, updated_at, status`.
- Xóa mềm, không hard delete. Bản ghi nhật ký thì không xóa kể cả mềm — chỉ dọn theo tuổi có kiểm soát.
- Tiền: **số nguyên VNĐ**, không dùng dấu phẩy động (áp dụng cho `YC-AN-04` chi phí gọi model).
- Ngày: lưu `YYYY-MM-DD` / `TIMESTAMPTZ`, hiển thị `DD/MM/YYYY`.
- UI: palette `#1e3a5f`, sidebar 240px, xác nhận trước khi xóa, toast sau thao tác.
- Thông báo lỗi cho người dùng bằng **tiếng Việt có dấu**, đủ cụ thể để biết phải làm gì.

---

## 3. YC-LG — Log hệ thống có cấu trúc

**Mục tiêu:** trả lời được ba câu hỏi mà hôm nay phải SSH mới trả lời được — *"request này hỏng ở đâu?"*,
*"đêm qua có sự cố gì?"*, *"vì sao tài liệu X xử lý mất 20 phút?"*.

| Mã | Ưu tiên | Yêu cầu | Tiêu chí nghiệm thu |
|---|---|---|---|
| YC-LG-01 | BB | Log dạng **JSON một dòng** cho `api` và `worker`, trường chuẩn: `ts, level, logger, msg, request_id, job_id, actor, module` | Một dòng log bất kỳ parse được bằng `json.loads` |
| YC-LG-02 | BB | **`request_id`** sinh cho mỗi request (nhận `X-Request-Id` từ ngoài nếu có), truyền qua `contextvars` xuống mọi lớp, trả về trong header phản hồi | Lấy `request_id` từ trình duyệt, grep ra đủ chuỗi log của request đó |
| YC-LG-03 | BB | **`job_id`** gắn vào mọi dòng log của worker trong suốt vòng đời một tài liệu | Grep một `job_id` ra được đủ log OCR → trích xuất → xuất |
| YC-LG-04 | BB | Middleware ghi **một dòng tổng kết mỗi request**: method, path, status, thời gian (ms), kích thước phản hồi, `actor` | Có dòng tổng kết cho 100% request, kể cả request lỗi 500 |
| YC-LG-05 | BB | **Bộ lọc che bí mật** cưỡng chế ở tầng logging: khóa API, mật khẩu, `Authorization`, cookie phiên → thay bằng `***` | Cố tình log `CLAUDE_API_KEY` → tệp log chứa `***`, không chứa khóa (YC-BM-03) |
| YC-LG-06 | BB | Ghi ra **tệp JSONL** có luân chuyển theo kích thước + số tệp giữ lại (cấu hình), song song với stdout | Chạy sinh > ngưỡng dung lượng → tệp cũ được luân chuyển, không đầy đĩa |
| YC-LG-07 | BB | **Dọn nhật ký theo tuổi**: tệp JSONL, `system_events`, `user_activity` — chạy định kỳ, có ghi nhận số bản ghi đã dọn | Chạy tác vụ dọn → bản ghi quá hạn biến mất, bản ghi trong hạn còn nguyên, có dòng `system_events` ghi lại việc dọn |
| YC-LG-08 | NC | **API xem log**: `GET /api/v2/logs` lọc theo khoảng thời gian, mức, `request_id`, `job_id`, từ khóa; phân trang | Tìm được log của một `job_id` cụ thể qua API, không cần SSH |
| YC-LG-09 | NC | **Trang `/nhat-ky-he-thong`**: xem log + sự kiện hệ thống, lọc, tự làm mới, tải xuống đoạn log đang xem | Quản trị viên xem được log 24h qua trên trình duyệt |
| YC-LG-10 | NC | **Mức log đổi được lúc chạy** qua biến môi trường + endpoint quản trị (không phải build lại) | Đổi sang `DEBUG` → log chi tiết hơn ngay, không restart |
| YC-LG-11 | TT | Endpoint **`/metrics`** định dạng Prometheus: số request, độ trễ, độ sâu hàng đợi, số worker, số lần gọi model | `curl /metrics` trả về đúng định dạng; Grafana (profile tùy chọn) vẽ được |

### Thiết kế

```
scripts/core/logging_setup.py     # JsonFormatter + SecretRedactionFilter + RotatingFileHandler
scripts/core/context.py           # contextvars: request_id, job_id, actor
scripts/middleware/request_log.py # RequestContextMiddleware (FastAPI)
scripts/core/retention.py         # dọn log/sự kiện theo tuổi (gọi từ cron hoặc tác vụ nền)
```

Biến môi trường mới: `LOG_FORMAT=json|text` (mặc định `json`; `text` là van lùi), `LOG_LEVEL`,
`LOG_DIR`, `LOG_ROTATE_MB`, `LOG_ROTATE_KEEP`, `LOG_RETENTION_DAYS`,
`SYSTEM_EVENTS_RETENTION_DAYS`, `USER_ACTIVITY_RETENTION_DAYS`.

> **Van lùi:** `LOG_FORMAT=text` khôi phục đúng định dạng log hiện tại. Nếu định dạng JSON gây khó khăn
> cho ai đó đang quen đọc log cũ, đổi một biến là xong.

---

## 4. YC-AN — Phân tích chi tiết kết quả AI

**Mục tiêu:** biến mỗi lần gọi model thành **dữ liệu đo được**, để trả lời: model nào chính xác hơn
*trên việc thật của Nhà trường* (không phải trên tập mẫu), trường nào hay sai, mỗi tháng tốn bao nhiêu tiền.

> Đây là nhóm có giá trị cao nhất cho hồ sơ dự thi: nó tạo ra **số liệu tự thân** để chứng minh
> luận điểm "hai chế độ", thay vì phải chạy lại harness thủ công mỗi lần cần số.

| Mã | Ưu tiên | Yêu cầu | Tiêu chí nghiệm thu |
|---|---|---|---|
| YC-AN-01 | BB | Mở rộng `model_calls`: `prompt_tokens`, `completion_tokens`, `total_tokens` | Sau một lần trích xuất, ba cột có số > 0 với provider báo cáo token |
| YC-AN-02 | BB | Ghi **kết quả từng trường** vào bảng `model_call_fields`: `field_key`, `value_preview`, `confidence`, `grounded`, `attempt` | Trích một tài liệu 11 trường → có 11 dòng, giá trị khớp `metadata_fields` |
| YC-AN-03 | BB | Ghi **chỉ số OCR** vào bảng `ocr_runs`: số trang, DPI, dung lượng trước/sau, thời gian, số ký tự text, số trang không có lớp text, cảnh báo của OCRmyPDF | Xử lý một PDF 50 trang → một dòng `ocr_runs` đủ trường |
| YC-AN-04 | NC | **Chi phí** mỗi lần gọi: `cost_micro_usd` (số nguyên) + `cost_vnd` (**số nguyên VNĐ**, quy đổi theo `USD_VND_RATE` cấu hình được). Chế độ tại chỗ = 0 | Báo cáo chi phí tháng hiển thị đúng định dạng `N.NNN.NNN đ` |
| YC-AN-05 | BB | **Độ chính xác đo trên việc thật**: đối chiếu giá trị AI trả về (`model_call_fields`) với giá trị cuối cùng cán bộ đã duyệt (`metadata_fields` sau khi sửa) → tỉ lệ đúng theo trường / theo lược đồ / theo công cụ | Báo cáo hiện tỉ lệ đúng kèm **cỡ mẫu**; trường chưa đủ mẫu ghi "chưa đủ dữ liệu" thay vì hiện % |
| YC-AN-06 | NC | **So sánh công cụ song song**: bảng đối chiếu độ chính xác / độ trễ / chi phí giữa các provider trong cùng khoảng thời gian | Xuất được bảng so sánh cho hồ sơ mà không cần chạy lại harness |
| YC-AN-07 | NC | **Lưu prompt & phản hồi thô** (tùy chọn, mặc định TẮT): `AI_LOG_RAW=1` lưu vào tệp riêng có thời hạn, DB chỉ giữ `prompt_hash` + `prompt_version` | Bật cờ → có tệp; tắt cờ → không có tệp nào, DB vẫn có hash |
| YC-AN-08 | NC | **Phát hiện suy giảm chất lượng**: cảnh báo khi tỉ lệ `needs_review` hoặc tỉ lệ trường bị sửa trong 7 ngày vượt ngưỡng so với 30 ngày trước | Dựng dữ liệu suy giảm giả lập → có cảnh báo; dữ liệu ổn định → không cảnh báo |
| YC-AN-09 | NC | **Trang `/phan-tich-ai`**: độ chính xác theo trường, chi phí theo tháng, độ trễ p50/p95 theo công cụ, top trường hay sai, tỉ lệ ảo giác (không bám văn bản gốc) | Cán bộ nghiệp vụ đọc hiểu được mà không cần giải thích |
| YC-AN-10 | NC | **Xuất Excel** mọi bảng phân tích, giữ dấu tiếng Việt | Mở bằng Excel trên Windows, tiếng Việt hiển thị đúng |
| YC-AN-11 | TT | Ghi **lý do mỗi lần thử lại** (`retry_reason`) và số lần thử vào `model_calls` | Dựng ca đầu ra sai định dạng → thấy `retry_reason='invalid_json'` |

### YC-AN-05 — vì sao đây là yêu cầu quan trọng nhất nhóm này

Kế hoạch kiểm thử (mục 1.3) định nghĩa độ chính xác = *số trường đúng ÷ tổng số trường*, đối chiếu với
**đáp án chuẩn do người lập ghi tay**. Bộ BD-01 chỉ có 30–50 tài liệu và tốn rất nhiều công.

Nhưng hệ thống đang chạy thật đã có sẵn một nguồn đáp án chuẩn liên tục: **giá trị cuối cùng mà cán bộ
duyệt**. Nếu AI trả `dc.title = "Bao cao tong ket"` và cán bộ sửa thành `"Báo cáo tổng kết"`, thì đó là
một điểm dữ liệu về độ chính xác — miễn phí, có thật, và tích lũy mỗi ngày.

YC-AN-05 biến việc này thành số liệu tự động. Kèm hai điều kiện bắt buộc để số liệu trung thực:
- **Ghi rõ cỡ mẫu** bên cạnh mọi %; dưới ngưỡng tối thiểu (đề xuất 30 quan sát/trường) thì hiện
  "chưa đủ dữ liệu", **không hiện %**.
- **Nói rõ phương pháp** ngay trên giao diện: *"đối chiếu với giá trị cán bộ đã duyệt, không phải với
  đáp án chuẩn độc lập"* — vì cán bộ cũng có thể bỏ sót. Đây là chỉ báo xu hướng, không thay thế BD-01.

### Thiết kế cơ sở dữ liệu

```sql
-- Mở rộng (migration 003) — thêm cột, KHÔNG đổi cột cũ
ALTER TABLE model_calls
  ADD COLUMN prompt_tokens     INTEGER,
  ADD COLUMN completion_tokens INTEGER,
  ADD COLUMN total_tokens      INTEGER,
  ADD COLUMN cost_micro_usd    BIGINT,      -- số nguyên, tránh dấu phẩy động
  ADD COLUMN cost_vnd          BIGINT,      -- số nguyên VNĐ (chuẩn HPU)
  ADD COLUMN prompt_version    VARCHAR(50),
  ADD COLUMN prompt_hash       CHAR(64),
  ADD COLUMN context_chars     INTEGER,
  ADD COLUMN context_pages     INTEGER,
  ADD COLUMN retry_reason      TEXT,
  ADD COLUMN confidence_avg    NUMERIC(4,3),
  ADD COLUMN confidence_min    NUMERIC(4,3),
  ADD COLUMN grounded_ratio    NUMERIC(4,3),  -- tỉ lệ trường tìm thấy trong văn bản gốc (YC-CF-05)
  ADD COLUMN request_id        VARCHAR(64);   -- nối với log JSONL (YC-LG-02)

CREATE TABLE model_call_fields (   -- chi tiết TỪNG TRƯỜNG của một lần gọi
    id             BIGSERIAL PRIMARY KEY,
    model_call_id  BIGINT NOT NULL REFERENCES model_calls(id) ON DELETE CASCADE,
    document_id    TEXT,
    field_key      VARCHAR(100) NOT NULL,
    value_preview  TEXT,          -- cắt ngắn, đủ để đối chiếu, không lưu toàn văn
    confidence     NUMERIC(4,3),
    grounded       BOOLEAN,       -- giá trị có xuất hiện trong văn bản gốc không
    attempt        INTEGER NOT NULL DEFAULT 1,
    status         VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE ocr_runs (            -- chất lượng & chi phí xử lý OCR
    id                 BIGSERIAL PRIMARY KEY,
    document_id        TEXT NOT NULL,
    engine             VARCHAR(50)  NOT NULL DEFAULT 'ocrmypdf',
    language           VARCHAR(20),
    pages              INTEGER,
    pages_without_text INTEGER,     -- trang không tạo được lớp text → chỉ báo scan xấu
    dpi_pre            INTEGER,
    dpi_post           INTEGER,
    size_in_bytes      BIGINT,
    size_out_bytes     BIGINT,
    text_chars         INTEGER,
    duration_ms        INTEGER,
    warnings           TEXT,
    status             VARCHAR(20)  NOT NULL DEFAULT 'success',
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

> **Ràng buộc bắt buộc:** ghi các bảng này **không bao giờ được làm hỏng việc số hóa**. Áp dụng đúng
> mẫu đã dùng ở `scripts/core/extraction.py:255` — bọc `try/except`, lỗi ghi truy vết chỉ ghi log,
> không ném ra ngoài.

---

## 5. YC-QT — Quản trị người dùng & phân quyền

**Mục tiêu:** có danh tính thật để nhật ký kiểm toán có nghĩa, và để mở hệ thống cho nhiều cán bộ dùng
mà không ai vô tình xóa việc của người khác.

### 5.1 Mô hình vai trò đề xuất

Bốn vai trò + một loại tài khoản dịch vụ. Ít vai trò nhưng đủ tách bạch trách nhiệm:

| Vai trò | Mã | Làm được | Không làm được |
|---|---|---|---|
| Quản trị hệ thống | `admin` | Tất cả: quản lý người dùng, đổi độ nhạy cảm lược đồ, cấu hình, xem mọi nhật ký | *(không sửa được `audit_log` — DB chặn)* |
| Cán bộ nghiệp vụ | `librarian` | Tải lên, xem, sửa metadata, gửi duyệt, xem báo cáo | Duyệt, đẩy DSpace, quản lý người dùng *(vì không có quyền, không phải vì quan hệ sở hữu)* |
| Cán bộ duyệt | `approver` | Mọi quyền của `librarian` + **duyệt** + **đẩy DSpace** + xóa mềm — **kể cả tài liệu do chính mình tải lên** | Quản lý người dùng, đổi cấu hình hệ thống |
| Người xem | `viewer` | Xem tài liệu, xem báo cáo | Mọi thao tác ghi |
| Tài khoản dịch vụ | `service` | Chỉ các quyền được cấp rõ ràng qua API key (xem `YC-TK`) | Đăng nhập bằng giao diện |

> **`QĐ-05` — ĐÃ CHỐT (31/07/2026):** **quyền duyệt do phân quyền quyết định, không do quan hệ sở hữu.**
> Ai có quyền `document:approve` thì duyệt được mọi tài liệu, **kể cả tài liệu do chính mình tải lên**.
> Không áp chốt bốn mắt mặc định. Cấu hình `REQUIRE_SEPARATE_APPROVER` vẫn được hiện thực và **mặc định
> `0` (tắt)** để Trung tâm bật sau nếu đủ nhân sự — nhưng đó là lựa chọn, không phải hành vi mặc định.
>
> *Hệ quả kỹ thuật:* kiểm tra quyền là **một phép thử duy nhất** (`require("document:approve")`),
> không phải phép thử kép "có quyền VÀ không phải người tải lên". Đơn giản hơn và ít chỗ sai hơn.

### 5.2 Yêu cầu

| Mã | Ưu tiên | Yêu cầu | Tiêu chí nghiệm thu |
|---|---|---|---|
| YC-QT-01 | BB | Bảng `users`: tên đăng nhập, email, họ tên, mật khẩu **băm** (Argon2id hoặc bcrypt), vai trò, trạng thái, lần đăng nhập cuối | Mật khẩu không bao giờ xuất hiện dạng thô trong DB hay log |
| YC-QT-02 | BB | **Đăng nhập/đăng xuất** bằng phiên phía máy chủ; cookie `HttpOnly` + `SameSite=Lax` + `Secure` (khi HTTPS); phiên **thu hồi được** | Quản trị viên thu hồi phiên → người dùng đó bị đăng xuất ở request kế tiếp |
| YC-QT-03 | BB | **Phân quyền cưỡng chế ở máy chủ** qua dependency `require(permission)`. Ẩn nút trên giao diện là tiện ích, **không phải cơ chế bảo vệ** | Gọi thẳng API bằng `curl` với vai trò `viewer` → trả 403, ghi `user_activity` |
| YC-QT-04 | BB | **Van chuyển tiếp `AUTH_MODE`**: `off` (như hiện nay) → `shadow` (không chặn, chỉ ghi nhận request thiếu xác thực) → `on` (chặn). Đổi bằng biến môi trường | Ở `shadow`, hệ thống chạy y như cũ nhưng nhật ký chỉ ra endpoint nào còn client cũ đang gọi |
| YC-QT-05 | BB | **Khởi tạo quản trị viên đầu tiên** từ biến môi trường lúc khởi động lần đầu, **bắt buộc đổi mật khẩu** ở lần đăng nhập đầu | Tài khoản mặc định không dùng được nếu chưa đổi mật khẩu |
| YC-QT-06 | BB | **Chính sách mật khẩu**: độ dài tối thiểu cấu hình được, chặn mật khẩu phổ biến, khóa tài khoản sau N lần sai trong M phút | Sai 5 lần → khóa 15 phút, có bản ghi `user_activity`, thông báo tiếng Việt rõ ràng |
| YC-QT-07 | BB | **Giao diện quản trị người dùng** `/quan-tri/nguoi-dung`: tạo, sửa, đổi vai trò, khóa/mở, đặt lại mật khẩu, xem phiên đang hoạt động. Xác nhận trước mọi thao tác nguy hiểm | Quản trị viên tạo được tài khoản mới mà không cần lập trình viên |
| YC-QT-08 | BB | **Vô hiệu hóa thay vì xóa** người dùng (xóa mềm) — vì `audit_log` tham chiếu tới họ | Vô hiệu hóa một tài khoản → nhật ký cũ của họ vẫn truy được đầy đủ |
| YC-QT-09 | NC | **Quyền cấu hình được**: bảng `roles` + `role_permissions` trong DB, không phải hằng số trong mã (cùng triết lý YC-SC-01) | Thêm quyền mới cho một vai trò bằng cấu hình, không sửa mã |
| YC-QT-10 | NC | **Nền tảng xác thực cắm được** (`AUTH_BACKEND=local\|ldap\|oidc`), viết interface trước — hiện thực `local` trước, LDAP/AD của Nhà trường sau | Thêm LDAP chỉ cần viết một lớp hiện thực, không sửa lớp gọi (đúng mẫu YC-MP-08) |
| YC-QT-11 | NC | Gắn **`actor` thật** vào `audit_log`, `model_calls`, `user_activity` — thay các giá trị `'api'`/`'worker'` hiện tại | Sau khi bật, không còn bản ghi audit nào có `actor='api'` từ thao tác của người |
| YC-QT-12 | TT | Xác thực hai yếu tố (TOTP) cho vai trò `admin` | Bật 2FA → đăng nhập cần mã 6 số |

### 5.3 Chiến lược chuyển đổi — không làm gián đoạn hệ đang chạy

Đây là phần rủi ro nhất của cả đợt nâng cấp. Kế hoạch ba nấc, mỗi nấc dừng lại được:

```
Nấc 1 (AUTH_MODE=off)     Triển khai toàn bộ mã: bảng, đăng nhập, giao diện quản trị.
                          Hành vi hệ thống KHÔNG ĐỔI. Cán bộ vẫn dùng như cũ.
                          → Tạo tài khoản, tập huấn, kiểm thử đăng nhập song song.

Nấc 2 (AUTH_MODE=shadow)  API vẫn phục vụ request không xác thực nhưng ghi cảnh báo
                          "request thiếu xác thực tới <endpoint> từ <ip>".
                          → Chạy ÍT NHẤT 1 TUẦN. Đọc nhật ký, tìm hết chỗ còn sót
                            (script cũ, n8n, bookmark của cán bộ) rồi sửa.
                          → Điều kiện sang nấc 3: 0 cảnh báo trong 48 giờ liên tiếp.

Nấc 3 (AUTH_MODE=on)      Chặn thật. Van lùi: đổi lại `shadow` là chạy ngay,
                          không cần build lại image.
```

> **Không có nấc 2 thì gần như chắc chắn hỏng việc:** hệ thống đang phục vụ thật, và không ai biết hết
> những chỗ nào đang gọi API — có thể có script cá nhân, luồng n8n, hay tab trình duyệt mở từ tuần trước.
> Nấc `shadow` biến câu hỏi "còn sót chỗ nào không?" từ phỏng đoán thành **dữ liệu**.

---

## 6. YC-NK — Nhật ký người dùng

**Mục tiêu:** trả lời *"ai đã làm gì, lúc nào, từ đâu"* — kể cả những thao tác không chạm vào tài liệu
(đăng nhập, tìm kiếm, kết xuất báo cáo, bị từ chối quyền).

| Mã | Ưu tiên | Yêu cầu | Tiêu chí nghiệm thu |
|---|---|---|---|
| YC-NK-01 | BB | Bảng `user_activity` **append-only** (trigger chặn UPDATE/DELETE như `audit_log`): `user_id`, `username`, `action`, `resource_type`, `resource_id`, `ip`, `user_agent`, `request_id`, `result`, `detail` | Thử `UPDATE user_activity` → DB từ chối |
| YC-NK-02 | BB | Ghi **đăng nhập thành công / thất bại / đăng xuất / hết phiên / bị khóa** kèm IP | Đăng nhập sai 3 lần từ 2 IP → có 3 bản ghi đủ IP |
| YC-NK-03 | BB | Ghi **mọi lần bị từ chối quyền** (403) — đây là tín hiệu an ninh quan trọng nhất | `viewer` gọi API xóa → có bản ghi `result='denied'` |
| YC-NK-04 | BB | Ghi thao tác **đọc dữ liệu nhạy cảm**: xem tài liệu nội bộ/nhạy cảm, kết xuất báo cáo, tải tệp | Tải một ZIP → có bản ghi kèm `document_id` |
| YC-NK-05 | NC | **Giao diện `/quan-tri/nhat-ky-nguoi-dung`**: lọc theo người, thao tác, khoảng thời gian, IP, kết quả; phân trang | Tìm được toàn bộ hoạt động của một cán bộ trong một ngày |
| YC-NK-06 | NC | **Xuất Excel** nhật ký theo bộ lọc (YC-AU-05 mở rộng cho người dùng) | Xuất 10.000 dòng không quá thời gian chờ hợp lý, tiếng Việt đúng |
| YC-NK-07 | NC | **Dòng thời gian một tài liệu**: gộp `audit_log` + `user_activity` + `model_calls` + `ocr_runs` thành một dòng thời gian duy nhất trên trang chi tiết tài liệu | Nhìn một màn hình biết tài liệu đã qua tay ai, model nào, sửa gì |
| YC-NK-08 | NC | **Cảnh báo hành vi bất thường**: nhiều lần sai mật khẩu, đăng nhập ngoài giờ, kết xuất lượng lớn bất thường | Dựng kịch bản → có bản ghi `system_events` mức `warning` |
| YC-NK-09 | NC | **Thời hạn lưu cấu hình được**, mặc định 365 ngày; dọn có ghi nhận (nối YC-LG-07) | Chạy dọn → còn đúng phần trong hạn |

> **YC-NK-07 là hạng mục tôi khuyến nghị mạnh nhất trong nhóm này.** Bốn nguồn dữ liệu đã tồn tại
> nhưng nằm rời rạc; gộp lại thành một dòng thời gian là công việc nhỏ (một truy vấn UNION + một
> thành phần giao diện) nhưng đổi hẳn khả năng giải trình khi có tranh chấp về một tài liệu cụ thể.

---

## 7. YC-BU — Nạp & xử lý tài liệu khối lượng lớn

**Mục tiêu:** từ "tải 10 file một lần, ngồi canh" thành "thả 500 file vào, đi về, sáng mai xem kết quả".

### 7.1 Yêu cầu — đường vào (nhận tài liệu)

| Mã | Ưu tiên | Yêu cầu | Tiêu chí nghiệm thu |
|---|---|---|---|
| YC-BU-01 | BB | **Ghi tệp bất đồng bộ** — sửa N-03: ghi đĩa trong thread pool (`run_in_threadpool`) hoặc streaming, không chặn event loop | Tải file 200MB trong khi mở SSE ở tab khác → SSE không đứt, API khác vẫn phản hồi |
| YC-BU-02 | BB | **Bỏ trần 10 file**, thay bằng giới hạn cấu hình được theo *tổng dung lượng* và *số tệp* (`MAX_BATCH_FILES`, `MAX_BATCH_MB`), có thông báo tiếng Việt rõ khi vượt | Tải 200 file thành công; tải vượt hạn mức → lỗi 400 nói rõ hạn mức và số hiện tại |
| YC-BU-03 | BB | **Khái niệm lô (`batches`)**: mỗi lần nạp tạo một lô có tên, người tạo, tổng số, tiến độ, trạng thái | Mở trang lô thấy "Lô công văn tháng 7 — 312/500 xong, 4 lỗi" |
| YC-BU-04 | BB | **Chống trùng bằng SHA-256**: tính hash lúc nhận; trùng → mặc định **cảnh báo và bỏ qua** (cấu hình cho phép xử lý lại), ghi rõ trùng với tài liệu nào | Tải lại đúng file cũ → báo "đã có, trùng với tài liệu X", không tốn OCR |
| YC-BU-05 | BB | **Kiểm tra dung lượng đĩa trước khi nhận**; dưới ngưỡng an toàn → từ chối kèm thông báo, ghi `system_events` | Giả lập đĩa gần đầy → từ chối nhận, hệ thống không chết |
| YC-BU-06 | NC | **Nạp từ thư mục theo dõi** (`watch folder`): thư mục trên máy chủ (dùng chung với FileBrowser sẵn có trong compose), quét định kỳ, tự tạo lô | Cán bộ chép 100 file vào thư mục qua SMB/FileBrowser → tự vào hàng đợi |
| YC-BU-07 | NC | **Nạp từ tệp ZIP**: giải nén phía máy chủ, giữ cấu trúc thư mục làm gợi ý bộ sưu tập | Tải một ZIP 300 file → tạo lô 300 tài liệu |
| YC-BU-08 | NC | **Upload chia mảnh, tiếp tục được** khi đứt mạng (`init` → `chunk` → `complete`) | Ngắt mạng giữa chừng, nối lại → tiếp tục từ mảnh dở, không tải lại từ đầu |
| YC-BU-09 | NC | **Kiểm tra tệp đầu vào**: đúng PDF (kiểm chữ ký tệp, không chỉ đuôi), không hỏng, không mã hóa, số trang hợp lệ | Tải file `.pdf` giả (thực chất là ảnh đổi tên) → từ chối, nói rõ lý do |
| YC-BU-10 | TT | **Quét virus** tùy chọn (ClamAV, profile riêng) trước khi xử lý | Bật profile → tệp nhiễm bị chặn và ghi nhật ký |
| YC-BU-21 | NC | **Nạp tự động từ thư mục Google Drive** — cán bộ chia sẻ thư mục cho tài khoản dịch vụ, hệ thống quét định kỳ, tải tệp mới về và đưa vào hàng đợi. CHỈ ĐỌC trên Drive (không đổi tên, không chuyển thư mục, không xóa). Chống trùng ba lớp: mã tệp Drive → SHA-256 nội dung → khóa Redis khi quét | Đặt 20 tệp vào thư mục → trong ≤ 2 chu kỳ quét, 20 tài liệu vào hàng đợi; quét lại → không tạo job trùng; gỡ chia sẻ thư mục → nguồn báo lỗi tiếng Việt, worker vẫn chạy bình thường |

> **YC-BU-21 khác YC-BU-06 thế nào.** YC-BU-06 là thư mục **trên máy chủ** (FileBrowser/SMB) — cán bộ
> phải ở trong mạng Nhà trường. YC-BU-21 là thư mục **trên Drive** — máy scan ở phòng nào cũng đổ
> thẳng vào được, không cần VPN. Hai đường bổ sung cho nhau, dùng chung phần hạ nguồn (lô, chống
> trùng, hàng đợi); YC-BU-06 vẫn chưa làm.

**Ranh giới tự động hóa của YC-BU-21 (quan trọng):** hệ thống tự làm tới bước *trích metadata*, rồi
DỪNG. Việc chọn bộ sưu tập DSpace và xác nhận vẫn ở màn hình Duyệt. Nguồn Drive chỉ đặt sẵn **gợi ý**
bộ sưu tập. Đây là hiện thực hóa nguyên tắc SRS "con người giữ quyền quyết định — không tự ghi vào
hệ đích khi chưa có cán bộ xác nhận" (chốt cứng YC-RV-04 vẫn áp dụng nguyên vẹn cho tài liệu từ Drive).

### 7.2 Yêu cầu — đường xử lý (hàng đợi & worker)

| Mã | Ưu tiên | Yêu cầu | Tiêu chí nghiệm thu |
|---|---|---|---|
| YC-BU-11 | BB | **Hàng đợi tin cậy** — sửa N-02: `BLMOVE` sang danh sách đang-xử-lý riêng cho từng worker; hoàn tất mới xóa | Kill `-9` worker giữa chừng → job **quay lại hàng đợi**, không mất |
| YC-BU-12 | BB | **Bộ thu hồi việc mồ côi**: worker chết (hết hạn nhịp tim) → job trong danh sách đang-xử-lý của nó được trả lại hàng đợi, có ghi `system_events` | Dựng worker chết → trong vòng ≤ 2 phút job được nhận lại bởi worker khác |
| YC-BU-13 | BB | **Thử lại có giới hạn**: job lỗi hạ tầng thử lại tối đa N lần với khoảng lùi tăng dần; hết lượt → **hàng đợi chết** (`dead_letter`) có lý do, không im lặng biến mất | Job lỗi 3 lần → vào hàng đợi chết, hiện trên giao diện với lý do đọc được |
| YC-BU-14 | BB | **Chạy lại từ hàng đợi chết** bằng một thao tác trên giao diện (một job hoặc cả lô) | Sửa nguyên nhân → bấm "Chạy lại" → job chạy tiếp, giữ nguyên `document_id` |
| YC-BU-15 | NC | **Ưu tiên hàng đợi**: `high` / `normal` / `low`. Tài liệu lẻ cán bộ đang chờ không bị kẹt sau lô 500 file chạy đêm | Nạp lô 500 (`low`), rồi tải 1 file (`high`) → file lẻ được xử lý trước |
| YC-BU-16 | NC | **Tạm dừng / tiếp tục / hủy một lô** | Tạm dừng lô đang chạy → job đang chạy dở vẫn xong, job chưa bắt đầu thì dừng |
| YC-BU-17 | NC | **Kiểm soát tải**: độ sâu hàng đợi vượt ngưỡng → tạm ngừng nhận nạp mới, báo tiếng Việt rõ ràng | Hàng đợi > ngưỡng → nạp mới bị từ chối mềm, không sập hệ thống |
| YC-BU-18 | NC | **Tiến độ lô realtime** qua SSE sẵn có + ETA tính từ thông lượng thực đo | Trang lô cập nhật không cần tải lại; ETA hiện kèm ghi chú "ước tính" |
| YC-BU-19 | NC | **Đẩy DSpace theo lô ở phía máy chủ** (thay vì trình duyệt gọi tuần tự từng item), có báo cáo từng item | Đẩy 100 item → đóng trình duyệt vẫn chạy tiếp; xong có bảng kết quả từng item |
| YC-BU-20 | NC | **Bảng khuyến nghị cấu hình theo phần cứng** dựa trên số liệu **đo thật**, thay cho ước lượng trong `docker-compose.yml` hiện tại | Có bảng: CPU/RAM → `WORKER_REPLICAS`, kèm thông lượng đo được và cỡ mẫu |

> **Về YC-BU-20:** `docker-compose.yml:161-163` hiện đã có bảng khuyến nghị, nhưng là **ước lượng
> theo quy tắc ngón tay cái**, chưa đo. Sprint V6 phải thay bằng số đo thật trên bộ BD-06 — đúng
> nguyên tắc "đo được mới tuyên bố".

### 7.3 Thiết kế hàng đợi tin cậy

```
        ┌── digitization_jobs:high ──┐
LPUSH ──┼── digitization_jobs:normal ┼── BLMOVE ──► worker:<id>:processing ──► xử lý
        └── digitization_jobs:low ───┘                      │
                                                            ├─ xong  → LREM (xóa khỏi processing)
                                                            ├─ lỗi   → attempts+1, LPUSH lại (lùi dần)
                                                            └─ hết lượt → digitization_jobs:dead

   Bộ thu hồi (chạy trong API hoặc worker rảnh, mỗi 60s):
     với mỗi khóa worker:*:processing mà KHÔNG còn nhịp tim tương ứng
       → trả job về hàng đợi + ghi system_events(kind='job_reclaimed')
```

`BLMOVE` là nguyên tử: job **luôn** nằm ở đúng một chỗ — hàng đợi hoặc danh sách đang-xử-lý. Đây là
điểm khác biệt cốt lõi so với `BLPOP` hiện tại, nơi job tồn tại chỉ trong bộ nhớ tiến trình worker
trong suốt thời gian OCR (có thể vài phút).

### 7.4 Bảng mới

```sql
CREATE TABLE batches (
    id            TEXT PRIMARY KEY,             -- uuid4
    name          VARCHAR(200) NOT NULL,        -- "Công văn tháng 7/2026"
    source        VARCHAR(20)  NOT NULL DEFAULT 'web',  -- web|folder|zip|watch|api
    created_by    BIGINT REFERENCES users(id),
    priority      VARCHAR(10)  NOT NULL DEFAULT 'normal',
    total_files   INTEGER      NOT NULL DEFAULT 0,
    done_files    INTEGER      NOT NULL DEFAULT 0,
    failed_files  INTEGER      NOT NULL DEFAULT 0,
    skipped_files INTEGER      NOT NULL DEFAULT 0,   -- trùng, không hợp lệ
    status        VARCHAR(20)  NOT NULL DEFAULT 'running', -- running|paused|completed|cancelled|deleted
    note          TEXT,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at   TIMESTAMPTZ
);

ALTER TABLE documents
  ADD COLUMN batch_id    TEXT REFERENCES batches(id),
  ADD COLUMN file_hash   CHAR(64),      -- SHA-256, chống trùng
  ADD COLUMN file_size   BIGINT,
  ADD COLUMN page_count  INTEGER,
  ADD COLUMN priority    VARCHAR(10) NOT NULL DEFAULT 'normal',
  ADD COLUMN attempts    INTEGER     NOT NULL DEFAULT 0,
  ADD COLUMN uploaded_by BIGINT REFERENCES users(id),
  ADD COLUMN assigned_to BIGINT REFERENCES users(id);   -- ai chịu trách nhiệm duyệt

CREATE INDEX idx_documents_batch  ON documents(batch_id);
CREATE INDEX idx_documents_hash   ON documents(file_hash) WHERE file_hash IS NOT NULL;
```

---

## 8. YC-DB — Bảng điều khiển theo dõi công việc

**Mục tiêu:** hai câu hỏi, hai đối tượng. Cán bộ: *"hôm nay tôi phải làm gì?"*. Quản lý: *"việc đang
tắc ở đâu, ai đang quá tải?"*.

> Phân biệt với hai trang đã có: `/bao-cao` là **phân tích lịch sử**, `/cong-cu` là **sức khỏe kỹ
> thuật**. `/bang-dieu-khien` là **điều hành công việc hàng ngày** — trang mặc định sau khi đăng nhập.

| Mã | Ưu tiên | Yêu cầu | Tiêu chí nghiệm thu |
|---|---|---|---|
| YC-DB-01 | BB | **Thẻ "Việc của tôi"**: tài liệu tôi tải lên đang xử lý, đang chờ tôi duyệt, tôi đã duyệt hôm nay, tài liệu của tôi bị lỗi | Cán bộ đăng nhập thấy ngay việc của mình, không phải lọc tay |
| YC-DB-02 | BB | **Tình trạng hàng đợi realtime**: độ sâu theo mức ưu tiên, số worker sống, tài liệu đang xử lý, thời gian chờ trung bình | Khớp với `/api/v2/stats`; không có worker → nói rõ chứ không hiện 0 im lặng |
| YC-DB-03 | BB | **Tiến độ theo lô**: bảng các lô đang chạy với thanh tiến độ, số lỗi, ETA | Mở lô ra xem được danh sách tài liệu trong lô |
| YC-DB-04 | BB | **Cảnh báo SLA**: tài liệu ở một trạng thái quá N giờ (ngưỡng cấu hình theo trạng thái) → hiện nổi bật, đếm số lượng | Đặt ngưỡng 24h, dựng tài liệu tồn 30h → xuất hiện trong danh sách quá hạn |
| YC-DB-05 | NC | **Năng suất theo cán bộ** *(công khai — `QĐ-06`)*: số tài liệu duyệt/ngày, thời gian duyệt trung bình, tỉ lệ trường phải sửa. Mọi người đăng nhập đều xem được bảng theo từng cán bộ; `admin` thêm phần tổng thể toàn Trung tâm | Bảng theo tuần, hiện tên từng cán bộ; **có ghi chú rõ** đây là số liệu vận hành, không phải đánh giá thi đua |
| YC-DB-06 | NC | **Xu hướng độ sâu hàng đợi** theo giờ/ngày (bảng `queue_samples` lấy mẫu mỗi phút) | Biểu đồ 7 ngày chỉ ra giờ cao điểm |
| YC-DB-07 | NC | **Bộ lọc thời gian dùng chung** cho mọi thẻ (hôm nay / 7 ngày / 30 ngày / tùy chọn) | Đổi bộ lọc → mọi thẻ cập nhật đồng bộ |
| YC-DB-08 | NC | **Xuất Excel** dữ liệu bảng điều khiển theo bộ lọc hiện tại | Tệp mở được bằng Excel, tiếng Việt đúng, ngày `DD/MM/YYYY` |
| YC-DB-09 | NC | **Bảng chỉ số theo ngày** (`daily_metrics`) tổng hợp mỗi đêm — để bảng điều khiển không quét bảng lớn khi dữ liệu tích lũy | Với 100.000 tài liệu, bảng điều khiển tải trong ngưỡng đã đo và ghi nhận |
| YC-DB-10 | TT | **Chế độ màn hình lớn** (kiosk) cho màn hình treo tường ở Trung tâm | Mở toàn màn hình, tự làm mới, chữ đọc được từ 3m |

> **`QĐ-06` — ĐÃ CHỐT (31/07/2026): năng suất duyệt là số liệu CÔNG KHAI.** Mọi người dùng đăng nhập
> đều xem được bảng năng suất theo từng cán bộ (có tên); `admin`/quản trị hệ thống thêm phần **tổng thể
> toàn Trung tâm**. Đây là quyết định của Trung tâm, đội phát triển hiện thực theo.
>
> *Hai điều bắt buộc kèm theo, vì minh bạch số liệu chỉ có ích khi số liệu được đọc đúng:*
> 1. **Ghi chú mục đích ngay trên trang** — số liệu vận hành để cân đối công việc, không phải bảng
>    xếp hạng thi đua. Tài liệu có độ khó rất khác nhau (một công văn 2 trang so với một khóa luận
>    200 trang), nên số tài liệu/ngày **không so sánh trực tiếp được** giữa các cán bộ.
> 2. **Hiện kèm bối cảnh, không chỉ hiện số đếm** — số trang đã duyệt và tỉ lệ trường phải sửa, để
>    người đọc thấy được khối lượng thật thay vì chỉ thấy số tài liệu.

---

## 9. Nhóm đề xuất chủ động

Bốn nhóm dưới đây **không nằm trong 4 mục bạn liệt kê**, nhưng phát hiện trong quá trình rà mã nguồn.
Xếp theo mức khuyến nghị.

### 9.1 YC-RV — Không gian duyệt tài liệu ⭐ *khuyến nghị cao nhất*

**Vì sao:** API đã sẵn sàng từ tháng 7 (`GET /api/v2/jobs?needs_review=true`, `POST .../restore`),
`metadata_fields.confidence` đã có, `ConfidenceBadge` đã có. **Chỉ thiếu trang giao diện.** Đây là
công việc còn nợ có tỉ lệ giá trị/công sức cao nhất trong toàn bộ danh sách: mọi thứ khác đã trả tiền
rồi, chỉ chưa dùng được.

| Mã | Ưu tiên | Yêu cầu |
|---|---|---|
| YC-RV-01 | BB | Trang `/duyet` — danh sách tài liệu `needs_review`, sắp theo độ ưu tiên & thời gian chờ |
| YC-RV-02 | BB | Màn hình duyệt hai cột: PDF bên trái, trường metadata bên phải; **tô màu trường điểm tin cậy thấp** (YC-CF-04) |
| YC-RV-03 | BB | Bàn phím tắt để duyệt nhanh (chuyển trường, chấp nhận, tài liệu tiếp theo) — cán bộ duyệt hàng trăm tài liệu/tuần |
| YC-RV-04 | BB | Nút **Xác nhận** ghi `audit_log` action `confirm` với `actor` thật; sau xác nhận mới được đẩy DSpace |
| YC-RV-05 | BB | Trang **thùng rác** `/thung-rac`: xem tài liệu đã xóa mềm, phục hồi, xóa vĩnh viễn (chỉ `admin`, có xác nhận hai bước + ghi audit) |
| YC-RV-06 | NC | Duyệt hàng loạt: chọn nhiều tài liệu điểm tin cậy cao → xác nhận một lần (có xác nhận rõ ràng) |
| YC-RV-07 | NC | Phân công: gán tài liệu cho cán bộ cụ thể (`documents.assigned_to`) |
| YC-RV-08 | NC | Nối `/luoc-do` vào `/api/v2/schemas` — bỏ dữ liệu mẫu đang hiển thị |

### 9.2 YC-TB — Thông báo & cảnh báo

**Vì sao:** worker chết lúc 2h sáng thì 8h sáng mới có người phát hiện — cả một đêm xử lý mất trắng.
`system_events` đã ghi nhận sự cố nhưng **không ai được báo**.

| Mã | Ưu tiên | Yêu cầu |
|---|---|---|
| YC-TB-01 | BB | Kênh thông báo cắm được: `log` (mặc định), `email` (SMTP nội bộ), `webhook` (n8n/Telegram) — interface trước, hiện thực sau (mẫu YC-MP-08) |
| YC-TB-02 | BB | Cảnh báo hạ tầng: không còn worker sống > N phút, mất Redis/PostgreSQL, đĩa dưới ngưỡng, hàng đợi vượt ngưỡng |
| YC-TB-03 | NC | Cảnh báo nghiệp vụ: lô xử lý xong, lô có tỉ lệ lỗi vượt ngưỡng, tài liệu quá hạn SLA |
| YC-TB-04 | NC | **Chống spam cảnh báo**: gộp và giới hạn tần suất — một sự cố kéo dài gửi một lần, không gửi mỗi phút |
| YC-TB-05 | NC | Người dùng tự chọn nhận cảnh báo nào (`notification_preferences`) |
| YC-TB-06 | BB | **Cảnh báo phải chạy được khi ngắt Internet** — SMTP nội bộ hoặc webhook nội mạng; không phụ thuộc dịch vụ đám mây (YC-BM-02) |

### 9.3 YC-VH-07→12 — Vận hành dài hạn *(mở rộng nhóm YC-VH sẵn có)*

| Mã | Ưu tiên | Yêu cầu | Vì sao |
|---|---|---|---|
| YC-VH-07 | BB | **Sao lưu tự động** `pg_dump` theo lịch + sao lưu thư mục tài liệu; giữ N bản, kiểm tra tính toàn vẹn | YC-VH-05 mới là yêu cầu, chưa có hiện thực. Không có sao lưu = một lệnh sai là mất toàn bộ |
| YC-VH-08 | BB | **Diễn tập khôi phục có tài liệu hóa** — khôi phục vào môi trường tạm, đối chiếu số bản ghi | Sao lưu chưa từng khôi phục thử thì chưa phải là sao lưu |
| YC-VH-09 | BB | **Dọn dữ liệu theo tuổi**: tệp trung gian trong `/data/digitization/jobs`, log, sự kiện, tài liệu xóa mềm quá N ngày (purge phải có phê duyệt của `admin` + audit) | Đĩa sẽ đầy. Đây là câu hỏi *khi nào*, không phải *có xảy ra không* |
| YC-VH-10 | NC | **CI**: GitHub Actions chạy `pytest` + `npm run build` mỗi push | 224 test hiện chỉ chạy khi ai đó nhớ chạy |
| YC-VH-11 | NC | **Kiểm thử E2E** (Playwright) cho 5 luồng chính: đăng nhập, tải lên, duyệt, đẩy DSpace, xem báo cáo | Lỗi `Content-Length` đã sửa ở commit `3663eaf` thuộc loại chỉ E2E mới bắt được |
| YC-VH-12 | NC | **Trang trợ giúp tiếng Việt trong ứng dụng** (YC-VH-04) — hướng dẫn theo vai trò | Cán bộ mới tự làm được không cần kèm |

### 9.4b YC-SC-09 — Đoán loại tài liệu tự động

**Vấn đề.** Từ khi có 7 lược đồ biên mục (`docs/CATALOG_SCHEMAS.md`), chọn sai loại tài liệu nghĩa là
trích xuất theo sai lược đồ — sai từ gốc, cán bộ phải gõ lại toàn bộ metadata. Nhưng bắt chọn tay
từng tệp trong lô 500 tệp thì không ai làm nổi; thực tế mọi tệp sẽ đi với loại mặc định `book`.

| Mã | Ưu tiên | Yêu cầu | Tiêu chí nghiệm thu |
|---|---|---|---|
| YC-SC-09 | BB | **Đoán loại tài liệu ba tầng**: (1) từ TÊN TỆP ngay khi chọn tệp, (2) từ NỘI DUNG sau khi OCR, (3) hỏi model chỉ khi hai tầng trên chưa đủ tự tin | Tệp `KL_NguyenVanA.pdf` → gợi ý "Khóa luận" ngay trước khi tải lên; tệp tên vô nghĩa nhưng nội dung là công văn → sau OCR nhận đúng "Công văn" |
| YC-SC-10 | BB | **Gợi ý phải GIẢI THÍCH ĐƯỢC**: trả về đúng những dấu hiệu đã khớp, không chỉ một điểm số | Giao diện hiện "Gợi ý: Luận văn thạc sỹ · 82% — thấy: «luan van thac si», «nguoi huong dan khoa hoc»" |
| YC-SC-11 | BB | **Người luôn thắng máy**: dropdown loại tài liệu ở màn hình tải lên, màn hình lô và màn hình duyệt; cán bộ chọn tay thì KHÔNG đoán lại | Chọn "Sách" cho một tệp → worker dùng lược đồ Sách kể cả khi nội dung giống công văn |
| YC-SC-12 | BB | **Lưu tách biệt ý kiến máy và kết luận người** (`detected_type` vs `document_type`) để ĐO được độ chính xác | Trang thống kê hiện "đúng 87% trên 340 tài liệu đã duyệt" + bảng nhầm lẫn thường gặp |
| YC-SC-13 | BB | **Mặc định an toàn khi đoán loại**: chưa biết độ nhạy cảm thì KHÔNG gửi văn bản ra đám mây chỉ để hỏi "đây là loại gì" — chỉ hỏi model TẠI CHỖ | Cấu hình chỉ có công cụ đám mây → tầng 3 bị bỏ qua, chỉ dùng đối sánh từ khóa |
| YC-SC-14 | NC | Bản quét MẤT DẤU vẫn nhận ra được (đối sánh trên bản đã bỏ dấu) | OCR ra "luan van thac si" không dấu → vẫn đoán đúng |

**Vì sao đối sánh từ khóa trước, không gọi model ngay:** chạy được khi ngắt mạng; kiểm thử được không
cần dịch vụ ngoài (CI bắt được hồi quy); không tốn chi phí trên mỗi tài liệu của lô hàng nghìn tệp;
và giải thích được — một điểm số trần trụi thì không cán bộ nào dám tin.

---

### 9.4c YC-TT — Thống kê theo người dùng & quản trị

**Vấn đề.** `dashboard.staff_workload` (sprint V6) chỉ đếm hai hành động của việc duyệt trong 7 ngày.
Nó trả lời "hôm nay ai duyệt nhiều", đủ để chia việc — nhưng không trả lời được: *người này đã làm
những gì*, *toàn Trung tâm tháng này ra sao*, và *có dấu hiệu bất thường nào không*.

| Mã | Ưu tiên | Yêu cầu | Tiêu chí nghiệm thu |
|---|---|---|---|
| YC-TT-01 | BB | **Thống kê theo từng cán bộ**: tải lên, duyệt, số trang, số trường đã sửa, đẩy DSpace, đăng nhập — gộp từ cả 4 lớp nhật ký | Mở trang thống kê thấy một dòng cho mỗi cán bộ, đủ 7 cột |
| YC-TT-02 | BB | **Hồ sơ một người**: phân bố theo ngày, theo loại tài liệu, và 50 thao tác gần nhất | Bấm vào tên cán bộ → mở hồ sơ, thấy được người làm đều mỗi ngày hay dồn cuối tháng |
| YC-TT-03 | BB | **Mỗi người xem được thống kê CỦA CHÍNH MÌNH** không cần quyền báo cáo | Tài khoản `viewer` gọi `/api/v2/stats/me` → 200 |
| YC-TT-04 | BB | **Tổng quan quản trị** kèm số liệu AN NINH (đăng nhập hỏng, IP dò mật khẩu, số lần bị từ chối quyền) — cần quyền `USER_MANAGE`, KHÔNG phải `REPORT_READ` | Tài khoản `librarian` gọi `/api/v2/stats/admin` → 403 kèm thông báo tiếng Việt |
| YC-TT-05 | BB | **Cảnh báo tính sẵn ở backend**, không để giao diện tự đặt ngưỡng | Một IP thử ≥3 tài khoản → cảnh báo mức "nguy hiểm" ghi rõ địa chỉ IP |
| YC-TT-06 | BB | **Ngưỡng kép (số tuyệt đối VÀ tỉ lệ)** để hệ thống mới ít dữ liệu không báo động giả | Hệ thống có 1 lần đăng nhập hỏng trên 2 lần thử → KHÔNG cảnh báo |
| YC-TT-07 | BB | **Ghi chú cách đọc (QĐ-06) nằm TRONG dữ liệu backend trả về**, giao diện luôn hiển thị | Ẩn cột nào cũng được, nhưng dòng "không phải bảng xếp hạng thi đua" không bị cắt |
| YC-TT-08 | NC | **Độ chính xác đoán loại tài liệu** đo trên việc thật + bảng nhầm lẫn thường gặp | Chưa có tài liệu nào được duyệt → hiện "chưa đủ dữ liệu", KHÔNG hiện 0% |

> **QĐ-06 được giữ nguyên hiệu lực.** Số liệu theo người là để **cân đối công việc**, không phải bảng
> xếp hạng thi đua. Vì vậy cột *số trang* luôn đứng cạnh cột *số tài liệu*: một công văn 2 trang và
> một khóa luận 200 trang đều là "1 tài liệu".

---

### 9.4 YC-TK — Tích hợp & tài khoản dịch vụ

| Mã | Ưu tiên | Yêu cầu |
|---|---|---|
| YC-TK-01 | NC | **API key** cho tài khoản dịch vụ: băm khi lưu, hiện đúng một lần khi tạo, thu hồi được, có thời hạn |
| YC-TK-02 | NC | Phạm vi quyền cho từng key (chỉ nạp tài liệu / chỉ đọc báo cáo) |
| YC-TK-03 | NC | **Webhook ra ngoài** khi tài liệu xong / lô xong — để n8n (đã có trong compose) tự động hóa bước sau |
| YC-TK-04 | TT | **Giới hạn tần suất** theo key và theo IP |
| YC-TK-05 | TT | Tài liệu API (OpenAPI có sẵn của FastAPI) + trang mô tả bằng tiếng Việt |

---

## 10. Ảnh hưởng tới các yêu cầu SRS sẵn có

Đợt nâng cấp này **đóng được ba khoảng trống của SRS** mà hiện chưa thể hiện thực:

| YC gốc | Trạng thái hiện tại | Được đóng bởi |
|---|---|---|
| YC-AU-02 "ghi rõ ai thực hiện" | ⚠️ Bảng đúng nhưng `actor` không tin cậy | YC-QT-11 (V3) |
| YC-DR-04 "chỉ quản trị viên đổi được độ nhạy cảm" | ❌ Không có khái niệm quản trị viên | YC-QT-01/03 (V3) |
| YC-RG-10 "kết quả tra cứu tuân theo phân quyền" | ❌ Chặn GĐ3 | YC-QT-03/09 (V3) |
| YC-CF-04 "giao diện tô màu trường điểm thấp" | ⚠️ Có thành phần, chưa có trang | YC-RV-02 (V8) |
| YC-VH-05 "sao lưu/khôi phục" | ❌ Chưa hiện thực | YC-VH-07/08 (V9) |
| YC-VH-06 "giám sát + cảnh báo" | ⚠️ Có giám sát, chưa có cảnh báo | YC-TB-02 (V8) |
| YC-MP-07 "chạy song song 2 provider so sánh" | ⚠️ Có ở harness, không có ở vận hành | YC-AN-06 (V2) |

**Không yêu cầu SRS nào bị thay thế hay hủy bỏ.** Sprint 7 của `ROADMAP.md` (Nhật ký kiểm toán +
Báo cáo/Dashboard) được **hấp thụ và mở rộng** bởi V2 + V7 — phần `audit_log` của Sprint 7 thực tế đã
làm xong từ GĐ2.

---

## 11. Rủi ro & cách giảm thiểu

| # | Rủi ro | Mức | Cách giảm thiểu |
|---|---|---|---|
| R-01 | **Bật xác thực làm gián đoạn công việc thật** của Trung tâm | Cao | Ba nấc `off → shadow → on` (mục 5.3); nấc `shadow` chạy ≥ 1 tuần; van lùi đổi biến môi trường |
| R-02 | Nhật ký chi tiết làm **phình cơ sở dữ liệu**, chậm sao lưu | Cao | Bốn lớp nhật ký tách bạch (mục 2.1); chi tiết kỹ thuật ra tệp; thời hạn lưu thiết kế **cùng lúc** với lúc tạo bảng, không để nợ |
| R-03 | Xử lý khối lượng lớn **làm đầy đĩa** máy chủ | Cao | YC-BU-05 kiểm tra trước khi nhận + YC-VH-09 dọn tệp trung gian + cảnh báo YC-TB-02 |
| R-04 | **Ôm quá phạm vi** — chính rủi ro SRS cảnh báo là lớn nhất | Cao | 9 sprint độc lập, mỗi sprint dùng được; ưu tiên BB trước, NC/TT cắt được mà không hỏng sprint |
| R-05 | Đổi hàng đợi sang `BLMOVE` gây lỗi ở đường đang chạy | Trung bình | Van lùi `QUEUE_MODE=blpop\|reliable`; chạy song song một tuần; test tái hiện được ca worker bị kill |
| R-06 | Số liệu độ chính xác YC-AN-05 **bị hiểu sai là đáp án chuẩn** | Trung bình | Bắt buộc hiện cỡ mẫu + ghi chú phương pháp trên giao diện; dưới 30 mẫu không hiện % |
| R-07 | Thống kê năng suất cá nhân gây **phản ứng tiêu cực** từ cán bộ | Trung bình | Chốt `QĐ-06` với Trung tâm trước khi làm; mặc định chỉ `admin` xem theo người |
| R-08 | Hạ tầng mới (JSONL, quét thư mục, cảnh báo) **cần Internet** — vi phạm YC-BM-02 | Trung bình | Mọi thành phần mới bắt buộc chạy nội mạng; kiểm thử ngắt mạng bổ sung `KT-BM-16` |
| R-09 | Mất mật khẩu quản trị viên → **khóa cả hệ thống** | Thấp | Lệnh CLI đặt lại mật khẩu chạy từ container (có ghi audit); tài liệu hóa trong `DEPLOY.md` |
| R-10 | Migration trên dữ liệu thật gây mất dữ liệu | Cao | Mọi migration chỉ `ADD COLUMN`/`CREATE TABLE`, không `DROP`/`ALTER TYPE`; chạy được nhiều lần; **bắt buộc `pg_dump` trước** |

---

## 12. Quyết định cần chốt trước khi lập trình

Đây là các quyết định kiến trúc **chưa chốt**. Theo quy ước dự án, mỗi quyết định khi được duyệt sẽ
viết thành ADR trong `docs/DECISIONS.md` (dự kiến ADR-010 → ADR-016) **trước khi** viết mã.

| Mã | Quyết định | Lựa chọn | Khuyến nghị của tôi |
|---|---|---|---|
| **QĐ-01** | Cơ chế phiên đăng nhập | (a) Phiên phía máy chủ + cookie HttpOnly · (b) JWT không trạng thái · (c) JWT + danh sách thu hồi | **(a)** — thu hồi được ngay, đơn giản, không cần quản lý khóa. Đơn vị một tổ chức, quy mô nhỏ, không cần JWT |
| **QĐ-02** | Nơi lưu phiên | (a) PostgreSQL · (b) Redis | **(a)** — Redis trong hệ này là hàng đợi, không cấu hình bền vững (`appendonly`); Redis restart là đăng xuất toàn bộ. Số phiên rất nhỏ, PG thừa sức |
| **QĐ-03** | Hạ tầng log | (a) Tệp JSONL + API đọc · (b) Loki + Grafana · (c) Cả hai (Loki là profile tùy chọn) | **(c)** — mặc định (a) để giữ air-gapped và đơn giản; (b) bật thêm khi Trung tâm cần |
| **QĐ-04** | Băm mật khẩu | (a) Argon2id · (b) bcrypt | **(a)** nếu `argon2-cffi` cài được trong image; **(b)** là phương án lùi an toàn, đã kiểm chứng rộng |
| **QĐ-05** ✅ | Bốn mắt: người tải lên có được tự duyệt? | (a) Được · (b) Không · (c) Cấu hình được | **ĐÃ CHỐT 31/07/2026: (c) với mặc định (a)** — quyền duyệt do **phân quyền** quyết định, không do quan hệ sở hữu. `REQUIRE_SEPARATE_APPROVER=0`. → ADR-012 |
| **QĐ-06** ✅ | Ai xem được năng suất theo từng cán bộ | (a) Mọi người · (b) Chỉ `admin` · (c) `admin` + bản thân | **ĐÃ CHỐT 31/07/2026: (a) công khai** — mọi người xem được theo từng cán bộ; `admin` thêm phần tổng thể. Kèm 2 ràng buộc hiển thị ở mục 8 |
| **QĐ-07** | Nạp khối lượng lớn: đường chính | (a) Upload nhiều file qua trình duyệt · (b) Thư mục theo dõi trên máy chủ · (c) Cả hai | **(c)**, làm (a) trước — (b) phù hợp hơn với lô hàng nghìn tài liệu và tận dụng FileBrowser đã có trong compose |
| **QĐ-08** | Thời hạn lưu mặc định | — | Kiểm toán nghiệp vụ: **vĩnh viễn** · Hành vi người dùng: **365 ngày** · Sự cố hạ tầng: **90 ngày** · Log kỹ thuật: **14 ngày**. Tất cả cấu hình được |

---

## 13. Ngoài phạm vi đợt này

Ghi rõ để tránh hiểu nhầm — các hạng mục sau **không** làm trong đợt nâng cấp này:

- **Đa đơn vị (multi-tenant)/RLS** — sản phẩm là single-tenant theo `CLAUDE.md`. Nếu sau này bán cho
  trường khác thì mỗi trường một bản cài riêng.
- **Lớp RAG (YC-RG)** — vẫn thuộc GĐ3 theo `ROADMAP.md`. Đợt này chỉ **chuẩn bị điều kiện**: phân
  quyền (YC-QT) là tiền đề bắt buộc của YC-RG-10.
- **Trình soạn lược đồ cho người không lập trình (YC-SC-05/06/07)** — thuộc GĐ2 Sprint 6, giữ nguyên
  ở đó. Đợt này chỉ nối `/luoc-do` vào API thật (YC-RV-08).
- **Ứng dụng di động** — giao diện web đáp ứng (responsive) là đủ cho nghiệp vụ tại chỗ.
- **Đa ngôn ngữ giao diện** — người dùng là cán bộ Nhà trường, tiếng Việt là đủ.

---

## 14. Tài liệu liên quan

| Tài liệu | Nội dung |
|---|---|
| `docs/UPGRADE_SPRINTS.md` | **Chia sprint chi tiết** V1–V9: việc, thứ tự, DoD, van lùi, rollback |
| `docs/UPGRADE_TEST_CASES.md` | **Bộ trường hợp kiểm thử** + ma trận truy vết YC ↔ KT ↔ Sprint |
| `docs/REQUIREMENTS.md` | Yêu cầu gốc từ SRS (YC-MP, MS, DR, SC, CF, RG, AU, PC, BM, PL, VH) |
| `docs/ROADMAP.md` | Lộ trình tổng GĐ0–GĐ3 + nhánh nâng cấp này |
| `docs/DECISIONS.md` | ADR-001→009 đã chốt; ADR-010→016 sẽ viết khi duyệt các `QĐ-*` ở mục 12 |
| `docs/STATUS.md` | Trạng thái bàn giao hiện tại |
| `docs/05_Dac_ta_yeu_cau_phan_mem.docx` | SRS gốc — nguồn nghiệp vụ chuẩn |
| `docs/06_Ke_hoach_kiem_thu.docx` | Kế hoạch kiểm thử gốc (KT-CN/BM/CX/HN/KH/PL) |
