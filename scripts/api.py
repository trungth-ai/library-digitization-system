#!/usr/bin/env python3
"""
Library Digitization API
FastAPI + Redis Queue + PostgreSQL + SSE
"""

import os
import uuid
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote
import zipfile
import io

import redis
from fastapi import Depends, FastAPI, UploadFile, File, Form, HTTPException, Request, Query, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

import scripts.db as db
from scripts.sse import job_event_stream

# Module GĐ1-2 + envelope HPU (endpoints MỚI dùng envelope; route cũ giữ nguyên — ADR-003)
from scripts.core import reports, audit, schema_store, provider_view, uploads
from scripts.core import queue as jobqueue
from scripts.core import users as user_store
from scripts.core.responses import success, error as err_envelope

# Danh tính & phân quyền (ADR-012). `require(...)` cưỡng chế ở MÁY CHỦ; ẩn nút trên giao diện chỉ là
# tiện ích. Ba nấc AUTH_MODE quyết định có chặn hay không — xem scripts/auth/deps.py.
from scripts.auth import bootstrap, local as auth_local, policy, sessions
from scripts.auth.deps import Principal, current_principal, require, require_authenticated


# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------

BASE_DIR   = Path(os.getenv("DIGITIZE_DATA_DIR", "/data/digitization/jobs"))
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_QUEUE = "digitization_jobs"

# Kích thước mảnh khi ghi tệp tải lên (ADR-010). Đủ nhỏ để event loop mượt, đủ lớn để không tạo quá
# nhiều lượt chuyển thread. Đổi được khi đĩa/hạ tầng khác nhau, không phải sửa mã.
UPLOAD_CHUNK_SIZE = int(float(os.getenv("UPLOAD_CHUNK_MB", "1")) * 1024 * 1024)

# ---------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("library-api")

# ---------------------------------------------------------------------
# MODELS
# ---------------------------------------------------------------------

class JobStatus(BaseModel):
    job_id:      str
    filename:    str
    status:      str
    progress:    int
    created_at:  str
    finished_at: Optional[str] = None
    error:       Optional[str] = None

class BatchUploadResponse(BaseModel):
    jobs:    List[dict]
    total:   int
    message: str

class MetadataUpdate(BaseModel):
    metadata: List[dict]

class DSpaceCollectionUpdate(BaseModel):
    collection_id:   str
    collection_name: str
    community_name:  Optional[str] = ""

class DSpaceStatusUpdate(BaseModel):
    dspace_status: str                  # uploading | uploaded | upload_failed
    item_id:       Optional[str] = None
    handle:        Optional[str] = None
    error:         Optional[str] = None

# ---------------------------------------------------------------------
# APP
# ---------------------------------------------------------------------

app = FastAPI(
    title="Library Digitization API",
    version="3.0.0",
    description="FastAPI + PostgreSQL + SSE"
)

# CORS: `allow_origins=["*"]` KHÔNG dùng được cùng `allow_credentials=True` — trình duyệt từ chối
# gửi cookie tới nguồn dùng ký tự thay thế, nên khi bật xác thực bằng cookie thì cấu hình cũ sẽ làm
# đăng nhập không hoạt động. Giao diện đã gọi API qua proxy same-origin (commit 440f550) nên mặc định
# không cần mở nguồn nào; đặt `CORS_ORIGINS` (phân tách bằng dấu phẩy) nếu có client khác nguồn.
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if not _cors_origins:
    logger.info("CORS: không mở nguồn ngoài (giao diện dùng proxy same-origin). "
                "Đặt CORS_ORIGINS nếu cần client khác nguồn.")

# ---------------------------------------------------------------------
# STARTUP / SHUTDOWN
# ---------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    # API chạy 2 uvicorn workers → pool cần đủ cho cả hai
    db.init_pool(min_conn=2, max_conn=10)
    logger.info("DB pool initialized")

    # Nấc xác thực hiện tại — ghi rõ ra log vì đây là thông tin vận hành quan trọng nhất khi gỡ lỗi
    # "vì sao gọi API không cần đăng nhập" hoặc "vì sao bị 401" (ADR-012).
    auth_mode = policy.resolve_auth_mode()
    if auth_mode == policy.AUTH_OFF:
        logger.warning("AUTH_MODE=off — API KHÔNG yêu cầu xác thực (hành vi như trước ADR-012). "
                       "Chuyển sang 'shadow' khi đã tạo tài khoản và tập huấn xong.")
    elif auth_mode == policy.AUTH_SHADOW:
        logger.warning("AUTH_MODE=shadow — vẫn phục vụ request thiếu xác thực nhưng CÓ GHI NHẬN. "
                       "Theo dõi sự kiện kind='auth_missing'; chỉ bật 'on' khi 48 giờ liền không có.")
    else:
        logger.info("AUTH_MODE=on — bắt buộc đăng nhập. Van lùi: đặt lại AUTH_MODE=shadow.")

    bootstrap.ensure_admin()

@app.on_event("shutdown")
async def shutdown():
    db.close_pool()
    logger.info("DB pool closed")

# ---------------------------------------------------------------------
# REDIS (vẫn giữ cho queue và backward compat)
# ---------------------------------------------------------------------

try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    redis_client.ping()
    logger.info("Connected to Redis %s:%s", REDIS_HOST, REDIS_PORT)
except Exception as e:
    logger.exception("Redis connection failed")
    raise RuntimeError("Redis unavailable") from e

# ---------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------

def create_job_dirs(job_id: str) -> dict:
    job_dir   = BASE_DIR / job_id
    input_dir  = job_dir / "input"
    output_dir = job_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    return {"job_dir": job_dir, "input_dir": input_dir, "output_dir": output_dir}


