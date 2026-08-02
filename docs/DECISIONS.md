# DECISIONS.md — Architecture Decision Records (ADR)

> Ghi mọi quyết định kiến trúc lớn của DocuFlow HP. **ADR mới nhất ở đầu.**
> Format: Status · Date · Context · Decision · Rationale · Consequences · Alternatives.

---

## ADR-012: Danh tính & phân quyền — phiên phía máy chủ, bật theo ba nấc
**Status:** Accepted · **Date:** 2026-07-31 · **Decided by:** Người phụ trách (QĐ-05, QĐ-06) + đội phát triển

**Context:** Rà mã nguồn tại commit `50dd3bd` phát hiện **backend không có một cơ chế xác thực nào**:
`scripts/api.py` không có `Depends` xác thực, và `actor` là **query param** mặc định `"api"`
(`api.py:703`, `api.py:743`). Hệ quả không phải chỉ là tiện ích:

- Bất kỳ ai vào được mạng nội bộ đều xóa/sửa được tài liệu.
- `audit_log` đã đúng về thiết kế (bất biến, có trigger chặn) nhưng cột `actor` **không có nguồn tin
  cậy** → **YC-AU-02 "ghi rõ ai thực hiện" hiện KHÔNG thỏa mãn** dù bảng đã sẵn sàng từ GĐ2.
- **YC-DR-04** ("chỉ quản trị viên đổi được độ nhạy cảm" — yêu cầu **BB của GĐ1**) và **YC-RG-10**
  ("tra cứu tuân theo phân quyền" — GĐ3) **không thể hiện thực** khi chưa có khái niệm người dùng.

Ràng buộc chi phối: hệ thống **đang phục vụ thật** tại Trung tâm Thông tin Thư viện. Bật xác thực
sai cách sẽ làm gián đoạn công việc, và không ai biết hết những chỗ đang gọi API (script cá nhân,
luồng n8n, tab trình duyệt mở từ tuần trước).

**Decision:**
1. **Phiên phía máy chủ + cookie `HttpOnly`** (QĐ-01), **lưu trong PostgreSQL** (QĐ-02) — không JWT,
   không lưu phiên trong Redis. Lý do Redis: trong hệ này Redis là **hàng đợi**, không bật
   `appendonly`; Redis restart sẽ đăng xuất toàn bộ người dùng. Số phiên rất nhỏ (một Trung tâm),
   PostgreSQL thừa sức và cho **thu hồi phiên ngay lập tức** — điều JWT không trạng thái không làm được.
2. **Ba nấc bật `AUTH_MODE=off → shadow → on`**, đổi bằng biến môi trường, **không build lại image**.
   Nấc `shadow` phục vụ request thiếu xác thực **nhưng ghi cảnh báo** kèm endpoint + IP + user-agent.
   Điều kiện chuyển sang `on`: **0 cảnh báo trong 48 giờ liên tiếp**. Đây là điểm quan trọng nhất của
   ADR này — xem Rationale.
3. **Bốn vai trò** `admin` / `approver` / `librarian` / `viewer` + loại tài khoản `service`.
   Quyền lưu **dạng dữ liệu** trong `roles` + `role_permissions` (cùng triết lý YC-SC-01: cấu hình
   được, không phải hằng số trong mã).
4. **QĐ-05: quyền duyệt do phân quyền quyết định, KHÔNG do quan hệ sở hữu.** Ai có
   `document:approve` thì duyệt được mọi tài liệu, **kể cả tài liệu do chính mình tải lên**. Cấu hình
   `REQUIRE_SEPARATE_APPROVER` được hiện thực nhưng **mặc định `0`**. Hệ quả: kiểm tra quyền là **một**
   phép thử (`require("document:approve")`), không phải phép thử kép "có quyền VÀ không phải người tải lên".
5. **QĐ-06: năng suất duyệt là số liệu công khai** — mọi người dùng đăng nhập xem được theo từng cán bộ;
   `admin` thêm phần tổng thể. Bắt buộc hiện kèm **bối cảnh** (số trang, tỉ lệ trường phải sửa) và ghi
   chú "số liệu vận hành, không phải xếp hạng thi đua", vì tài liệu có độ khó rất khác nhau nên số
   tài liệu/ngày không so sánh trực tiếp được.
6. **Cưỡng chế ở máy chủ, không ở giao diện.** Ẩn nút là tiện ích. Có một test **liệt kê tự động** mọi
   route POST/PUT/PATCH/DELETE và khẳng định từng route có dependency phân quyền — test này **hỏng khi
   thêm endpoint mới mà quên gắn**, đó chính là mục đích của nó.
7. **Nền tảng xác thực cắm được** (`AUTH_BACKEND=local|ldap|oidc`) — viết interface trước, hiện thực
   `local` trước. Cùng mẫu đã dùng thành công cho lớp provider (YC-MP-08): thêm LDAP/AD của Nhà trường
   về sau chỉ cần một lớp hiện thực, không sửa lớp gọi.
8. **`actor` lấy từ `contextvars`**, không truyền qua tham số. Một chỗ duy nhất được điền → `audit_log`,
   `model_calls`, nhật ký người dùng tự có tên thật mà không phải sửa từng nơi gọi.

**Rationale:** Nấc `shadow` là phần đắt nhất về thời gian và cũng là phần **không được rút gọn**. Câu
hỏi "còn chỗ nào đang gọi API mà chưa biết?" không trả lời được bằng phỏng đoán hay bằng đọc mã — chỉ
trả lời được bằng cách chạy thật và đo. Bỏ nấc này thì gần như chắc chắn có một luồng công việc bị chặn
đột ngột, và niềm tin của cán bộ vào hệ thống mất nhanh hơn nhiều so với thời gian tiết kiệm được.

