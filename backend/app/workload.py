"""Health/workload-based gating for heavy backend operations (Issue #113).

Centralizes the logic that decides whether the backend should accept a heavy
or sensitive workload at all.  Gating is **enforced on the backend** and
returns ``503 Service Unavailable`` with a structured ``error_code`` so
callers (and operators) can distinguish capacity gating from authorization
failure (``403``) or generic errors.

Signals taken into account:

* ``running`` + ``queued`` ``processing_jobs`` rows — proxy for GPU worker
  saturation.
* Optional environment overrides (``WORKLOAD_GATING_DISABLED``,
  ``WORKLOAD_QUEUE_THRESHOLD``, ``WORKLOAD_RUNNING_THRESHOLD``) so on-call can
  adjust thresholds without a redeploy.

Use :func:`require_workload_capacity` as a FastAPI dependency on heavy
endpoints.  Use :func:`assess_workload` for the health/workload status surface
returned by ``GET /api/v1/health/workload``.

The module is intentionally dependency-light so it can be imported by both
routers and tests without dragging in the full ORM.
"""

from __future__ import annotations

import enum
import os
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

import structlog
from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.governance import audit_event
from app.models import JobStatus, ProcessingJob, User

log = structlog.get_logger("app.workload")


# ── Configuration ────────────────────────────────────────────────────────────


DEFAULT_QUEUE_THRESHOLD = 50  # queued jobs before we start gating
DEFAULT_RUNNING_THRESHOLD = 20  # concurrently-running jobs before gating


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        log.warning("workload.invalid_threshold_env", env=name, value=raw)
        return default
    return max(0, value)


def _gating_disabled() -> bool:
    return os.environ.get("WORKLOAD_GATING_DISABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# ── Data model ───────────────────────────────────────────────────────────────


class WorkloadStatus(enum.StrEnum):
    healthy = "healthy"
    degraded = "degraded"
    saturated = "saturated"


@dataclass(slots=True)
class WorkloadSnapshot:
    """A point-in-time view of the worker queue."""

    queued: int
    running: int
    queue_threshold: int
    running_threshold: int
    status: WorkloadStatus
    gating_disabled: bool

    def is_gated(self) -> bool:
        """Return True if heavy endpoints should reject new work."""
        if self.gating_disabled:
            return False
        return self.status == WorkloadStatus.saturated

    def to_dict(self) -> dict[str, Any]:
        return {
            "queued": self.queued,
            "running": self.running,
            "queue_threshold": self.queue_threshold,
            "running_threshold": self.running_threshold,
            "status": self.status.value,
            "gating_disabled": self.gating_disabled,
        }


def _classify(
    *, queued: int, running: int, queue_threshold: int, running_threshold: int
) -> WorkloadStatus:
    """Derive a status bucket from raw counts.

    * ``saturated`` when *either* signal is at-or-above its threshold.
    * ``degraded`` when either signal is above 75% of its threshold.
    * ``healthy`` otherwise.
    """
    if queued >= queue_threshold or running >= running_threshold:
        return WorkloadStatus.saturated
    degraded_q = queue_threshold * 3 // 4
    degraded_r = running_threshold * 3 // 4
    if queued >= max(1, degraded_q) or running >= max(1, degraded_r):
        return WorkloadStatus.degraded
    return WorkloadStatus.healthy


async def assess_workload(db: AsyncSession) -> WorkloadSnapshot:
    """Sample the workload signals and return a :class:`WorkloadSnapshot`."""
    queued_stmt = (
        select(func.count())
        .select_from(ProcessingJob)
        .where(ProcessingJob.status == JobStatus.queued)
    )
    running_stmt = (
        select(func.count())
        .select_from(ProcessingJob)
        .where(ProcessingJob.status == JobStatus.running)
    )
    queued_total = (await db.execute(queued_stmt)).scalar_one() or 0
    running_total = (await db.execute(running_stmt)).scalar_one() or 0

    queue_threshold = _env_int("WORKLOAD_QUEUE_THRESHOLD", DEFAULT_QUEUE_THRESHOLD)
    running_threshold = _env_int(
        "WORKLOAD_RUNNING_THRESHOLD", DEFAULT_RUNNING_THRESHOLD
    )
    status_bucket = _classify(
        queued=int(queued_total),
        running=int(running_total),
        queue_threshold=queue_threshold,
        running_threshold=running_threshold,
    )

    return WorkloadSnapshot(
        queued=int(queued_total),
        running=int(running_total),
        queue_threshold=queue_threshold,
        running_threshold=running_threshold,
        status=status_bucket,
        gating_disabled=_gating_disabled(),
    )


# ── FastAPI dependency ───────────────────────────────────────────────────────


def require_workload_capacity(
    endpoint: str,
) -> Callable[..., Coroutine[Any, Any, WorkloadSnapshot]]:
    """Return a dependency that gates ``endpoint`` on current workload.

    The dependency:

    * Resolves the snapshot.
    * If the snapshot is ``saturated`` (and gating is not disabled), emits a
      structured ``audit.gating.rejected`` event and raises 503 with a
      machine-readable ``error_code`` of ``workload_gated``.
    * Otherwise returns the snapshot so the handler can include it in logs or
      response headers if desired.

    ``endpoint`` is a short, label-safe identifier used for both audit logs
    and the response detail (e.g. ``"jobs.create"``).
    """

    async def _dep(
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> WorkloadSnapshot:
        snapshot = await assess_workload(db)
        if snapshot.is_gated():
            audit_event(
                "audit.gating.rejected",
                actor_id=user.id,
                actor_role=user.role.value,
                endpoint=endpoint,
                queue_depth=snapshot.queued,
                queue_threshold=snapshot.queue_threshold,
                decision="rejected",
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error_code": "workload_gated",
                    "endpoint": endpoint,
                    "message": (
                        "Heavy workload temporarily unavailable due to system "
                        "load. Please retry shortly."
                    ),
                    "workload": snapshot.to_dict(),
                },
                headers={"Retry-After": "30"},
            )
        audit_event(
            "audit.gating.allowed",
            actor_id=user.id,
            actor_role=user.role.value,
            endpoint=endpoint,
            queue_depth=snapshot.queued,
            queue_threshold=snapshot.queue_threshold,
            decision="allowed",
        )
        return snapshot

    return _dep
