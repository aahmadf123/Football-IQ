"""Pre-snap play predictions + per-opponent Dirichlet priors (Issues #135/#136).

Creates the two tables behind the calibrated pre-snap run/pass predictor:

* ``play_predictions`` — one calibrated prediction per snap. The six pre-snap
  signals (Issue #135) are stored as a JSON ``signal_vector``; the ensemble
  outputs (raw + calibrated probability, logit, predicted/true class,
  confidence, calibrated uncertainty per Issue #146) sit alongside.
* ``opponent_priors`` — the per-opponent situational Dirichlet (Beta)
  posteriors keyed by (opponent, down, distance-bucket, field-zone). The
  default ``Beta(2,2)`` is uninformative (0.5); cells only diverge once
  coach-confirmed outcomes accumulate (``n_pass`` / ``n_run``), so every
  non-default prior is data-backed — there are no hard-coded opponent priors.

Notes / deviations from the issue sketch:
* Opponents are identified by ``opponent_team`` (VARCHAR) to match the existing
  derived-opponent model (``videos.opponent_team``); there is no opponents
  table to FK against (see ``app/routers/opponents.py``).
* ``model_version_id`` references the existing ``model_versions`` registry
  table (the issue's ``mlops_registry`` name) with ON DELETE SET NULL.
* JSON (not JSONB) matches the column type used throughout this schema.

Both tables upgrade and downgrade cleanly.

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-29 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID_PK = sa.text("gen_random_uuid()")
_NOW = sa.text("now()")


def upgrade() -> None:
    # gen_random_uuid() is core in PG13+; pgcrypto provides it defensively.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "play_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK),
        sa.Column(
            "clip_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clips.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("play_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("opponent_team", sa.String(length=120), nullable=True),
        sa.Column("signal_vector", sa.JSON(), nullable=False),
        sa.Column("logit_score", sa.Float(), nullable=True),
        sa.Column("predicted_class", sa.String(length=32), nullable=True),
        sa.Column("true_class", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("calibrated_prob", sa.Float(), nullable=True),
        sa.Column("uncertainty", sa.Float(), nullable=True),
        sa.Column("is_calibrated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "model_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("model_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
    )
    op.create_index("play_predictions_clip_id_idx", "play_predictions", ["clip_id"])
    op.create_index("play_predictions_opponent_team_idx", "play_predictions", ["opponent_team"])

    op.create_table(
        "opponent_priors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK),
        sa.Column("opponent_team", sa.String(length=120), nullable=True),
        sa.Column("down", sa.Integer(), nullable=True),
        sa.Column("distance_bucket", sa.String(length=16), nullable=True),
        sa.Column("field_zone", sa.String(length=16), nullable=True),
        sa.Column("alpha_pass", sa.Float(), nullable=False, server_default=sa.text("2.0")),
        sa.Column("alpha_run", sa.Float(), nullable=False, server_default=sa.text("2.0")),
        sa.Column("n_pass", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("n_run", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.UniqueConstraint(
            "opponent_team",
            "down",
            "distance_bucket",
            "field_zone",
            name="opponent_priors_situation_uq",
        ),
    )
    op.create_index("opponent_priors_opponent_team_idx", "opponent_priors", ["opponent_team"])


def downgrade() -> None:
    op.drop_index("opponent_priors_opponent_team_idx", table_name="opponent_priors")
    op.drop_table("opponent_priors")
    op.drop_index("play_predictions_opponent_team_idx", table_name="play_predictions")
    op.drop_index("play_predictions_clip_id_idx", table_name="play_predictions")
    op.drop_table("play_predictions")
