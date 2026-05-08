"""Phase 2 — Coach-Trusted Football Layer tables.

Adds:
  - Expanded correction_type enum: route_tag, coverage_tag, personnel_tag,
    leverage_tag, effort_tag.
  - Expanded job_type enum: routes, coverage, oline, self_scout.
  - New columns on clips: personnel_grouping, down, distance, field_zone.
  - New columns on tracklets: position_group, side_of_ball.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Expand correction_type enum ───────────────────────────────────────
    op.execute("ALTER TYPE correction_type ADD VALUE IF NOT EXISTS 'route_tag'")
    op.execute("ALTER TYPE correction_type ADD VALUE IF NOT EXISTS 'coverage_tag'")
    op.execute("ALTER TYPE correction_type ADD VALUE IF NOT EXISTS 'personnel_tag'")
    op.execute("ALTER TYPE correction_type ADD VALUE IF NOT EXISTS 'leverage_tag'")
    op.execute("ALTER TYPE correction_type ADD VALUE IF NOT EXISTS 'effort_tag'")

    # ── Expand job_type enum ──────────────────────────────────────────────
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'routes'")
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'coverage'")
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'oline'")
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'self_scout'")

    # ── New columns on clips ──────────────────────────────────────────────
    op.add_column("clips", sa.Column("personnel_grouping", sa.String(20), nullable=True))
    op.add_column("clips", sa.Column("down", sa.Integer(), nullable=True))
    op.add_column("clips", sa.Column("distance", sa.Float(), nullable=True))
    op.add_column("clips", sa.Column("field_zone", sa.String(30), nullable=True))

    # ── New columns on tracklets ──────────────────────────────────────────
    op.add_column("tracklets", sa.Column("position_group", sa.String(20), nullable=True))
    op.add_column("tracklets", sa.Column("side_of_ball", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("tracklets", "side_of_ball")
    op.drop_column("tracklets", "position_group")
    op.drop_column("clips", "field_zone")
    op.drop_column("clips", "distance")
    op.drop_column("clips", "down")
    op.drop_column("clips", "personnel_grouping")
