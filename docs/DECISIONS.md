# DECISIONS.md — Architecture Decision Records (ADR)

> Ghi mọi quyết định kiến trúc lớn của DocuFlow HP. **ADR mới nhất ở đầu.**
> Format: Status · Date · Context · Decision · Rationale · Consequences · Alternatives.

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
**Status:** Accepted · **Date:** 2026-07-18 · **Decided by:** Đội phát triển

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
