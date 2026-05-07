"""Field calibrations router — homography calibration records."""

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user, require_any_staff
from app.models import FieldCalibration, User, Video

log = structlog.get_logger(__name__)
router = APIRouter(tags=["calibrations"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class CalibrationCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    video_id: uuid.UUID
    homography: list[float] | None = None
    confidence: float | None = None
    confidence_threshold: float = 0.7
    calibration_points: dict[str, Any] | None = None
    model_version_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None


class CalibrationResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: uuid.UUID
    video_id: uuid.UUID
    homography: list[float] | None
    confidence: float | None
    confidence_threshold: float
    calibration_points: dict[str, Any] | None
    model_version_id: uuid.UUID | None
    job_id: uuid.UUID | None
    # True when confidence meets or exceeds threshold — metrics are reliable
    metrics_enabled: bool
    created_at: str

    @classmethod
    def from_orm_cal(cls, c: FieldCalibration) -> "CalibrationResponse":
        metrics_enabled = c.confidence is not None and c.confidence >= c.confidence_threshold
        return cls(
            id=c.id,
            video_id=c.video_id,
            homography=c.homography,
            confidence=c.confidence,
            confidence_threshold=c.confidence_threshold,
            calibration_points=c.calibration_points,
            model_version_id=c.model_version_id,
            job_id=c.job_id,
            metrics_enabled=metrics_enabled,
            created_at=c.created_at.isoformat(),
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/api/v1/calibrations",
    response_model=CalibrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_calibration(
    body: CalibrationCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(require_any_staff)],
) -> CalibrationResponse:
    """Store a new field calibration result for a video."""
    vid_result = await db.execute(select(Video).where(Video.id == body.video_id))
    if vid_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    cal = FieldCalibration(
        id=uuid.uuid4(),
        video_id=body.video_id,
        homography=body.homography,
        confidence=body.confidence,
        confidence_threshold=body.confidence_threshold,
        calibration_points=body.calibration_points,
        model_version_id=body.model_version_id,
        job_id=body.job_id,
    )
    db.add(cal)
    await db.flush()
    log.info("calibration_created", cal_id=str(cal.id), video_id=str(body.video_id))
    return CalibrationResponse.from_orm_cal(cal)


@router.get(
    "/api/v1/videos/{video_id}/calibrations",
    response_model=list[CalibrationResponse],
)
async def list_calibrations_for_video(
    video_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> list[CalibrationResponse]:
    """List all calibrations for a video, newest first."""
    vid_result = await db.execute(select(Video).where(Video.id == video_id))
    if vid_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    result = await db.execute(
        select(FieldCalibration)
        .where(FieldCalibration.video_id == video_id)
        .order_by(FieldCalibration.created_at.desc())
    )
    return [CalibrationResponse.from_orm_cal(c) for c in result.scalars().all()]


@router.get("/api/v1/calibrations/{calibration_id}", response_model=CalibrationResponse)
async def get_calibration(
    calibration_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> CalibrationResponse:
    """Get a single calibration record."""
    result = await db.execute(select(FieldCalibration).where(FieldCalibration.id == calibration_id))
    cal = result.scalar_one_or_none()
    if cal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calibration not found")
    return CalibrationResponse.from_orm_cal(cal)
