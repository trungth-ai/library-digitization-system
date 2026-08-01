# DocuFlow HP — Lộ trình nâng cấp (chia Sprint)

> Bám sát 4 giai đoạn trong SRS (mục IV) và mốc cuộc thi, chia nhỏ thành sprint ~1–2 tuần.
> Mỗi sprint gắn mã yêu cầu **YC-*** (SRS) và mã kiểm thử **KT-*** (test plan) làm Definition of Done.
> Nguyên tắc xuyên suốt: *bổ sung không viết lại*, *kiểm thử không hồi quy (KT-KH) trước khi coi là xong*.

## Tổng quan giai đoạn ↔ mốc cuộc thi

| GĐ | Thời gian | Mục tiêu | Mốc |
|---|---|---|---|
| **GĐ 0** | 16–29/7/2026 | POC có đo đạc (chế độ tại chỗ chạy được + số liệu) | **Hạn hồ sơ 30/7** |
| GĐ 1 | 8–9/2026 | Chế độ tại chỗ dùng được trong vận hành | Bán kết T9 |
| GĐ 2 | 10–11/2026 | Lược đồ cấu hình được + Kiểm toán/Báo cáo | Chung kết T11 |
| **GĐ 2B** ⭐ | 8–11/2026 | **Nhánh nâng cấp vận hành & quản trị** (V0–V9) — đan xen với GĐ1/GĐ2 | xem `docs/UPGRADE_SPRINTS.md` |
| GĐ 3 | 12/2026–5/2027 | Lớp RAG & khai thác dữ liệu | Cam kết 6 tháng |

> **Cập nhật 25/7/2026 → đang trong GĐ 0, còn 5 ngày tới hạn hồ sơ.** Kỷ luật phạm vi GĐ 0 là ưu
> tiên số 1: SRS cảnh báo rủi ro lớn nhất là *ôm quá phạm vi* → GĐ 0 KHÔNG làm RAG, schema UI, routing
> tự động, confidence đầy đủ, audit đầy đủ.
>
> 📍 **Tiến độ thực tế** (đã vượt kế hoạch GĐ 0 ở phần lớp mô hình, xem `docs/STATUS.md` và
> `docs/PLAN.md`): phần code của GĐ 0 đã xong; đường găng còn lại là **số liệu đo thật + bằng chứng
> ngắt mạng + bảng giấy phép** — đều cần máy chủ và người phụ trách, không phải cần code.

---

## GĐ 0 — POC có đo đạc  *(gấp, ưu tiên tuyệt đối)*

### Sprint 0A — Lớp trừu tượng hóa mô hình + Log nền tảng  ⭐ BẮT ĐẦU TỪ ĐÂY
**Vì sao trước tiên:** SRS nói rõ "viết lớp trừu tượng hóa TRƯỚC, chọn công cụ SAU — đây là thứ DUY
NHẤT có giá trị lâu dài". Là việc code thuần, không cần phần cứng đặc biệt.
- YC-MP-01: interface `ModelProvider` (`extract_fields`, `embed`, `health`) — `scripts/providers/base.py`
- YC-MP-02: `CloudProvider` bọc logic Claude hiện tại — **giữ nguyên hành vi** (KT-KH-01, KT-CN-04)
- YC-MP-03: provider gọi công cụ tại chỗ — Ollama, **và** vLLM/llama.cpp/LM Studio/TGI (KT-CN-03)
- YC-MP-04: chọn provider qua cấu hình/`.env`, không sửa mã (KT-CN-05)
- YC-MP-06: **log mỗi lần gọi model** (provider/model/version/latency) — nền tảng "log chi tiết"
- YC-MP-05: dự phòng — provider lỗi → job vào trạng thái lỗi có mô tả, không mất dữ liệu (KT-CN-06)
- **Kéo sớm từ GĐ 1** (ADR-007, làm luôn vì rẻ khi lớp trừu tượng còn mới): YC-MP-08 phép thử thêm công
  cụ = một lớp nhỏ; YC-MS-05 model riêng cho từng tác vụ; YC-MS-06 thay công cụ bằng cấu hình.
- Nền tảng: `structured logging` + `request_id`/`job_id` tương quan; `scripts/core/responses.py` + `scripts/core/exceptions.py` (chuẩn HPU, cho code mới)
- **DoD:** cùng một tài liệu chạy được qua cả CloudProvider và LocalProvider bằng đổi cấu hình; test không hồi quy pass; có log gọi model truy vấn được.

