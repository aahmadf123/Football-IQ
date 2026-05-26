"""Jobs router — processing job observability and retry."""

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user, require_any_staff
from app.models import JobStatus, JobType, PipelineMode, ProcessingJob, User, Video

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class JobCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: uuid.UUID | None = None
    video_id: uuid.UUID
    job_type: JobType
    priority: int = 0
    pipeline_mode: str | None = None
    input_artifacts: dict[str, Any] | None = None
    model_version_id: uuid.UUID | None = None


class JobStatusUpdate(BaseModel):
    status: JobStatus
    error_stage: str | None = None
    error_message: str | None = None
    output_artifacts: dict[str, Any] | None = None


class JobResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: uuid.UUID
    video_id: uuid.UUID | None
    clip_id: uuid.UUID | None
    job_type: str
    status: str
    priority: int
    pipeline_mode: str | None
    is_same_session: bool
    error_stage: str | None
    error_message: str | None
    nightly_followup_job_id: uuid.UUID | None
    input_artifacts: dict[str, Any] | None
    output_artifacts: dict[str, Any] | None
    model_version_id: uuid.UUID | None
    started_at: str | None
    finished_at: str | None
    created_at: str

    @classmethod
    def from_orm_job(cls, j: ProcessingJob) -> "JobResponse":
        return cls(
            id=j.id,
            video_id=j.video_id,
            clip_id=j.clip_id,
            job_type=j.job_type.value,
            status=j.status.value,
            priority=j.priority,
            pipeline_mode=j.pipeline_mode,
            is_same_session=j.priority >= 10,
            error_stage=j.error_stage,
            error_message=j.error_message,
            nightly_followup_job_id=j.nightly_followup_job_id,
            input_artifacts=j.input_artifacts,
            output_artifacts=j.output_artifacts,
            model_version_id=j.model_version_id,
            started_at=j.started_at.isoformat() if j.started_at else None,
            finished_at=j.finished_at.isoformat() if j.finished_at else None,
            created_at=j.created_at.isoformat(),
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    job_type: JobType | None = Query(default=None),
    video_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[JobResponse]:
    """List processing jobs with optional filters, newest first."""
    q = select(ProcessingJob).order_by(ProcessingJob.created_at.desc()).limit(limit).offset(offset)
    if status_filter is not None:
        q = q.where(ProcessingJob.status == status_filter)
    if job_type is not None:
        q = q.where(ProcessingJob.job_type == job_type)
    if video_id is not None:
        q = q.where(ProcessingJob.video_id == video_id)
    result = await db.execute(q)
    return [JobResponse.from_orm_job(j) for j in result.scalars().all()]


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    body: JobCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(require_any_staff)],
) -> JobResponse:
    """Submit a new processing job for a video."""
    vid_result = await db.execute(select(Video).where(Video.id == body.video_id))
    if vid_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    mode = body.pipeline_mode or (
        PipelineMode.same_session if body.priority >= 10 else PipelineMode.nightly
    )
    job = ProcessingJob(
        id=body.id or uuid.uuid4(),
        video_id=body.video_id,
        job_type=body.job_type,
        status=JobStatus.queued,
        priority=body.priority,
        pipeline_mode=mode,
        input_artifacts=body.input_artifacts,
        model_version_id=body.model_version_id,
    )
    db.add(job)
    await db.flush()
    log.info("job_created", job_id=str(job.id), job_type=body.job_type, video_id=str(body.video_id))
    return JobResponse.from_orm_job(job)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> JobResponse:
    """Get full job details including error reason, stage, and input file."""
    result = await db.execute(select(ProcessingJob).where(ProcessingJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobResponse.from_orm_job(job)


@router.patch("/{job_id}", response_model=JobResponse)
async def update_job_status(
    job_id: uuid.UUID,
    body: JobStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(require_any_staff)],
) -> JobResponse:
    """Update job status — used by GPU worker callbacks."""
    from datetime import UTC, datetime

    result = await db.execute(select(ProcessingJob).where(ProcessingJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    job.status = body.status
    if body.status == JobStatus.running and job.started_at is None:
        job.started_at = datetime.now(UTC)
    if body.status in (JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled):
        job.finished_at = datetime.now(UTC)
    if body.error_stage is not None:
        job.error_stage = body.error_stage
    if body.error_message is not None:
        job.error_message = body.error_message
    if body.output_artifacts is not None:
        job.output_artifacts = body.output_artifacts

    await db.flush()
    log.info("job_status_updated", job_id=str(job_id), status=body.status)
    return JobResponse.from_orm_job(job)


@router.post("/{job_id}/retry", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def retry_job(
    job_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(require_any_staff)],
) -> JobResponse:
    """Retry a failed job by creating a new queued copy."""
    result = await db.execute(select(ProcessingJob).where(ProcessingJob.id == job_id))
    original = result.scalar_one_or_none()
    if original is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if original.status != JobStatus.failed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only failed jobs can be retried (current status: {original.status})",
        )

    retry = ProcessingJob(
        id=uuid.uuid4(),
        video_id=original.video_id,
        clip_id=original.clip_id,
        job_type=original.job_type,
        status=JobStatus.queued,
        priority=original.priority,
        input_artifacts=original.input_artifacts,
        model_version_id=original.model_version_id,
    )
    db.add(retry)
    await db.flush()
    log.info("job_retried", original_job_id=str(job_id), new_job_id=str(retry.id))
    return JobResponse.from_orm_job(retry)
