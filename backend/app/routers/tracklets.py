"""Tracklets router — player tracking data within clips."""

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.deps import get_current_user, require_any_staff
from app.models import Clip, Tracklet, TrackPoint, User

log = structlog.get_logger(__name__)
router = APIRouter(tags=["tracklets"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class TrackPointSchema(BaseModel):
    id: uuid.UUID
    tracklet_id: uuid.UUID
    frame_number: int
    field_x: float | None
    field_y: float | None
    bbox: list[float] | None
    detection_confidence: float | None

    @classmethod
    def from_orm(cls, tp: TrackPoint) -> "TrackPointSchema":
        return cls(
            id=tp.id,
            tracklet_id=tp.tracklet_id,
            frame_number=tp.frame_number,
            field_x=tp.field_x,
            field_y=tp.field_y,
            bbox=tp.bbox,
            detection_confidence=tp.detection_confidence,
        )


class TrackletResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: uuid.UUID
    clip_id: uuid.UUID
    player_id: uuid.UUID | None
    start_frame: int
    end_frame: int
    track_confidence: float | None
    team_label: str | None
    model_version_id: uuid.UUID | None
    job_id: uuid.UUID | None
    created_at: str
    track_points: list[TrackPointSchema] = []

    @classmethod
    def from_orm_tracklet(cls, t: Tracklet, include_points: bool = False) -> "TrackletResponse":
        return cls(
            id=t.id,
            clip_id=t.clip_id,
            player_id=t.player_id,
            start_frame=t.start_frame,
            end_frame=t.end_frame,
            track_confidence=t.track_confidence,
            team_label=t.team_label,
            model_version_id=t.model_version_id,
            job_id=t.job_id,
            created_at=t.created_at.isoformat(),
            track_points=[TrackPointSchema.from_orm(p) for p in t.track_points]
            if include_points
            else [],
        )


class TrackletCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    clip_id: uuid.UUID
    player_id: uuid.UUID | None = None
    start_frame: int
    end_frame: int
    track_confidence: float | None = None
    team_label: str | None = None
    model_version_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    track_points: list[dict[str, Any]] = []


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/api/v1/clips/{clip_id}/tracklets", response_model=list[TrackletResponse])
async def list_tracklets_for_clip(
    clip_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> list[TrackletResponse]:
    """List all tracklets for a clip (summary — no points)."""
    clip_result = await db.execute(select(Clip).where(Clip.id == clip_id))
    if clip_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    result = await db.execute(
        select(Tracklet).where(Tracklet.clip_id == clip_id).order_by(Tracklet.start_frame)
    )
    return [
        TrackletResponse.from_orm_tracklet(t, include_points=False) for t in result.scalars().all()
    ]


@router.get("/api/v1/tracklets/{tracklet_id}", response_model=TrackletResponse)
async def get_tracklet(
    tracklet_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> TrackletResponse:
    """Get a single tracklet with all its track points."""
    result = await db.execute(
        select(Tracklet)
        .options(selectinload(Tracklet.track_points))
        .where(Tracklet.id == tracklet_id)
    )
    tracklet = result.scalar_one_or_none()
    if tracklet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracklet not found")
    return TrackletResponse.from_orm_tracklet(tracklet, include_points=True)


@router.post(
    "/api/v1/tracklets",
    response_model=TrackletResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tracklet(
    body: TrackletCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(require_any_staff)],
) -> TrackletResponse:
    """Store a new tracklet (with optional inline track points)."""
    clip_result = await db.execute(select(Clip).where(Clip.id == body.clip_id))
    if clip_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    tracklet = Tracklet(
        id=uuid.uuid4(),
        clip_id=body.clip_id,
        player_id=body.player_id,
        start_frame=body.start_frame,
        end_frame=body.end_frame,
        track_confidence=body.track_confidence,
        team_label=body.team_label,
        model_version_id=body.model_version_id,
        job_id=body.job_id,
    )
    db.add(tracklet)
    await db.flush()

    for pt in body.track_points:
        tp = TrackPoint(
            id=uuid.uuid4(),
            tracklet_id=tracklet.id,
            frame_number=int(pt["frame_number"]),
            field_x=pt.get("field_x"),
            field_y=pt.get("field_y"),
            bbox=pt.get("bbox"),
            detection_confidence=pt.get("detection_confidence"),
        )
        db.add(tp)

    await db.flush()
    log.info("tracklet_created", tracklet_id=str(tracklet.id), clip_id=str(body.clip_id))

    # Re-fetch with points
    result = await db.execute(
        select(Tracklet)
        .options(selectinload(Tracklet.track_points))
        .where(Tracklet.id == tracklet.id)
    )
    tracklet = result.scalar_one()
    return TrackletResponse.from_orm_tracklet(tracklet, include_points=True)