### Sprint 0B — Model serving tại chỗ (Docker)
- YC-MS-01: thêm service model-serving vào compose, mạng nội bộ, **không mở cổng ngoài** (KT-BM-03)
- YC-MS-02: model lưu volume, không tải lại khi khởi động (KT-CN-02)
- YC-MS-03: **chạy khi ngắt Internet** (KT-BM-01 — bằng chứng cốt lõi, quay video)
- YC-MS-04: health check trước khi xử lý (KT-CN-01)
- **DoD:** một lệnh `docker compose up` bao gồm model serving; ngắt mạng, xử lý trọn 1 tài liệu thành công.

### Sprint 0C — Lược đồ công văn (thô) + Harness đo
- YC-SC-03 (bản thô, chấp nhận mã cứng): trường công văn (số hiệu, ngày, cơ quan, loại, trích yếu, độ khẩn, độ mật, nơi nhận, người ký)
- Harness đo độ chính xác theo công thức test plan mục 1.3 (KT-CX-01/02/03) — xuất bảng theo từng trường + cỡ mẫu
- Script kiểm thử không hồi quy trên tài liệu thư viện (KT-KH-01)
- Kịch bản chống ảo giác cơ bản (KT-CX-05)
- **DoD:** chạy được cả 2 chế độ trên tập kiểm thử, sinh bảng so sánh độ chính xác + thời gian.

### Sprint 0D — Hồ sơ (không code)  *(người phụ trách + tôi hỗ trợ)*
- YC-PL-01/03: bảng đối chiếu giấy phép model AI + thành phần nguồn mở (lưu ý Ghostscript) (KT-PL-01→05)
- Bộ ảnh + video demo ngắt mạng cho hồ sơ dự thi
- **DoD:** đủ 6 hạng mục nghiệm thu GĐ 0 (bảng 2.7 test plan).

---

## GĐ 1 — Chế độ tại chỗ dùng được  *(8–9/2026)*

| Sprint | Nội dung | YC | KT |
|---|---|---|---|
| **1** | ~~Hoàn thiện model abstraction~~ **phần lớn đã xong ở GĐ 0** (ADR-007). Còn lại: **YC-MS-07** đo tài nguyên (thời gian/RAM/GPU) mỗi lần gọi, **YC-MS-08** giao diện quản trị hiện công cụ/model + tình trạng (nay chỉ có ở CLI), **chính sách dự phòng chéo công cụ**, và **wire pipeline** (`worker.py` dùng router thay vì gọi trực tiếp — ADR-004) | YC-MS-07/08, YC-MP-07 | KT-CN-06b/c/d, KT-HN-03 |
| **2** | Định tuyến theo độ nhạy cảm — **ràng buộc cứng** không ghi đè | YC-DR-01→06 | KT-BM-05→10 |
| **3** | Điểm tin cậy từng trường + kiểm tra hợp lệ + thử lại + tô màu + **chống ảo giác** | YC-CF-01→05 | KT-CN-07→10, KT-CX-07/08 |
| **4** | Kiểm chứng bảo mật đầy đủ + hồ sơ pháp lý + ngưỡng hiệu năng | YC-BM-01→05, YC-PL đầy đủ, YC-PC-02/03 | KT-BM, KT-PL-06→09, KT-HN-02 |

**Nghiệm thu GĐ 1:** cán bộ xử lý tài liệu nhạy cảm bằng chế độ tại chỗ trong việc thật; giám sát
mạng chứng minh không rò dữ liệu; thử ghi đè thủ công bị từ chối; hệ thống cũ vẫn chạy.

---

## GĐ 2 — Lược đồ cấu hình được + Kiểm toán/Báo cáo  *(10–11/2026)*

