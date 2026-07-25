# Hướng dẫn chế độ tại chỗ & chọn công cụ mô hình — DocuFlow HP

> Hướng dẫn tiếng Việt (YC-VH-04) để bật/kiểm chứng **chế độ xử lý tại chỗ** bằng mô hình mở, và để
> **đổi công cụ mô hình** bằng cấu hình (YC-MP-04, YC-MS-06).
>
> **Ollama không phải "chế độ tại chỗ" — nó là một trong các công cụ chạy chế độ đó.** Xem ADR-007.
> Mọi công cụ tại chỗ nằm trong profile Docker Compose riêng → `docker compose up` mặc định KHÔNG chạy
> cái nào, deploy hiện tại không bị ảnh hưởng.

## 1. Xem các công cụ khả dụng

```bash
python -m scripts.eval.run_eval --list-providers
```

| Chế độ | Công cụ | Ghi chú chọn công cụ |
|---|---|---|
| **Tại chỗ** | `ollama` | Dựng nhanh nhất, chạy CPU tốt. Lựa chọn của GĐ0 (ADR-002). |
| | `vllm` | Thông lượng cao nhất **khi có GPU**; dựng phức tạp hơn. Ứng viên cho GĐ1. |
| | `llamacpp` | Nhẹ nhất, ít RAM nhất, không cần GPU. Dùng file `.gguf` đặt sẵn → **air-gapped tuyệt đối**. |
| | `lmstudio` | Cán bộ thử nhanh trên máy cá nhân trước khi đưa lên máy chủ. |
| | `tgi` | Hugging Face text-generation-inference. |
| | `ollama_openai` | Chính máy chủ Ollama nhưng qua cổng `/v1` tương thích OpenAI. |
| **Đám mây** | `claude` | Đang vận hành thật từ 2025 — **mặc định**, giữ nguyên hành vi (YC-MP-02). |
| | `openai`, `azure_openai`, `gemini` | Nhà cung cấp lớn; dùng để so sánh chi phí/độ chính xác. |
| | `moonshot` (bí danh **`kimi`**) | Ngữ cảnh dài 32k/128k — phù hợp tài liệu OCR nhiều trang. |
| | `dashscope` (bí danh **`qwen`**) | Qwen bản dịch vụ. Cân nhắc: Qwen bản **mở** chạy tại chỗ được (mục 1b). |
| | `openrouter`, `groq`, `together`, `deepseek`, `mistral` | So sánh nhiều model NHANH mà chưa phải tự dựng máy chủ. |
| | `openai_compat` | Điểm cuối tương thích OpenAI chưa có trong bảng (vd dịch vụ trong nước). |

> Vùng dữ liệu: `moonshot` và `dashscope` mặc định dùng **điểm cuối quốc tế**. Bản Trung Quốc đổi bằng
> `MOONSHOT_BASE_URL` / `DASHSCOPE_BASE_URL` — đây là quyết định của Nhà trường, không phải mặc định
> kỹ thuật, và cần nêu trong ý kiến pháp lý về bảo vệ dữ liệu (YC-PL-06).

## 1b. Chọn MODEL — khác với chọn công cụ

Đây là chỗ dễ lẫn nhất. **Công cụ** (mục 1) là thứ *phục vụ* model; **model** là thứ chạy trên đó.
Nhiều tên quen thuộc là **model**, không phải công cụ → đã dùng được ngay, không cần thêm dòng nào:

```env
# Qwen tại chỗ (đang là mặc định của hệ thống)
LOCAL_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:7b

# Xiaomi MiMo tại chỗ — chỉ là một giá trị cấu hình
LOCAL_PROVIDER=vllm
VLLM_MODEL=XiaomiMiMo/MiMo-7B-RL
```

| Họ model | Chạy tại chỗ | Giấy phép (THAM KHẢO — phải xác minh) | Ghi chú kỹ thuật |
|---|---|---|---|
| **Qwen** (Alibaba) | ✅ `qwen2.5:7b`, `Qwen/Qwen2.5-7B-Instruct` | Nhiều bản Apache-2.0, **một số cỡ có giấy phép riêng** | Tiếng Việt khá; đang là mặc định của hệ thống |
| **Xiaomi MiMo** | ✅ `XiaomiMiMo/MiMo-7B-RL` | Xác minh trên model card | 7B → vừa cấu hình worker hiện tại |
| **DeepSeek** | ⚠️ chỉ bản **distill** | Bản distill theo giấy phép **model NỀN** (Qwen/Llama) | Xem cảnh báo dưới |
| **Kimi K2** (Moonshot) | ❌ không khả thi tại chỗ | Modified MIT (xác minh) | ~1000 tỉ tham số MoE — cần cụm nhiều GPU, không chạy trên máy chủ thư viện → dùng qua `kimi` (đám mây) |
| **Llama / Gemma** | ✅ | **CÓ ràng buộc**, không phải OSS thuần | Xem `docs/LICENSES.md` mục 1 |
| **PhoGPT / Vistral / SeaLLM** | ✅ | Rà tới model nền | Model tiếng Việt — đáng thử cho tài liệu tiếng Việt |

