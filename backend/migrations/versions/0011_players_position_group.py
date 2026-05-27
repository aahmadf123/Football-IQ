"""Players: add ``position_group`` column for roster filtering (Issue #103).

Adds a nullable ``position_group`` text column to the ``players`` table so the
new ``/api/v1/players`` API can filter by coaching group (QB, Skill, OL, DL,
LB, DB, ST) without forcing callers to enumerate every position string. The
column is indexed because filtering by group is the dominant access pattern
for roster and position-coach views.

The column is intentionally nullable: legacy rows imported before this
migration may not have a group assigned, and assignment is handled in the
application layer rather than at the schema boundary.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-27 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    col_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='public' "
            "AND table_name='players' "
            "AND column_name='position_group'"
        )
    ).scalar()
    if not col_exists:
        op.add_column(
            "players",
            sa.Column("position_group", sa.String(20), nullable=True),
        )
    idx_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes "
            "WHERE tablename='players' "
            "AND indexname='ix_players_position_group'"
        )
    ).scalar()
    if not idx_exists:
        op.create_index(
            "ix_players_position_group",
            "players",
            ["position_group"],
        )


def downgrade() -> None:
    op.drop_index("ix_players_position_group", table_name="players")
    op.drop_column("players", "position_group")
