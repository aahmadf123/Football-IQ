"""Settings persistence tables (Issue #112).

Adds ``system_settings`` (singleton KV) and ``user_settings`` (per-user KV)
so configuration values survive page reloads and sessions. Both tables store
their payload in a JSON column whose shape is validated by Pydantic schemas
in ``app.schemas.settings``; this keeps the database flexible while the
known-key set evolves.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-28 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    system_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='system_settings'"
        )
    ).scalar()
    if not system_exists:
        op.create_table(
            "system_settings",
            sa.Column("key", sa.String(128), primary_key=True),
            sa.Column("value", sa.JSON, nullable=False),
            sa.Column(
                "updated_by",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    user_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='user_settings'"
        )
    ).scalar()
    if not user_exists:
        op.create_table(
            "user_settings",
            sa.Column(
                "user_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("key", sa.String(128), primary_key=True),
            sa.Column("value", sa.JSON, nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    op.drop_table("user_settings")
    op.drop_table("system_settings")
