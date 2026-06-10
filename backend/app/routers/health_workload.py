"""Athlete health/workload surface router (Issue #113).

Exposes the **role-gated, audit-logged** athlete health/workload surface.  No
sensitive athlete data is returned yet — the surface only describes the
planned integration contracts (wellness, GPS/wearables, S&C) and the policy
guardrails the UI must honour.

Access is restricted to the ``health_workload:read`` policy (sports
performance / analytics lead / admin) via
:func:`app.governance.require_policy`, and every read emits a structured
``audit.health_workload.surface.read`` event carrying only the actor UUID and
role — never athlete PII.

This is intentionally separate from ``GET /api/v1/health/workload`` in
:mod:`app.routers.health`, which reports *system* GPU-queue capacity for the
gating layer.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends

from app.governance import Action, Resource, audit_event, require_policy
from app.health_workload import build_surface_status
from app.models import User

router = APIRouter(prefix="/api/v1/health-workload", tags=["health-workload"])
log = structlog.get_logger(__name__)


@router.get("/surface")
async def health_workload_surface(
    user: Annotated[User, Depends(require_policy(Resource.HEALTH_WORKLOAD, Action.READ))],
) -> dict[str, object]:
    """Return the policy-safe athlete health/workload surface status.

    Restricted to sports-performance / analyst / admin roles.  The payload
    contains only the viewer's role, the placeholder integration contracts,
    the approved-role list, and the non-medical disclaimer — never per-athlete
    health data, names, or other PII.
    """
    audit_event(
        "audit.health_workload.surface.read",
        actor_id=user.id,
        actor_role=user.role.value,
        resource=Resource.HEALTH_WORKLOAD.value,
        action=Action.READ.value,
        surface="status",
    )
    return build_surface_status(role=user.role)
