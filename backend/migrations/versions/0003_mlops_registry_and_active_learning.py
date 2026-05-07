"""Phase 1 MLOps infrastructure: dataset versioning and active learning queue.

Revision ID: 0003_mlops
Revises: 0002
Create Date: 2026-05-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_mlops"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    active_learning_reason = postgresql.ENUM(
        "low_confidence",
        "uncertainty_sampling",
        "regression",
        "hard_negative",
        name="active_learning_reason",
    )
    active_learning_status = postgresql.ENUM(
        "queued",
        "in_review",
        "resolved",
        name="active_learning_status",
    )
    active_learning_reason.create(op.get_bind(), checkfirst=True)
    active_learning_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "training_datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "snapshot_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("model_scope", sa.String(length=100), nullable=False),
        sa.Column("source_label_ids", postgresql.JSONB(), nullable=False),
        sa.Column("source_correction_ids", postgresql.JSONB(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("artifact_uri", sa.Text(), nullable=False),
        sa.Column("changelog", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_training_datasets_model_scope", "training_datasets", ["model_scope"])

    op.add_column(
        "labels",
        sa.Column(
            "model_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("model_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "labels",
        sa.Column(
            "training_dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("training_datasets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "coach_corrections",
        sa.Column("training_eligible", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "processing_jobs",
        sa.Column(
            "training_dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("training_datasets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_model_versions_training_dataset_id",
        "model_versions",
        "training_datasets",
        ["training_dataset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_model_versions_promotion_requires_metrics",
        "model_versions",
        "(promoted_stage IN ('experimental', 'retired')) OR (metrics IS NOT NULL)",
    )

    op.create_table(
        "active_learning_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "clip_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clips.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("label_type", sa.String(length=100), nullable=False),
        sa.Column(
            "queue_reason",
            postgresql.ENUM(
                "low_confidence",
                "uncertainty_sampling",
                "regression",
                "hard_negative",
                name="active_learning_reason",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("priority_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("model_confidence", sa.Float(), nullable=True),
        sa.Column(
            "source_model_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("model_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "correction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("coach_corrections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "queued",
                "in_review",
                "resolved",
                name="active_learning_status",
                create_type=False,
            ),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_active_learning_queue_clip_id", "active_learning_queue", ["clip_id"])
    op.create_index("ix_active_learning_queue_label_type", "active_learning_queue", ["label_type"])


def downgrade() -> None:
    op.drop_index("ix_active_learning_queue_label_type", table_name="active_learning_queue")
    op.drop_index("ix_active_learning_queue_clip_id", table_name="active_learning_queue")
    op.drop_table("active_learning_queue")

    op.drop_constraint(
        "ck_model_versions_promotion_requires_metrics", "model_versions", type_="check"
    )
    op.drop_constraint(
        "fk_model_versions_training_dataset_id",
        "model_versions",
        type_="foreignkey",
    )
    op.drop_column("processing_jobs", "training_dataset_id")
    op.drop_column("coach_corrections", "training_eligible")
    op.drop_column("labels", "training_dataset_id")
    op.drop_column("labels", "model_version_id")

    op.drop_index("ix_training_datasets_model_scope", table_name="training_datasets")
    op.drop_table("training_datasets")

    op.execute("DROP TYPE IF EXISTS active_learning_status")
    op.execute("DROP TYPE IF EXISTS active_learning_reason")
