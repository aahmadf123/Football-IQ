"""Issue #16 — Real-Time Same-Session Feedback Pipeline: Alerts table.

Adds:
  - alert_type enum (bio_deviation, effort_anomaly, formation_anomaly)
  - alert_severity enum (low, medium, high)
  - alerts table

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── New enums ─────────────────────────────────────────────────────────────
    alert_type = postgresql.ENUM(
        "bio_deviation",
        "effort_anomaly",
        "formation_anomaly",
        name="alert_type",
        create_type=True,
    )
    alert_severity = postgresql.ENUM(
        "low",
        "medium",
        "high",
        name="alert_severity",
        create_type=True,
    )
    alert_type.create(op.get_bind(), checkfirst=True)
    alert_severity.create(op.get_bind(), checkfirst=True)

    # ── alerts table ──────────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "clip_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clips.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("position_group", sa.String(20), nullable=False),
        sa.Column("alert_type", sa.Enum("bio_deviation", "effort_anomaly", "formation_anomaly",
                                        name="alert_type", create_type=False), nullable=False),
        sa.Column("severity", sa.Enum("low", "medium", "high",
                                      name="alert_severity", create_type=False), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("metric_name", sa.String(255), nullable=False),
        sa.Column("metric_value", sa.JSON(), nullable=False),
        sa.Column("deviation_sd", sa.Float(), nullable=True),
        sa.Column("clip_uri", sa.Text(), nullable=True),
        sa.Column("period_name", sa.String(100), nullable=True),
        sa.Column("session_id", sa.String(100), nullable=True, index=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("processing_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_acknowledged", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "acknowledged_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index("ix_alerts_alert_type", "alerts", ["alert_type"])
    op.create_index("ix_alerts_position_group", "alerts", ["position_group"])


def downgrade() -> None:
    op.drop_index("ix_alerts_position_group", table_name="alerts")
    op.drop_index("ix_alerts_alert_type", table_name="alerts")
    op.drop_table("alerts")

    op.execute("DROP TYPE IF EXISTS alert_severity")
    op.execute("DROP TYPE IF EXISTS alert_type")
