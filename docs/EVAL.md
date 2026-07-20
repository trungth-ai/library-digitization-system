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
# So sánh 2 chế độ trên cùng tập (cần CLAUDE_API_KEY cho cloud; Ollama chạy cho local)
python -m scripts.eval.run_eval \
    --data ./eval_data \
    --truth ./eval_data/ground_truth.json \
    --schema book \
    --providers cloud,local \
    --out ./eval_out
```
- `--schema`: `book` | `thesis` | `cong_van`.
- `--providers`: `cloud`, `local`, hoặc `cloud,local` (chế độ đánh giá — KT-CX-03).

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
- Lược đồ `cong_van` cần **generic schema-driven prompt** (bước kế) để provider trích theo lược đồ này;
  hiện `book`/`thesis` (Dublin Core) chạy đầy đủ → đủ cho **KT-KH** (không hồi quy trên tài liệu thư viện)
  và **KT-CX trên sách**.
- Số liệu phải chạy trên môi trường thật (Ollama + tài liệu + đáp án chuẩn).
