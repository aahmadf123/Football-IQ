"""Position-group filter dependency for Issue #16.

Each coach sees only their assigned position group's clips, metrics, and alerts.
Admins and analysts see all position groups.

NOTE: Path deviation from ISSUE16_PLAN.md — the plan specified
backend/app/deps/position_filter.py, but backend/app/deps.py already exists
as a flat file.  This module lives at backend/app/position_filter.py to avoid
a Python import conflict.

Usage in routers:

    from app.position_filter import position_group_filter

    @router.get("/alerts")
    async def list_alerts(
        pg: str | None = Depends(position_group_filter),
        ...
    ):
        # pg is None → no filter (admin/analyst sees all)
        # pg == "OL"  → filter to OL position group only
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, Query

from app.deps import get_current_user
from app.models import User, UserRole

log = structlog.get_logger(__name__)


async def position_group_filter(
    current_user: Annotated[User, Depends(get_current_user)],
    position_group: str | None = Query(
        default=None,
        description=(
            "Restrict results to this position group.  "
            "Admins and analysts may omit to see all groups.  "
            "Coaches default to their assigned position group if not overridden."
        ),
    ),
) -> str | None:
    """Return the effective position-group scope for the current request.

    - admin / analyst: honour the query param (None = all groups)
    - coach: defaults to the user's ``position_group`` attribute; may override
      downward (i.e. a WR coach cannot query OL data)
    - sportsperformance: same as coach — restricted to their group
    - player / viewer: not permitted at alert endpoints (blocked upstream)

    Returns:
        Position group string (e.g. "OL") or None if no filter applies.
    """
    role = current_user.role

    if role in (UserRole.admin, UserRole.analyst):
        return position_group

    user_pg: str | None = getattr(current_user, "position_group", None)

    if position_group is not None:
        if user_pg and position_group.upper() != user_pg.upper():
            log.warning(
                "position_filter_cross_group_attempt",
                user_id=str(current_user.id),
                user_pg=user_pg,
                requested_pg=position_group,
            )
        return position_group.upper()

    if user_pg:
        return user_pg.upper()

    return None
