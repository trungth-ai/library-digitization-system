# DECISIONS.md — Architecture Decision Records (ADR)

> Ghi mọi quyết định kiến trúc lớn của DocuFlow HP. **ADR mới nhất ở đầu.**
> Format: Status · Date · Context · Decision · Rationale · Consequences · Alternatives.

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
   DeepSeek, Mistral). `GeminiProvider` bổ sung một định dạng dây khác hẳn.
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
