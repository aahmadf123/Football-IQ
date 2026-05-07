"""R2 / S3-compatible storage helpers for the GPU worker pipeline.

All uploads/downloads go through boto3 using Cloudflare R2's S3-compat API.
The bucket name is read from the R2_BUCKET_NAME env var (default: football-iq).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import boto3
import structlog

log = structlog.get_logger(__name__)

R2_ENDPOINT = os.environ.get("R2_ENDPOINT_URL", "")
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.environ.get("R2_BUCKET_NAME", "football-iq")


def _s3_client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
    )


def download_to_temp(r2_key: str) -> Path:
    """Download an R2 object to a local temporary file and return the path.

    The caller is responsible for deleting the file when finished.
    """
    suffix = Path(r2_key).suffix or ".bin"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        log.info("r2_download_start", key=r2_key)
        _s3_client().download_fileobj(R2_BUCKET, r2_key, tmp)
        tmp.flush()
        log.info("r2_download_done", key=r2_key, path=tmp.name)
        return Path(tmp.name)
    finally:
        tmp.close()


def upload_file(local_path: Path, r2_key: str, content_type: str = "application/octet-stream") -> str:
    """Upload a local file to R2 and return the R2 URI (r2://<bucket>/<key>)."""
    log.info("r2_upload_start", key=r2_key, path=str(local_path))
    with local_path.open("rb") as fh:
        _s3_client().upload_fileobj(
            fh,
            R2_BUCKET,
            r2_key,
            ExtraArgs={"ContentType": content_type},
        )
    uri = f"r2://{R2_BUCKET}/{r2_key}"
    log.info("r2_upload_done", key=r2_key, uri=uri)
    return uri


def upload_bytes(data: bytes, r2_key: str, content_type: str = "application/octet-stream") -> str:
    """Upload raw bytes to R2 and return the R2 URI."""
    import io

    log.info("r2_upload_bytes_start", key=r2_key, size=len(data))
    _s3_client().upload_fileobj(
        io.BytesIO(data),
        R2_BUCKET,
        r2_key,
        ExtraArgs={"ContentType": content_type},
    )
    uri = f"r2://{R2_BUCKET}/{r2_key}"
    log.info("r2_upload_bytes_done", key=r2_key, uri=uri)
    return uri