def save_upload_file(upload_file: UploadFile, destination: Path):
    """
    ⚠️ ĐỒNG BỘ — chỉ dùng ngoài ngữ cảnh async (CLI, script, test).

    Trong endpoint `async def` PHẢI dùng `save_upload_stream()`: hàm này chặn event loop suốt thời
    gian ghi đĩa (xem ADR-010). Giữ lại để không phá nơi gọi cũ, không xóa.
    """
    with destination.open("wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)


async def save_upload_stream(upload_file: UploadFile, destination: Path) -> tuple:
    """
    Ghi tệp tải lên KHÔNG chặn event loop, băm SHA-256 trong cùng lượt đọc (ADR-010).

    Logic nằm ở `scripts/core/uploads.py` để kiểm thử được mà không cần fastapi/redis; ở đây chỉ tiêm
    `run_in_threadpool` của Starlette vào — dùng thread pool CÓ GIỚI HẠN của web server thay vì
    executor mặc định, để nhiều người tải lên cùng lúc không sinh thread vô hạn.

    Trả về: `(sha256_hex, so_byte)`.
    """
    result = await uploads.save_stream(
        read=upload_file.read,
        destination=destination,
        chunk_size=UPLOAD_CHUNK_SIZE,
        offload=run_in_threadpool,
    )
    return result.sha256, result.size_bytes


def enqueue_job(job_id: str, filename: str, payload: dict,
                priority: str = jobqueue.PRIORITY_NORMAL):
    """
    Ghi Redis hash + đẩy vào queue + tạo document trong DB.

    Đẩy qua `scripts.core.queue.push` để dùng đúng khóa theo mức ưu tiên (ADR-011). Mức `normal` là
    CHÍNH khóa `digitization_jobs` đang dùng, nên hành vi mặc định không đổi — chỉ khác là `LPUSH`
    thay `RPUSH` để khớp chiều nhận từ bên phải của `BLMOVE` (vẫn là FIFO).
    """
    redis_client.hset(
        f"job:{job_id}",
        mapping={
            "status":     "queued",
            "filename":   filename,
            "created_at": datetime.utcnow().isoformat(),
            "progress":   "10",
        },
    )
    jobqueue.push(redis_client, REDIS_QUEUE, payload, priority=priority)

    # Tạo document trong DB
    db.create_document(
        job_id=job_id,
        filename=filename,
        collection_id=payload.get("collection_id", ""),
        document_type=payload.get("document_type", "book"),
    )


def content_disposition(filename: str) -> str:
    return f"attachment; filename*=UTF-8''{quote(filename)}"


def validate_metadata(metadata: dict) -> bool:
    if "metadata" not in metadata or not isinstance(metadata["metadata"], list):
        return False
    keys = [item.get("key") for item in metadata["metadata"]]
    for req in ["dc.title", "dc.type"]:
        if req not in keys:
            logger.warning(f"Missing required field: {req}")
            return False
    for item in metadata["metadata"]:
        if "key" not in item or "value" not in item or not item["value"]:
            return False
    return True


# ---------------------------------------------------------------------
# ROUTES - HEALTH
# ---------------------------------------------------------------------

@app.get("/health")
async def health():
    try:
        redis_client.ping()
        redis_ok = True
    except Exception:
        redis_ok = False

    return {"status": "ok" if redis_ok else "degraded", "redis": redis_ok, "version": "3.0.0"}


# ---------------------------------------------------------------------
# ROUTES - XÁC THỰC (ADR-012)
# ---------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class CreateUserRequest(BaseModel):
    username:  str
    full_name: str
    password:  str
    role:      str
    email:     Optional[str] = None


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    email:     Optional[str] = None
    role:      Optional[str] = None
    status:    Optional[str] = None


def _set_session_cookie(response: Response, token: str) -> None:
    """
    Đặt cookie phiên. `HttpOnly` để JavaScript không đọc được (chống XSS lấy phiên);
    `SameSite=Lax` chống CSRF cho thao tác nguy hiểm mà vẫn cho điều hướng thường hoạt động.

    `Secure` bật theo `SESSION_COOKIE_SECURE` — mặc định TẮT vì hệ đang chạy HTTP nội bộ; bật khi đã
    có HTTPS. Mặc định bật sẽ làm đăng nhập im lặng không hoạt động trên HTTP, một lỗi rất khó lần ra.
    """
    secure = os.getenv("SESSION_COOKIE_SECURE", "0").strip() not in ("0", "false", "no", "")
    response.set_cookie(
        key=sessions.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=sessions.SESSION_TTL_HOURS * 3600,
        path="/",
    )


@app.post("/api/v2/auth/login")
async def api_login(payload: LoginRequest, request: Request, response: Response):
    """
    Đăng nhập vào DocuFlow.

    ⚠️ KHÁC HOÀN TOÀN với `/api/dspace/login` của giao diện — đó là đăng nhập vào DSpace. Hai hệ
    thống, hai bộ tài khoản; trộn lẫn sẽ làm cán bộ nhầm mật khẩu nào dùng ở đâu (ADR-012).
    """
    client_ip = request.client.host if request.client else None
    outcome = auth_local.get_backend()(payload.username, payload.password, ip=client_ip)

    if not outcome.ok:
        audit.log_action(action="login_failed", actor=payload.username,
                         detail={"reason": outcome.reason, "ip": client_ip})
        # 401 cho mọi lý do: mã lý do nằm trong body để giao diện hiển thị đúng thông báo tiếng Việt
        return JSONResponse(status_code=401, content=err_envelope(
            outcome.message, code=(outcome.reason or "UNAUTHORIZED").upper()))

    token = sessions.create_session(
        outcome.user["id"], ip=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, token)
    audit.log_action(action="login", actor=outcome.user["username"], detail={"ip": client_ip})

    return success({
        "user": {
            "user_id": outcome.user["id"],
            "username": outcome.user["username"],
            "full_name": outcome.user["full_name"],
            "role": outcome.user["role"],
            "role_label": policy.ROLE_LABELS.get(outcome.user["role"], outcome.user["role"]),
            "permissions": sorted(user_store.get_role_permissions(outcome.user["role"])),
            "must_change_password": outcome.must_change_password,
        },
    }, "Đăng nhập thành công")


@app.post("/api/v2/auth/logout")
async def api_logout(request: Request, response: Response):
    """Đăng xuất: thu hồi phiên ở máy chủ VÀ xóa cookie. Chỉ xóa cookie là chưa thu hồi được phiên."""
    token = request.cookies.get(sessions.SESSION_COOKIE_NAME)
    actor = policy.LEGACY_ACTOR
    if token:
        row = sessions.resolve_session(token)
        if row:
            actor = row["username"]
        sessions.revoke_session(token)

    response.delete_cookie(sessions.SESSION_COOKIE_NAME, path="/")
    audit.log_action(action="logout", actor=actor)
    return success(None, "Đã đăng xuất")


@app.get("/api/v2/auth/me")
async def api_me(principal: Principal = Depends(current_principal)):
    """
    Ai đang đăng nhập + có những quyền gì. Giao diện dùng để ẩn/hiện menu.

    KHÔNG chặn: ở nấc off/shadow trả về chủ thể "(chưa xác thực)" để giao diện cũ vẫn chạy được.
    """
    return success({**principal.as_dict(), "auth_mode": policy.resolve_auth_mode()},
                   "Thông tin phiên hiện tại")


@app.post("/api/v2/auth/change-password")
async def api_change_password(payload: ChangePasswordRequest, request: Request,
                              principal: Principal = Depends(require_authenticated())):
    """
    Tự đổi mật khẩu. Bắt buộc nhập mật khẩu HIỆN TẠI — nếu không, ai chiếm được phiên sẽ đổi được
    mật khẩu và chiếm luôn tài khoản.
    """
    if not principal.is_authenticated:
        return JSONResponse(status_code=401, content=err_envelope(
            "Bạn cần đăng nhập để đổi mật khẩu", code="UNAUTHORIZED"))

    check = auth_local.authenticate(principal.username, payload.current_password,
                                    ip=request.client.host if request.client else None)
    if not check.ok:
        return JSONResponse(status_code=400, content=err_envelope(
            "Mật khẩu hiện tại không đúng", code="BAD_CURRENT_PASSWORD"))

    try:
        user_store.set_password(principal.user_id, payload.new_password, must_change=False)
    except ValueError as e:
        return JSONResponse(status_code=400, content=err_envelope(
            str(e), code="WEAK_PASSWORD"))

    audit.log_action(action="password_change", actor=principal.actor)
    # `set_password` đã thu hồi mọi phiên (kể cả phiên hiện tại) → giao diện phải đăng nhập lại
    return success({"must_login_again": True},
                   "Đã đổi mật khẩu. Vui lòng đăng nhập lại.")


# ---------------------------------------------------------------------
# ROUTES - QUẢN TRỊ NGƯỜI DÙNG (YC-QT-07)
# ---------------------------------------------------------------------

@app.get("/api/v2/users")
async def api_list_users(status: Optional[str] = Query(None), role: Optional[str] = Query(None),
                         page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=200),
                         principal: Principal = Depends(require(policy.USER_MANAGE))):
    rows = user_store.list_users(status=status, role=role,
                                 limit=per_page, offset=(page - 1) * per_page)
    for r in rows:
        for field in ("created_at", "updated_at", "last_login_at", "locked_until"):
            if r.get(field):
                r[field] = r[field].isoformat()
    return success(rows, f"{len(rows)} người dùng")