| Sprint | Nội dung | YC | KT |
|---|---|---|---|
| **5** | Lược đồ dạng dữ liệu trong DB + di trú Dublin Core **không hồi quy** + quy tắc ngữ cảnh theo lược đồ | YC-SC-01/02/04 | KT-CN-18/19, KT-KH-04 |
| **6** | Giao diện quản trị tạo/sửa/nhân bản/xuất/nhập lược đồ (không cần lập trình) | YC-SC-05/06/07 | KT-CN-15/20/21 |
| **7** ⭐ | **Nhật ký kiểm toán bất biến + Báo cáo & Dashboard** *(trọng tâm "báo cáo, log chi tiết")* | YC-AU-01→06, YC-DR-06, YC-CF-06/07 | KT-CN-22→25, KT-BM-11 |
| **8** | Tài liệu hóa + đào tạo người thứ hai + hướng dẫn tiếng Việt | YC-VH-01→04 | KT-CN-16/17 |

**Sprint 7 chi tiết** (đáp ứng trực tiếp yêu cầu bổ sung của bạn):
- Bảng `audit_log` **append-only**, chặn UPDATE/DELETE bằng trigger + phân quyền (YC-AU-03, KT-BM-11)
- Ghi ai/khi nào/thao tác/giá trị cũ/mới/chế độ/model cho toàn vòng đời tài liệu (YC-AU-01/02/04)
- Kết xuất kiểm toán theo thời gian/người/tài liệu ra Excel (YC-AU-05)
- Dashboard: throughput OCR theo thời gian, tỉ lệ thành công/thất bại, tài liệu theo chế độ (YC-DR-06),
  tỉ lệ trường bị sửa theo lược đồ (YC-CF-07)

**Nghiệm thu GĐ 2 (phép thử quyết định):** người **không biết lập trình** tạo được lược đồ mới và
chạy thử thành công; nhật ký kiểm toán truy được trách nhiệm tới từng trường, không sửa được.

---

## GĐ 2B — Nhánh nâng cấp vận hành & quản trị  *(8–11/2026, đan xen GĐ1–GĐ2)* ⭐

> **Chi tiết đầy đủ nằm ở ba tài liệu riêng** (nhánh này lớn ngang một giai đoạn):
> `docs/UPGRADE_REQUIREMENTS.md` (yêu cầu) · `docs/UPGRADE_SPRINTS.md` (sprint) ·
> `docs/UPGRADE_TEST_CASES.md` (kiểm thử). Mục này chỉ tóm tắt để đọc lộ trình tổng.

**Vì sao có nhánh này:** rà mã nguồn tại commit `50dd3bd` phát hiện ba vấn đề của hệ đang chạy —
(N-01) **không có xác thực nào ở backend** nên `audit_log.actor` không tin cậy; (N-02) hàng đợi
`BLPOP` **mất việc** khi worker chết; (N-03) upload **chặn event loop**. Ba vấn đề này chặn cả việc
mở rộng quy mô lẫn việc nghiệm thu một số yêu cầu BB của SRS.

| Sprint | Nội dung | YC | KT | Tuần |
|---|---|---|---|---|
| **V0** | Chốt `QĐ-01→08`, viết ADR-010→016, sao lưu + khôi phục thử, chuẩn bị BD-06/07/08 | — | — | 03–04/8 |
| **V1** | Log hệ thống có cấu trúc (JSON, `request_id`, che bí mật, dọn theo tuổi, trang xem log) | YC-LG-01→11 | KT-LG | 1 |
| **V2** | Phân tích chi tiết kết quả AI (token, chi phí VNĐ, từng trường, chỉ số OCR, **độ chính xác đo trên việc thật**) | YC-AN-01→11 | KT-AN | 2–3 |
| **V3** ⚠️ | **Danh tính & phân quyền** — 4 vai trò, ba nấc `off→shadow→on` | YC-QT-01→12 | KT-QT, KT-BM-16→18 | 4–5 |
| **V4** | Nhật ký người dùng + dòng thời gian một tài liệu | YC-NK-01→09 | KT-NK | 7 |
| **V5** | Nạp khối lượng lớn: bỏ trần 10 tệp, lô, chống trùng, ZIP, thư mục theo dõi | YC-BU-01→10 | KT-BU-01→14 | 8–9 |
| **V6** | Hàng đợi tin cậy (`BLMOVE` + thu hồi + thử lại + hàng đợi chết + ưu tiên) | YC-BU-11→20 | KT-BU-15→26 | 10–11 |
| **V7** | Bảng điều khiển theo dõi công việc (việc của tôi, hàng đợi, lô, SLA) | YC-DB-01→10 | KT-DB | 12–13 |
| **V8** | Không gian duyệt tài liệu + thùng rác + thông báo/cảnh báo | YC-RV, YC-TB | KT-RV, KT-TB | 14–15 |
| **V9** | Sao lưu tự động + dọn dữ liệu + CI/E2E + tài khoản dịch vụ | YC-VH-07→12, YC-TK | KT-VH, KT-TK | 16 |

