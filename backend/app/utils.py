"""Shared utility functions used across multiple routers."""

import uuid

from app.config import get_settings


def make_dataset_artifact_uri(model_scope: str) -> str:
    """Generate a deterministic-format R2 URI for a new training dataset snapshot."""
    settings = get_settings()
    return f"r2://{settings.r2_bucket_artifacts}/datasets/{model_scope}/{uuid.uuid4()}.jsonl"
