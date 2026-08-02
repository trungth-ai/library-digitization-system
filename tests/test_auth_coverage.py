#!/usr/bin/env python3
"""
KT-QT-09 — KHÔNG endpoint ghi nào được thiếu phân quyền.

Đây là test có giá trị lâu dài nhất của ADR-012: nó **hỏng khi ai đó thêm endpoint mới mà quên gắn
`require(...)`**. Đó chính là mục đích. Rà soát bằng mắt trong code review sẽ bỏ sót; test thì không.

CÁCH LÀM: phân tích cây cú pháp (AST) của `scripts/api.py` thay vì import nó. `api.py` import fastapi
và mở kết nối Redis ngay lúc import (raise nếu không nối được) nên không import được trên máy dev —
xem `scripts/core/uploads.py`. AST đọc được mã nguồn mà không cần chạy nó, và không cần gói nào.
"""

import ast
from pathlib import Path

import pytest

API_PATH = Path(__file__).resolve().parents[1] / "scripts" / "api.py"

WRITE_METHODS = {"post", "put", "patch", "delete"}

# Endpoint ghi ĐƯỢC PHÉP không có `require(...)`, kèm lý do. Danh sách này là chỗ duy nhất hợp pháp
# để miễn trừ — thêm vào đây là một quyết định có ý thức, phải viết lý do.
MIEN_TRU = {
    "/api/v2/auth/login":  "Chưa đăng nhập thì mới cần đăng nhập — không thể đòi quyền",
    "/api/v2/auth/logout": "Đăng xuất phải luôn làm được, kể cả khi phiên đã hỏng",
    # `change-password` dùng `require_authenticated()` (chỉ cần đã đăng nhập, không cần quyền cụ thể),
    # nên không xuất hiện với `require(...)`. Vẫn được bảo vệ.
    "/api/v2/auth/change-password": "Dùng require_authenticated() — đã đăng nhập là đủ",
}


def _parse_api():
    return ast.parse(API_PATH.read_text(encoding="utf-8"), filename=str(API_PATH))


def _route_decorators(tree):
    """
    Sinh ra `(method, path, node)` cho mỗi hàm có decorator `@app.<method>("...")`.
    """
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            if not isinstance(func, ast.Attribute) or func.attr not in (
                    "get", "post", "put", "patch", "delete"):
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id == "app"):
                continue
            path = None
            if dec.args and isinstance(dec.args[0], ast.Constant):
                path = dec.args[0].value
            yield func.attr, path, node


