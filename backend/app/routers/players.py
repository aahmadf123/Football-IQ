"""Players router — roster identity with visibility-mode shaping.

This is the P1 read surface for the player domain.  The endpoint is shared
between staff (full identity payload), player self-views, and external
recruiting consumers — visibility is selected per-request via ``?mode=`` and
enforced server-side by :mod:`app.governance`.

Endpoints:
    GET   /api/v1/players                       — list (filtered + mode shaped)
    GET   /api/v1/players/{id}                  — single player (mode shaped)
    PATCH /api/v1/players/{id}/visibility       — change visibility state
    GET   /api/v1/players/{id}/visibility/audit — visibility change history

Sensitive metrics (pose, biomechanics, health, alerts) are *never* returned
here; they live on dedicated routers that perform their own RBAC.  The
visibility shaping in this router only governs identity-level fields.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.governance import (
    Action,
    Resource,
    VisibilityMode,
    VisibilityState,
    audit_event,
    policy_allows,
    require_policy,
    resolve_visibility_mode,
    shape_player,
)
from app.models import Player, PlayerVisibilityAudit, PlayerVisibilityState, User

log = structlog.get_logger(__name__)
router = APIRouter(tags=["players"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class VisibilityUpdate(BaseModel):
    """Request body for :func:`update_visibility`."""

    state: VisibilityState
    reason: str | None = None


class VisibilityAuditEntry(BaseModel):
    id: uuid.UUID
    player_id: uuid.UUID
    previous_state: str | None
    next_state: str
    actor_id: uuid.UUID | None
    reason: str | None
    created_at: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/api/v1/players")
async def list_players(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[
        User, Depends(require_policy(Resource.PLAYER_PROFILE, Action.READ))
    ],
    position: Annotated[
        str | None,
        Query(description="Exact match on the ``position`` column (e.g. ``WR``)."),
    ] = None,
    position_group: Annotated[
        str | None,
        Query(
            description=(
                "Coaching group (``QB``, ``Skill``, ``OL``, ``DL``, ``LB``, ``DB``, ``ST``)."
            ),
        ),
    ] = None,
    is_active: Annotated[
        bool | None,
        Query(description="Filter by active-roster flag. Omit to include both."),
    ] = None,
    jersey_number: Annotated[
        int | None,
        Query(description="Exact jersey number match."),
    ] = None,
    search: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=80,
            description="Case-insensitive substring match on first or last name.",
        ),
    ] = None,
    mode: Annotated[
        VisibilityMode | None,
        Query(description="Visibility mode override (staff|player|recruiting)."),
    ] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Return the roster shaped for the caller's effective visibility mode.

    Ordering is deterministic — jersey number ascending (NULLs last), then
    last name, first name, and finally id.  Players whose visibility state
    excludes them from the resolved mode are silently filtered out (rather
    than returning a redacted stub) so list views don't leak that a record
    exists at all.
    """
    effective_mode = resolve_visibility_mode(current_user, mode)
    audit_event(
        "audit.visibility.applied",
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        effective_mode=effective_mode.value,
        endpoint="players.list",
    )

    stmt = select(Player)
    if position is not None:
        stmt = stmt.where(Player.position == position)
    if position_group is not None:
        stmt = stmt.where(Player.position_group == position_group)
    if is_active is not None:
        stmt = stmt.where(Player.is_active == is_active)
    if jersey_number is not None:
        stmt = stmt.where(Player.jersey_number == jersey_number)
    if search is not None:
        needle = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                Player.first_name.ilike(needle),
                Player.last_name.ilike(needle),
            )
        )
    stmt = (
        stmt.order_by(
            Player.jersey_number.asc().nulls_last(),
            Player.last_name.asc(),
            Player.first_name.asc(),
            Player.id.asc(),
        )
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(stmt)
    out: list[dict[str, Any]] = []
    for p in result.scalars().all():
        shaped = shape_player(p, effective_mode, actor=current_user)
        if shaped is not None:
            out.append(shaped)
    return out


@router.get("/api/v1/players/{player_id}")
async def get_player(
    player_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[
        User, Depends(require_policy(Resource.PLAYER_PROFILE, Action.READ))
    ],
    mode: Annotated[
        VisibilityMode | None,
        Query(description="Visibility mode override (staff|player|recruiting)."),
    ] = None,
) -> dict[str, Any]:
    """Return a single player record shaped for the caller's mode."""
    effective_mode = resolve_visibility_mode(current_user, mode)

    result = await db.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player not found",
        )

    shaped = shape_player(player, effective_mode, actor=current_user)
    if shaped is None:
        # Return 404 so non-staff callers can't tell whether the record exists
        # or simply isn't approved for their view.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player not found",
        )
    audit_event(
        "audit.visibility.applied",
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        effective_mode=effective_mode.value,
        player_id=player.id,
        endpoint="players.detail",
    )
    return shaped


