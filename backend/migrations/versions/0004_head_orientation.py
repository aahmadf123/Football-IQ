"""Head orientation & gaze estimation — Phase 1.

Adds:
  - New columns to the metrics table: tracklet_id, experimental_flag,
    analytics_safe, confidence.
    (evidence_uri is already added by migration 0003_pipeline_columns.)
  - pose_keypoints table: per-frame RTMPose/ViTPose keypoints with derived
    head yaw angle and orientation confidence.
  - head_orientation_reviews table: position-coach approve/reject/flag
    workflow for experimental metrics.

All head orientation metrics default to experimental_flag=True and
analytics_safe=False until a position coach explicitly approves them.
Player-facing views must never surface experimental metrics.

Revision ID: 0004
Revises: 0003_merge
Create Date: 2026-05-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003_merge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── New columns on metrics ─────────────────────────────────────────────
    op.add_column(
        "metrics",
        sa.Column(
            "tracklet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracklets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_metrics_tracklet_id", "metrics", ["tracklet_id"])

    op.add_column(
        "metrics",
        sa.Column(
            "experimental_flag",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "metrics",
        sa.Column(
            "analytics_safe",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "metrics",
        sa.Column("confidence", sa.Float(), nullable=True),
    )

    # ── pose_keypoints ─────────────────────────────────────────────────────
    op.create_table(
        "pose_keypoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tracklet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracklets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("frame_number", sa.Integer(), nullable=False),
        # Full keypoint payload from RTMPose/ViTPose: [{name, x, y, confidence}, ...]
        sa.Column("keypoints", postgresql.JSONB(), nullable=False),
        # Derived head-direction yaw in degrees (0° = facing field direction)
        sa.Column("head_yaw_degrees", sa.Float(), nullable=True),
        # 0.0–1.0 confidence based on keypoint visibility and head occlusion
        sa.Column("head_orientation_confidence", sa.Float(), nullable=True),
        sa.Column(
            "model_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("model_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("processing_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_pose_keypoints_tracklet_id", "pose_keypoints", ["tracklet_id"])
    op.create_index(
        "ix_pose_keypoints_tracklet_frame",
        "pose_keypoints",
        ["tracklet_id", "frame_number"],
    )

    # ── head_orientation_reviews ───────────────────────────────────────────
    op.create_table(
        "head_orientation_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "metric_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("metrics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reviewer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # "approve" → analytics_safe=True; "reject" → stays suppressed;
        # "flag"    → sent to model review queue
        sa.Column("review_action", sa.String(20), nullable=False),
        # Position group: "QB", "Safety", "CB", "LB"
        sa.Column("position_group", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_head_orientation_reviews_metric_id",
        "head_orientation_reviews",
        ["metric_id"],
    )


def downgrade() -> None:
    op.drop_table("head_orientation_reviews")
    op.drop_table("pose_keypoints")

    op.drop_index("ix_metrics_tracklet_id", table_name="metrics")
    op.drop_column("metrics", "confidence")
    op.drop_column("metrics", "analytics_safe")
    op.drop_column("metrics", "experimental_flag")
    op.drop_column("metrics", "tracklet_id")
