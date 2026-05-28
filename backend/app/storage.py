"""Server-side R2 (S3-compatible) client + presigned URL helpers.

Used by the reports/export service (Issue #111) to upload generated artifacts
and mint short-lived download URLs. This is the first server-side R2 client
in the backend — earlier R2 access went through the Cloudflare Worker for the
streaming/HLS path. Reports are one-off downloads, so a direct boto3
presigned ``get_object`` URL is the simpler correct fit and avoids sharing a
JWT secret with the Worker.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from app.config import get_settings


def _parse_r2_uri(uri: str) -> tuple[str, str]:
    """Split an ``r2://bucket/key`` URI into ``(bucket, key)``."""
    if not uri.startswith("r2://"):
        raise ValueError(f"Not an r2:// URI: {uri!r}")
    rest = uri[len("r2://") :]
    if "/" not in rest:
        raise ValueError(f"Malformed r2:// URI (no key): {uri!r}")
    bucket, key = rest.split("/", 1)
    return bucket, key


@lru_cache(maxsize=1)
def get_r2_client() -> Any:
    """Return a lazily-built boto3 R2 client configured from app settings.

    Memoised so the same client is reused for the process lifetime. Raises
    a clear error when R2 credentials are not configured.
    """
    settings = get_settings()
    if not settings.r2_endpoint_url or not settings.r2_access_key_id:
        raise RuntimeError(
            "R2 storage is not configured. Set R2_ENDPOINT_URL, "
            "R2_ACCESS_KEY_ID, and R2_SECRET_ACCESS_KEY in the environment."
        )
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def put_object(bucket: str, key: str, body: bytes, content_type: str) -> str:
    """Upload ``body`` to ``bucket/key`` and return the canonical ``r2://`` URI."""
    client = get_r2_client()
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
    return f"r2://{bucket}/{key}"


def generate_download_url(bucket: str, key: str, ttl: int | None = None) -> str:
    """Return a short-lived presigned GET URL for ``bucket/key``.

    Falls back to the configured ``R2_PRESIGN_TTL`` when ``ttl`` is not given.
    """
    settings = get_settings()
    expires = ttl if ttl is not None else settings.r2_presign_ttl
    client = get_r2_client()
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )
    return str(url)


def generate_download_url_for_uri(uri: str, ttl: int | None = None) -> str:
    """Convenience wrapper accepting a full ``r2://bucket/key`` URI."""
    bucket, key = _parse_r2_uri(uri)
    return generate_download_url(bucket, key, ttl=ttl)
