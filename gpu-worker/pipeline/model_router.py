"""Lightweight vs. full-quality model router (Issue #16).

Routes pose-estimation jobs to the appropriate RTMPose variant based on
the processing_jobs.priority field:

  Same-session (period-break) jobs  → RTMPose-t  (fastest; ~1000 FPS on GTX 1660 Ti)
  Nightly full-quality jobs          → RTMPose-m  (~430 FPS on GTX 1660 Ti)

Priority constants are imported from the Copilot-owned queue module so this
router stays in sync with any future threshold changes there.

Usage:

    from pipeline.model_router import select_model, is_same_session

    model_variant = select_model(job["priority"])
    # model_variant is "rtmpose-t" or "rtmpose-m"
"""

from __future__ import annotations

import structlog

from queue.same_session_queue import NIGHTLY_PRIORITY, SAME_SESSION_PRIORITY

log = structlog.get_logger(__name__)

# Model variant identifiers — used as model_name keys in the model registry
RTMPOSE_FAST: str = "rtmpose-t"    # RTMPose-tiny: fastest, period-break window
RTMPOSE_MEDIUM: str = "rtmpose-m"  # RTMPose-medium: full quality, nightly run


def select_model(priority: int) -> str:
    """Return the RTMPose variant appropriate for the given job priority.

    Args:
        priority: Value from processing_jobs.priority.
                  SAME_SESSION_PRIORITY (10) = period-break / real-time.
                  NIGHTLY_PRIORITY (0)        = full-session nightly.

    Returns:
        "rtmpose-t" for same-session jobs, "rtmpose-m" for nightly jobs.
    """
    if priority >= SAME_SESSION_PRIORITY:
        log.info(
            "model_router_select",
            model=RTMPOSE_FAST,
            priority=priority,
            reason="same_session_high_priority",
        )
        return RTMPOSE_FAST

    log.info(
        "model_router_select",
        model=RTMPOSE_MEDIUM,
        priority=priority,
        reason="nightly_full_quality",
    )
    return RTMPOSE_MEDIUM


def is_same_session(priority: int) -> bool:
    """Return True if the job priority qualifies as same-session (high priority)."""
    return priority >= SAME_SESSION_PRIORITY


def is_nightly(priority: int) -> bool:
    """Return True if the job is a nightly full-quality run."""
    return priority <= NIGHTLY_PRIORITY
