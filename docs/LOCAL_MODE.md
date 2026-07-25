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
| | `openrouter`, `groq`, `together`, `deepseek`, `mistral` | So sánh nhiều model NHANH mà chưa phải tự dựng máy chủ. |
| | `openai_compat` | Điểm cuối tương thích OpenAI chưa có trong bảng (vd dịch vụ trong nước). |

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
