"""R2 / S3-compatible storage helpers for the GPU worker pipeline.

All uploads/downloads go through boto3 using Cloudflare R2's S3-compat API.
The bucket name is read from the R2_BUCKET_NAME env var (default: football-iq).
"""

from __future__ import annotations

import io
import os
import tempfile
import time
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


def _record_r2(operation: str, outcome: str, duration: float) -> None:
    """Best-effort metrics emission — never raises."""
    try:
        from worker.observability import record_r2_operation

        record_r2_operation(operation, R2_BUCKET, outcome, duration)
    except Exception:
        pass


def download_to_temp(r2_key: str) -> Path:
    """Download an R2 object to a local temporary file and return the path.

    The caller is responsible for deleting the file when finished.
    """
    suffix = Path(r2_key).suffix or ".bin"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    start = time.monotonic()
    try:
        log.info("r2_download_start", key=r2_key, bucket=R2_BUCKET)
        _s3_client().download_fileobj(R2_BUCKET, r2_key, tmp)
        tmp.flush()
        duration = time.monotonic() - start
        _record_r2("download", "success", duration)
        log.info("r2_download_done", key=r2_key, path=tmp.name,
                 duration_seconds=round(duration, 3))
        return Path(tmp.name)
    except Exception as exc:
        duration = time.monotonic() - start
        _record_r2("download", "error", duration)
        log.error("r2_download_failed", key=r2_key, bucket=R2_BUCKET,
                  error=str(exc), duration_seconds=round(duration, 3))
        raise
    finally:
        tmp.close()


def upload_file(local_path: Path, r2_key: str, content_type: str = "application/octet-stream") -> str:
    """Upload a local file to R2 and return the R2 URI (r2://<bucket>/<key>)."""
    start = time.monotonic()
    try:
        log.info("r2_upload_start", key=r2_key, path=str(local_path), bucket=R2_BUCKET)
        with local_path.open("rb") as fh:
            _s3_client().upload_fileobj(
                fh,
                R2_BUCKET,
                r2_key,
                ExtraArgs={"ContentType": content_type},
            )
        uri = f"r2://{R2_BUCKET}/{r2_key}"
        duration = time.monotonic() - start
        _record_r2("upload", "success", duration)
        log.info("r2_upload_done", key=r2_key, uri=uri,
                 duration_seconds=round(duration, 3))
        return uri
    except Exception as exc:
        duration = time.monotonic() - start
        _record_r2("upload", "error", duration)
        log.error("r2_upload_failed", key=r2_key, bucket=R2_BUCKET,
                  error=str(exc), duration_seconds=round(duration, 3))
        raise


def upload_bytes(data: bytes, r2_key: str, content_type: str = "application/octet-stream") -> str:
    """Upload raw bytes to R2 and return the R2 URI."""
    start = time.monotonic()
    try:
        log.info("r2_upload_bytes_start", key=r2_key, size=len(data), bucket=R2_BUCKET)
        _s3_client().upload_fileobj(
            io.BytesIO(data),
            R2_BUCKET,
            r2_key,
            ExtraArgs={"ContentType": content_type},
        )
        uri = f"r2://{R2_BUCKET}/{r2_key}"
        duration = time.monotonic() - start
        _record_r2("upload_bytes", "success", duration)
        log.info("r2_upload_bytes_done", key=r2_key, uri=uri,
                 duration_seconds=round(duration, 3))
        return uri
    except Exception as exc:
        duration = time.monotonic() - start
        _record_r2("upload_bytes", "error", duration)
        log.error("r2_upload_bytes_failed", key=r2_key, bucket=R2_BUCKET,
                  error=str(exc), duration_seconds=round(duration, 3))
        raise