**Quan hệ với các giai đoạn khác:**
- **V3 mở nút cho GĐ 1:** `YC-DR-04` ("chỉ quản trị viên đổi được độ nhạy cảm") của Sprint 2 hiện
  **không thể hiện thực** vì chưa có khái niệm quản trị viên. Vì vậy V3 xếp trước Bán kết T9.
- **V2 + V7 hấp thụ Sprint 7 của GĐ 2** (Nhật ký kiểm toán + Báo cáo/Dashboard). Phần `audit_log`
  của Sprint 7 thực tế **đã làm xong**; phần báo cáo/dashboard được mở rộng đáng kể ở V2/V7.
- **V3 là tiền đề bắt buộc của GĐ 3:** `YC-RG-10` ("kết quả tra cứu tuân theo phân quyền") không
  làm được nếu không có phân quyền.

**Nghiệm thu GĐ 2B:** cán bộ đăng nhập bằng tài khoản riêng · nhật ký kiểm toán ghi **tên thật** ·
nạp được lô 500 tài liệu · **khởi động lại máy chủ giữa chừng không mất tài liệu nào** ·
bảng điều khiển trả lời được "hôm nay tôi phải làm gì" · dữ liệu được sao lưu **và đã khôi phục thử**.

---

## GĐ 3 — RAG & khai thác dữ liệu  *(12/2026–5/2027)*

| Sprint | Nội dung | YC | KT |
|---|---|---|---|
| **9** | `pgvector` trên PG hiện có + embedding tại chỗ + chia đoạn theo cấu trúc | YC-RG-01/02/03 | KT-CN-30 |
| **10** | RAG cho trích xuất: truy hồi ví dụ đã duyệt + cách ly dữ liệu | YC-RG-04/05 | KT-CX-09/10 |
| **11** | RAG cho tra cứu: hỏi ngôn ngữ tự nhiên + truy hồi kết hợp + **dẫn nguồn bắt buộc** + phân quyền | YC-RG-06→10 | KT-CN-26→29, KT-BM-12 |
| **12** | Hiệu năng RAG + vận hành đầy đủ (sao lưu, giám sát) | YC-PC-04/05, YC-VH-05/06 | KT-HN-05→07 |

**Nghiệm thu GĐ 3:** không câu trả lời nào thiếu dẫn nguồn; trả lời "không tìm thấy" khi không có
căn cứ; tra cứu chạy khi ngắt Internet; phân quyền tôn trọng trong mọi kết quả.

---

## Workstream xuyên suốt — Chuẩn hóa HPU  *(chèn vào sprint, không phá hệ đang chạy)*
Làm dần theo nguyên tắc "bổ sung không viết lại":
- **Code mới** dùng envelope `{status,data,message}` + `success/error/paginated` ngay (từ Sprint 0A).
- Sửa `delete_job` hard-delete → **soft delete** (khi chạm module đó) — YC an toàn dữ liệu.
- Bổ sung `updated_at` cho `documents`.
- UI dần theo design system `#1e3a5f` + sidebar 240px (khi làm giao diện mới: duyệt, báo cáo).
- Docker: healthcheck `service_healthy`, non-root user, backup pg_dump (khi đụng compose ở Sprint 0B).

## Định nghĩa "Hoàn thành" chung cho mọi sprint
- [ ] Code merged, không phá endpoint/UI đang chạy (KT-KH pass)
- [ ] Có kiểm thử tương ứng KT-* và **đã chạy đạt** (đo thật, không kỳ vọng)
- [ ] Tài liệu cập nhật (`PLAN.md`, `DECISIONS.md` nếu có quyết định lớn)
- [ ] Số liệu (nếu có) ghi kèm cỡ mẫu + phương pháp (nguyên tắc "đo được mới tuyên bố")

## Thứ tự đề xuất bắt đầu
**Sprint 0A** (model abstraction + log nền tảng) — đúng ưu tiên SRS, code được ngay, và giao luôn phần
"log chi tiết" mức nền tảng. Các sprint sau tuần tự theo bảng trên.
