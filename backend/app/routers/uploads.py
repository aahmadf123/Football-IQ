"""Uploads router — Worker-parity upload/download endpoints on the backend.

Mirrors the Cloudflare Worker's edge contract exactly, so the frontend uses
one code path in both deployments (``workerBase()`` falls back to the API
base when ``NEXT_PUBLIC_WORKER_URL`` is unset):

    POST /api/v1/videos/upload-url         -> { uploadUrl, key }
    PUT  /api/v1/videos/upload/{key}       -> { key, size, etag, storageUri }
    GET  /api/v1/videos/download-url       -> { downloadUrl }

The response field names are camelCase on purpose — they are the Worker's
wire shapes (see workers/src/index.ts), not backend conventions.

NOTE: this router must be registered BEFORE the videos router so the
literal ``/download-url`` path wins over ``/{video_id}``.
"""

import hashlib
import time
from typing import Annotated
from urllib.parse import quote

import structlog
from anyio import to_thread
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from app.config import get_settings
from app.deps import get_current_user
from app.models import User
from app.storage import (
    DOWNLOADABLE_BUCKETS,
    active_storage_backend,
    generate_download_url,
    get_r2_client,
    is_valid_key,
    local_object_path,
)

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/videos", tags=["uploads"])

_RAW_BUCKET = "raw-video"


class UploadUrlRequest(BaseModel):
    filename: str


@router.post("/upload-url")
async def create_upload_url(
    body: UploadUrlRequest,
    _current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    """Mint an upload key + proxy URL (Worker parity)."""
    if not body.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="filename is required")
    settings = get_settings()
    # Worker uses `raw/${Date.now()}-${filename}`; mirror it. The filename is
    # embedded in the key, so strip path separators and traversal sequences.
    safe_name = body.filename.replace("\\", "/").split("/")[-1].replace("..", "_") or "upload.bin"
    key = f"raw/{int(time.time() * 1000)}-{safe_name}"
    base = settings.public_api_base_url.rstrip("/")
    upload_url = f"{base}/api/v1/videos/upload/{quote(key, safe='')}"
    return {"uploadUrl": upload_url, "key": key}


@router.put("/upload/{key:path}", status_code=status.HTTP_201_CREATED)
async def upload_object(
    key: str,
    request: Request,
    _current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    """Stream the request body into raw-video storage (Worker parity)."""
    if not key or not is_valid_key(key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing upload key")

    md5 = hashlib.md5(usedforsecurity=False)
    size = 0

    if active_storage_backend() == "local":
        path = local_object_path(_RAW_BUCKET, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as out:
            async for chunk in request.stream():
                out.write(chunk)
                md5.update(chunk)
                size += len(chunk)
        storage_uri = f"local://{_RAW_BUCKET}/{key}"
    else:
        import tempfile

        content_type = request.headers.get("content-type", "video/mp4")
        with tempfile.NamedTemporaryFile() as tmp:
            async for chunk in request.stream():
                tmp.write(chunk)
                md5.update(chunk)
                size += len(chunk)
            tmp.flush()
            tmp.seek(0)
            client = get_r2_client()
            await to_thread.run_sync(
                lambda: client.upload_fileobj(
                    tmp, _RAW_BUCKET, key, ExtraArgs={"ContentType": content_type}
                )
            )
        storage_uri = f"r2://{_RAW_BUCKET}/{key}"

    log.info("upload_stored", key=key, size=size, backend=active_storage_backend())
    return {"key": key, "size": size, "etag": md5.hexdigest(), "storageUri": storage_uri}


@router.get("/download-url")
async def create_download_url(
    _current_user: Annotated[User, Depends(get_current_user)],
    bucket: str = Query(...),
    key: str = Query(...),
) -> dict[str, str]:
    """Mint a short-lived streaming URL for ``bucket/key`` (Worker parity)."""
    if bucket not in DOWNLOADABLE_BUCKETS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Bucket not allowed: {bucket}"
        )
    if not is_valid_key(key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid key")
    try:
        download_url = generate_download_url(bucket, key)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return {"downloadUrl": download_url}