Về QĐ-05: chốt bốn mắt là kiểm soát tốt về nguyên tắc, nhưng Trung tâm hiện ít nhân sự — áp mặc định
sẽ tạo ra tình huống tài liệu không ai duyệt được, và cách người dùng vượt qua rào cản đó (dùng chung
tài khoản) tệ hơn nhiều so với việc không có rào cản.

**Consequences:** ✅ Đóng ba khoảng trống SRS: YC-AU-02, YC-DR-04, YC-RG-10.
✅ `audit_log` ghi tên thật → nhật ký kiểm toán có giá trị giải trình.
✅ Thu hồi phiên tức thời; khóa tài khoản sau N lần sai.
✅ Van lùi `AUTH_MODE=off` khôi phục hành vi trước đây mà không cần rollback DB (bảng mới không ảnh
hưởng đường cũ).
⚠️ Cần chạy migration `003_users_rbac.sql`.
⚠️ **Phải chạy nấc `shadow` ≥ 1 tuần trước khi bật `on`** — bỏ bước này là rủi ro vận hành, không phải
tiết kiệm thời gian.
⚠️ Mất mật khẩu quản trị sẽ khóa cả hệ thống → có lệnh CLI cứu hộ chạy từ trong container, có ghi audit.
⚠️ `LoginForm.jsx` hiện là đăng nhập **DSpace**, không phải DocuFlow. Hai thứ phải giữ tách bạch và
đặt tên rõ trên giao diện ("Đăng nhập DocuFlow" / "Kết nối DSpace"), nếu trộn sẽ làm cán bộ nhầm mật khẩu.

**Alternatives:** (a) **JWT không trạng thái** — không thu hồi được phiên ngay, phải thêm danh sách
thu hồi (tức là lại có trạng thái), và cần quản lý khóa; không đáng cho một tổ chức đơn lẻ. (b) **Lưu
phiên trong Redis** — Redis ở đây là hàng đợi không bền vững, restart là đăng xuất toàn bộ. (c) **Bật
xác thực một lần (không có nấc `shadow`)** — nhanh hơn vài ngày nhưng đánh cược vào giả định "đã biết
hết chỗ gọi API", giả định này không kiểm chứng được trước khi bật. (d) **Dùng luôn tài khoản DSpace
làm tài khoản DocuFlow** — buộc mọi cán bộ phải có tài khoản DSpace (không đúng thực tế: người quét
tài liệu không cần quyền DSpace), và làm DocuFlow phụ thuộc vào DSpace sống mới đăng nhập được.

---

## ADR-011: Hàng đợi tin cậy — `BLMOVE` + thu hồi việc mồ côi, thay cho `BLPOP`
**Status:** Accepted · **Date:** 2026-07-31 · **Decided by:** Đội phát triển

**Context:** `worker.py:223` dùng `redis.blpop(REDIS_QUEUE)`. `BLPOP` lấy job **ra khỏi** hàng đợi rồi
job chỉ tồn tại trong bộ nhớ tiến trình worker trong **toàn bộ** thời gian xử lý — với OCR hai pha
150→120 DPI, đó là vài phút cho một tài liệu vài trăm trang. Trong cửa sổ đó, nếu worker bị `kill`,
OOM, hay `docker compose restart`, **job biến mất im lặng**: không có trong hàng đợi, không có worker
nào xử lý, và tài liệu treo mãi ở "Chờ xử lý" mà không ai biết vì sao.

Ở quy mô hiện tại (trần 10 tệp/lần, xử lý theo đợt nhỏ, có người ngồi canh) lỗi này gần như không
gặp. Ở quy mô đang chuẩn bị (lô hàng trăm tệp chạy đêm) thì xác suất gặp là **gần như chắc chắn** —
và đúng lúc không có ai ngồi canh.

Ngoài ra hàng đợi hiện tại không có: thử lại, hàng đợi chết, ưu tiên. Một tài liệu lẻ mà cán bộ đang
chờ sẽ nằm sau 500 tệp của lô chạy đêm.

**Decision:**
1. **`BLMOVE` thay `BLPOP`**: job được chuyển **nguyên tử** từ hàng đợi sang danh sách đang-xử-lý
   riêng của từng worker (`worker:processing:{worker_id}`). Job **luôn** nằm ở đúng một chỗ — hàng đợi
   hoặc danh sách đang-xử-lý — không bao giờ chỉ nằm trong RAM. Hoàn tất mới `LREM` khỏi danh sách đó.
2. **Ưu tiên bằng cách đặt tên khóa, giữ tương thích ngược:** `{base}:high`, **`{base}` (mức normal —
   chính là khóa đang dùng hôm nay)**, `{base}:low`. Nghĩa là mọi thứ đang đẩy vào `digitization_jobs`
   tiếp tục chạy đúng, được coi là mức normal. Tương thích ngược **do cấu trúc**, không do lớp chuyển đổi.
3. **Thăm dò không chặn theo thứ tự ưu tiên, rồi chặn trên mức normal.** Khi cả ba hàng đợi rỗng thì
   `BLMOVE` chặn trên khóa normal với `BLPOP_TIMEOUT`. Đánh đổi được ghi nhận rõ: job `high` đến trong
   lúc đang chặn có thể chờ tối đa `BLPOP_TIMEOUT` (5s) — **chỉ khi hệ thống đang rỗi**. Redis không có
   `BLMOVE` nhiều khóa, và 5s khi rỗi là cái giá rẻ so với việc thăm dò liên tục làm nóng Redis.
4. **Thu hồi việc mồ côi dựa trên nhịp tim đã có** (ADR-009): quét `worker:processing:*`, worker nào
   **không còn khóa nhịp tim** (TTL 60s) thì trả job của nó về hàng đợi bằng `RPUSH` (vào đầu bên phải
   = được nhận ngay lượt sau, vì `BLMOVE` lấy từ bên phải) + ghi `system_events` `kind='job_reclaimed'`.
5. **Thử lại có khoảng lùi qua ZSET `{base}:delayed`** (score = thời điểm đến hạn), **không phải bằng
   cách cho worker ngủ**. Worker ngủ để chờ thử lại là biến một job lỗi thành một worker bị chiếm dụng.
6. **Phân biệt lỗi hạ tầng với lỗi tài liệu.** Mất Redis/PostgreSQL/công cụ mô hình → thử lại. PDF hỏng,
   tệp không tồn tại, vi phạm ràng buộc độ nhạy cảm (`SensitivityViolation`) → **vào hàng đợi chết ngay**,
   không thử lại 3 lần vô ích. Thử lại một tài liệu hỏng chỉ tốn thời gian và làm nhiễu nhật ký.
7. **Van lùi `QUEUE_MODE=blpop`** khôi phục chính xác vòng lặp cũ.
8. **Job phải idempotent.** Điều kiện để (4) an toàn. Đã thỏa mãn sẵn: `save_metadata` dùng
   `ON CONFLICT (document_id, key, value) DO NOTHING`, và `_update_status` là ghi đè trạng thái.

**Rationale:** Đây là **lỗi mất dữ liệu**, không phải thiếu tính năng — nên nó không thể chờ tới khi
làm phần khối lượng lớn. `BLMOVE` là mẫu chuẩn (reliable queue) của Redis cho đúng vấn đề này, và
điều kiện tiên quyết của nó — biết worker nào còn sống — **đã có sẵn** từ ADR-009. Nói cách khác:
phần khó đã làm xong từ trước, phần còn lại chỉ là dùng nó đúng chỗ.

Chọn thứ tự khóa `{base}` = mức normal (thay vì tạo `{base}:normal` mới) là quyết định nhỏ nhưng bỏ đi
được toàn bộ nhu cầu di trú dữ liệu và toàn bộ nguy cơ "job nằm trong khóa cũ mà không worker nào đọc".

**Consequences:** ✅ Khởi động lại máy chủ giữa lúc chạy lô không mất tài liệu nào.
✅ Job lỗi có nơi để nhìn thấy (hàng đợi chết có lý do tiếng Việt) thay vì biến mất.
✅ Tài liệu lẻ không bị kẹt sau lô chạy đêm.
✅ Đẩy được sang phần khối lượng lớn (V5/V6) mà không phải làm lại.
⚠️ Hàng đợi chết nằm trong Redis (không bền vững) → **bản ghi có thẩm quyền vẫn là `documents` trong
PostgreSQL** với `status='failed'` + `error_message`; danh sách trong Redis chỉ để tiện chạy lại.
⚠️ Thêm một tiến trình nền (thu hồi) chạy trong worker khi rỗi — không thêm container.
⚠️ Trễ tối đa 5s cho job `high` khi hệ thống đang rỗi (mục 3).

**Alternatives:** (a) **Giữ `BLPOP`, chấp nhận mất job** — không chấp nhận được với hệ đang phục vụ
thật. (b) **Celery/RQ/Dramatiq** — có sẵn mọi thứ này, nhưng thêm một phụ thuộc lớn vào hệ đang chạy
ổn, và trái nguyên tắc "bổ sung không viết lại"; chi phí di trú cao hơn nhiều so với ~200 dòng mã.
(c) **`LPOS`/khóa riêng cho từng job** — phức tạp hơn mà không nguyên tử bằng. (d) **Hàng đợi trong
PostgreSQL (`SELECT FOR UPDATE SKIP LOCKED`)** — bền vững hơn thật, nhưng đánh đổi bằng việc bỏ hẳn
Redis pub/sub đang dùng cho SSE, và biến một sửa lỗi thành một lần viết lại.

---

## ADR-010: Ghi tệp tải lên không chặn event loop, băm trong cùng một lượt đọc
**Status:** Accepted · **Date:** 2026-07-31 · **Decided by:** Đội phát triển

**Context:** `save_upload_file` (`api.py:142`) dùng `shutil.copyfileobj` — **đồng bộ** — và được gọi
bên trong `async def` (`api.py:206` và `api.py:257`). Trong suốt thời gian ghi một tệp xuống đĩa,
event loop của FastAPI **bị chặn hoàn toàn**: SSE của mọi client đang mở bị ngắt, mọi request khác
treo. Một tệp 200 MB trên đĩa chậm là vài giây API "chết". `batch_upload` ghi tuần tự tối đa 10 tệp
trong **một** request, nên hiệu ứng cộng dồn.

Đây là loại lỗi không ai báo: nó biểu hiện thành "giao diện thỉnh thoảng chậm" và "SSE hay bị đứt",
không thành thông báo lỗi.

**Decision:**
1. **Ghi theo mảnh, mỗi mảnh qua `run_in_threadpool`.** Đọc `await upload_file.read(CHUNK)` (bất đồng
   bộ, sẵn có của Starlette), ghi trong thread pool → event loop luôn rảnh giữa các mảnh.
2. **Băm SHA-256 trong CÙNG lượt đọc**, và **cùng lời gọi thread pool** với phép ghi. Hai lý do:
   không đọc tệp lần thứ hai chỉ để băm, và `hashlib.update` trên mảnh 1 MB tốn vài ms CPU — đủ để
   không nên chạy trên event loop. Hash này là điều kiện của việc chống trùng tài liệu (YC-BU-04) ở
   V5, nên làm luôn: lấy nó **miễn phí** khi đã đang đọc tệp, đắt hơn nhiều nếu thêm sau.