@app.get("/api/v2/roles")
async def api_list_roles(principal: Principal = Depends(require(policy.USER_MANAGE))):
    """Vai trò + quyền, kèm nhãn tiếng Việt để người cấp quyền không phải đọc mã quyền."""
    try:
        roles = user_store.list_roles()
    except Exception as e:  # noqa: BLE001 - bảng chưa di trú thì lùi về bảng trong mã
        logger.warning("Không đọc được vai trò từ DB (%s) → dùng bảng trong mã", e)
        roles = [{"code": code, "label": policy.ROLE_LABELS.get(code, code),
                  "permissions": sorted(policy.permissions_for_role(code)), "is_system": True}
                 for code in policy.ALL_ROLES]

    return success({"roles": roles, "permission_labels": policy.PERMISSION_LABELS}, "Vai trò & quyền")


@app.post("/api/v2/users")
async def api_create_user(payload: CreateUserRequest,
                          principal: Principal = Depends(require(policy.USER_MANAGE))):
    try:
        user = user_store.create_user(
            username=payload.username, full_name=payload.full_name,
            password=payload.password, role=payload.role, email=payload.email,
            must_change_password=True, created_by=principal.user_id,
        )
    except ValueError as e:
        return JSONResponse(status_code=400, content=err_envelope(str(e), code="INVALID_INPUT"))
    except Exception as e:  # noqa: BLE001 - trùng tên đăng nhập là ca phổ biến nhất
        logger.warning("Không tạo được người dùng: %s", e)
        return JSONResponse(status_code=400, content=err_envelope(
            "Không tạo được người dùng — có thể tên đăng nhập đã tồn tại",
            code="CREATE_FAILED"))

    audit.log_action(action="user_create", actor=principal.actor,
                     detail={"target_user": payload.username, "role": payload.role})
    return success({"user_id": user["id"], "username": user["username"]},
                   f"Đã tạo người dùng '{user['username']}'. Người dùng phải đổi mật khẩu khi đăng nhập.")


@app.put("/api/v2/users/{user_id}")
async def api_update_user(user_id: int, payload: UpdateUserRequest,
                          principal: Principal = Depends(require(policy.USER_MANAGE))):
    before = user_store.get_user(user_id)
    if not before:
        return JSONResponse(status_code=404, content=err_envelope(
            "Không tìm thấy người dùng", code="NOT_FOUND"))

    # Chốt tự bảo vệ: không cho quản trị viên tự hạ quyền/vô hiệu hóa chính mình. Đây là cách phổ biến
    # nhất để một hệ thống mất hết quản trị viên, và không có đường quay lại qua giao diện.
    if principal.user_id == user_id and (payload.role or payload.status):
        return JSONResponse(status_code=400, content=err_envelope(
            "Không thể tự đổi vai trò hoặc tự vô hiệu hóa tài khoản của mình. "
            "Hãy nhờ một quản trị viên khác thực hiện.", code="SELF_MODIFY_DENIED"))

    try:
        after = user_store.update_user(user_id, full_name=payload.full_name, email=payload.email,
                                       role=payload.role, status=payload.status)
    except ValueError as e:
        return JSONResponse(status_code=400, content=err_envelope(str(e), code="INVALID_INPUT"))

    for field in ("role", "status", "full_name", "email"):
        old, new = before.get(field), (after or {}).get(field)
        if getattr(payload, field, None) is not None and old != new:
            audit.log_action(action="user_update", actor=principal.actor,
                             field_key=field, old_value=str(old), new_value=str(new),
                             detail={"target_user": before["username"]})

    return success({"user_id": user_id}, "Đã cập nhật người dùng")


@app.post("/api/v2/users/{user_id}/reset-password")
async def api_admin_reset_password(user_id: int,
                                   principal: Principal = Depends(require(policy.USER_MANAGE))):
    """
    Quản trị viên đặt lại mật khẩu: sinh mật khẩu tạm, buộc người dùng đổi khi đăng nhập.

    Trả mật khẩu tạm MỘT LẦN trong phản hồi — quản trị viên đọc cho người dùng. Không gửi email vì
    hệ thống phải chạy được khi ngắt Internet (YC-BM-02).
    """
    from scripts.core import passwords

    user = user_store.get_user(user_id)
    if not user:
        return JSONResponse(status_code=404, content=err_envelope(
            "Không tìm thấy người dùng", code="NOT_FOUND"))

    temp_password = passwords.generate_password()
    try:
        user_store.set_password(user_id, temp_password, must_change=True)
    except ValueError as e:
        return JSONResponse(status_code=400, content=err_envelope(str(e), code="WEAK_PASSWORD"))

    user_store.unlock_user(user_id)
    audit.log_action(action="password_reset", actor=principal.actor,
                     detail={"target_user": user["username"]})

    return success({"temp_password": temp_password, "username": user["username"]},
                   "Đã đặt lại mật khẩu. Mật khẩu tạm chỉ hiện MỘT LẦN — hãy chuyển cho người dùng.")


@app.post("/api/v2/users/{user_id}/unlock")
async def api_unlock_user(user_id: int,
                          principal: Principal = Depends(require(policy.USER_MANAGE))):
    user = user_store.get_user(user_id)
    if not user:
        return JSONResponse(status_code=404, content=err_envelope(
            "Không tìm thấy người dùng", code="NOT_FOUND"))

    user_store.unlock_user(user_id)
    audit.log_action(action="user_unlock", actor=principal.actor,
                     detail={"target_user": user["username"]})
    return success({"user_id": user_id}, f"Đã mở khóa '{user['username']}'")


@app.delete("/api/v2/users/{user_id}")
async def api_delete_user(user_id: int,
                          principal: Principal = Depends(require(policy.USER_MANAGE))):
    """
    Vô hiệu hóa người dùng bằng XÓA MỀM (YC-QT-08).

    Không xóa cứng: `audit_log` tham chiếu tới người này, và nhật ký kiểm toán phải truy được trách
    nhiệm kể cả với người đã rời cơ quan.
    """
    if principal.user_id == user_id:
        return JSONResponse(status_code=400, content=err_envelope(
            "Không thể tự xóa tài khoản của mình", code="SELF_DELETE_DENIED"))

    user = user_store.get_user(user_id)
    if not user:
        return JSONResponse(status_code=404, content=err_envelope(
            "Không tìm thấy người dùng", code="NOT_FOUND"))

    user_store.soft_delete_user(user_id)
    audit.log_action(action="user_delete", actor=principal.actor,
                     detail={"target_user": user["username"], "soft_delete": True})
    return success({"user_id": user_id},
                   f"Đã vô hiệu hóa '{user['username']}'. Nhật ký của người này vẫn được giữ.")


