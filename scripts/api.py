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
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import scripts.db as db
from scripts.sse import job_event_stream

# Module GĐ1-2 + envelope HPU (endpoints MỚI dùng envelope; route cũ giữ nguyên — ADR-003)
from scripts.core import reports, audit, schema_store, provider_view
from scripts.core.responses import success, error as err_envelope


# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------

BASE_DIR   = Path(os.getenv("DIGITIZE_DATA_DIR", "/data/digitization/jobs"))
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_QUEUE = "digitization_jobs"

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------
# STARTUP / SHUTDOWN
# ---------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    # API chạy 2 uvicorn workers → pool cần đủ cho cả hai
    db.init_pool(min_conn=2, max_conn=10)
    logger.info("DB pool initialized")

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
    with destination.open("wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)


def enqueue_job(job_id: str, filename: str, payload: dict):
    """Ghi Redis hash + đẩy vào queue + tạo document trong DB"""
    redis_client.hset(
        f"job:{job_id}",
        mapping={
            "status":     "queued",
            "filename":   filename,
            "created_at": datetime.utcnow().isoformat(),
            "progress":   "10",
        },
    )
    redis_client.rpush(REDIS_QUEUE, json.dumps(payload))

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
# ROUTES - UPLOAD
# ---------------------------------------------------------------------

@app.post("/api/v1/process")
async def process_document(
    request:    Request,
    file:       UploadFile = File(...),
    collection: str = Form("default"),
    language:   str = Form("vie"),
    doc_type:   str = Form("book"),
):
    """Single file upload"""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    job_id = str(uuid.uuid4())
    logger.info("New job %s from %s", job_id, request.client.host)

    paths = create_job_dirs(job_id)
    input_file_path = paths["input_dir"] / file.filename

    try:
        save_upload_file(file, input_file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to save file") from e
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
            save_upload_file(file, input_file_path)
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
async def update_metadata(job_id: str, body: MetadataUpdate):
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
async def set_dspace_collection(job_id: str, body: DSpaceCollectionUpdate):
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
async def update_dspace_status(job_id: str, body: DSpaceStatusUpdate):
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
async def reset_dspace_upload(job_id: str):
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
async def download_batch_get(ids: List[str] = Query(...)):
    """Download nhiều jobs thành 1 ZIP qua GET ?ids=x&ids=y (dung voi window.location.href)"""
    return await _download_batch_impl(ids)


@app.get("/api/v2/download/{job_id}")
async def download_job(job_id: str):
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
async def download_batch(job_ids: List[str]):
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
async def delete_job(job_id: str, purge: bool = Query(False), actor: str = Query("api")):
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
        # Ghi bằng chứng trước, vì sau khi xóa thì không còn tài liệu để gắn bản ghi kiểm toán
        audit.log_action(
            action=audit.ACTION_DELETE, document_id=job_id, actor=actor,
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
        action=audit.ACTION_DELETE, document_id=job_id, actor=actor,
        detail={"purge": False, "filename": (doc or {}).get("filename")},
    )
    return {"message": "Job deleted (xóa mềm — có thể phục hồi)", "job_id": job_id, "purged": False}


@app.post("/api/v2/jobs/{job_id}/restore")
async def restore_job(job_id: str, actor: str = Query("api")):
    """Phục hồi job đã xóa mềm. Có xóa mềm thì phải có đường về."""
    if not db.restore_document(job_id):
        raise HTTPException(status_code=404,
                            detail="Không tìm thấy job đã xóa mềm với id này")
    audit.log_action(action="restore", document_id=job_id, actor=actor)
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
async def api_document_audit(job_id: str):
    """Nhật ký kiểm toán toàn vòng đời 1 tài liệu (YC-AU-01)."""
    return success(audit.get_document_audit_trail(job_id), "Nhật ký tài liệu")


@app.get("/api/v2/audit")
async def api_list_audit(
    actor:     Optional[str] = Query(None),
    action:    Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    limit:     int           = Query(500, ge=1, le=5000),
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
# GLOBAL ERROR HANDLER
# ---------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(_, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )