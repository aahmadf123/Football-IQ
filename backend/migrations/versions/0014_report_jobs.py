"""Report export jobs (Issue #111).

Adds ``report_jobs`` for tracking async report generation. The status column
reuses the existing ``job_status`` enum (created by an earlier migration), so
the only new enum here is ``report_format``.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-28 12:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FORMAT_ENUM_NAME = "report_format"
FORMAT_ENUM_VALUES = ("pdf", "csv", "json")

STATUS_ENUM_NAME = "job_status"
STATUS_ENUM_VALUES = ("queued", "running", "succeeded", "failed", "cancelled")


def upgrade() -> None:
    conn = op.get_bind()

    fmt_exists = conn.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :name"),
        {"name": FORMAT_ENUM_NAME},
    ).scalar()
    if not fmt_exists:
        sa.Enum(*FORMAT_ENUM_VALUES, name=FORMAT_ENUM_NAME).create(conn, checkfirst=False)

    fmt_enum = sa.Enum(*FORMAT_ENUM_VALUES, name=FORMAT_ENUM_NAME, create_type=False)
    status_enum = sa.Enum(*STATUS_ENUM_VALUES, name=STATUS_ENUM_NAME, create_type=False)

    table_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='report_jobs'"
        )
    ).scalar()
    if not table_exists:
        op.create_table(
            "report_jobs",
            sa.Column(
                "id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                primary_key=True,
            ),
            sa.Column("report_type", sa.String(64), nullable=False),
            sa.Column("format", fmt_enum, nullable=False),
            sa.Column("status", status_enum, nullable=False, server_default="queued"),
            sa.Column("parameters", sa.JSON, nullable=True),
            sa.Column("output_uri", sa.Text, nullable=True),
            sa.Column("error_message", sa.Text, nullable=True),
            sa.Column(
                "requested_by",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_report_jobs_report_type",
            "report_jobs",
            ["report_type"],
        )
        op.create_index(
            "ix_report_jobs_requested_by",
            "report_jobs",
            ["requested_by"],
        )
        op.create_index(
            "ix_report_jobs_created_at",
            "report_jobs",
            ["created_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_report_jobs_created_at", table_name="report_jobs")
    op.drop_index("ix_report_jobs_requested_by", table_name="report_jobs")
    op.drop_index("ix_report_jobs_report_type", table_name="report_jobs")
    op.drop_table("report_jobs")
    sa.Enum(name=FORMAT_ENUM_NAME).drop(op.get_bind(), checkfirst=True)