> ⚠️ **Bẫy giấy phép với DeepSeek:** `deepseek-r1:7b` / `:8b` trong Ollama **KHÔNG phải** DeepSeek-R1
> thật — chúng là bản **chưng cất (distill) từ Qwen hoặc Llama**. Hệ quả: (1) giấy phép phải truy về
> model nền, và nếu nền là Llama thì kèm ràng buộc của Llama Community License; (2) không được ghi
> "dùng DeepSeek-R1" trong hồ sơ. DeepSeek-V3/R1 bản đầy đủ là 671 tỉ tham số MoE → không chạy được
> trên hạ tầng hiện tại, muốn dùng thì qua dịch vụ `deepseek` (đám mây).

> 💡 **Trần phần cứng hiện tại:** worker được cấp 10 CPU / 12GB RAM, GPU tùy chọn. Trên CPU, model
> **7B lượng tử hóa 4-bit** (~5–6GB) là mức thực tế; 14B rất chật; từ 32B trở lên cần GPU. Chọn model
> theo trần này trước, đo độ chính xác sau — đừng chọn model không chạy nổi rồi mới đo.

> ⚠️ **Giấy phép trước, hiệu năng sau:** rà giấy phép model **TRƯỚC** khi tải/dùng và điền
> `docs/LICENSES.md` (YC-PL-01/02). Bảng trên là công cụ *phục vụ* model — giấy phép công cụ ≠ giấy phép model.

## 2. Bật một công cụ tại chỗ

Chỉ bật **một** công cụ tại một thời điểm để không tranh RAM/GPU.

```bash
# Lựa chọn 1 — Ollama (CPU, dựng nhanh nhất)
docker compose --profile local-ai up -d
docker compose exec ollama ollama pull qwen2.5:7b       # tải model 1 lần, lưu vào volume (YC-MS-02)
docker compose exec ollama ollama list

# Lựa chọn 2 — vLLM (cần GPU NVIDIA)
docker compose --profile local-ai-vllm up -d
# ⚠️ vLLM tải model từ Hugging Face lúc khởi động → LẦN ĐẦU cần mạng; sau đó model nằm trong volume.

# Lựa chọn 3 — llama.cpp (CPU, nhẹ nhất, không tải gì lúc khởi động)
docker cp ./model-da-ra-giay-phep.gguf library-llamacpp:/models/model.gguf
docker compose --profile local-ai-llamacpp up -d
```

## 3. Chọn công cụ (YC-MP-04) — chỉ sửa `.env`, KHÔNG sửa mã

```env
# Cách A — chỉ định thẳng công cụ
MODEL_PROVIDER=vllm
VLLM_BASE_URL=http://vllm:8000/v1
VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct

# Cách B — dùng bí danh theo chế độ (bắt buộc khi bật định tuyến theo độ nhạy cảm)
MODEL_PROVIDER=local        # hoặc cloud
LOCAL_PROVIDER=vllm         # công cụ đảm nhiệm chế độ tại chỗ
CLOUD_PROVIDER=claude       # công cụ đảm nhiệm chế độ đám mây
```

Quy ước biến môi trường đồng nhất cho **mọi** công cụ (`<TÊN>` là tên công cụ viết HOA):

| Biến | Ý nghĩa |
|---|---|
| `<TÊN>_BASE_URL` | điểm cuối (vd `LLAMACPP_BASE_URL=http://llamacpp:8080/v1`) |
| `<TÊN>_MODEL` | model trích xuất |
| `<TÊN>_EMBED_MODEL` | model embedding — **YC-MS-05**: tác vụ khác dùng model khác (vd `bge-m3`) |
| `<TÊN>_API_KEY` | khóa (dịch vụ đám mây); máy chủ tại chỗ thường không cần |
| `<TÊN>_DEPLOYMENT` | `cloud`\|`local` — ghi đè khi cùng công cụ được dựng ở nơi khác |

Tên biến cũ `OLLAMA_URL`, `LOCAL_MODEL`, `CLOUD_MODEL`, `CLAUDE_API_KEY` **vẫn dùng được** (không phá
cấu hình đang chạy).

## 4. Ràng buộc an toàn khi khai báo "tại chỗ" (YC-DR-03)

Ràng buộc cứng "tài liệu Nội bộ/Nhạy cảm KHÔNG BAO GIỜ ra đám mây" dựa vào **chế độ triển khai** của
công cụ, nên có hai chốt chặn cấu hình sai:

1. **Điểm cuối phải thực sự nội bộ.** Provider khai báo `local` mà `BASE_URL` không thuộc dải nội bộ
   (localhost, 10.x, 192.168.x, tên service Docker, `.local`/`.internal`) thì hệ thống **từ chối khởi
   tạo** kèm hướng dẫn xử lý. Nếu đường truyền đã được kiểm soát (VPN/đường riêng của Nhà trường):
   `ALLOW_PUBLIC_LOCAL_ENDPOINT=1`.
2. **`LOCAL_PROVIDER` phải là công cụ tại chỗ.** Đặt `LOCAL_PROVIDER=groq` chẳng hạn thì mọi tài liệu
   nhạy cảm sẽ bị **từ chối xử lý** (`SensitivityViolation`) thay vì âm thầm gửi ra ngoài.

## 5. So sánh công cụ bằng số liệu (YC-MP-07)

```bash
# Chạy nhiều công cụ trên CÙNG tập tài liệu + CÙNG đáp án chuẩn trong một lần
python -m scripts.eval.run_eval --data ./eval_data --truth ./eval_data/ground_truth.json \
    --schema book --providers claude,ollama,vllm --out ./eval_out
```
Kết quả JSON ghi kèm `provider` + `deployment` + `model` + cỡ mẫu → đây là cơ sở chọn công cụ cho GĐ1.
Nguyên tắc: **đo được mới tuyên bố**, không đưa con số chưa chạy vào hồ sơ.

## 6. Kiểm chứng bằng chứng cốt lõi cho hồ sơ dự thi

### KT-BM-01 — Chạy khi NGẮT Internet (YC-MS-03)
```bash
# 1) Đảm bảo model đã nằm trong volume (bước 2)
# 2) Ngắt kết nối Internet ra ngoài của máy chủ (giữ mạng nội bộ Docker)
# 3) Xử lý một tài liệu ở chế độ tại chỗ từ đầu đến cuối
#    → Phải thành công, không lỗi mạng. QUAY VIDEO làm bằng chứng.
```
> `llamacpp` là lựa chọn thuyết phục nhất cho phép thử này: model là file `.gguf` đặt sẵn, container
> không gọi ra ngoài lúc khởi động. `vllm` cần mạng ở **lần đầu** để tải model — chuẩn bị trước khi ngắt mạng.

### KT-BM-03 — Máy chủ model KHÔNG mở cổng ra ngoài (YC-MS-01, YC-BM-05)
```bash
# Từ một máy NGOÀI mạng nội bộ, quét cổng của máy chủ:
nmap -p 11434,8000,8080 <IP_may_chu>
# Kỳ vọng: đóng/không truy cập được (compose chỉ 'expose', KHÔNG 'ports' ra host cho cả 3 công cụ).
```

### Health (YC-MS-04)
```bash
docker compose exec worker curl -s http://ollama:11434/api/tags      # Ollama
docker compose exec worker curl -s http://vllm:8000/v1/models        # vLLM
docker compose exec worker curl -s http://llamacpp:8080/v1/models    # llama.cpp
```
`provider.health()` còn soát cả **model đã nạp chưa** — điểm cuối sống nhưng thiếu model vẫn báo
`ready=False` kèm câu lệnh cần chạy.

## 7. Kiến trúc liên quan
- Lớp trừu tượng hóa: `scripts/providers/` — xem `__init__.py` để biết vai trò từng file.
- Thêm một công cụ mới: nếu nói được giao thức tương thích OpenAI → **thêm một dòng** vào
  `scripts/providers/registry.py`; nếu là giao thức mới → thêm một lớp con `TextGenProvider`
  (chỉ cần hiện thực `_complete`) + một dòng `factory._BUILDERS`.
- Quyết định kiến trúc: `docs/DECISIONS.md` — **ADR-007** (bảng đăng ký, tách công cụ/chế độ),
  ADR-002 (Ollama cho GĐ0), ADR-001 (giao diện trước, công cụ sau).
- Tích hợp vào pipeline production: **GĐ1** (ADR-004) — hiện lớp provider đứng độc lập, an toàn cho hệ đang chạy.