@app.get("/api/v2/sessions")
async def api_list_sessions(user_id: Optional[int] = Query(None),
                            principal: Principal = Depends(require(policy.USER_MANAGE))):
    """Phiên đang hoạt động — để thấy ai đang đăng nhập, từ IP nào."""
    rows = sessions.list_sessions(user_id=user_id)
    for r in rows:
        for field in ("created_at", "last_seen_at", "expires_at"):
            if r.get(field):
                r[field] = r[field].isoformat()
    return success(rows, f"{len(rows)} phiên đang hoạt động")


@app.delete("/api/v2/sessions/{session_ref}")
async def api_revoke_session(session_ref: str,
                             principal: Principal = Depends(require(policy.USER_MANAGE))):
    """Thu hồi một phiên — có hiệu lực NGAY ở request kế tiếp của người đó (YC-QT-02)."""
    count = sessions.revoke_by_ref(session_ref)
    if not count:
        return JSONResponse(status_code=404, content=err_envelope(
            "Không tìm thấy phiên đang hoạt động này", code="NOT_FOUND"))

    audit.log_action(action="session_revoke", actor=principal.actor,
                     detail={"session_ref": session_ref})
    return success({"revoked": count}, "Đã thu hồi phiên")


# ---------------------------------------------------------------------
# ROUTES - UPLOAD
# ---------------------------------------------------------------------

