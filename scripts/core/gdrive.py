#!/usr/bin/env python3
"""
Máy khách Google Drive tối giản (YC-BU-21) — chỉ những gì việc nạp tài liệu cần.

VÌ SAO KHÔNG DÙNG `google-api-python-client`: bộ SDK chính thức kéo theo hơn 10 gói phụ thuộc
(google-auth, googleapis-common-protos, httplib2, uritemplate...). Sản phẩm này phải cài được ở
chế độ TẠI CHỖ, trong mạng đóng, nơi mỗi gói thêm là một thứ phải kiểm giấy phép và phải tải về
bằng tay. Ta chỉ dùng 3 lời gọi HTTP của Drive v3 — viết thẳng bằng `urllib` là đủ và rẻ hơn nhiều.

HAI CÁCH XÁC THỰC (chọn bằng biến môi trường):

  1. TÀI KHOẢN DỊCH VỤ (khuyến nghị cho thư mục dùng chung)
       GDRIVE_SERVICE_ACCOUNT_FILE=/run/secrets/gdrive-sa.json
     Cán bộ chia sẻ thư mục Drive cho địa chỉ thư của tài khoản dịch vụ (quyền Người xem là đủ).
     Chạy không cần người bấm nút — hợp với việc quét định kỳ.
     ⚠️ Cần gói `cryptography` để ký JWT RS256 (nạp lười, chỉ khi dùng cách này).

  2. OAUTH REFRESH TOKEN (khi không tạo được tài khoản dịch vụ)
       GDRIVE_OAUTH_CLIENT_ID / GDRIVE_OAUTH_CLIENT_SECRET / GDRIVE_OAUTH_REFRESH_TOKEN
     Chỉ dùng thư viện chuẩn. Quyền là quyền của CHÍNH người đã cấp — cần cân nhắc phạm vi.

BẢO MẬT (YC-BM-03): tuyệt đối KHÔNG ghi khóa/token ra log. Mọi thông điệp lỗi ở đây chỉ nói tới
tên biến môi trường và mã lỗi HTTP, không bao giờ nói tới giá trị.

CHỈ ĐỌC: máy khách này KHÔNG có hàm nào ghi/xóa trên Drive. Tài liệu gốc của Nhà trường không bị hệ
thống số hóa đụng vào — muốn đánh dấu đã xử lý thì ghi ở phía ta (bảng `drive_files`), không sửa Drive.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger("core.gdrive")

DRIVE_API = "https://www.googleapis.com/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Phạm vi CHỈ ĐỌC. Không xin quyền ghi khi không có nhu cầu ghi — nguyên tắc quyền tối thiểu.
SCOPE_READONLY = "https://www.googleapis.com/auth/drive.readonly"

# Xin token mới sớm hơn hạn này để không có request nào lỡ dùng token vừa hết hạn giữa chừng
TOKEN_EARLY_REFRESH_SEC = 120

HTTP_TIMEOUT = int(os.getenv("GDRIVE_HTTP_TIMEOUT", "60"))

# Trần dung lượng một tệp tải về. Một tệp 5 GB đặt nhầm trong thư mục sẽ làm đầy đĩa máy chủ và
# kéo đổ toàn bộ hàng đợi — chặn ở đây rẻ hơn nhiều so với dọn dẹp sau đó.
MAX_FILE_MB = int(os.getenv("GDRIVE_MAX_FILE_MB", "500"))

PDF_MIME = "application/pdf"


class DriveError(RuntimeError):
    """Lỗi khi làm việc với Google Drive — thông điệp đã viết sẵn bằng tiếng Việt cho cán bộ đọc."""


@dataclass
class DriveFile:
    """Một tệp trên Drive. `md5` dùng để bỏ qua tệp đã nạp mà không phải tải về lần nữa."""
    id: str
    name: str
    mime_type: str
    size_bytes: int = 0
    md5: str = ""
    modified_time: str = ""

    @property
    def is_pdf(self) -> bool:
        return self.mime_type == PDF_MIME


# =====================================================================
# XÁC THỰC
# =====================================================================

def _post_form(url: str, data: Dict[str, str]) -> Dict:
    """POST dạng form, trả JSON. Không bao giờ đưa nội dung `data` vào log — trong đó có bí mật."""
    body = urllib.parse.urlencode(data).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        raise DriveError(
            f"Google từ chối cấp token (HTTP {e.code}). Kiểm tra lại cấu hình xác thực Drive."
        ) from e
    except urllib.error.URLError as e:
        raise DriveError(f"Không kết nối được tới Google ({e.reason})") from e


def _service_account_token(key_file: str) -> Tuple[str, float]:
    """
    Đổi khóa tài khoản dịch vụ lấy access token, qua luồng JWT Bearer (RFC 7523).

    `cryptography` nạp LƯỜI ngay tại đây: bản cài chỉ dùng OAuth refresh token không cần gói này,
    và bản cài trong mạng đóng không nên bị bắt tải thêm thứ nó không dùng.
    """
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as e:
        raise DriveError(
            "Xác thực bằng tài khoản dịch vụ cần gói 'cryptography' (pip install cryptography). "
            "Hoặc chuyển sang cách 2: đặt GDRIVE_OAUTH_CLIENT_ID / _SECRET / _REFRESH_TOKEN."
        ) from e

    try:
        with open(key_file, "r", encoding="utf-8") as f:
            key_data = json.load(f)
    except OSError as e:
        raise DriveError(f"Không đọc được tệp khóa tài khoản dịch vụ tại '{key_file}'") from e
    except json.JSONDecodeError as e:
        raise DriveError(f"Tệp khóa tài khoản dịch vụ '{key_file}' không phải JSON hợp lệ") from e

    for field in ("client_email", "private_key"):
        if not key_data.get(field):
            raise DriveError(f"Tệp khóa tài khoản dịch vụ thiếu trường '{field}'")

    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": key_data["client_email"],
        "scope": SCOPE_READONLY,
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }
    # Google yêu cầu 'sub' khi tài khoản dịch vụ mạo danh người dùng trong Workspace (uỷ quyền
    # toàn miền). Không đặt thì tài khoản dịch vụ chỉ thấy thứ được chia sẻ cho chính nó — đúng
    # với cách dùng khuyến nghị (chia sẻ thư mục cho địa chỉ thư của tài khoản dịch vụ).
    subject = os.getenv("GDRIVE_IMPERSONATE_SUBJECT", "").strip()
    if subject:
        claims["sub"] = subject

    def b64(raw: bytes) -> bytes:
        import base64
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    signing_input = b64(json.dumps(header).encode()) + b"." + b64(json.dumps(claims).encode())
    private_key = serialization.load_pem_private_key(
        key_data["private_key"].encode(), password=None,
    )
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    assertion = (signing_input + b"." + b64(signature)).decode()

    payload = _post_form(TOKEN_URL, {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    })
    return payload["access_token"], time.time() + int(payload.get("expires_in", 3600))


def _refresh_token_grant(client_id: str, client_secret: str,
                         refresh_token: str) -> Tuple[str, float]:
    """Đổi refresh token lấy access token. Chỉ dùng thư viện chuẩn."""
    payload = _post_form(TOKEN_URL, {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    })
    return payload["access_token"], time.time() + int(payload.get("expires_in", 3600))


# =====================================================================
# MÁY KHÁCH
# =====================================================================

class DriveClient:
    """
    Máy khách Drive CHỈ ĐỌC, giữ access token trong bộ nhớ và tự xin lại khi sắp hết hạn.

    Một đối tượng cho mỗi lượt quét là đủ: token sống một giờ, còn một lượt quét chỉ vài phút.
    """

    def __init__(self, service_account_file: Optional[str] = None,
                 client_id: Optional[str] = None, client_secret: Optional[str] = None,
                 refresh_token: Optional[str] = None):
        self.service_account_file = service_account_file or os.getenv(
            "GDRIVE_SERVICE_ACCOUNT_FILE", "").strip()
        self.client_id = client_id or os.getenv("GDRIVE_OAUTH_CLIENT_ID", "").strip()
        self.client_secret = client_secret or os.getenv("GDRIVE_OAUTH_CLIENT_SECRET", "").strip()
        self.refresh_token = refresh_token or os.getenv("GDRIVE_OAUTH_REFRESH_TOKEN", "").strip()

        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # -- Xác thực ------------------------------------------------------
    @property
    def configured(self) -> bool:
        """Đã cấu hình đủ để gọi Drive chưa? Dùng để tắt tính năng gọn gàng thay vì để nó lỗi."""
        return bool(self.service_account_file or
                    (self.client_id and self.client_secret and self.refresh_token))

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - TOKEN_EARLY_REFRESH_SEC:
            return self._token

        if self.service_account_file:
            self._token, self._token_expires_at = _service_account_token(self.service_account_file)
            logger.info("Đã lấy access token Drive bằng tài khoản dịch vụ")
        elif self.client_id and self.client_secret and self.refresh_token:
            self._token, self._token_expires_at = _refresh_token_grant(
                self.client_id, self.client_secret, self.refresh_token)
            logger.info("Đã lấy access token Drive bằng refresh token")
        else:
            raise DriveError(
                "Chưa cấu hình xác thực Google Drive. Đặt GDRIVE_SERVICE_ACCOUNT_FILE, "
                "hoặc bộ ba GDRIVE_OAUTH_CLIENT_ID / _CLIENT_SECRET / _REFRESH_TOKEN."
            )
        return self._token

    # -- Gọi API -------------------------------------------------------
    def _get(self, path: str, params: Dict[str, str]) -> Dict:
        url = f"{DRIVE_API}{path}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self._access_token()}",
        })
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            raise DriveError(_http_message(e.code, path)) from e
        except urllib.error.URLError as e:
            raise DriveError(f"Không kết nối được tới Google Drive ({e.reason})") from e

    def list_pdfs(self, folder_id: str, page_size: int = 100) -> Iterator[DriveFile]:
        """
        Liệt kê tệp PDF trong một thư mục Drive, tự đi hết các trang.

        `includeItemsFromAllDrives` + `supportsAllDrives`: thiếu hai tham số này thì thư mục nằm
        trên Drive dùng chung (Shared drive) trả về RỖNG mà không báo lỗi — một cái bẫy im lặng
        khiến người cấu hình tưởng mình chia sẻ nhầm thư mục.

        Lọc `trashed = false`: tệp cán bộ đã bỏ vào thùng rác trên Drive là tệp họ KHÔNG muốn số hóa.
        """
        if not folder_id:
            raise DriveError("Chưa có mã thư mục Drive (folder_id)")

        query = f"'{folder_id}' in parents and mimeType = '{PDF_MIME}' and trashed = false"
        page_token = None

        while True:
            params = {
                "q": query,
                "fields": "nextPageToken, files(id, name, mimeType, size, md5Checksum, modifiedTime)",
                "pageSize": str(page_size),
                "orderBy": "modifiedTime",       # tệp cũ trước — vào hàng đợi theo đúng thứ tự đặt vào
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if page_token:
                params["pageToken"] = page_token

            payload = self._get("/files", params)
            for row in payload.get("files", []):
                yield DriveFile(
                    id=row["id"],
                    name=row.get("name", ""),
                    mime_type=row.get("mimeType", ""),
                    size_bytes=int(row.get("size") or 0),
                    md5=row.get("md5Checksum", "") or "",
                    modified_time=row.get("modifiedTime", "") or "",
                )

            page_token = payload.get("nextPageToken")
            if not page_token:
                return

    def folder_name(self, folder_id: str) -> str:
        """Tên thư mục — để hiện cho cán bộ thay vì một chuỗi mã vô nghĩa."""
        payload = self._get(f"/files/{folder_id}", {
            "fields": "name", "supportsAllDrives": "true",
        })
        return payload.get("name", "")

    def download(self, file_id: str, destination, max_mb: int = MAX_FILE_MB) -> int:
        """
        Tải một tệp về đĩa THEO MẢNH, trả về số byte đã ghi.

        Đọc theo mảng 1 MB thay vì `response.read()` một phát: một tệp scan 400 MB nạp trọn vào RAM
        sẽ giết tiến trình worker, và mất luôn cả những tài liệu đang xử lý dở cùng lúc.

        Trần dung lượng kiểm tra TRONG LÚC ghi chứ không chỉ dựa vào cỡ tệp Drive báo: cỡ báo trước
        có thể thiếu hoặc sai, và lúc đó đĩa đã đầy rồi mới biết.
        """
        limit_bytes = max_mb * 1024 * 1024
        url = f"{DRIVE_API}/files/{file_id}?" + urllib.parse.urlencode({
            "alt": "media", "supportsAllDrives": "true",
        })
        request = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self._access_token()}",
        })

        written = 0
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                with open(destination, "wb") as out:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > limit_bytes:
                            raise DriveError(
                                f"Tệp vượt quá giới hạn {max_mb} MB — bỏ qua để không làm đầy đĩa"
                            )
                        out.write(chunk)
        except urllib.error.HTTPError as e:
            _cleanup(destination)
            raise DriveError(_http_message(e.code, f"tải tệp {file_id}")) from e
        except urllib.error.URLError as e:
            _cleanup(destination)
            raise DriveError(f"Không tải được tệp từ Drive ({e.reason})") from e
        except DriveError:
            _cleanup(destination)       # tệp dở dang không được để lại trên đĩa
            raise

        return written

    def health(self) -> Tuple[bool, str]:
        """Kiểm tra cấu hình Drive có dùng được không — cho trang kiểm tra sức khỏe hệ thống."""
        if not self.configured:
            return False, "Chưa cấu hình xác thực Google Drive"
        try:
            self._access_token()
            return True, "Kết nối Google Drive bình thường"
        except DriveError as e:
            return False, str(e)


def _cleanup(path) -> None:
    """Xóa tệp tải dở. Không ném lỗi — đây là dọn dẹp, không phải nghiệp vụ."""
    try:
        os.unlink(path)
    except OSError:
        pass


def _http_message(code: int, what: str) -> str:
    """Đổi mã HTTP của Google thành câu tiếng Việt nói rõ PHẢI LÀM GÌ, không chỉ 'lỗi 403'."""
    if code == 401:
        return ("Google từ chối xác thực (401). Khóa tài khoản dịch vụ hoặc refresh token đã hết "
                "hiệu lực — cấp lại rồi cập nhật biến môi trường.")
    if code == 403:
        return ("Google từ chối truy cập (403). Thường là thư mục CHƯA được chia sẻ cho tài khoản "
                "dịch vụ, hoặc Drive API chưa bật trong dự án Google Cloud.")
    if code == 404:
        return f"Không tìm thấy trên Drive ({what}). Kiểm tra lại mã thư mục/tệp."
    if code == 429:
        return "Google đang giới hạn tần suất (429). Giảm chu kỳ quét hoặc thử lại sau."
    return f"Google Drive trả về lỗi HTTP {code} khi {what}"


def client_from_env() -> DriveClient:
    """Máy khách dựng từ biến môi trường — đường dùng thông thường."""
    return DriveClient()
