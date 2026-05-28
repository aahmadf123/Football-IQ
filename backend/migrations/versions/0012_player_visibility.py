"""Player visibility state + audit log (Issues #113, #114).

Adds the outward-facing visibility lifecycle to ``players`` and a
``player_visibility_audit`` append-only table that records every state
transition. See ``docs/governance.md`` for the full policy.

States:
    ``staff_only`` (default)
    ``player_approved``
    ``recruiting_approved``
    ``archived``

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-27 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ENUM_NAME = "player_visibility_state"
ENUM_VALUES = (
    "staff_only",
    "player_approved",
    "recruiting_approved",
    "archived",
)


def upgrade() -> None:
    conn = op.get_bind()

    # Create the enum type idempotently.
    enum_exists = conn.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :name"),
        {"name": ENUM_NAME},
    ).scalar()
    if not enum_exists:
        sa.Enum(*ENUM_VALUES, name=ENUM_NAME).create(conn, checkfirst=False)

    enum_type = sa.Enum(*ENUM_VALUES, name=ENUM_NAME, create_type=False)

    # players.visibility_state
    col_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='public' "
            "AND table_name='players' "
            "AND column_name='visibility_state'"
        )
    ).scalar()
    if not col_exists:
        op.add_column(
            "players",
            sa.Column(
                "visibility_state",
                enum_type,
                nullable=False,
                server_default="staff_only",
            ),
        )

    for extra in ("visibility_updated_by", "visibility_updated_at"):
        present = conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' "
                "AND table_name='players' "
                "AND column_name=:c"
            ),
            {"c": extra},
        ).scalar()
        if not present:
            if extra == "visibility_updated_by":
                op.add_column(
                    "players",
                    sa.Column(
                        "visibility_updated_by",
                        sa.dialects.postgresql.UUID(as_uuid=True),
                        sa.ForeignKey("users.id", ondelete="SET NULL"),
                        nullable=True,
                    ),
                )
            else:
                op.add_column(
                    "players",
                    sa.Column(
                        "visibility_updated_at",
                        sa.DateTime(timezone=True),
                        nullable=True,
                    ),
                )

    # Audit log table.
    table_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' "
            "AND table_name='player_visibility_audit'"
        )
    ).scalar()
    if not table_exists:
        op.create_table(
            "player_visibility_audit",
            sa.Column(
                "id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                primary_key=True,
            ),
            sa.Column(
                "player_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey("players.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("previous_state", enum_type, nullable=True),
            sa.Column("next_state", enum_type, nullable=False),
            sa.Column(
                "actor_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("reason", sa.Text, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_player_visibility_audit_player_id",
            "player_visibility_audit",
            ["player_id"],
        )


def downgrade() -> None:
    op.drop_index(
        "ix_player_visibility_audit_player_id",
        table_name="player_visibility_audit",
    )
    op.drop_table("player_visibility_audit")
    op.drop_column("players", "visibility_updated_at")
    op.drop_column("players", "visibility_updated_by")
    op.drop_column("players", "visibility_state")
    sa.Enum(name=ENUM_NAME).drop(op.get_bind(), checkfirst=True)
