"""Corrections → Labels/TrainingDataset export as a callable service.

Extracted from the /api/v1/corrections/export endpoint so the nightly
scheduler (app.scheduler) can run the same export without an HTTP call.
The router remains the manual/analyst entry point.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Clip, CoachCorrection, Label, TrainingDataset
from app.utils import make_dataset_artifact_uri

log = structlog.get_logger(__name__)


@dataclass
class ExportResult:
    exported_count: int
    label_ids: list[uuid.UUID] = field(default_factory=list)
    training_dataset_id: uuid.UUID | None = None


async def export_corrections(
    db: AsyncSession,
    *,
    clip_id: uuid.UUID | None = None,
    model_scope: str = "general",
) -> ExportResult:
    """Export un-exported, training-eligible corrections as Label rows.

    Creates a TrainingDataset snapshot when anything was exported. The caller
    owns the transaction (flush here, commit outside).
    """
    q = select(CoachCorrection).where(
        CoachCorrection.exported_as_label.is_(False),
        CoachCorrection.training_eligible.is_(True),
    )
    if clip_id is not None:
        q = q.where(CoachCorrection.clip_id == clip_id)
    result = await db.execute(q)
    corrections = result.scalars().all()

    labels: list[Label] = []
    correction_ids: list[uuid.UUID] = []
    for correction in corrections:
        clip_result = await db.execute(select(Clip).where(Clip.id == correction.clip_id))
        clip = clip_result.scalar_one_or_none()
        label = Label(
            id=uuid.uuid4(),
            clip_id=correction.clip_id,
            label_type=correction.correction_type.value,
            label_value=correction.corrected_value,
            annotated_by=correction.corrected_by,
            source="human",
            model_version_id=clip.model_version_id if clip is not None else None,
        )
        db.add(label)
        correction.exported_as_label = True
        labels.append(label)
        correction_ids.append(correction.id)

    training_dataset_id: uuid.UUID | None = None
    if labels:
        previous_result = await db.execute(
            select(TrainingDataset)
            .where(TrainingDataset.model_scope == model_scope)
            .order_by(TrainingDataset.snapshot_date.desc())
            .limit(1)
        )
        previous = previous_result.scalar_one_or_none()
        previous_corrections = (
            {uuid.UUID(c) for c in previous.source_correction_ids}
            if previous is not None
            else set()
        )
        added_corrections = [
            str(c_id) for c_id in correction_ids if c_id not in previous_corrections
        ]

        dataset = TrainingDataset(
            id=uuid.uuid4(),
            model_scope=model_scope,
            source_label_ids=[str(label.id) for label in labels],
            source_correction_ids=[str(c_id) for c_id in correction_ids],
            row_count=len(labels),
            artifact_uri=make_dataset_artifact_uri(model_scope),
            changelog={"added_correction_ids": added_corrections},
        )
        db.add(dataset)
        await db.flush()
        training_dataset_id = dataset.id

        for exported_label in labels:
            exported_label.training_dataset_id = training_dataset_id
            exported_label.dataset_version = str(training_dataset_id)

    await db.flush()
    log.info(
        "corrections_exported",
        count=len(labels),
        training_dataset_id=str(training_dataset_id),
    )
    return ExportResult(
        exported_count=len(labels),
        label_ids=[label.id for label in labels],
        training_dataset_id=training_dataset_id,
    )