3. **Trả về `(sha256, số_byte)`** để nơi gọi ghi được `file_hash`/`file_size` — chưa dùng ngay ở
   sprint này nhưng không phải đọc lại tệp về sau.
4. **Giữ nguyên `save_upload_file` cũ** (đánh dấu deprecated) — có nơi khác và có test đang dùng;
   xóa đi là vi phạm "bổ sung không viết lại" mà không đổi lấy gì.
5. **Kích thước mảnh cấu hình được** (`UPLOAD_CHUNK_MB`, mặc định 1 MB) — đủ nhỏ để event loop mượt,
   đủ lớn để không tạo quá nhiều lượt chuyển thread.

**Rationale:** Sửa đúng chỗ, không đổi kiến trúc. Phần khó là **nhận ra** đây là lỗi; bản vá chỉ vài
chục dòng. Việc gộp băm vào cùng lượt đọc là ví dụ của nguyên tắc "làm cái rẻ khi đang mở đúng tệp
đó" — tách ra làm sau sẽ tốn một lượt đọc toàn bộ tệp cho mỗi tài liệu.

**Consequences:** ✅ SSE không còn bị ngắt khi có người tải tệp lớn; API phản hồi trong suốt quá trình
ghi. ✅ Có sẵn `file_hash` cho chống trùng ở V5 mà không cần đọc lại tệp. ✅ Không đổi giao diện API
(ADR-003 — endpoint cũ giữ nguyên định dạng phản hồi).
⚠️ Thông lượng ghi một tệp đơn lẻ có thể **giảm nhẹ** do chi phí chuyển thread mỗi mảnh — đánh đổi có
chủ đích: đổi một chút thông lượng của người đang tải lấy khả năng phục vụ của toàn hệ thống. Cần **đo**
ở `KT-HN-08`, không tuyên bố trước.

**Alternatives:** (a) **`aiofiles`** — thêm một phụ thuộc để làm đúng việc `run_in_threadpool` đã làm
được. (b) **Ghi toàn bộ trong một lời gọi thread pool** (`copyfileobj` trong threadpool) — đơn giản
hơn, nhưng không có cơ hội băm theo mảnh và không cho theo dõi tiến độ về sau. (c) **Chuyển endpoint
upload sang `def` đồng bộ** để Starlette tự đẩy vào thread pool — sửa được việc chặn, nhưng mất
`await upload_file.read()` và làm endpoint lệch mẫu với phần còn lại của `api.py`.

---

## ADR-009: Theo dõi vận hành — sự kiện hạ tầng tách khỏi nhật ký kiểm toán
**Status:** Accepted · **Date:** 2026-07-29 · **Decided by:** Đội phát triển

**Context:** Ba lần liên tiếp khi deploy, triệu chứng đều là **sự im lặng**: tài liệu treo ở "Chờ xử lý"
(không có worker), "Failed to fetch" (không rõ URL nào), "Failed to push" (không rõ bước nào). Mỗi lần
đều mất một vòng trao đổi chỉ để biết chuyện gì đang xảy ra. Song song đó, log worker ngập traceback
`redis.exceptions.TimeoutError: Timeout reading from socket` — một chuyện **bình thường** bị báo như lỗi.

**Decision:**
1. **`BLPOP` hết giờ chờ KHÔNG phải lỗi.** redis-py áp thời hạn đọc socket theo chính `timeout` của
   lệnh chặn, nên phản hồi "hàng đợi rỗng" về chậm một nhịp là ném `TimeoutError`. Client tạo với
   `socket_timeout=None` (bắt buộc cho lệnh chặn) + `socket_keepalive` + `health_check_interval=30`,
   và vòng lặp bắt riêng `TimeoutError` → `continue` không ghi lỗi, không ngủ.
   `_redis_exception_classes()` là hàm module-level để test dựng được tình huống này trên máy không
   cài redis — nếu để lấy lớp ngoại lệ ngay trong `run()` thì đúng lỗi production lại không test được.
2. **Bảng `system_events` TÁCH KHỎI `audit_log`.** Audit ghi thao tác **nghiệp vụ** của con người và
   bất biến (YC-AU-03); `system_events` ghi sự cố **hạ tầng**. Trộn vào một bảng sẽ làm nhật ký kiểm
   toán bị nhiễu bởi mỗi lần Redis chớp mạng, và nhật ký kiểm toán thì không được xóa.
3. **Ghi theo LẦN ĐỔI trạng thái, không ghi mỗi vòng.** Mỗi 5 giây một dòng sẽ làm bảng vô dụng. Cái
   người vận hành cần là "mất lúc nào, nối lại lúc nào" → có thêm `status='resolved'`. Lần quan sát
   đầu tiên mà kết nối bình thường thì **không** báo "đã nối lại" — chưa mất thì không có gì để nối
   lại (test bắt được lỗi này của bản đầu).
4. **Thời gian xử lý đo phần worker THỰC SỰ làm** (`duration_ms` + `stage_timings`), không dùng
   `finished_at - created_at` vì con số đó gồm cả thời gian nằm chờ hàng đợi — nói về tải hệ thống chứ
   không nói về hiệu năng. Báo cáo dùng **p50/p95**, không chỉ trung bình: một tài liệu 500 trang kéo
   trung bình lên và che mất thực tế của phần lớn tài liệu.
5. **`/api/v2/health/detailed` trả tình trạng TỪNG thành phần** (Redis, PostgreSQL, worker, công cụ
   mô hình) kèm lý do tiếng Việt. Khi hệ thống im lặng, câu hỏi thật là *cái nào* đang hỏng — một chữ
   "ok" chung không trả lời được.
