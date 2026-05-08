"""Phase 2 — Pose-Lite Biomechanics Pilot (Issue #6).

Adds:
  - biomechanics JSONB column on pose_keypoints (per-frame computed angles).
  - pose_biomechanics_tag value to correction_type enum.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Extend correction_type enum ───────────────────────────────────────────
    op.execute("ALTER TYPE correction_type ADD VALUE IF NOT EXISTS 'pose_biomechanics_tag'")

    # ── Add biomechanics column to pose_keypoints ─────────────────────────────
    op.add_column(
        "pose_keypoints",
        sa.Column("biomechanics", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    # Drop biomechanics column (enum value cannot be removed in Postgres without recreation)
    op.drop_column("pose_keypoints", "biomechanics")
