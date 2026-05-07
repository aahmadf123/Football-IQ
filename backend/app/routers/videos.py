"""Videos router — upload records, status, and presigned URL helpers."""

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user, require_any_staff
from app.models import ProcessingJob, User, Video, VideoStatus

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/videos", tags=["videos"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class VideoCreate(BaseModel):
    filename: str
    storage_uri: str
    recorded_at: str | None = None


class VideoStatusUpdate(BaseModel):
    status: VideoStatus
    duration_seconds: float | None = None
    fps: float | None = None
    width: int | None = None
    height: int | None = None
    codec: str | None = None


class VideoResponse(BaseModel):
    id: uuid.UUID
    filename: str
    storage_uri: str
    status: VideoStatus
    duration_seconds: float | None
    fps: float | None
    width: int | None
    height: int | None
    codec: str | None
    uploaded_by: uuid.UUID | None
    metadata_: dict[str, Any] | None = None
    created_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_video(cls, v: Video) -> "VideoResponse":
        return cls(
            id=v.id,
            filename=v.filename,
            storage_uri=v.storage_uri,
            status=v.status,
            duration_seconds=v.duration_seconds,
            fps=v.fps,
            width=v.width,
            height=v.height,
            codec=v.codec,
            uploaded_by=v.uploaded_by,
            metadata_=v.metadata_,
            created_at=v.created_at.isoformat(),
        )


class JobSummary(BaseModel):
    id: uuid.UUID
    job_type: str
    status: str
    error_stage: str | None
    error_message: str | None
    created_at: str

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=list[VideoResponse])
async def list_videos(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status_filter: VideoStatus | None = Query(default=None, alias="status"),
) -> list[VideoResponse]:
    """List videos with optional status filter, newest first."""
    q = select(Video).order_by(Video.created_at.desc()).limit(limit).offset(offset)
    if status_filter is not None:
        q = q.where(Video.status == status_filter)
    result = await db.execute(q)
    videos = result.scalars().all()
    return [VideoResponse.from_orm_video(v) for v in videos]


@router.post("", response_model=VideoResponse, status_code=status.HTTP_201_CREATED)
async def create_video(
    body: VideoCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_any_staff)],
) -> VideoResponse:
    """Register a new video record after the file has been uploaded to R2."""
    video = Video(
        id=uuid.uuid4(),
        filename=body.filename,
        storage_uri=body.storage_uri,
        status=VideoStatus.uploaded,
        uploaded_by=current_user.id,
    )
    db.add(video)
    await db.flush()
    log.info("video_created", video_id=str(video.id), filename=video.filename)
    return VideoResponse.from_orm_video(video)


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> VideoResponse:
    """Get a single video record."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return VideoResponse.from_orm_video(video)


@router.patch("/{video_id}/status", response_model=VideoResponse)
async def update_video_status(
    video_id: uuid.UUID,
    body: VideoStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(require_any_staff)],
) -> VideoResponse:
    """Update video processing status and optional metadata."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    video.status = body.status
    if body.duration_seconds is not None:
        video.duration_seconds = body.duration_seconds
    if body.fps is not None:
        video.fps = body.fps
    if body.width is not None:
        video.width = body.width
    if body.height is not None:
        video.height = body.height
    if body.codec is not None:
        video.codec = body.codec

    await db.flush()
    log.info("video_status_updated", video_id=str(video_id), status=body.status)
    return VideoResponse.from_orm_video(video)


@router.get("/{video_id}/jobs", response_model=list[JobSummary])
async def list_video_jobs(
    video_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> list[JobSummary]:
    """List processing jobs for a video, newest first."""
    result = await db.execute(select(Video).where(Video.id == video_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    jobs_result = await db.execute(
        select(ProcessingJob)
        .where(ProcessingJob.video_id == video_id)
        .order_by(ProcessingJob.created_at.desc())
    )
    jobs = jobs_result.scalars().all()
    return [
        JobSummary(
            id=j.id,
            job_type=j.job_type.value,
            status=j.status.value,
            error_stage=j.error_stage,
            error_message=j.error_message,
            created_at=j.created_at.isoformat(),
        )
        for j in jobs
    ]