@app.post("/api/v1/process")
async def process_document(
    request:    Request,
    file:       UploadFile = File(...),
    collection: str = Form("default"),
    language:   str = Form("vie"),
    doc_type:   str = Form("book"),
    principal:  Principal = Depends(require(policy.DOCUMENT_UPLOAD)),
):
    """Single file upload"""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    job_id = str(uuid.uuid4())
    logger.info("New job %s from %s", job_id, request.client.host)

    paths = create_job_dirs(job_id)
    input_file_path = paths["input_dir"] / file.filename

    try:
        # ADR-010: ghi theo mảnh, không chặn event loop; băm luôn trong cùng lượt đọc
        file_hash, file_size = await save_upload_stream(file, input_file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to save file") from e
    finally:
        await file.close()

    logger.info("Job %s: đã nhận '%s' (%.1f MB, sha256=%s)",
                job_id, file.filename, file_size / 1024 / 1024, file_hash[:12])

    job_payload = {
        "job_id":        job_id,
        "filename":      file.filename,
        "input_file":    str(input_file_path),
        "output_dir":    str(paths["output_dir"]),
        "collection_id": collection,
        "language":      language,
        "document_type": doc_type,
        "file_hash":     file_hash,
        "file_size":     file_size,
    }

    try:
        enqueue_job(job_id, file.filename, job_payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Queue error") from e

    return {
        "job_id":        job_id,
        "status":        "queued",
        "message":       "Job enqueued successfully",
        "filename":      file.filename,
        "collection_id": collection,
        "language":      language,
        "progress":      10,
    }


@app.post("/api/v2/batch-upload", response_model=BatchUploadResponse)
async def batch_upload(
    request:    Request,
    files:      List[UploadFile] = File(...),
    collection: str = Form("default"),
    language:   str = Form("vie"),
    doc_type:   str = Form("book"),
    principal:  Principal = Depends(require(policy.DOCUMENT_UPLOAD)),
):
    """Batch upload (max 10 files)"""
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files allowed")

    for file in files:
        if not file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"{file.filename} is not a PDF")

    jobs = []
    for file in files:
        job_id = str(uuid.uuid4())
        paths  = create_job_dirs(job_id)
        input_file_path = paths["input_dir"] / file.filename

        try:
            # ADR-010: ghi theo mảnh — quan trọng hơn ở đây vì batch ghi tối đa 10 tệp TRONG MỘT
            # request, nên hiệu ứng chặn event loop cộng dồn
            file_hash, file_size = await save_upload_stream(file, input_file_path)
        except Exception:
            logger.exception(f"Failed to save {file.filename}")
            continue
        finally:
            await file.close()

        job_payload = {
            "job_id":        job_id,
            "filename":      file.filename,
            "input_file":    str(input_file_path),
            "output_dir":    str(paths["output_dir"]),
            "collection_id": collection,
            "language":      language,
            "document_type": doc_type,
            "file_hash":     file_hash,
            "file_size":     file_size,
        }

        try:
            enqueue_job(job_id, file.filename, job_payload)
            jobs.append({"job_id": job_id, "filename": file.filename,
                         "status": "queued", "progress": 10})
        except Exception:
            logger.exception(f"Failed to enqueue {file.filename}")

    return BatchUploadResponse(
        jobs=jobs, total=len(jobs),
        message=f"Successfully queued {len(jobs)} jobs"
    )


# ---------------------------------------------------------------------
# ROUTES - SSE
# ---------------------------------------------------------------------

@app.get("/api/v2/jobs/stream")
async def stream_all_jobs():
    """
    SSE stream cho toàn bộ jobs.
    Frontend subscribe 1 lần, nhận updates realtime khi bất kỳ job nào đổi status.

    Dùng EventSource trên frontend:
        const es = new EventSource('/api/v2/jobs/stream')
        es.addEventListener('job_update', e => {
            const data = JSON.parse(e.data)  // {job_id, status, progress, filename, error}
            // cập nhật bảng
        })
    """
    return StreamingResponse(
        job_event_stream(job_id=None),
        media_type="text/event-stream",
        headers={
            "Cache-Control":  "no-cache",
            "X-Accel-Buffering": "no",   # tắt nginx buffering
        },
    )


@app.get("/api/v2/jobs/{job_id}/stream")
async def stream_single_job(job_id: str):
    """
    SSE stream cho 1 job cụ thể.
    Tự đóng khi job đạt terminal status (completed / failed / cancelled).
    """
    return StreamingResponse(
        job_event_stream(job_id=job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------
# ROUTES - STATUS / LIST
# ---------------------------------------------------------------------

@app.get("/api/v1/status/{job_id}")
async def job_status(job_id: str):
    """Get single job status — đọc từ DB, fallback Redis"""
    doc = db.get_document(job_id)
    if not doc:
        # Fallback: kiểm tra Redis (job mới enqueue chưa kịp ghi DB)
        if not redis_client.exists(f"job:{job_id}"):
            raise HTTPException(status_code=404, detail="Job not found")
        job_data = redis_client.hgetall(f"job:{job_id}")
        return {
            "job_id":     job_id,
            "status":     job_data.get("status", "unknown"),
            "filename":   job_data.get("filename", ""),
            "progress":   int(job_data.get("progress", 10)),
            "created_at": job_data.get("created_at"),
        }

    response = {
        "job_id":             doc["id"],
        "filename":           doc["filename"],
        "status":             doc["status"],
        "status_label":       doc["status_label"],
        "status_color":       doc["status_color"],
        "progress":           doc["progress"],
        "created_at":         doc["created_at"].isoformat() if doc["created_at"] else None,
        "finished_at":        doc["finished_at"].isoformat() if doc["finished_at"] else None,
        "error":              doc["error_message"],
        "dspace_status":      doc["dspace_status"],
        "dspace_item_id":     doc["dspace_item_id"],
        "dspace_handle":      doc["dspace_handle"],
    }

    if doc["status"] == "completed":
        metadata = db.get_metadata(job_id)
        response["metadata"] = metadata

    return response


@app.get("/api/v2/jobs")
async def list_jobs(
    status:           Optional[str]  = Query(None),
    dspace_status:    Optional[str]  = Query(None),
    limit:            int            = Query(100, ge=1, le=1000),
    offset:           int            = Query(0, ge=0),
    include_metadata: bool           = Query(False),
    include_deleted:  bool           = Query(False),
    needs_review:     Optional[bool] = Query(None),
):
    """
    List jobs — đọc từ DB.
    Hỗ trợ filter theo status OCR và dspace_status.

    - `include_deleted=true`: hiện cả tài liệu đã xóa mềm (thùng rác).
    - `needs_review=true`: chỉ tài liệu cần cán bộ kiểm tra lại (YC-CF-03).
    """
    docs = db.list_documents(
        status=status,
        dspace_status=dspace_status,
        limit=limit,
        offset=offset,
        include_deleted=include_deleted,
        needs_review=needs_review,
    )

    jobs = []
    for doc in docs:
        job_obj = {
            "job_id":               doc["id"],
            "filename":             doc["filename"],
            "status":               doc["status"],
            "status_label":         doc["status_label"],
            "status_color":         doc["status_color"],
            "progress":             doc["progress"],
            "created_at":           doc["created_at"].isoformat() if doc["created_at"] else None,
            "finished_at":          doc["finished_at"].isoformat() if doc["finished_at"] else None,
            "error":                doc["error_message"],
            # Trích bằng công cụ/chế độ nào + có cần xem lại (YC-AU-04, YC-CF-03)
            "extraction_provider":  doc.get("extraction_provider"),
            "extraction_mode":      doc.get("extraction_mode"),
            "extraction_model":     doc.get("extraction_model"),
            "needs_review":         doc.get("needs_review", False),
            "dspace_status":        doc["dspace_status"],
            "dspace_status_label":  doc["dspace_status_label"],
            "dspace_status_color":  doc["dspace_status_color"],
            "dspace_collection_id": doc["dspace_collection_id"],
            "dspace_collection_name": doc["dspace_collection_name"],
            "dspace_community_name":  doc["dspace_community_name"],
            "dspace_item_id":       doc["dspace_item_id"],
            "dspace_handle":        doc["dspace_handle"],
            "dspace_error":         doc.get("dspace_error"),
        }

        if include_metadata and doc["status"] == "completed":
            job_obj["metadata"] = db.get_metadata(doc["id"])

        jobs.append(job_obj)

    return {"jobs": jobs, "total": len(jobs)}


# ---------------------------------------------------------------------
# ROUTES - METADATA
# ---------------------------------------------------------------------

@app.get("/api/v2/jobs/{job_id}/metadata")
async def get_metadata(job_id: str):
    """Lấy metadata từ DB"""
    doc = db.get_document(job_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")
    if doc["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")

    metadata = db.get_metadata(job_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Metadata not found")

    return metadata


@app.put("/api/v2/jobs/{job_id}/metadata")
async def update_metadata(job_id: str, body: MetadataUpdate,
                          principal: Principal = Depends(require(policy.DOCUMENT_EDIT))):
    """
    Cập nhật metadata — thủ thư hiệu chỉnh trước khi đẩy lên DSpace.
    Trigger DB tự ghi history.
    """
    doc = db.get_document(job_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")
    if doc["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")

    metadata_dict = body.dict()
    if not validate_metadata(metadata_dict):
        raise HTTPException(status_code=400, detail="Invalid metadata format")

    count = db.update_metadata(job_id, body.metadata)

    # Đồng bộ ra file metadata.json (download ZIP vẫn cần)
    metadata_path = BASE_DIR / job_id / "output" / "metadata.json"
    try:
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata_dict, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Could not sync metadata.json for {job_id}: {e}")

    return {"message": "Metadata updated", "job_id": job_id, "fields_updated": count}


@app.get("/api/v2/jobs/{job_id}/metadata/history")
async def get_metadata_history(job_id: str):
    """Lịch sử hiệu chỉnh metadata"""
    doc = db.get_document(job_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")

    history = db.get_metadata_history(job_id)
    return {"job_id": job_id, "history": history}


# ---------------------------------------------------------------------
# ROUTES - DSPACE TRACKING
# ---------------------------------------------------------------------

@app.put("/api/v2/jobs/{job_id}/dspace-collection")
async def set_dspace_collection(job_id: str, body: DSpaceCollectionUpdate,
                                principal: Principal = Depends(require(policy.DOCUMENT_EDIT))):
    """
    Lưu collection người dùng đã chọn trên UI.
    Gọi khi người dùng confirm collection, trước khi bấm upload lên DSpace.
    """
    doc = db.get_document(job_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")
    if doc["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")

    db.set_dspace_collection(
        job_id=job_id,
        collection_id=body.collection_id,
        collection_name=body.collection_name,
        community_name=body.community_name or "",
    )

    return {"message": "Collection updated", "job_id": job_id}


@app.put("/api/v2/jobs/{job_id}/dspace-status")
async def update_dspace_status(job_id: str, body: DSpaceStatusUpdate,
                               principal: Principal = Depends(require(policy.DSPACE_PUSH))):
    """
    Cập nhật trạng thái upload DSpace — gọi từ frontend sau mỗi bước upload.

    Flow:
      PUT dspace-status {dspace_status: "uploading"}
      → upload lên DSpace
      PUT dspace-status {dspace_status: "uploaded", item_id: "...", handle: "..."}
      hoặc
      PUT dspace-status {dspace_status: "upload_failed", error: "..."}
    """
    doc = db.get_document(job_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")

    allowed = {"uploading", "uploaded", "upload_failed"}
    if body.dspace_status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid dspace_status. Allowed: {allowed}")

    db.update_dspace_status(
        job_id=job_id,
        dspace_status=body.dspace_status,
        item_id=body.item_id,
        handle=body.handle,
        error=body.error,
    )

    return {"message": "DSpace status updated", "job_id": job_id, "dspace_status": body.dspace_status}


@app.post("/api/v2/jobs/{job_id}/dspace-reset")
async def reset_dspace_upload(job_id: str,
                              principal: Principal = Depends(require(policy.DSPACE_PUSH))):
    """Reset để thử upload lại sau khi thất bại"""
    doc = db.get_document(job_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Job not found")
    if doc["dspace_status"] != "upload_failed":
        raise HTTPException(status_code=400, detail="Job is not in upload_failed state")

    db.reset_dspace_upload(job_id)
    return {"message": "DSpace upload reset", "job_id": job_id}


@app.get("/api/v2/jobs/pending-dspace")
async def list_pending_dspace():
    """
    Danh sách jobs đã xong OCR nhưng chưa upload DSpace.
    Dùng cho trang preview/upload của frontend.
    """
    docs = db.list_pending_dspace_uploads()
    return {"jobs": docs, "total": len(docs)}


# ---------------------------------------------------------------------
# ROUTES - DOWNLOAD
# ---------------------------------------------------------------------

@app.get("/api/v2/download/batch")
async def download_batch_get(ids: List[str] = Query(...),
                             principal: Principal = Depends(require(policy.DOCUMENT_DOWNLOAD))):
    """Download nhiều jobs thành 1 ZIP qua GET ?ids=x&ids=y (dung voi window.location.href)"""
    return await _download_batch_impl(ids)


@app.get("/api/v2/download/{job_id}")
async def download_job(job_id: str,
                       principal: Principal = Depends(require(policy.DOCUMENT_DOWNLOAD))):
    """Download ZIP chứa PDF đã xử lý + metadata.json"""
    doc = db.get_document(job_id)
    if not doc:
        if not redis_client.exists(f"job:{job_id}"):
            raise HTTPException(status_code=404, detail="Job not found")
        job_data = redis_client.hgetall(f"job:{job_id}")
        if job_data.get("status") != "completed":
            raise HTTPException(status_code=400, detail="Job not completed")
        filename = job_data.get("filename", "document")
    else:
        if doc["status"] != "completed":
            raise HTTPException(status_code=400, detail="Job not completed")
        filename = doc["filename"]

    job_dir = BASE_DIR / job_id / "output"
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Output files not found")

    # Tim file _pdfa.pdf trong output dir
    pdfa_file = None
    metadata_file = job_dir / "metadata.json"

    for file_path in job_dir.iterdir():
        if file_path.is_file() and file_path.name.endswith("_pdfa.pdf"):
            pdfa_file = file_path
            break

    if not pdfa_file:
        raise HTTPException(status_code=404, detail="Processed PDF not found")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(pdfa_file, pdfa_file.name)
        if metadata_file.exists():
            zf.write(metadata_file, "metadata.json")

    zip_buffer.seek(0)
    safe_name = filename.replace(".pdf", "")
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition(f"{safe_name}_processed.zip")},
    )


@app.post("/api/v2/download/batch")
async def download_batch(job_ids: List[str],
                         principal: Principal = Depends(require(policy.DOCUMENT_DOWNLOAD))):
    """Download nhiều jobs thành 1 ZIP qua POST body"""
    return await _download_batch_impl(job_ids)


async def _download_batch_impl(job_ids: List[str]):
    """Download nhiều jobs thành 1 ZIP"""
    if len(job_ids) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 jobs per batch")

    valid_jobs = []
    for job_id in job_ids:
        doc = db.get_document(job_id)
        if doc and doc["status"] == "completed":
            valid_jobs.append({"job_id": job_id, "filename": doc["filename"]})

    if not valid_jobs:
        raise HTTPException(status_code=400, detail="No completed jobs found")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
        for job in valid_jobs:
            job_dir  = BASE_DIR / job["job_id"] / "output"
            safe_name = job["filename"].replace(".pdf", "")
            if not job_dir.exists():
                continue
            pdfa = next((f for f in job_dir.iterdir() if f.is_file() and f.name.endswith("_pdfa.pdf")), None)
            meta = job_dir / "metadata.json"
            if pdfa:
                master_zip.write(pdfa, Path(safe_name) / pdfa.name)
            if meta.exists():
                master_zip.write(meta, Path(safe_name) / "metadata.json")

    zip_buffer.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition(f"batch_download_{ts}.zip")},
    )


# ---------------------------------------------------------------------
# ROUTES - MANAGEMENT
# ---------------------------------------------------------------------

@app.delete("/api/v2/jobs/{job_id}")
async def delete_job(job_id: str, purge: bool = Query(False),
                     principal: Principal = Depends(require(policy.DOCUMENT_DELETE))):
    """
    XÓA MỀM job: đặt status='deleted', **giữ nguyên** file PDF/OCR và metadata (chuẩn HPU).

    Vì sao giữ file: bản PDF đã OCR là phần dữ liệu giá trị nhất của hệ thống (xem docs/DEPLOY.md
    mục sao lưu). Nếu xóa file mà chỉ giữ bản ghi thì "xóa mềm" là ảo — phục hồi ra một tài liệu
    trỏ vào hư không.

    `purge=true`: xóa VẬT LÝ cả bản ghi và file, KHÔNG phục hồi được. Chỉ dùng cho yêu cầu xóa dữ
    liệu thật sự (vd dữ liệu cá nhân — YC-PL-06). Ghi audit TRƯỚC khi xóa.
    """
    doc = db.get_document(job_id)
    if not doc and not redis_client.exists(f"job:{job_id}"):
        raise HTTPException(status_code=404, detail="Job not found")

    if purge:
        # Xóa VẬT LÝ đòi quyền riêng, cao hơn xóa mềm (chỉ `admin` có `document:purge`). Trước đây
        # bất kỳ ai gọi được API đều thêm `?purge=true` là xóa vĩnh viễn tài liệu — không phục hồi được.
        if not principal.can(policy.DOCUMENT_PURGE):
            return JSONResponse(status_code=403, content=err_envelope(
                "Chỉ quản trị viên được xóa vĩnh viễn. Bạn có thể xóa mềm (tài liệu vào thùng rác).",
                code="FORBIDDEN"))

        # Ghi bằng chứng trước, vì sau khi xóa thì không còn tài liệu để gắn bản ghi kiểm toán
        audit.log_action(
            action=audit.ACTION_DELETE, document_id=job_id, actor=principal.actor,
            detail={"purge": True, "filename": (doc or {}).get("filename"),
                    "note": "Xóa vật lý theo yêu cầu — không phục hồi được"},
        )
        db.purge_document(job_id)
        redis_client.delete(f"job:{job_id}")
        job_dir = BASE_DIR / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir)
        return {"message": "Job purged (đã xóa vật lý, không phục hồi được)", "job_id": job_id,
                "purged": True}

    db.delete_document(job_id)          # xóa mềm: chỉ đổi status
    redis_client.delete(f"job:{job_id}")   # trạng thái tạm trong Redis — DB là nguồn sự thật
    audit.log_action(
        action=audit.ACTION_DELETE, document_id=job_id, actor=principal.actor,
        detail={"purge": False, "filename": (doc or {}).get("filename")},
    )
    return {"message": "Job deleted (xóa mềm — có thể phục hồi)", "job_id": job_id, "purged": False}


@app.post("/api/v2/jobs/{job_id}/restore")
async def restore_job(job_id: str,
                      principal: Principal = Depends(require(policy.DOCUMENT_DELETE))):
    """Phục hồi job đã xóa mềm. Có xóa mềm thì phải có đường về."""
    if not db.restore_document(job_id):
        raise HTTPException(status_code=404,
                            detail="Không tìm thấy job đã xóa mềm với id này")
    audit.log_action(action="restore", document_id=job_id, actor=principal.actor)
    return success({"job_id": job_id}, "Đã phục hồi tài liệu")


@app.get("/api/v2/stats")
async def get_stats():
    """
    Thống kê từ DB + tình trạng hàng đợi + SỐ WORKER ĐANG SỐNG.

    `workers_alive` đếm khóa nhịp tim (TTL 60s) mà worker ghi mỗi vòng lặp. Có con số này thì giao
    diện phân biệt được "đang xử lý, chờ chút" với "KHÔNG có worker nào chạy, đợi mãi cũng vô ích" —
    trước đây hai trường hợp đó trông giống nhau y hệt.
    """
    stats = db.get_stats()
    stats["queue_length"] = redis_client.llen(REDIS_QUEUE)

    # Độ sâu ĐẦY ĐỦ mọi hàng đợi (ADR-011): `queue_length` ở trên chỉ đếm mức normal nên giữ nguyên
    # cho client cũ, còn `queue` mới cho biết cả job đang thử lại, job chết, job đang xử lý — trước
    # đây những job này "vô hình" trên giao diện.
    try:
        stats["queue"] = jobqueue.depth(redis_client, REDIS_QUEUE).as_dict()
    except Exception as e:  # noqa: BLE001 - Redis lỗi không được làm sập trang thống kê
        logger.warning("Không đọc được độ sâu hàng đợi: %s", e)
        stats["queue"] = None

    try:
        # Keyspace nhỏ (một khóa/worker) nên scan rẻ; dùng scan_iter để không chặn Redis
        stats["workers_alive"] = sum(1 for _ in redis_client.scan_iter("worker:heartbeat:*", count=100))
    except Exception as e:  # noqa: BLE001 - Redis lỗi không được làm sập trang thống kê
        logger.warning("Không đếm được worker đang sống: %s", e)
        stats["workers_alive"] = None      # None = KHÔNG BIẾT, khác hẳn 0 = không có worker nào

    return stats


@app.get("/api/v2/lookup/document-types")
async def get_document_types():
    return db.get_document_types()


@app.get("/api/v2/lookup/job-statuses")
async def get_job_statuses():
    return db.get_job_statuses()


@app.get("/api/v2/lookup/dspace-statuses")
async def get_dspace_statuses():
    return db.get_dspace_upload_statuses()


# ---------------------------------------------------------------------
# ROUTES - SCHEMAS / AUDIT / REPORTS (endpoints MỚI, envelope HPU — ADR-003)
# ---------------------------------------------------------------------

@app.get("/api/v2/schemas")
async def api_list_schemas():
    """Danh sách lược đồ trích xuất (YC-SC)."""
    return success(schema_store.list_schemas(), "Danh sách lược đồ")


@app.get("/api/v2/schemas/{code}")
async def api_get_schema(code: str):
    """Chi tiết 1 lược đồ (YC-SC)."""
    s = schema_store.load_schema(code)
    if not s:
        return JSONResponse(status_code=404,
                            content=err_envelope(f"Không tìm thấy lược đồ '{code}'", code="NOT_FOUND"))
    return success(schema_store.schema_to_dict(s), "Chi tiết lược đồ")


@app.get("/api/v2/reports/by-mode")
async def api_report_by_mode(date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None)):
    """Báo cáo tài liệu theo chế độ xử lý cloud/local (YC-DR-06)."""
    return success(reports.report_by_mode(date_from, date_to), "Thống kê theo chế độ")


@app.get("/api/v2/reports/field-edits")
async def api_report_field_edits(date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None)):
    """Trường bị cán bộ sửa nhiều nhất (YC-CF-07)."""
    return success(reports.report_field_edit_rate(date_from, date_to), "Tỉ lệ trường bị sửa")


@app.get("/api/v2/reports/throughput")
async def api_report_throughput(date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None)):
    """Throughput OCR theo ngày (hoàn thành/thất bại)."""
    return success(reports.report_throughput(date_from, date_to), "Throughput theo ngày")


@app.get("/api/v2/reports/actions")
async def api_report_actions(date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None)):
    """Tổng quan số thao tác theo loại (từ audit)."""
    return success(reports.report_action_summary(date_from, date_to), "Tổng quan thao tác")


@app.get("/api/v2/jobs/{job_id}/audit")
async def api_document_audit(job_id: str,
                             principal: Principal = Depends(require(policy.AUDIT_READ))):
    """Nhật ký kiểm toán toàn vòng đời 1 tài liệu (YC-AU-01)."""
    return success(audit.get_document_audit_trail(job_id), "Nhật ký tài liệu")


@app.get("/api/v2/audit")
async def api_list_audit(
    actor:     Optional[str] = Query(None),
    action:    Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    limit:     int           = Query(500, ge=1, le=5000),
    principal: Principal     = Depends(require(policy.AUDIT_READ)),
):
    """Kết xuất nhật ký kiểm toán theo bộ lọc thời gian/người/loại (YC-AU-05)."""
    rows = audit.list_audit(actor=actor, action=action, date_from=date_from, date_to=date_to, limit=limit)
    return success(rows, "Nhật ký kiểm toán")


# ---------------------------------------------------------------------
# ROUTES - CÔNG CỤ MÔ HÌNH (YC-MS-08, YC-MP-06) — envelope HPU
# ---------------------------------------------------------------------

@app.get("/api/v2/providers")
async def api_providers(check_health: bool = Query(True)):
    """
    Công cụ mô hình đang dùng + tình trạng + danh sách lựa chọn (YC-MS-08).

    `check_health=false` để bỏ qua lời gọi kiểm tra sẵn sàng (nhanh hơn khi chỉ cần danh sách).
    Logic nằm ở `core/provider_view.py` để test được không cần HTTP; endpoint chỉ bọc envelope.
    """
    return success(provider_view.build_provider_view(check_health=check_health), "Công cụ mô hình")


@app.get("/api/v2/model-calls")
async def api_model_calls(
    document_id: Optional[str] = Query(None),
    provider:    Optional[str] = Query(None),
    deployment:  Optional[str] = Query(None),
    limit:       int           = Query(200, ge=1, le=2000),
    offset:      int           = Query(0, ge=0),
    summary:     bool          = Query(False),
):
    """
    Nhật ký gọi model — provider/model/thời gian/tài nguyên (YC-MP-06, YC-MS-07).
    `summary=true` trả bảng gộp theo công cụ để so sánh (số lần gọi, thời gian TB, RAM đỉnh).
    """
    rows = db.list_model_calls(document_id=document_id, provider=provider,
                              deployment=deployment, limit=limit, offset=offset)
    if summary:
        return success(provider_view.summarize_model_calls(rows), "Tổng hợp theo công cụ")

    for r in rows:
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
    return success(rows, "Nhật ký gọi model")


# ---------------------------------------------------------------------
# ROUTES - THEO DÕI VẬN HÀNH (trạng thái kết nối, lỗi, thời gian xử lý)
# ---------------------------------------------------------------------

@app.get("/api/v2/health/detailed")
async def api_health_detailed():
    """
    Tình trạng TỪNG thành phần, thay vì một chữ "ok" chung.

    Vì sao cần: `/health` cũ chỉ kiểm Redis. Khi hệ thống "im lặng" thì câu hỏi thật là *cái nào*
    đang hỏng — Redis, PostgreSQL, worker, hay công cụ mô hình. Mỗi thành phần trả `ready` + `detail`
    bằng tiếng Việt để người vận hành đọc được ngay, không phải suy từ mã lỗi.
    """
    components = {}

    # Redis + hàng đợi
    try:
        redis_client.ping()
        queue_len = redis_client.llen(REDIS_QUEUE)
        workers = sum(1 for _ in redis_client.scan_iter("worker:heartbeat:*", count=100))
        components["redis"] = {"ready": True, "detail": "Kết nối bình thường",
                               "queue_length": queue_len, "workers_alive": workers}
    except Exception as e:  # noqa: BLE001
        components["redis"] = {"ready": False, "detail": f"Không nối được Redis: {e}",
                               "queue_length": None, "workers_alive": None}

    # PostgreSQL
    try:
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        components["postgres"] = {"ready": True, "detail": "Kết nối bình thường"}
    except Exception as e:  # noqa: BLE001
        components["postgres"] = {"ready": False, "detail": f"Không nối được PostgreSQL: {e}"}

    # Công cụ mô hình đang cấu hình
    try:
        from scripts.providers.factory import get_provider
        provider = get_provider()
        h = provider.health()
        components["model_provider"] = {
            "ready": h.ready, "detail": h.detail,
            "provider": provider.name, "deployment": provider.deployment, "model": provider.model,
        }
    except Exception as e:  # noqa: BLE001
        components["model_provider"] = {"ready": False, "detail": f"Cấu hình không dùng được: {e}"}

    # Worker: có nhịp tim nào không, và hàng đợi có bị ứ không
    redis_info = components["redis"]
    workers_alive = redis_info.get("workers_alive")
    queue_length = redis_info.get("queue_length")
    if workers_alive is None:
        components["worker"] = {"ready": False, "detail": "Không đọc được Redis nên chưa rõ"}
    elif workers_alive == 0:
        components["worker"] = {
            "ready": False,
            "detail": ("KHÔNG có worker nào đang chạy"
                       + (f" — {queue_length} tài liệu đang chờ vô ích. "
                          "Chạy `docker compose up -d --build` (KHÔNG kèm tên service)."
                          if queue_length else ".")),
        }
    else:
        components["worker"] = {"ready": True,
                                "detail": f"{workers_alive} worker đang chạy"}

    all_ready = all(c.get("ready") for c in components.values())
    return success(
        {"ready": all_ready, "components": components},
        "Hệ thống bình thường" if all_ready else "Có thành phần chưa sẵn sàng",
    )


@app.get("/api/v2/system-events")
async def api_system_events(
    level:       Optional[str] = Query(None, description="info | warning | error"),
    kind:        Optional[str] = Query(None),
    status:      Optional[str] = Query(None, description="new | resolved"),
    since_hours: Optional[int] = Query(None, ge=1, le=720),
    limit:       int           = Query(100, ge=1, le=1000),
):
    """Sự kiện hạ tầng: mất/nối lại kết nối, lỗi vòng lặp worker, job thất bại (theo dõi vận hành)."""
    rows = db.list_system_events(level=level, kind=kind, status=status,
                                since_hours=since_hours, limit=limit)
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
    return success(rows, "Sự kiện hệ thống")


# ---------------------------------------------------------------------
# ROUTES - HÀNG ĐỢI (ADR-011)
# ---------------------------------------------------------------------

@app.get("/api/v2/queue")
async def api_queue_depth():
    """Độ sâu mọi hàng đợi: chờ theo mức ưu tiên, đang thử lại, đã chết, đang xử lý."""
    try:
        depth = jobqueue.depth(redis_client, REDIS_QUEUE)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=503, content=err_envelope(
            f"Không đọc được hàng đợi: {e}", code="QUEUE_UNAVAILABLE"))
    return success({**depth.as_dict(), "mode": os.getenv("QUEUE_MODE", "reliable")},
                   "Tình trạng hàng đợi")


