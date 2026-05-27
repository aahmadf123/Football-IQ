"""Players router — roster listing and player identity (Issue #103).

This is the P1 read surface for the player domain. It deliberately does not
expose biomechanics, health, or per-clip metrics — those live on the dedicated
metrics, pose, and alerts routers and will be wired into the player profile
later (C1).

Endpoints:
    GET /api/v1/players          — list (filter by position / group / active)
    GET /api/v1/players/{id}     — single player identity
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import Player, User

log = structlog.get_logger(__name__)
router = APIRouter(tags=["players"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class PlayerResponse(BaseModel):
    """Player identity payload — used for both list and detail in P1.

    A richer ``PlayerProfile`` (with biomechanics, clip evidence, and trend
    series) will be introduced when the Player Development Passport (C1)
    lands; until then the profile UI gates those panels on the client.
    """

    id: uuid.UUID
    first_name: str
    last_name: str
    jersey_number: int | None
    position: str | None
    position_group: str | None
    is_active: bool
    user_id: uuid.UUID | None
    metadata: dict[str, Any] | None
    created_at: str

    @classmethod
    def from_orm_player(cls, p: Player) -> PlayerResponse:
        return cls(
            id=p.id,
            first_name=p.first_name,
            last_name=p.last_name,
            jersey_number=p.jersey_number,
            position=p.position,
            position_group=p.position_group,
            is_active=p.is_active,
            user_id=p.user_id,
            metadata=p.metadata_,
            created_at=p.created_at.isoformat(),
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/api/v1/players", response_model=list[PlayerResponse])
async def list_players(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
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
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[PlayerResponse]:
    """Return the team roster, optionally filtered.

    Ordering is deterministic — jersey number ascending (NULLs last), then
    last name, first name, and finally id — so list views and tests don't
    have to sort client-side.
    """
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
    return [PlayerResponse.from_orm_player(p) for p in result.scalars().all()]


@router.get("/api/v1/players/{player_id}", response_model=PlayerResponse)
async def get_player(
    player_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> PlayerResponse:
    """Return a single player's identity record."""
    result = await db.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player not found",
        )
    return PlayerResponse.from_orm_player(player)