6. **Trường chưa đo được để `None`, không để 0.** `workers_alive: null` nghĩa là không đọc được Redis;
   `0` nghĩa là chắc chắn không có worker nào. Hai điều đó dẫn tới hai hành động khác nhau.

**Rationale:** Chi phí lớn nhất trong ba lần deploy vừa rồi không phải sửa lỗi mà là **tìm ra lỗi gì**.
Đầu tư vào khả năng quan sát rẻ hơn nhiều so với mỗi sự cố lại mất một vòng trao đổi — và với hệ thống
mà người vận hành không phải người viết mã, thông báo đọc được chính là điều kiện để họ tự xử lý.

**Consequences:** ✅ Hết ngập log lỗi giả, job được nhận nhanh hơn (không còn ngủ 2s mỗi vòng).
✅ Tra được lịch sử sự cố sau khi log container đã bị cắt vòng. ✅ Có số liệu hiệu năng thật cho hồ sơ
(YC-HN) lấy từ vận hành, không cần chạy harness riêng. ✅ 224 pytest + 21 kiểm chứng PostgreSQL thật +
17 kiểm chứng trang theo dõi trên Next server thật.
⚠️ Cần chạy `database/migrations/002_monitoring.sql` trên DB đã tồn tại.
⚠️ `system_events` sẽ lớn dần — chưa có cơ chế dọn theo tuổi (xem PLAN.md).

**Alternatives:** (a) Ghi sự cố hạ tầng vào `audit_log` — làm nhiễu nhật ký bất biến, bị loại; (b) đặt
`socket_timeout` bằng một giá trị lớn hơn `BLPOP timeout` — vẫn còn cửa sổ đua, và không diễn tả được
ý "lệnh chặn thì không có thời hạn đọc"; (c) dùng Prometheus/Grafana cho toàn bộ theo dõi — hạ tầng
nặng cho một đội hai người, và `grafana` đã có sẵn ở profile `extras` nếu sau này cần.

---

## ADR-008: Nối pipeline vào lớp provider + xóa mềm + dự phòng chỉ trong cùng chế độ
**Status:** Accepted · **Date:** 2026-07-26 · **Decided by:** Đội phát triển

**Context:** ADR-004 cố ý hoãn việc nối lớp provider vào pipeline để bảo vệ hệ đang chạy. Hệ quả là
`docker compose` đổi `MODEL_PROVIDER` **không đổi được hành vi của worker** — worker vẫn gọi thẳng
`AIMetadataExtractor` (bám Claude). Lớp trừu tượng hóa chỉ dùng được qua `run_eval`. Cùng lúc còn 4
món nợ: `delete_job` xóa cứng (vi phạm chuẩn HPU), thiếu `updated_at`, chưa đo tài nguyên (YC-MS-07),
chưa có giao diện xem công cụ đang dùng (YC-MS-08). Chủ sản phẩm xác nhận sẽ khởi tạo lại dữ liệu nên
cho phép đổi schema.

**Decision:**
1. **Tiêm, không viết lại:** `DigitizationPipeline(metadata_extractor=...)` nhận bộ trích metadata bất
   kỳ có `extract(pdf_path) -> Dict`. `ProviderMetadataExtractor` (`core/extraction.py`) đi qua lược
   đồ (DB) → ngữ cảnh theo `context_strategy` → định tuyến độ nhạy cảm → lớp chất lượng → truy vết.
   Dublin Core giữ ĐÚNG 10 trang/6000 ký tự của hệ cũ, có test chốt (KT-KH).
2. **Van lùi `USE_PROVIDER_LAYER=0`** đưa worker về đường cũ mà không cần build lại image. Đây là van
   vận hành, không phải cờ tính năng dài hạn.
3. **Dự phòng chéo công cụ CHỈ trong cùng chế độ triển khai.** vLLM chết → Ollama: được. Ollama chết →
   Claude: **không bao giờ**, kể cả tài liệu Công khai. Một container chết không được phép âm thầm đổi
   nơi dữ liệu đi qua; nếu vượt chế độ thì YC-DR-03 chỉ đúng lúc bình thường và sai đúng lúc bất
   thường. Không cấu hình dự phòng thì KHÔNG tốn lần gọi health nào.
4. **Xóa mềm giữ cả file:** `delete_document` đổi `status='deleted'`, PDF/OCR và metadata **giữ nguyên**
   (bản PDF đã OCR là phần dữ liệu giá trị nhất). Xóa vật lý tách thành `purge_document` +
   `DELETE ...?purge=true`, ghi audit TRƯỚC khi xóa. Có `restore_document` — xóa mềm mà không có đường
   về thì chỉ là hình thức.
5. **`needs_review` là cờ RIÊNG, không phải một `status`:** tài liệu có thể `completed` (OCR xong) mà
   vẫn cần cán bộ kiểm tra. Gộp vào `status` sẽ khiến cán bộ tưởng tài liệu lỗi và OCR lại vô ích.
6. **Bảng `model_calls`** ghi provider/model/latency/RAM/GPU/dự phòng mỗi lần gọi (YC-MP-06 truy vấn
   được + YC-MS-07). Đo RAM bằng `/proc/self/status` → `getrusage` → None, KHÔNG thêm `psutil`; GPU chỉ
   khi bật `METRICS_GPU`. Trường chưa đo được để **None, không bịa 0**.
7. **`SensitivityViolation` không bị nuốt:** `DigitizationPipeline.process` bắt riêng và re-raise, vì
   "hệ thống từ chối vì bảo mật" khác hẳn "tài liệu lỗi" và người vận hành phải phân biệt được.
8. **Logic hiển thị tách khỏi `api.py`** (`core/provider_view.py`) để test được không cần FastAPI —
   nơi này quyết định việc không lộ khóa API, phải có test.