@app.get("/api/v2/queue/dead")
async def api_queue_dead(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    """
    Hàng đợi chết: job đã hết lượt thử hoặc lỗi tài liệu, kèm LÝ DO đọc được (KT-BU-21).

    Trước ADR-011 những job này biến mất không dấu vết — tài liệu treo mãi ở "Chờ xử lý".
    """
    try:
        rows = jobqueue.list_dead(redis_client, REDIS_QUEUE, limit=limit, offset=offset)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=503, content=err_envelope(
            f"Không đọc được hàng đợi chết: {e}", code="QUEUE_UNAVAILABLE"))
    return success(rows, f"{len(rows)} job trong hàng đợi chết")


@app.post("/api/v2/queue/dead/{job_id}/retry")
async def api_queue_retry_dead(job_id: str,
                               principal: Principal = Depends(require(policy.QUEUE_MANAGE))):
    """
    Chạy lại một job từ hàng đợi chết. GIỮ NGUYÊN `job_id` để không tạo bản ghi tài liệu trùng.
    """
    try:
        ok = jobqueue.retry_dead(redis_client, REDIS_QUEUE, job_id)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=503, content=err_envelope(
            f"Không chạy lại được: {e}", code="QUEUE_UNAVAILABLE"))

    if not ok:
        return JSONResponse(status_code=404, content=err_envelope(
            "Không tìm thấy job này trong hàng đợi chết", code="NOT_FOUND"))

    db.update_document_status(job_id, "queued", progress=10,
                              error_message="Được chạy lại từ hàng đợi chết")
    audit.log_action(action="queue_retry", document_id=job_id, actor=principal.actor)
    return success({"job_id": job_id}, "Đã đưa tài liệu trở lại hàng đợi")


