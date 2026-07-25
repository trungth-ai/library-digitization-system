# Hướng dẫn đo đạc (Harness KT-CX / KT-HN) — DocuFlow HP

> Tạo **bảng so sánh độ chính xác 2 chế độ** cho hồ sơ dự thi GĐ0. Nguyên tắc: **đo được mới tuyên bố**,
> luôn ghi **cỡ mẫu + phương pháp**; báo cáo theo **từng trường** (số tổng che giấu một trường luôn sai).

## 1. Chuẩn bị bộ dữ liệu

Tạo thư mục `eval_data/` (đã gitignore — KHÔNG commit tài liệu thật/nhạy cảm), gồm:
- Các tài liệu: `<doc_id>.txt` (văn bản đã trích) hoặc `<doc_id>.pdf`.
- `ground_truth.json`: đáp án chuẩn do người lập đọc từng tài liệu (căn cứ đối chiếu duy nhất).

Định dạng `ground_truth.json`:
```json
{
  "cv_001": {
    "so_hieu": "123/QĐ-ĐHQLCN",
    "ngay_ban_hanh": "15/03/2024",
    "co_quan_ban_hanh": "Trường ĐH Quản lý và Công nghệ Hải Phòng",
    "trich_yeu": "Về việc ...",
    "do_mat": ""
  }
}
```
- Khóa trường theo lược đồ: `book`/`thesis` → `dc.*`; `cong_van` → `so_hieu, ngay_ban_hanh, ...`.
- **Trường không có trong tài liệu: để `""`** — để đo chống ảo giác (KT-CX-05): model bịa ra = SAI.
- Đa giá trị (nhiều tác giả/nơi nhận): dùng mảng `["A", "B"]`.

Xem mẫu: `scripts/eval/samples/ground_truth.sample.json` + `scripts/eval/samples/cv_sample.txt`.

## 2. Chạy đo

```bash
# Xem công cụ khả dụng + biến môi trường mỗi công cụ cần
python -m scripts.eval.run_eval --list-providers

# Kiểm công cụ đã sẵn sàng chưa TRƯỚC khi đo (tránh đo ra số rác)
python -m scripts.eval.run_eval --health --providers claude,ollama

# So sánh nhiều công cụ trên CÙNG tập tài liệu, CÙNG đáp án chuẩn, một lần chạy
python -m scripts.eval.run_eval \
    --data ./eval_data \
    --truth ./eval_data/ground_truth.json \
    --schema book \
    --providers claude,ollama,vllm \
    --out ./eval_out
```
- `--schema`: `book` | `thesis` | `cong_van`.
- `--providers`: tên công cụ cụ thể (`claude`, `ollama`, `vllm`, `llamacpp`, `openai`, `gemini`...) hoặc
  bí danh chế độ (`cloud`, `local`). Nhiều tên = chế độ đánh giá song song (KT-CX-03, YC-MP-07).
- Mỗi công cụ cần cấu hình riêng trước khi chạy: khóa API (đám mây) hoặc máy chủ model đang chạy
  (tại chỗ) — xem `docs/LOCAL_MODE.md` mục 3.

> 💡 Hai phép so sánh khác nhau, đừng trộn: **(a) cloud vs local** trả lời "chế độ tại chỗ có dùng được
> không" (bằng chứng cho hồ sơ); **(b) ollama vs vllm vs llamacpp** trả lời "công cụ tại chỗ nào nên
> dùng ở GĐ1". Phép (b) phải chạy trên **cùng một model** mới công bằng.

## 3. Đọc kết quả
- Bảng in ra: độ chính xác **từng trường** + tổng + **tỉ lệ bịa** + thời gian TB/tài liệu.
- File `eval_out/eval_<schema>_<timestamp>.json`: số liệu chi tiết để lưu hồ sơ.
- Khi đưa vào hồ sơ: ghi kèm cỡ mẫu, phần cứng, tên+phiên bản model (mẫu ghi kết quả — test plan 6.1).

## 4. Bộ dữ liệu kiểm thử (test plan mục 1.3)
| Mã | Quy mô | Mục đích |
|---|---|---|
| BD-01 Công văn hành chính | 30–50 | Đo độ chính xác 2 chế độ (KT-CX-01/02/03) |
| BD-02 Tài liệu thư viện | 20–30 | Không hồi quy (KT-KH) — so kết quả hệ cũ |
| BD-03 Chất lượng kém | 10–15 | Đo giới hạn (KT-CX-06) |
| BD-04 Thiếu trường | 5–10 | Chống ảo giác (KT-CX-05) |
| BD-05 Nhạy cảm mô phỏng | 5–10 | Kiểm thử định tuyến (GĐ1) |

## 5. Giới hạn hiện tại
- Lược đồ `cong_van` **đã chạy được**: prompt/parse theo lược đồ bất kỳ nằm ở `scripts/providers/prompt.py`,
  dùng chung cho mọi công cụ nên so sánh giữa các chế độ là công bằng (KT-CX-03). `book`/`thesis`
  (Dublin Core) đi đúng đường của hệ đang chạy → đủ cho **KT-KH** (không hồi quy) và **KT-CX trên sách**.
- **Chưa đo tài nguyên** (YC-MS-07): harness ghi thời gian/tài liệu nhưng chưa ghi RAM/GPU. Khi so
  Ollama vs vLLM vs llama.cpp, hãy ghi tay thông số máy + `docker stats` kèm bảng kết quả.
- **Worker chưa dùng lớp provider** (ADR-004): `run_eval` gọi provider trực tiếp, nên số liệu ở đây phản
  ánh chất lượng trích xuất của từng công cụ, **chưa** phản ánh thông lượng pipeline production.
- Số liệu phải chạy trên môi trường thật (máy chủ model + tài liệu + đáp án chuẩn) — không có con số nào
  trong tài liệu này được tạo ra bằng suy đoán.
- Kết quả JSON ghi cả `provider` và `deployment` → bảng trong hồ sơ nói rõ **công cụ nào** và **dữ liệu
  chạy ở đâu**. Lưu ý: số liệu đo trước 25/07/2026 dùng tên cũ (`cloud`/`local` thay vì `claude`/`ollama`)
  — xem ADR-007 khi đối chiếu file cũ.
