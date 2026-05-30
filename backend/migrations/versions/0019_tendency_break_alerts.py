"""Tendency-break alerts: formation_tendency alert type + actioned tracking (Issue #137).

Two additive changes to the existing ``alerts`` infrastructure:

* A new ``formation_tendency`` value on the ``alert_type`` enum. Self-scout
  tendency-break alerts (season-long lopsided run/pass tendencies and in-game
  pattern breaks) are persisted as ordinary ``alerts`` rows so they reuse the
  existing SSE stream, listing, and acknowledgement surfaces.
* Three nullable columns on ``alerts`` — ``is_actioned`` / ``actioned_by`` /
  ``actioned_at`` — so a coach can mark an alert as turned-into-a-follow-up.
  "Actioned" is intentionally distinct from "acknowledged": acknowledging means
  "seen", actioning means "addressed in practice/scheme".

Downgrade notes
---------------
The new columns are dropped cleanly on downgrade. The ``formation_tendency``
enum *value* is intentionally left in place: PostgreSQL has no ``ALTER TYPE ...
DROP VALUE``, and the ``alert_type`` enum is dropped wholesale by the 0007
downgrade in a full ``downgrade base`` run, so leaving the value is harmless and
keeps this migration's downgrade simple and re-runnable. Any persisted
``formation_tendency`` rows are removed first so a single-step downgrade does
not leave dangling rows referencing the (still-present) value.

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-29 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _alerts_columns() -> set[str]:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='alerts'"
        )
    ).fetchall()
    return {r[0] for r in rows}


def upgrade() -> None:
    # ── New enum value (idempotent; safe inside the migration transaction on
    #    PostgreSQL 12+ because it is never *used* in this same transaction). ──
    op.execute("ALTER TYPE alert_type ADD VALUE IF NOT EXISTS 'formation_tendency'")

    existing = _alerts_columns()
    if "is_actioned" not in existing:
        op.add_column(
            "alerts",
            sa.Column(
                "is_actioned",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
        )
    if "actioned_by" not in existing:
        op.add_column(
            "alerts",
            sa.Column(
                "actioned_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if "actioned_at" not in existing:
        op.add_column(
            "alerts",
            sa.Column("actioned_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    # Remove any rows that use the new enum value before the columns go, so a
    # single-step downgrade leaves a consistent table.
    op.execute("DELETE FROM alerts WHERE alert_type = 'formation_tendency'")

    existing = _alerts_columns()
    if "actioned_at" in existing:
        op.drop_column("alerts", "actioned_at")
    if "actioned_by" in existing:
        op.drop_column("alerts", "actioned_by")
    if "is_actioned" in existing:
        op.drop_column("alerts", "is_actioned")
    # The ``formation_tendency`` enum value is intentionally not removed — see
    # the module docstring. The enum type is dropped wholesale by 0007's
    # downgrade in a full ``downgrade base`` run.