def _co_bao_ve(node) -> bool:
    """
    Hàm này có gọi `require(...)` hoặc `require_authenticated(...)` ở đâu đó trong chữ ký / decorator?

    Tìm trong toàn bộ cây con của định nghĩa hàm: bao trùm cả `Depends(require(...))` ở tham số mặc
    định và `dependencies=[Depends(require(...))]` trên decorator.
    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and \
                sub.func.id in ("require", "require_authenticated"):
            return True
    return False


def test_moi_endpoint_ghi_deu_co_phan_quyen():
    """
    KT-QT-09 🔴 — 0 endpoint POST/PUT/PATCH/DELETE thiếu `require(...)`.

    Nếu test này hỏng: bạn vừa thêm một endpoint ghi mà chưa gắn quyền. Thêm
    `principal: Principal = Depends(require(policy.<QUYỀN>))` vào chữ ký hàm.
    """
    tree = _parse_api()
    thieu = []

    for method, path, node in _route_decorators(tree):
        if method not in WRITE_METHODS:
            continue
        if path in MIEN_TRU:
            continue
        if not _co_bao_ve(node):
            thieu.append(f"{method.upper()} {path} (hàm {node.name})")

    assert thieu == [], (
        "Các endpoint GHI sau đây KHÔNG có require(...) — lỗ hổng N-01 quay lại:\n  "
        + "\n  ".join(thieu)
    )


def test_endpoint_doc_du_lieu_nhay_cam_co_phan_quyen():
    """
    Một số endpoint ĐỌC cũng phải có quyền: nhật ký kiểm toán, người dùng, phiên, tải tệp.

    Không chặn thì ở nấc `AUTH_MODE=on` bất kỳ ai vẫn đọc được toàn bộ nhật ký kiểm toán và tải được
    mọi tài liệu — chặn đường ghi mà để hở đường đọc là chỉ vá một nửa lỗ hổng.
    """
    tree = _parse_api()
    can_bao_ve = ("/api/v2/audit", "/api/v2/users", "/api/v2/roles", "/api/v2/sessions",
                  "/api/v2/download/", "/api/v2/jobs/{job_id}/audit")
    thieu = []

    for method, path, node in _route_decorators(tree):
        if method != "get" or not path:
            continue
        if not any(path.startswith(p) for p in can_bao_ve):
            continue
        if not _co_bao_ve(node):
            thieu.append(f"GET {path} (hàm {node.name})")

    assert thieu == [], "Endpoint đọc dữ liệu nhạy cảm thiếu phân quyền:\n  " + "\n  ".join(thieu)


def test_endpoint_ghi_khong_nhan_actor_tu_request():
    """
    🔴 Chính là lỗ hổng N-01: endpoint GHI không được nhận `actor` từ request.

    Trước bản vá, `DELETE /api/v2/jobs/{id}?actor=ai-cung-duoc` cho phép bất kỳ ai ghi tên người khác
    vào nhật ký kiểm toán — nghĩa là YC-AU-02 ("ghi rõ ai thực hiện") không có giá trị giải trình.

    Endpoint ĐỌC vẫn được nhận `actor` làm BỘ LỌC (vd `GET /api/v2/audit?actor=...`) — đó là lọc dữ
    liệu, không phải khai báo danh tính.
    """
    tree = _parse_api()
    vi_pham = []

    for method, path, node in _route_decorators(tree):
        if method not in WRITE_METHODS:
            continue
        for arg in list(node.args.args) + list(node.args.kwonlyargs):
            if arg.arg == "actor":
                vi_pham.append(f"{method.upper()} {path} (hàm {node.name})")

    assert vi_pham == [], (
        "Endpoint GHI còn nhận `actor` từ request — bất kỳ ai cũng ghi được tên người khác vào "
        "nhật ký kiểm toán:\n  " + "\n  ".join(vi_pham)
    )


def test_ghi_audit_khong_dung_actor_do_client_truyen():
    """
    `audit.log_action(actor=X)` không được dùng X là một THAM SỐ của endpoint.

    Đây là dạng chính xác của lỗ hổng: giá trị đi thẳng từ request vào nhật ký kiểm toán. Nguồn hợp
    lệ là `principal.actor` (đã xác thực), một hằng, hoặc biến cục bộ suy ra từ phiên.
    """
    tree = _parse_api()
    vi_pham = []

    for _, path, node in _route_decorators(tree):
        ten_tham_so = {a.arg for a in list(node.args.args) + list(node.args.kwonlyargs)}

        for sub in ast.walk(node):
            if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "log_action"):
                continue
            for kw in sub.keywords:
                if kw.arg == "actor" and isinstance(kw.value, ast.Name) \
                        and kw.value.id in ten_tham_so:
                    vi_pham.append(f"{path} dòng {sub.lineno}: actor={kw.value.id} "
                                   f"(tham số của endpoint)")

    assert vi_pham == [], ("Ghi audit bằng giá trị client truyền vào:\n  " + "\n  ".join(vi_pham))


def test_moi_quyen_dung_trong_api_deu_ton_tai():
    """
    Chống lỗi chính tả: mọi `policy.<TÊN>` dùng trong `api.py` phải là quyền/vai trò có thật.

    `require()` đã kiểm lúc nạp module, nhưng test này bắt được sớm hơn và không cần fastapi.
    """
    from scripts.auth import policy

    tree = _parse_api()
    khong_ton_tai = []

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)):
            continue
        if node.value.id != "policy":
            continue
        if not hasattr(policy, node.attr):
            khong_ton_tai.append(f"dòng {node.lineno}: policy.{node.attr}")

    assert khong_ton_tai == [], "Tham chiếu policy không tồn tại:\n  " + "\n  ".join(khong_ton_tai)


def test_khong_dung_allow_origins_ky_tu_thay_the_voi_cookie():
    """
    `allow_origins=["*"]` KHÔNG dùng được cùng `allow_credentials=True`.

    Trình duyệt từ chối gửi cookie tới nguồn dùng ký tự thay thế → đăng nhập sẽ im lặng không hoạt
    động. Đây là lỗi rất khó lần ra vì phía máy chủ không có thông báo nào.

    Đọc bằng AST chứ không tìm chuỗi trong mã nguồn: bản đầu của test này khớp phải chính đoạn chú
    thích giải thích vấn đề, và báo hỏng khi mã đã đúng.
    """
    tree = _parse_api()

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_middleware"):
            continue

        kwargs = {kw.arg: kw.value for kw in node.keywords}
        origins = kwargs.get("allow_origins")
        credentials = kwargs.get("allow_credentials")

        dung_ky_tu_thay_the = (
            isinstance(origins, ast.List)
            and any(isinstance(e, ast.Constant) and e.value == "*" for e in origins.elts)
        )
        cho_cookie = isinstance(credentials, ast.Constant) and credentials.value is True

        assert not (dung_ky_tu_thay_the and cho_cookie), (
            "CORS dùng allow_origins=['*'] cùng allow_credentials=True — trình duyệt sẽ không gửi "
            "cookie phiên và đăng nhập im lặng không hoạt động"
        )