**Rationale:** (1) Lớp trừu tượng hóa chỉ có giá trị khi đường xử lý thật đi qua nó; (2) mọi thay đổi
đều có van lùi hoặc kiểm thử chốt, nên rủi ro cho hệ đang chạy vẫn thấp; (3) hai nguyên tắc "không mất
tài liệu" và "ràng buộc cứng độ nhạy cảm" xung đột ở nhánh lỗi — giải bằng cách: mọi lỗi khác đều xử lý
tiếp + đánh dấu xem lại, **chỉ** vi phạm độ nhạy cảm mới được làm job thất bại.

**Consequences:** ✅ Đổi `MODEL_PROVIDER` giờ đổi thật hành vi worker. ✅ Mỗi tài liệu biết được trích
bằng công cụ/model nào (`documents.extraction_*`, `model_calls`, `audit_log`). ✅ 198 pytest + **39
kiểm chứng trên PostgreSQL 17 thật** + 23 kiểm chứng chuỗi trích xuất ghi DB thật. ✅ UI build exit 0.
⚠️ **Cần chạy `database/migrations/001_*.sql`** trên DB đã tồn tại — `init.sql` KHÔNG chạy lại khi
volume đã có (đã kiểm: áp 2 lần không lỗi, dữ liệu cũ nguyên vẹn).
⚠️ `metadata.json` xuất ra có thêm khối `extraction` (thêm khóa, không đổi khóa cũ).
⚠️ Nợ mới: chưa có nút "phục hồi"/thùng rác trên UI (API đã có), chưa có trang duyệt tài liệu
`needs_review` (đã có cờ + bộ lọc API).

**Alternatives:** (a) Sửa thẳng `AIMetadataExtractor` để gọi provider — trộn hai trách nhiệm, mất
đường lùi, bị loại; (b) dự phòng vượt chế độ khi tài liệu Công khai — làm ràng buộc cứng thành "mềm
khi có sự cố", bị loại; (c) xóa mềm nhưng vẫn xóa file — phục hồi ra tài liệu trỏ vào hư không, bị loại;
(d) thêm `psutil` để đo RAM — thêm phụ thuộc vào đường air-gapped (ADR-006), bị loại.

---

## ADR-007: Bảng đăng ký nhiều công cụ mô hình — tách `name` (công cụ) khỏi `deployment` (chế độ)
**Status:** Accepted · **Date:** 2026-07-25 · **Decided by:** Đội phát triển

**Context:** ADR-001/002 đã dựng lớp trừu tượng hóa và chọn Ollama cho GĐ0. Nhưng khi hiện thực,
`factory.get_provider(kind)` chỉ nhận `kind ∈ {cloud, local}`, trong đó `"cloud"` **thực chất nghĩa là
Claude** và `"local"` **nghĩa là Ollama**. Cùng lúc đó `router.resolve_mode()` cũng trả về đúng hai chuỗi
ấy, nhưng ở đó chúng mang nghĩa **chế độ triển khai** (cơ sở của ràng buộc cứng YC-DR-03).

Hai khái niệm khác nhau bị trộn vào một chuỗi → hệ quả: thêm công cụ thứ ba (vLLM) là **thêm được vào
factory nhưng làm vỡ định tuyến** — router không bao giờ trả về `"vllm"`, và không có chỗ nào biết
`"vllm"` là máy trong phòng máy chủ hay dịch vụ thuê ngoài. Nói cách khác, thiết kế cũ vẫn ngầm khóa vào
**hai** nhà cung cấp thay vì một — đúng cái bẫy mà ADR-001 muốn tránh.

**Decision:**
1. `ModelProvider` tách hai thuộc tính: `name` = **công cụ** (`claude`, `ollama`, `vllm`, `gemini`...),
   `deployment` = **chế độ** (`cloud` | `local`). Ràng buộc cứng YC-DR-03 chỉ dựa vào `deployment`.
   Mặc định của `deployment` là `cloud` (mặc định an toàn: lớp con chưa khai báo thì bị coi là "ra ngoài").
2. `registry.py` là **bảng đăng ký** công cụ. Thêm lựa chọn = thêm một dòng; chỉ khi gặp giao thức mới
   mới cần thêm một lớp `ModelProvider`.
3. `textgen.TextGenProvider` gom logic trích xuất/dự phòng/nhật ký dùng chung → lớp con chỉ hiện thực
   `_complete(prompt) -> str`.
4. `OpenAICompatProvider` phủ cả họ giao thức tương thích OpenAI: **tại chỗ** (vLLM, llama.cpp,
   LM Studio, TGI, cổng `/v1` của Ollama) và **đám mây** (OpenAI, Azure, Groq, OpenRouter, Together,
   DeepSeek, Mistral, **Moonshot/Kimi**, **DashScope/Qwen**). `GeminiProvider` bổ sung một định dạng dây
   khác hẳn. Bảng đăng ký có **bí danh thương hiệu** (`kimi`→`moonshot`, `qwen`→`dashscope`) vì cán bộ
   nhớ tên model chứ không nhớ tên công ty; nhật ký vẫn ghi tên nhà cung cấp chuẩn.
5. `MODEL_PROVIDER` nhận tên công cụ; hai bí danh `cloud`/`local` trỏ tới `CLOUD_PROVIDER`/`LOCAL_PROVIDER`
   → cấu hình đang chạy không phải sửa gì, và router chỉ cần quyết định chế độ.
6. **Chốt an toàn mới:** provider khai báo `local` mà điểm cuối không thuộc dải mạng nội bộ thì factory
   **từ chối khởi tạo** (mở bằng `ALLOW_PUBLIC_LOCAL_ENDPOINT=1` nếu đường truyền đã được kiểm soát).
   Router cũng từ chối nếu `LOCAL_PROVIDER` lại là một công cụ đám mây.