@app.post("/api/v2/queue/dead/retry-all")
async def api_queue_retry_all_dead(limit: int = Query(500, ge=1, le=5000),
                                   principal: Principal = Depends(require(policy.QUEUE_MANAGE))):
    """Chạy lại toàn bộ hàng đợi chết — dùng sau khi đã sửa nguyên nhân chung (vd Redis/DB đã lên lại)."""
    try:
        count = jobqueue.retry_all_dead(redis_client, REDIS_QUEUE, limit=limit)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=503, content=err_envelope(
            f"Không chạy lại được: {e}", code="QUEUE_UNAVAILABLE"))

    audit.log_action(action="queue_retry_all", actor=principal.actor, detail={"count": count})
    return success({"count": count}, f"Đã đưa {count} tài liệu trở lại hàng đợi")


@app.get("/api/v2/reports/processing-time")
async def api_processing_time(since_hours: int = Query(24, ge=1, le=720)):
    """
    Thời gian xử lý tài liệu (YC-HN). Trả p50/p95 chứ không chỉ trung bình: một tài liệu 500 trang
    kéo trung bình lên và che mất thực tế của phần lớn tài liệu.
    """
    return success(db.processing_time_summary(since_hours=since_hours),
                   f"Thời gian xử lý {since_hours} giờ gần nhất")


# ---------------------------------------------------------------------
# GLOBAL ERROR HANDLER
# ---------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(_, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )