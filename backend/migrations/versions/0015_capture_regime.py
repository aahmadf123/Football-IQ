"""Capture-regime metadata on videos + clips (Issue #126).

Adds the ``capture_regime`` Postgres enum (``drone_follow|fixed_sideline|
unknown``) plus ``capture_regime`` and ``regime_confidence`` columns on
both ``videos`` and ``clips``. The regime is detected once at ingest on
the source video and denormalized onto each clip when the segment stage
creates it, mirroring how ``session_kind`` is propagated (see 0010).

Existing rows are backfilled to ``unknown`` / ``0.0`` per the issue's
acceptance criteria so downstream code can safely assume the columns are
non-null after this migration runs (the columns themselves stay nullable
because ingest is the only writer and may legitimately set ``NULL``
mid-flight before the detector finishes).

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-28 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


REGIME_ENUM_NAME = "capture_regime"
REGIME_ENUM_VALUES = ("drone_follow", "fixed_sideline", "unknown")


def upgrade() -> None:
    bind = op.get_bind()

    # Create the enum up-front (checkfirst keeps the migration idempotent),
    # then reference it on every column with ``create_type=False`` so
    # SQLAlchemy never re-issues a CREATE TYPE on subsequent adds.
    postgresql.ENUM(*REGIME_ENUM_VALUES, name=REGIME_ENUM_NAME).create(
        bind, checkfirst=True
    )
    regime_enum = postgresql.ENUM(
        *REGIME_ENUM_VALUES, name=REGIME_ENUM_NAME, create_type=False
    )

    for table in ("videos", "clips"):
        op.add_column(
            table,
            sa.Column("capture_regime", regime_enum, nullable=True),
        )
        op.add_column(
            table,
            sa.Column("regime_confidence", sa.Float(), nullable=True),
        )
        op.create_index(
            f"ix_{table}_capture_regime", table, ["capture_regime"]
        )

    # Backfill pre-existing rows to ``unknown`` / 0.0 per Issue #126.
    op.execute(
        "UPDATE videos SET capture_regime = 'unknown', regime_confidence = 0.0 "
        "WHERE capture_regime IS NULL"
    )
    op.execute(
        "UPDATE clips SET capture_regime = 'unknown', regime_confidence = 0.0 "
        "WHERE capture_regime IS NULL"
    )


def downgrade() -> None:
    for table in ("clips", "videos"):
        op.drop_index(f"ix_{table}_capture_regime", table_name=table)
        op.drop_column(table, "regime_confidence")
        op.drop_column(table, "capture_regime")

    op.execute(f"DROP TYPE IF EXISTS {REGIME_ENUM_NAME}")