**Rationale:** (1) "Không khóa nhà cung cấp" chỉ có thật khi lựa chọn thứ ba **rẻ như lựa chọn thứ hai**;
(2) một điểm cuối tương thích OpenAI có thể ở trong hay ngoài tổ chức — suy diễn từ tên công cụ là sai,
phải khai báo tường minh; (3) ràng buộc cứng YC-DR-03 trước đây tin vào một chuỗi mà **cấu hình có thể
làm sai nghĩa** — nay có hai lớp phòng vệ độc lập; (4) so sánh nhiều công cụ trong một lần chạy
`run_eval` cho phép chọn công cụ GĐ1 bằng số liệu (YC-MP-07) chứ không bằng cảm tính.

**Consequences:** ✅ Thêm công cụ tại chỗ/đám mây = 1 dòng cấu hình. ✅ Ollama trở thành một lựa chọn
bình thường, ADR-002 hết vai trò "khóa mềm". ✅ Nhật ký YC-MP-06 nay phân biệt được công cụ *và* chế độ.
✅ 112/112 kiểm thử đạt, gồm kiểm thử không hồi quy đường Claude (KT-KH).
⚠️ **Breaking (nội bộ):** `provider.name` đổi `"cloud"→"claude"`, `"local"→"ollama"`. Giá trị này đi vào
log và JSON kết quả `run_eval` → số liệu đo trước 25/07/2026 dùng tên cũ. `CloudProvider`/`LocalProvider`
vẫn là bí danh lớp nên mã cũ import được.
⚠️ Chưa hiện thực Vertex AI / AWS Bedrock (cần thư viện xác thực SigV4/GCP, trái nguyên tắc "không thêm
phụ thuộc cho chế độ tại chỗ") — dùng qua `openai_compat` nếu có cổng tương thích.

**Alternatives:** (a) Thêm `elif kind == "vllm"` vào factory — làm vỡ router, bị loại; (b) suy diễn
`deployment` từ URL — sai với tên miền nội bộ hợp lệ, chỉ dùng làm **chốt kiểm tra** chứ không làm nguồn
sự thật; (c) dùng SDK `openai`/`google-generativeai` — kéo thêm phụ thuộc vào đường chạy air-gapped
(ADR-006), bị loại, dùng `urllib` như `LocalProvider`.

---

## ADR-006: Bỏ Google Fonts (dùng system font) + hardening để deploy air-gapped
**Status:** Accepted · **Date:** 2026-07-21 · **Decided by:** Đội phát triển

**Context:** UI dùng `next/font/google` (Geist) → `next build` tải font từ Google lúc build. Trên
`node:20-alpine` (thiếu ca-certificates) hoặc server **air-gapped** (đúng kịch bản chế độ tại chỗ),
docker build **fail**. Kèm vài lỗi deploy khác: UI healthcheck gọi `/api/health` không tồn tại, thiếu
`.dockerignore` (lộ `.env` vào image), `Dockerfile.api` healthcheck `import requests` (thiếu dependency),
`install.sh` ghi đè `database/init.sql` bằng schema legacy.

**Decision:** Bỏ `next/font/google`, dùng **system font** (`system-ui...`) — trùng đúng design system HPU.
Thêm route `/api/health`; thêm `.dockerignore` (root + ui) chặn secret/rác; healthcheck `Dockerfile.api`
dùng `urllib` (stdlib); dọn `next.config.mjs`; `install.sh` KHÔNG ghi đè init.sql.

**Rationale:** (1) Build chạy được air-gapped/alpine — nhất quán triết lý "chạy tại chỗ, không phụ thuộc
mạng ngoài"; (2) không lộ khóa API vào image; (3) hệ deploy `docker compose up` chạy được.

**Consequences:** ✅ `npm run build` không cần mạng/TLS-flag (verify exit 0). ✅ Không lộ secret.
⚠️ `NEXT_PUBLIC_*` vẫn cần truyền qua **build-args** khi build UI image (xem `docs/DEPLOY.md` mục 4).

**Alternatives:** Self-host file font Geist (`next/font/local`) — thêm asset, không cần vì HPU dùng system font;
thêm `ca-certificates` vào alpine + giữ Google font — vẫn fail khi air-gapped, bị loại.

---

## ADR-005: Lazy import pypdf & anthropic trong digitize.py
**Status:** Accepted · **Date:** 2026-07-18 · **Decided by:** Đội phát triển

**Context:** `digitize.py` import `pypdf` và `anthropic` ở top-level → không import được module ở môi
trường chưa cài 2 gói này, cản trở viết unit/regression test cho tầng logic (build_metadata) và lớp provider.

**Decision:** Chuyển 2 import thành lazy (vào trong hàm dùng chúng: `PDFTextExtractor.extract`,
`AIMetadataExtractor.__init__`).

**Rationale:** (1) Hành vi runtime không đổi khi deps có mặt; (2) cho phép test tầng logic + provider
ở dev tối giản; (3) giảm coupling — provider tái dùng logic cũ mà không kéo theo deps nặng lúc import.

**Consequences:** ✅ Test được không cần cài anthropic/pypdf; regression test bảo chứng không hồi quy.
⚠️ Import chậm hơn một chút ở lần gọi đầu (không đáng kể).

**Alternatives:** Cài deps global ở dev (nặng, vẫn coupling) — bị loại.

---

## ADR-004: GĐ 0 KHÔNG đụng pipeline production — provider layer + harness đo đạc
**Status:** Accepted · **Date:** 2026-07-18 · **Decided by:** Đội phát triển

**Context:** SRS cảnh báo rủi ro lớn nhất GĐ0 là *ôm quá phạm vi*; nguyên tắc "bổ sung không viết lại"
yêu cầu hệ đang chạy không được gián đoạn. Hạn hồ sơ 30/7 rất gần.

**Decision:** Ở GĐ 0 chỉ xây **lớp trừu tượng hóa mô hình** (provider layer) + **harness đo đạc** để so
sánh 2 chế độ (KT-CX). **Không** thay `metadata_extractor` trong worker/pipeline production. Việc tích
hợp "chế độ tại chỗ dùng được trong vận hành" để **GĐ 1**.

**Rationale:** (1) Đủ để tạo bằng chứng + số liệu cho hồ sơ (mục tiêu GĐ0); (2) giữ hệ production an
toàn tuyệt đối; (3) đúng phân kỳ SRS.

**Consequences:** ✅ Không rủi ro cho người dùng hiện tại. ✅ Vẫn có số liệu POC. ⚠️ Chế độ tại chỗ
chưa dùng trong vận hành thật cho tới GĐ1 (đúng kế hoạch).

**Alternatives:** Tích hợp thẳng vào worker ngay GĐ0 — rủi ro cho hệ đang chạy + vượt phạm vi, bị loại.

---

## ADR-003: Giữ endpoint API cũ, code mới dùng envelope HPU, di trú dần
**Status:** Accepted · **Date:** 2026-07-18 · **Decided by:** Đội phát triển

**Context:** Chuẩn HPU bắt buộc envelope `{status,data,message}`, nhưng API hiện tại trả JSON thô và
frontend đang chạy phụ thuộc định dạng đó. Đổi đồng loạt = breaking change.

**Decision:** Endpoint cũ (`/api/v1/process`, `/api/v2/*`) **giữ nguyên**. Mọi endpoint/module **mới**
dùng `core/responses.py` (envelope HPU). Di trú endpoint cũ dần khi cập nhật UI tương ứng.

**Rationale:** Không phá UI đang chạy (nguyên tắc "bổ sung không viết lại") mà vẫn hội tụ dần về chuẩn.

**Consequences:** ✅ An toàn. ⚠️ Tạm thời tồn tại 2 định dạng — chấp nhận trong giai đoạn chuyển tiếp.

**Alternatives:** Refactor toàn bộ về envelope ngay (rủi ro cao) / bỏ chuẩn HPU (mất tính nhất quán) — đều loại.

---

## ADR-002: Ollama là công cụ model-serving tại chỗ cho GĐ 0 (thay được qua cấu hình)
**Status:** Accepted (bổ sung bởi **ADR-007**: Ollama nay chỉ là MỘT dòng trong bảng đăng ký; vLLM,
llama.cpp, LM Studio, TGI đã dùng được ngay bằng cấu hình) · **Date:** 2026-07-18 · **Decided by:** Đội phát triển

**Context:** GĐ0 cần một công cụ phục vụ mô hình tại chỗ để đo đạc. SRS (mục 2.2.1): giai đoạn kiểm
chứng chọn công cụ **dựng nhanh nhất**, không tối ưu hiệu năng; và công cụ phải **thay được**.

**Decision:** Dùng **Ollama** cho GĐ0. `LocalProvider` gọi Ollama qua HTTP (`urllib`, không thêm dep).
Có thể đổi công cụ khác (vLLM...) chỉ bằng viết một lớp `ModelProvider` mới + cấu hình (YC-MP-08).

**Rationale:** Ollama dựng nhanh, chạy CPU, air-gapped được; đủ cho mục tiêu "có số liệu trong 2 tuần".

**Consequences:** ✅ Nhanh có POC. ⚠️ Chưa tối ưu thông lượng — sẽ đo và cân nhắc công cụ khác ở GĐ1+
theo 4 tiêu chí kích hoạt chuyển đổi (SRS 2.2.1). **Chưa chốt mô hình cụ thể tới khi rà xong giấy phép (YC-PL).**

**Alternatives:** vLLM (thông lượng cao, dựng phức tạp hơn) — để cân nhắc GĐ1 nếu nghẽn; llama.cpp — dự phòng.

---

## ADR-001: Kiến trúc hai chế độ qua lớp trừu tượng hóa mô hình (interface trước, công cụ sau)
**Status:** Accepted · **Date:** 2026-07-18 · **Decided by:** Đội phát triển

**Context:** Hệ thống phụ thuộc hoàn toàn mô hình đám mây → không xử lý được tài liệu nhạy cảm, không
chạy khi mất mạng, chi phí tăng tuyến tính. Cần bổ sung chế độ tại chỗ mà không khóa vào một nhà cung cấp.

**Decision:** Định nghĩa giao diện `ModelProvider` (`extract_fields`/`embed`/`health`); toàn hệ thống
chỉ gọi model qua giao diện này. Viết **giao diện TRƯỚC**, chọn công cụ SAU (YC-MP). CloudProvider giữ
nguyên hành vi hiện tại; LocalProvider cho chế độ tại chỗ; đổi provider bằng cấu hình.

**Rationale:** (1) Gỡ phụ thuộc một nhà cung cấp — thay model = một lớp mới + cấu hình; (2) là "thứ duy
nhất có giá trị lâu dài" (SRS); (3) cho phép chạy song song 2 chế độ để so sánh (chế độ đánh giá).

**Consequences:** ✅ Không khóa nhà cung cấp; ✅ CloudProvider regression-verified giữ nguyên hành vi;
✅ mở đường cho định tuyến độ nhạy cảm (YC-DR) và RAG (`embed`). ⚠️ Thêm một lớp trừu tượng (chi phí nhỏ).

**Alternatives:** Viết mã bám thẳng Ollama (nhanh trước mắt, khóa công cụ, phải viết lại sau) — SRS gọi
đây là "cái bẫy phổ biến nhất", bị loại.
