"""Regime-aware calibration diagnostics on field_calibrations (Issues #127/#138).

Adds the per-regime calibration outputs that downstream stages (#128/#129/
#132/#133/#135/#139/#140/#150) consume to reason about *why* a homography is
weak, not just its blended confidence:

* ``kalman_state``      — 9-vector ``vec(H)`` from DRONE_FOLLOW nightly smoothing
* ``inlier_ratio``      — RANSAC inlier ratio of the chosen fit
* ``line_count``        — field lines detected on the calibration frame
* ``parallel_variance`` — angular variance of detected yard lines
* ``temporal_drift``    — mean inter-window re-projection drift (0.0 for a
                          bolted-down FIXED_SIDELINE anchor)
* ``is_game_anchor``    — the once-per-game FIXED_SIDELINE homography reused
                          across plays

All columns are nullable (the calibration stage may legitimately leave them
NULL on a failed fit); ``is_game_anchor`` defaults to FALSE and existing rows
are backfilled to FALSE.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "field_calibrations",
        sa.Column("kalman_state", sa.JSON(), nullable=True),
    )
    op.add_column(
        "field_calibrations",
        sa.Column("inlier_ratio", sa.Float(), nullable=True),
    )
    op.add_column(
        "field_calibrations",
        sa.Column("line_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "field_calibrations",
        sa.Column("parallel_variance", sa.Float(), nullable=True),
    )
    op.add_column(
        "field_calibrations",
        sa.Column("temporal_drift", sa.Float(), nullable=True),
    )
    op.add_column(
        "field_calibrations",
        sa.Column(
            "is_game_anchor",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Backfill pre-existing rows explicitly, then drop the server default so
    # the application-side default (False) is authoritative going forward.
    op.execute("UPDATE field_calibrations SET is_game_anchor = FALSE WHERE is_game_anchor IS NULL")
    op.alter_column("field_calibrations", "is_game_anchor", server_default=None)


def downgrade() -> None:
    op.drop_column("field_calibrations", "is_game_anchor")
    op.drop_column("field_calibrations", "temporal_drift")
    op.drop_column("field_calibrations", "parallel_variance")
    op.drop_column("field_calibrations", "line_count")
    op.drop_column("field_calibrations", "inlier_ratio")
    op.drop_column("field_calibrations", "kalman_state")
