"""Phase 3 — Real-Time Same-Session Feedback Pipeline (Issue #16).

Adds:
  - ``pipeline_mode`` column on ``processing_jobs`` — tracks whether a job
    runs on the same-session lightweight path or nightly full-quality path.
  - ``nightly_followup_job_id`` column on ``processing_jobs`` — links a
    same-session render job to its nightly HLS follow-up.
  - ``render_hls`` value on the ``job_type`` enum for nightly follow-up
    full-resolution HLS encoding.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add pipeline_mode column
    op.add_column(
        "processing_jobs",
        sa.Column("pipeline_mode", sa.String(20), nullable=True, index=True),
    )
    # Add nightly_followup_job_id column
    op.add_column(
        "processing_jobs",
        sa.Column(
            "nightly_followup_job_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    # Add render_hls to the job_type enum
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'render_hls'")


def downgrade() -> None:
    op.drop_column("processing_jobs", "nightly_followup_job_id")
    op.drop_column("processing_jobs", "pipeline_mode")
    # Enum values cannot be removed in PostgreSQL without recreating the type.
