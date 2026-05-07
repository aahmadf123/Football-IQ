"""Phase 1 pipeline column additions.

Adds:
  - clips.boundary_source  — "model" | "manual", identifies who proposed the boundary
  - clips.boundary_confidence — float, model's boundary-proposal confidence
  - field_calibrations.analytics_safe — bool, suppresses metrics when False
  - field_calibrations.reason_codes   — JSONB list of calibration failure reasons
  - metrics.evidence_uri              — URI pointing to the evidence artefact

Revision ID: 0003
Revises: 0002
Create Date: 2025-01-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── clips ─────────────────────────────────────────────────────────────
    op.add_column(
        "clips",
        sa.Column("boundary_source", sa.String(20), nullable=True),
    )
    op.add_column(
        "clips",
        sa.Column("boundary_confidence", sa.Float(), nullable=True),
    )

    # ── field_calibrations ────────────────────────────────────────────────
    op.add_column(
        "field_calibrations",
        sa.Column(
            "analytics_safe",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "field_calibrations",
        sa.Column("reason_codes", postgresql.JSONB(), nullable=True),
    )

    # ── metrics ───────────────────────────────────────────────────────────
    op.add_column(
        "metrics",
        sa.Column("evidence_uri", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("metrics", "evidence_uri")
    op.drop_column("field_calibrations", "reason_codes")
    op.drop_column("field_calibrations", "analytics_safe")
    op.drop_column("clips", "boundary_confidence")
    op.drop_column("clips", "boundary_source")
