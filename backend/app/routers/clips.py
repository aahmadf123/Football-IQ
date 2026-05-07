"""Clips router — play segmentation, clip CRUD, and boundary corrections."""

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user, require_any_staff, require_coach_or_above
from app.models import Clip, Metric, User, Video

log = structlog.get_logger(__name__)
router = APIRouter(tags=["clips"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class ClipCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    start_time: float
    end_time: float
    play_number: int | None = None
    label_data: dict[str, Any] | None = None
    confidence: float | None = None
    storage_uri: str | None = None
    boundary_source: str | None = None
    boundary_confidence: float | None = None
    model_version_id: uuid.UUID | None = None
    calibration_version_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None


class ClipUpdate(BaseModel):
    start_time: float | None = None
    end_time: float | None = None
    play_number: int | None = None
    label_data: dict[str, Any] | None = None
    is_reviewed: bool | None = None
    storage_uri: str | None = None
    boundary_source: str | None = None
    boundary_confidence: float | None = None


class ClipResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: uuid.UUID
    video_id: uuid.UUID
    start_time: float
    end_time: float
    play_number: int | None
    confidence: float | None
    is_reviewed: bool
    storage_uri: str | None
    label_data: dict[str, Any] | None
    boundary_source: str | None
    boundary_confidence: float | None
    model_version_id: uuid.UUID | None
    calibration_version_id: uuid.UUID | None
    job_id: uuid.UUID | None
    created_at: str

    @classmethod
    def from_orm_clip(cls, c: Clip) -> "ClipResponse":
        return cls(
            id=c.id,
            video_id=c.video_id,
            start_time=c.start_time,
            end_time=c.end_time,
            play_number=c.play_number,
            confidence=c.confidence,
            is_reviewed=c.is_reviewed,
            storage_uri=c.storage_uri,
            label_data=c.label_data,
            boundary_source=c.boundary_source,
            boundary_confidence=c.boundary_confidence,
            model_version_id=c.model_version_id,
            calibration_version_id=c.calibration_version_id,
            job_id=c.job_id,
            created_at=c.created_at.isoformat(),
        )


class MetricCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    clip_id: uuid.UUID
    metric_name: str
    metric_value: dict[str, Any]
    unit: str | None = None
    is_suppressed: bool = False
    suppression_reason: str | None = None
    evidence_uri: str | None = None
    model_version_id: uuid.UUID | None = None
    calibration_version_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None


class MetricResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: uuid.UUID
    metric_name: str
    metric_value: dict[str, Any]
    unit: str | None
    is_suppressed: bool
    suppression_reason: str | None
    evidence_uri: str | None
    clip_id: uuid.UUID
    model_version_id: uuid.UUID | None
    calibration_version_id: uuid.UUID | None
    job_id: uuid.UUID | None
    created_at: str

    @classmethod
    def from_orm_metric(cls, m: Metric) -> "MetricResponse":
        return cls(
            id=m.id,
            metric_name=m.metric_name,
            metric_value=m.metric_value,
            unit=m.unit,
            is_suppressed=m.is_suppressed,
            suppression_reason=m.suppression_reason,
            evidence_uri=m.evidence_uri,
            clip_id=m.clip_id,
            model_version_id=m.model_version_id,
            calibration_version_id=m.calibration_version_id,
            job_id=m.job_id,
            created_at=m.created_at.isoformat(),
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/api/v1/videos/{video_id}/clips", response_model=list[ClipResponse])
async def list_clips_for_video(
    video_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ClipResponse]:
    """List all clips for a video, ordered by start_time."""
    vid_result = await db.execute(select(Video).where(Video.id == video_id))
    if vid_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    result = await db.execute(
        select(Clip)
        .where(Clip.video_id == video_id)
        .order_by(Clip.start_time)
        .limit(limit)
        .offset(offset)
    )
    return [ClipResponse.from_orm_clip(c) for c in result.scalars().all()]


@router.post(
    "/api/v1/videos/{video_id}/clips",
    response_model=ClipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_clip(
    video_id: uuid.UUID,
    body: ClipCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(require_any_staff)],
) -> ClipResponse:
    """Propose a new play boundary for a video (manual or system-generated)."""
    vid_result = await db.execute(select(Video).where(Video.id == video_id))
    if vid_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if body.start_time >= body.end_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_time must be less than end_time",
        )

    clip = Clip(
        id=uuid.uuid4(),
        video_id=video_id,
        start_time=body.start_time,
        end_time=body.end_time,
        play_number=body.play_number,
        label_data=body.label_data,
        confidence=body.confidence,
        storage_uri=body.storage_uri,
        boundary_source=body.boundary_source,
        boundary_confidence=body.boundary_confidence,
        model_version_id=body.model_version_id,
        calibration_version_id=body.calibration_version_id,
        job_id=body.job_id,
    )
    db.add(clip)
    await db.flush()
    log.info("clip_created", clip_id=str(clip.id), video_id=str(video_id))
    return ClipResponse.from_orm_clip(clip)


@router.get("/api/v1/clips/{clip_id}", response_model=ClipResponse)
async def get_clip(
    clip_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> ClipResponse:
    """Get a single clip by ID."""
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()
    if clip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
    return ClipResponse.from_orm_clip(clip)


@router.patch("/api/v1/clips/{clip_id}", response_model=ClipResponse)
async def update_clip(
    clip_id: uuid.UUID,
    body: ClipUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_coach_or_above)],
) -> ClipResponse:
    """Update a clip's boundaries or review status (coach/analyst override)."""
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()
    if clip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    if body.start_time is not None:
        clip.start_time = body.start_time
    if body.end_time is not None:
        clip.end_time = body.end_time
    if clip.start_time >= clip.end_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_time must be less than end_time",
        )
    if body.play_number is not None:
        clip.play_number = body.play_number
    if body.label_data is not None:
        clip.label_data = body.label_data
    if body.is_reviewed is not None:
        clip.is_reviewed = body.is_reviewed
        if body.is_reviewed:
            clip.reviewed_by = current_user.id
    if body.storage_uri is not None:
        clip.storage_uri = body.storage_uri
    if body.boundary_source is not None:
        clip.boundary_source = body.boundary_source
    if body.boundary_confidence is not None:
        clip.boundary_confidence = body.boundary_confidence

    await db.flush()
    log.info("clip_updated", clip_id=str(clip_id))
    return ClipResponse.from_orm_clip(clip)


