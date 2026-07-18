# 📘 Ghi chú tích hợp DSpace 6.3 REST API

Tài liệu này dùng để **ghi chú nhanh các vấn đề, bẫy kỹ thuật và best-practice** khi tích hợp **DSpace 6.3 REST API** vào ứng dụng web (Next.js / React / SPA), dựa trên quá trình test thực tế.

> 🎯 Mục tiêu: giúp đồng nghiệp **đỡ mất thời gian debug**, hiểu đúng bản chất API của DSpace 6.x.

---

## 1. Tổng quan quan trọng (CẦN ĐỌC TRƯỚC)

* DSpace 6.3 sử dụng **REST API thế hệ cũ** (Servlet / JAXB)
* ❌ Không phải REST hiện đại
* ❌ Không đảm bảo JSON cho mọi endpoint
* ✔ Có thể trả **XML / JSON / HTML** tuỳ ngữ cảnh
Thay thế collection_id khi test

👉 **Không bao giờ giả định response luôn là JSON**

---

## 2. Cơ chế đăng nhập & session (RẤT QUAN TRỌNG)

### 2.1 Login KHÔNG trả session đầy đủ

Endpoint:

```
POST /rest/login
```

* Chỉ dùng để **set session cookie (JSESSIONID)**
* Response **không đáng tin để hiển thị user info**

👉 **Không dùng response của `/rest/login` để hiển thị trạng thái đăng nhập**

---

### 2.2 Luôn kiểm tra session bằng `/rest/status`

Endpoint chuẩn để kiểm tra đăng nhập:

```
GET /rest/status
```

Response mẫu:

```json
{
  "okay": true,
  "authenticated": true,
  "email": "user@domain",
  "fullname": "User Name",
  "sourceVersion": null,
  "apiVersion": null
}
```

👉 Đây là **nguồn dữ liệu session DUY NHẤT đáng tin**

---

### 2.3 Cookie là bắt buộc

* DSpace dùng **session-cookie-based auth**
* Không dùng token / JWT

⚠️ Khi proxy qua Next.js API route:

* Phải **forward Cookie** từ client → DSpace
* Phải bật `credentials: "include"` ở fetch phía client

---

## 3. Content Negotiation – Vì sao Postman trả JSON, Browser lại trả XML?

### 3.1 DSpace 6.3 quyết định format dựa trên header

DSpace xem các header sau:

* `Accept`
* `User-Agent`

### 3.2 Postman mặc định gửi

```
Accept: application/json
User-Agent: PostmanRuntime/7.x
```

→ DSpace trả JSON

### 3.3 Browser / fetch thường KHÔNG gửi đủ

→ DSpace fallback sang XML hoặc HTML

---

### 3.4 Cách ép DSpace trả JSON

```http
Accept: application/json
User-Agent: PostmanRuntime/7.x
```

⚠️ Lưu ý: **KHÔNG phải endpoint nào cũng tôn trọng Accept**

---

## 4. Vấn đề XML / JSON khi tạo Item

### 4.1 Endpoint tạo Item

```
POST /rest/collections/{collectionId}/items
```

* Có thể trả:

  * XML (phổ biến)
  * JSON (nếu header phù hợp)

Ví dụ XML:

```xml
<item>
  <UUID>...</UUID>
  <handle>...</handle>
  <archived>true</archived>
</item>
```

👉 Item **đã được tạo thành công**, dù UI báo lỗi parse JSON

---

### 4.2 Không parse JSON mù quáng

❌ Sai:

```js
await res.json();
```

✅ Đúng:

```js
const text = await res.text();
```

Sau đó:

* Detect XML / JSON
* Format hiển thị ở UI

---

## 5. Best Practice kiến trúc (RẤT KHUYẾN NGHỊ)

### 5.1 API layer làm nhiệm vụ normalize

* API route nhận **XML / JSON / HTML** từ DSpace
* API route trả **JSON thống nhất** cho frontend

Frontend:

* ❌ Không parse XML
* ✔ Chỉ render dữ liệu

---

### 5.2 UI test (API Tester)

Nếu viết UI để test API nội bộ:

* Cho phép hiển thị **raw response**
* Detect & pretty-print XML / JSON
* Không che giấu lỗi thật bằng message "success"

---

## 6. Những lỗi thường gặp

| Lỗi                                    | Nguyên nhân                 | Ghi chú                         |
| -------------------------------------- | --------------------------- | ------------------------------- |
| 401 Unauthorized                       | Sai cookie / chưa login     | Kiểm tra `/rest/status`         |
| Unexpected token '<'                   | Parse XML bằng `res.json()` | Luôn dùng `res.text()`          |
| Login success nhưng không có user info | Dùng sai endpoint           | Phải gọi `/rest/status`         |
| Postman OK, UI lỗi                     | Thiếu header Accept         | Thêm `Accept: application/json` |

---

## 7. Những thứ DSpace 6.3 KHÔNG có

* ❌ JWT / OAuth2
* ❌ API versioning chuẩn
* ❌ Error response JSON đồng nhất
* ❌ REST HAL / HATEOAS

👉 Phải **chấp nhận và xử lý thủ công**

---

## 8. Kết luận

* DSpace 6.3 **ổn định nhưng cổ điển**
* Tích hợp cần **kiên nhẫn + hiểu bản chất servlet**
* Đừng tin bề ngoài là "REST"

> ✔ Khi đã quen, hệ thống chạy rất bền và ít thay đổi

---

📌 Tài liệu này được viết dựa trên **test thực tế**, không chỉ đọc docs.
Nếu gặp hành vi "lạ", hãy kiểm tra **header + response raw** trước khi kết luận bug.

