"""Labels router — football formation/coverage/route labels (Stage 8 output).

label_type examples: offensive_formation, defensive_front, defensive_shell,
    motion_type, route_family, coverage_shell, blitz_candidate, play_concept
source values: "model" (auto-label) | "human" (coach/analyst annotation)
"""

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user, require_analyst_or_above, require_any_staff
from app.models import Clip, Label, Tracklet, User

log = structlog.get_logger(__name__)
router = APIRouter(tags=["labels"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class LabelCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    clip_id: uuid.UUID | None = None
    tracklet_id: uuid.UUID | None = None
    label_type: str
    label_value: dict[str, Any]
    source: str = "model"
    dataset_version: str | None = None


class LabelResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: uuid.UUID
    clip_id: uuid.UUID | None
    tracklet_id: uuid.UUID | None
    label_type: str
    label_value: dict[str, Any]
    annotated_by: uuid.UUID | None
    source: str
    dataset_version: str | None
    created_at: str

    @classmethod
    def from_orm_label(cls, lb: Label) -> "LabelResponse":
        return cls(
            id=lb.id,
            clip_id=lb.clip_id,
            tracklet_id=lb.tracklet_id,
            label_type=lb.label_type,
            label_value=lb.label_value,
            annotated_by=lb.annotated_by,
            source=lb.source,
            dataset_version=lb.dataset_version,
            created_at=lb.created_at.isoformat(),
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/api/v1/clips/{clip_id}/labels", response_model=list[LabelResponse])
async def list_labels_for_clip(
    clip_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    label_type: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[LabelResponse]:
    """List all labels for a clip with optional type/source filters."""
    clip_result = await db.execute(select(Clip).where(Clip.id == clip_id))
    if clip_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    q = (
        select(Label)
        .where(Label.clip_id == clip_id)
        .order_by(Label.created_at)
        .limit(limit)
        .offset(offset)
    )
    if label_type is not None:
        q = q.where(Label.label_type == label_type)
    if source is not None:
        q = q.where(Label.source == source)
    result = await db.execute(q)
    return [LabelResponse.from_orm_label(lb) for lb in result.scalars().all()]


@router.get("/api/v1/tracklets/{tracklet_id}/labels", response_model=list[LabelResponse])
async def list_labels_for_tracklet(
    tracklet_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    label_type: str | None = Query(default=None),
) -> list[LabelResponse]:
    """List all labels for a tracklet (route family, coverage shell, etc.)."""
    tracklet_result = await db.execute(select(Tracklet).where(Tracklet.id == tracklet_id))
    if tracklet_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracklet not found")

    q = select(Label).where(Label.tracklet_id == tracklet_id).order_by(Label.created_at)
    if label_type is not None:
        q = q.where(Label.label_type == label_type)
    result = await db.execute(q)
    return [LabelResponse.from_orm_label(lb) for lb in result.scalars().all()]


@router.post(
    "/api/v1/labels",
    response_model=LabelResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_label(
    body: LabelCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_any_staff)],
) -> LabelResponse:
    """Store a formation/coverage/route label for a clip or tracklet."""
    if body.clip_id is None and body.tracklet_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of clip_id or tracklet_id must be provided",
        )
    if body.clip_id is not None:
        clip_result = await db.execute(select(Clip).where(Clip.id == body.clip_id))
        if clip_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
    if body.tracklet_id is not None:
        tracklet_result = await db.execute(select(Tracklet).where(Tracklet.id == body.tracklet_id))
        if tracklet_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracklet not found")

    label = Label(
        id=uuid.uuid4(),
        clip_id=body.clip_id,
        tracklet_id=body.tracklet_id,
        label_type=body.label_type,
        label_value=body.label_value,
        annotated_by=current_user.id,
        source=body.source,
        dataset_version=body.dataset_version,
    )
    db.add(label)
    await db.flush()
    log.info(
        "label_created",
        label_id=str(label.id),
        label_type=body.label_type,
        clip_id=str(body.clip_id),
        tracklet_id=str(body.tracklet_id),
    )
    return LabelResponse.from_orm_label(label)


@router.get("/api/v1/labels/{label_id}", response_model=LabelResponse)
async def get_label(
    label_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> LabelResponse:
    """Get a single label record."""
    result = await db.execute(select(Label).where(Label.id == label_id))
    label = result.scalar_one_or_none()
    if label is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
    return LabelResponse.from_orm_label(label)


@router.delete("/api/v1/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_label(
    label_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(require_analyst_or_above)],
) -> None:
    """Delete a label (e.g. erroneous model output)."""
    result = await db.execute(select(Label).where(Label.id == label_id))
    label = result.scalar_one_or_none()
    if label is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label not found")
    await db.delete(label)
    await db.flush()
    log.info("label_deleted", label_id=str(label_id))