@router.patch("/api/v1/players/{player_id}/visibility")
async def update_visibility(
    player_id: uuid.UUID,
    body: VisibilityUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[
        User, Depends(require_policy(Resource.PLAYER_VISIBILITY, Action.WRITE))
    ],
) -> dict[str, Any]:
    """Change a player's visibility state.

    * Coaches/analysts/admins may transition to/from ``staff_only`` and
      ``player_approved`` and may archive.
    * Approving for recruiting requires the additional ``APPROVE`` policy
      (admin/analyst only) — recruiting exposes the player externally so it
      gets a tighter approver list.
    """
    target_state = body.state
    if target_state == VisibilityState.recruiting_approved and not policy_allows(
        current_user.role, Resource.PLAYER_VISIBILITY, Action.APPROVE
    ):
        audit_event(
            "audit.access.denied",
            actor_id=current_user.id,
            actor_role=current_user.role.value,
            resource=Resource.PLAYER_VISIBILITY.value,
            action=Action.APPROVE.value,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "approval_required",
                "message": (
                    "Recruiting approval requires admin or analyst role."
                ),
            },
        )

    result = await db.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Player not found"
        )

    previous_model = player.visibility_state or PlayerVisibilityState.staff_only
    previous = VisibilityState(previous_model.value)
    next_state_model = PlayerVisibilityState(target_state.value)

    player.visibility_state = next_state_model
    player.visibility_updated_by = current_user.id
    player.visibility_updated_at = datetime.now(UTC)

    audit_row = PlayerVisibilityAudit(
        id=uuid.uuid4(),
        player_id=player.id,
        previous_state=PlayerVisibilityState(previous.value),
        next_state=next_state_model,
        actor_id=current_user.id,
        reason=body.reason,
    )
    db.add(audit_row)
    await db.flush()

    audit_event(
        "audit.visibility.changed",
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        player_id=player.id,
        previous_state=previous.value,
        next_state=next_state_model.value,
    )

    return {
        "player_id": str(player.id),
        "previous_state": previous.value,
        "next_state": next_state_model.value,
        "updated_by": str(current_user.id),
        "updated_at": player.visibility_updated_at.isoformat(),
    }


@router.get("/api/v1/players/{player_id}/visibility/audit")
async def get_visibility_audit(
    player_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[
        User, Depends(require_policy(Resource.PLAYER_VISIBILITY, Action.WRITE))
    ],
    limit: int = Query(default=50, ge=1, le=200),
) -> list[VisibilityAuditEntry]:
    """Return the visibility transition history for a player (staff only)."""
    stmt = (
        select(PlayerVisibilityAudit)
        .where(PlayerVisibilityAudit.player_id == player_id)
        .order_by(PlayerVisibilityAudit.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [
        VisibilityAuditEntry(
            id=row.id,
            player_id=row.player_id,
            previous_state=row.previous_state.value if row.previous_state else None,
            next_state=row.next_state.value,
            actor_id=row.actor_id,
            reason=row.reason,
            created_at=row.created_at.isoformat(),
        )
        for row in result.scalars().all()
    ]