@router.get("/api/v1/clips/{clip_id}/metrics", response_model=list[MetricResponse])
async def get_clip_metrics(
    clip_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> list[MetricResponse]:
    """Get all metrics for a clip — each includes its evidence lineage."""
    clip_result = await db.execute(select(Clip).where(Clip.id == clip_id))
    if clip_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    result = await db.execute(
        select(Metric).where(Metric.clip_id == clip_id).order_by(Metric.metric_name)
    )
    return [MetricResponse.from_orm_metric(m) for m in result.scalars().all()]


@router.post(
    "/api/v1/metrics",
    response_model=MetricResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_metric(
    body: MetricCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(require_any_staff)],
) -> MetricResponse:
    """Store a computed analytics metric for a clip (written by the GPU worker)."""
    clip_result = await db.execute(select(Clip).where(Clip.id == body.clip_id))
    if clip_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    metric = Metric(
        id=uuid.uuid4(),
        clip_id=body.clip_id,
        metric_name=body.metric_name,
        metric_value=body.metric_value,
        unit=body.unit,
        is_suppressed=body.is_suppressed,
        suppression_reason=body.suppression_reason,
        evidence_uri=body.evidence_uri,
        model_version_id=body.model_version_id,
        calibration_version_id=body.calibration_version_id,
        job_id=body.job_id,
    )
    db.add(metric)
    await db.flush()
    log.info(
        "metric_created",
        metric_id=str(metric.id),
        clip_id=str(body.clip_id),
        metric_name=body.metric_name,
    )
    return MetricResponse.from_orm_metric(metric)
