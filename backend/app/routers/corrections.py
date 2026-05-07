"""Coach corrections router — human overrides that become training labels."""

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user, require_analyst_or_above, require_coach_or_above
from app.models import Clip, CoachCorrection, CorrectionType, Label, User

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/corrections", tags=["corrections"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class CorrectionCreate(BaseModel):
    clip_id: uuid.UUID
    correction_type: CorrectionType
    original_value: dict[str, Any] | None = None
    corrected_value: dict[str, Any]
    notes: str | None = None


class CorrectionResponse(BaseModel):
    id: uuid.UUID
    clip_id: uuid.UUID
    correction_type: str
    original_value: dict[str, Any] | None
    corrected_value: dict[str, Any]
    corrected_by: uuid.UUID
    notes: str | None
    exported_as_label: bool
    created_at: str

    @classmethod
    def from_orm_correction(cls, c: CoachCorrection) -> "CorrectionResponse":
        return cls(
            id=c.id,
            clip_id=c.clip_id,
            correction_type=c.correction_type.value,
            original_value=c.original_value,
            corrected_value=c.corrected_value,
            corrected_by=c.corrected_by,
            notes=c.notes,
            exported_as_label=c.exported_as_label,
            created_at=c.created_at.isoformat(),
        )


class ExportResponse(BaseModel):
    exported_count: int
    label_ids: list[uuid.UUID]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", response_model=CorrectionResponse, status_code=status.HTTP_201_CREATED)
async def create_correction(
    body: CorrectionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_coach_or_above)],
) -> CorrectionResponse:
    """Submit a coach/analyst correction — recorded and eligible for training export."""
    clip_result = await db.execute(select(Clip).where(Clip.id == body.clip_id))
    if clip_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    correction = CoachCorrection(
        id=uuid.uuid4(),
        clip_id=body.clip_id,
        correction_type=body.correction_type,
        original_value=body.original_value,
        corrected_value=body.corrected_value,
        corrected_by=current_user.id,
        notes=body.notes,
    )
    db.add(correction)
    await db.flush()
    log.info(
        "correction_created",
        correction_id=str(correction.id),
        clip_id=str(body.clip_id),
        type=body.correction_type,
    )
    return CorrectionResponse.from_orm_correction(correction)


@router.get("", response_model=list[CorrectionResponse])
async def list_corrections(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    clip_id: uuid.UUID | None = Query(default=None),
    exported: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[CorrectionResponse]:
    """List corrections with optional filters."""
    q = (
        select(CoachCorrection)
        .order_by(CoachCorrection.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if clip_id is not None:
        q = q.where(CoachCorrection.clip_id == clip_id)
    if exported is not None:
        q = q.where(CoachCorrection.exported_as_label == exported)
    result = await db.execute(q)
    return [CorrectionResponse.from_orm_correction(c) for c in result.scalars().all()]


@router.post("/export", response_model=ExportResponse)
async def export_corrections_as_labels(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(require_analyst_or_above)],
    clip_id: uuid.UUID | None = Query(default=None),
) -> ExportResponse:
    """Export un-exported corrections as Label rows for model training."""
    q = select(CoachCorrection).where(CoachCorrection.exported_as_label.is_(False))
    if clip_id is not None:
        q = q.where(CoachCorrection.clip_id == clip_id)
    result = await db.execute(q)
    corrections = result.scalars().all()

    label_ids: list[uuid.UUID] = []
    for correction in corrections:
        label = Label(
            id=uuid.uuid4(),
            clip_id=correction.clip_id,
            label_type=correction.correction_type.value,
            label_value=correction.corrected_value,
            annotated_by=correction.corrected_by,
            source="human",
        )
        db.add(label)
        correction.exported_as_label = True
        label_ids.append(label.id)

    await db.flush()
    log.info("corrections_exported", count=len(label_ids))
    return ExportResponse(exported_count=len(label_ids), label_ids=label_ids)
