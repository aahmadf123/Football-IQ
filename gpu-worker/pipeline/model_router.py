"""Stage-aware model router (Issue #73 — generalises Issue #16's pose-only router).

Each pipeline stage chooses a model variant based on the
``processing_jobs.priority`` field:

  Same-session (priority >= SAME_SESSION_PRIORITY = 10) → fast variants
    tuned to fit the period-break window.
  Nightly       (priority <  SAME_SESSION_PRIORITY)      → heavier variants
    that can spend more compute for higher quality.

Defaults live in ``DEFAULT_ROUTING`` below. They can be overridden by
pointing the ``MODEL_ROUTING_CONFIG`` environment variable at a JSON
file shaped like::

    {
      "detect":  {"same_session": "yolov8s",   "nightly": "yolov8m"},
      "pose":    {"same_session": "rtmpose-t", "nightly": "rtmpose-m"}
    }

Stages not mentioned in the override file fall back to ``DEFAULT_ROUTING``.

Pose routing from Issue #16 is preserved exactly:

    select_model("pose", SAME_SESSION_PRIORITY) == "rtmpose-t"
    select_model("pose", NIGHTLY_PRIORITY)      == "rtmpose-m"

Usage::

    from pipeline.model_router import select_model, build_routing_artifact

    variant = select_model("detect", job["priority"])
    artifact = build_routing_artifact("detect", job["priority"])
    # artifact == {"detect": "yolov8n"}  (or similar)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import structlog

from queue.same_session_queue import NIGHTLY_PRIORITY, SAME_SESSION_PRIORITY

log = structlog.get_logger(__name__)

# Pose-variant identifiers retained from Issue #16 for callers that need
# the constants directly.
RTMPOSE_FAST: str = "rtmpose-t"
RTMPOSE_MEDIUM: str = "rtmpose-m"

# Returned for any stage that is not in the routing table.
UNKNOWN_STAGE_FALLBACK: str = "default"

# Priority bucket keys used inside the routing table.
_SAME_SESSION_KEY = "same_session"
_NIGHTLY_KEY = "nightly"

# Default stage × priority routing.
#
# Same-session variants must comfortably fit the 5–10 minute period-break
# window on a GTX 1660 Ti class GPU. Nightly variants can be heavier.
DEFAULT_ROUTING: dict[str, dict[str, str]] = {
    "segment":    {_SAME_SESSION_KEY: "optical-flow-fast", _NIGHTLY_KEY: "optical-flow-fast"},
    "detect":     {_SAME_SESSION_KEY: "yolov8n",           _NIGHTLY_KEY: "yolov8m"},
    "track":      {_SAME_SESSION_KEY: "iou-tracker",       _NIGHTLY_KEY: "iou-tracker"},
    "reid":       {_SAME_SESSION_KEY: "jersey-ocr",        _NIGHTLY_KEY: "jersey-ocr"},
    "pose":       {_SAME_SESSION_KEY: RTMPOSE_FAST,        _NIGHTLY_KEY: RTMPOSE_MEDIUM},
    "render":     {_SAME_SESSION_KEY: "ffmpeg-overlay",    _NIGHTLY_KEY: "ffmpeg-overlay"},
    "embeddings": {_SAME_SESSION_KEY: "none",              _NIGHTLY_KEY: "none"},
}


def _load_override() -> dict[str, dict[str, str]]:
    """Read the JSON override file pointed to by ``MODEL_ROUTING_CONFIG``.

    Returns an empty dict if the env var is unset or the file is missing /
    malformed (with a warning logged) so the worker never crashes on a bad
    config drop.
    """
    path_str = os.environ.get("MODEL_ROUTING_CONFIG")
    if not path_str:
        return {}
    path = Path(path_str)
    if not path.is_file():
        log.warning("model_router_override_missing", path=path_str)
        return {}
    try:
        raw: Any = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("model_router_override_unreadable", path=path_str, error=str(exc))
        return {}
    if not isinstance(raw, dict):
        log.warning("model_router_override_invalid_shape", path=path_str)
        return {}
    return raw


def _build_routing() -> dict[str, dict[str, str]]:
    """Merge ``DEFAULT_ROUTING`` with any JSON override.

    Per-stage merge: overridden stages fully replace their default entry,
    but stages not mentioned in the override keep their defaults.
    """
    routing: dict[str, dict[str, str]] = {
        stage: dict(variants) for stage, variants in DEFAULT_ROUTING.items()
    }
    for stage, variants in _load_override().items():
        if not isinstance(variants, dict):
            log.warning("model_router_override_stage_invalid", stage=stage)
            continue
        merged = dict(routing.get(stage, {}))
        for key, value in variants.items():
            if isinstance(value, str):
                merged[key] = value
        routing[stage] = merged
    return routing


# Resolved once at import; tests that mutate ``MODEL_ROUTING_CONFIG`` should
# call ``reload_routing()`` (or reload the module) to pick up changes.
ROUTING: dict[str, dict[str, str]] = _build_routing()


def reload_routing() -> dict[str, dict[str, str]]:
    """Re-read overrides and rebuild ``ROUTING``. Exposed for tests."""
    global ROUTING
    ROUTING = _build_routing()
    return ROUTING


def _priority_key(priority: int) -> str:
    return _SAME_SESSION_KEY if priority >= SAME_SESSION_PRIORITY else _NIGHTLY_KEY


def select_model(stage: str, priority: int) -> str:
    """Return the model variant for ``stage`` at the given ``priority``.

    Args:
        stage: Pipeline stage name — one of ``segment``, ``detect``,
            ``track``, ``reid``, ``pose``, ``render``, ``embeddings``,
            or any key configured via ``MODEL_ROUTING_CONFIG``.
        priority: Value from ``processing_jobs.priority``.
            ``SAME_SESSION_PRIORITY`` (10) routes to the fast variant;
            anything lower routes to the nightly variant.

    Returns:
        The model variant string. Unknown stages return
        ``UNKNOWN_STAGE_FALLBACK`` and log a warning rather than raising.
    """
    bucket = _priority_key(priority)
    variants = ROUTING.get(stage)
    if variants is None:
        log.warning(
            "model_router_unknown_stage",
            stage=stage,
            priority=priority,
            fallback=UNKNOWN_STAGE_FALLBACK,
        )
        return UNKNOWN_STAGE_FALLBACK

    variant = variants.get(bucket) or variants.get(_NIGHTLY_KEY) or UNKNOWN_STAGE_FALLBACK
    log.info(
        "model_router_select",
        stage=stage,
        model=variant,
        priority=priority,
        bucket=bucket,
    )
    return variant


def build_routing_artifact(stage: str, priority: int) -> dict[str, str]:
    """Return ``{stage: variant}`` for persistence in ``output_artifacts``.

    The dispatcher merges this dict into
    ``processing_jobs.output_artifacts["model_routing"]`` so every
    completed job records which model variant served it.
    """
    return {stage: select_model(stage, priority)}


def is_same_session(priority: int) -> bool:
    """Return True if ``priority`` qualifies as same-session."""
    return priority >= SAME_SESSION_PRIORITY


def is_nightly(priority: int) -> bool:
    """Return True if ``priority`` qualifies as a nightly full-quality run."""
    return priority <= NIGHTLY_PRIORITY
