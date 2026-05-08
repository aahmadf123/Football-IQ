"""iPad one-tap correction sync router (Issue #16).

Endpoints:
  POST /api/v1/corrections/sync — bulk-sync corrections from the iPad
                                   coaching app during or after a practice

Synced corrections feed the existing ``coach_corrections`` table.  A new
corrections table is NOT created — this router calls the same DB model
as the existing corrections router.

Use cases:
  - Coach taps "wrong formation" on iPad → sync queues the correction
  - Coach taps "wrong player" on clip → synced at end of period
  - Offline corrections collected while drone connectivity is down →
    synced when connectivity restores

The iPad client should call this endpoint with a list of correction dicts.
Each dict is validated and written to ``coach_corrections`` exactly like a
manual correction.  Duplicates (same clip_id + correction_type + corrected_by
within the same second) are silently skipped to handle retry semantics.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import require_coach_or_above
from app.models import Clip, CoachCorrection, CorrectionType, User

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/corrections", tags=["corrections"])

_DEDUP_WINDOW_SECONDS = 5


# ── Schemas ───────────────────────────────────────────────────────────────────


class CorrectionSyncItem(BaseModel):
    """One correction from the iPad queue."""

    clip_id: uuid.UUID
    correction_type: CorrectionType
    original_value: dict[str, Any] | None = None
    corrected_value: dict[str, Any]
    notes: str | None = None
    training_eligible: bool = True
    client_timestamp: str | None = None


class CorrectionSyncRequest(BaseModel):
    """Batch of corrections from the iPad coaching app."""

    corrections: list[CorrectionSyncItem]
    device_id: str | None = None
    session_id: str | None = None


class CorrectionSyncResponse(BaseModel):
    synced_count: int
    skipped_count: int
    correction_ids: list[uuid.UUID]


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post("/sync", response_model=CorrectionSyncResponse, status_code=status.HTTP_201_CREATED)
async def sync_corrections(
    body: CorrectionSyncRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_coach_or_above)],
) -> CorrectionSyncResponse:
    """Bulk-sync iPad one-tap corrections to the coach_corrections table.

    Each correction is written as a ``CoachCorrection`` row.  Duplicates
    (same clip_id + correction_type + corrected_by within a 5 s window) are
    skipped to handle retry/offline-queue replay safely.

    Returns a count of synced and skipped corrections plus the new IDs.
    """
    synced: list[uuid.UUID] = []
    skipped = 0
    now = datetime.now(UTC)
    dedup_window_start = now - timedelta(seconds=_DEDUP_WINDOW_SECONDS)

    for item in body.corrections:
        # Verify clip exists
        clip_result = await db.execute(select(Clip).where(Clip.id == item.clip_id))
        if clip_result.scalar_one_or_none() is None:
            log.warning(
                "correction_sync_clip_not_found",
                clip_id=str(item.clip_id),
                device_id=body.device_id,
            )
            skipped += 1
            continue

        # Deduplication: check for a recent identical correction
        dup_result = await db.execute(
            select(CoachCorrection).where(
                CoachCorrection.clip_id == item.clip_id,
                CoachCorrection.correction_type == item.correction_type,
                CoachCorrection.corrected_by == current_user.id,
                CoachCorrection.created_at >= dedup_window_start,
            )
        )
        if dup_result.scalar_one_or_none() is not None:
            log.debug(
                "correction_sync_duplicate_skipped",
                clip_id=str(item.clip_id),
                correction_type=item.correction_type.value,
            )
            skipped += 1
            continue

        correction = CoachCorrection(
            id=uuid.uuid4(),
            clip_id=item.clip_id,
            correction_type=item.correction_type,
            original_value=item.original_value,
            corrected_value=item.corrected_value,
            corrected_by=current_user.id,
            notes=item.notes,
            training_eligible=item.training_eligible,
        )
        db.add(correction)
        await db.flush()
        synced.append(correction.id)

    log.info(
        "correction_sync_complete",
        synced=len(synced),
        skipped=skipped,
        session_id=body.session_id,
        device_id=body.device_id,
    )
    return CorrectionSyncResponse(
        synced_count=len(synced),
        skipped_count=skipped,
        correction_ids=synced,
    )
