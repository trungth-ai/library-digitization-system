"""
Thông báo & cảnh báo (YC-TB — sprint V8).

Kênh CẮM ĐƯỢC theo đúng mẫu đã dùng thành công cho lớp mô hình (YC-MP-08): thêm kênh mới = viết một
lớp hiện thực + thêm một dòng vào bảng đăng ký, KHÔNG sửa nơi gọi.

    base.py     interface + bảng đăng ký + chống spam    (thuần, kiểm thử được)
    channels.py hiện thực: log, email (SMTP nội bộ), webhook
    rules.py    quy tắc sinh cảnh báo từ system_events / hàng đợi / SLA

⚠️ YC-TB-06: mọi kênh phải chạy được khi **ngắt Internet**. SMTP phải là máy chủ nội bộ, webhook phải
là địa chỉ nội mạng. Một hệ thống tự hào về khả năng air-gapped mà cảnh báo lại đi qua dịch vụ đám mây
thì đúng lúc mất mạng — lúc cần cảnh báo nhất — sẽ im lặng.
"""
