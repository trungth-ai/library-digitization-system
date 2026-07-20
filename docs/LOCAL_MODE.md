# Hướng dẫn chế độ tại chỗ (Ollama) — DocuFlow HP

> Hướng dẫn tiếng Việt (YC-VH-04) để bật/kiểm chứng **chế độ xử lý tại chỗ** bằng mô hình mở.
> Chế độ tại chỗ nằm trong **profile `local-ai`** của Docker Compose → KHÔNG ảnh hưởng deploy hiện tại.

## 1. Bật chế độ tại chỗ

```bash
# Khởi động kèm service Ollama (các service khác vẫn như cũ)
docker compose --profile local-ai up -d

# Kiểm tra Ollama đã chạy
docker compose ps ollama
```

## 2. Tải model (chỉ 1 lần — lưu vào volume, YC-MS-02)

```bash
# Ví dụ model tiếng Việt/đa ngữ chạy CPU được. CHỈ dùng model đã rà giấy phép (YC-PL-01/02)!
docker compose exec ollama ollama pull qwen2.5:7b

# Xem model đã có
docker compose exec ollama ollama list
```
> ⚠️ **Giấy phép trước, hiệu năng sau** (nguyên tắc SRS): rà giấy phép model TRƯỚC khi `pull`.
> Cập nhật `LOCAL_MODEL` trong `.env` cho khớp model đã tải.

## 3. Chọn provider (YC-MP-04)

Trong `.env`:
```env
MODEL_PROVIDER=local      # cloud (mặc định) | local
OLLAMA_URL=http://ollama:11434
LOCAL_MODEL=qwen2.5:7b
```
Đổi provider **chỉ bằng cấu hình**, không sửa mã, khởi động lại là xong.

## 4. Kiểm chứng bằng chứng cốt lõi cho hồ sơ dự thi

### KT-BM-01 — Chạy khi NGẮT Internet (YC-MS-03)
```bash
# 1) Đảm bảo model đã nằm trong volume (bước 2)
# 2) Ngắt kết nối Internet ra ngoài của máy chủ (giữ mạng nội bộ Docker)
# 3) Xử lý một tài liệu ở chế độ tại chỗ từ đầu đến cuối
#    → Phải thành công, không lỗi mạng. QUAY VIDEO làm bằng chứng.
```

### KT-BM-03 — Ollama KHÔNG mở cổng ra ngoài (YC-MS-01, YC-BM-05)
```bash
# Từ một máy NGOÀI mạng nội bộ, quét cổng 11434 của máy chủ:
nmap -p 11434 <IP_may_chu>
# Kỳ vọng: cổng đóng/không truy cập được (compose chỉ 'expose', không 'ports' ra host).
```

### Health (YC-MS-04)
```bash
# Từ trong mạng nội bộ (vd container worker):
docker compose exec worker curl -s http://ollama:11434/api/tags
```

## 5. Kiến trúc liên quan
- Lớp trừu tượng hóa: `scripts/providers/` (`base.py`, `cloud.py`, `local.py`, `factory.py`).
- `LocalProvider` gọi Ollama qua `urllib` (không thêm phụ thuộc, chạy air-gapped).
- Quyết định công cụ: xem `docs/DECISIONS.md` ADR-002 (Ollama cho GĐ0, thay được qua cấu hình).
- Tích hợp vào pipeline production: **GĐ1** (ADR-004) — hiện provider layer đứng độc lập, an toàn cho hệ đang chạy.
