"""Phase 1 tables — field_calibrations, tracklets, track_points, events,
labels, coach_corrections, metrics.  Also adds version-lineage columns to
clips (model_version_id, calibration_version_id, job_id).

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-02 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── New enum: correction_type ─────────────────────────────────────────
    correction_type = postgresql.ENUM(
        "clip_boundary",
        "player_identity",
        "event_tag",
        "formation_tag",
        name="correction_type",
    )
    correction_type.create(op.get_bind(), checkfirst=True)

    # ── field_calibrations ────────────────────────────────────────────────
    op.create_table(
        "field_calibrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "video_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("homography", postgresql.JSONB(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("confidence_threshold", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("calibration_points", postgresql.JSONB(), nullable=True),
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
    op.create_index("ix_field_calibrations_video_id", "field_calibrations", ["video_id"])

    # ── Version-lineage columns on clips ──────────────────────────────────
    op.add_column(
        "clips",
        sa.Column(
            "model_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("model_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "clips",
        sa.Column(
            "calibration_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("field_calibrations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "clips",
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("processing_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # ── tracklets ─────────────────────────────────────────────────────────
    op.create_table(
        "tracklets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "clip_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clips.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("start_frame", sa.Integer(), nullable=False),
        sa.Column("end_frame", sa.Integer(), nullable=False),
        sa.Column("track_confidence", sa.Float(), nullable=True),
        sa.Column("team_label", sa.String(20), nullable=True),
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
    op.create_index("ix_tracklets_clip_id", "tracklets", ["clip_id"])

    # ── track_points ──────────────────────────────────────────────────────
    op.create_table(
        "track_points",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tracklet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracklets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("frame_number", sa.Integer(), nullable=False),
        sa.Column("field_x", sa.Float(), nullable=True),
        sa.Column("field_y", sa.Float(), nullable=True),
        sa.Column("bbox", postgresql.JSONB(), nullable=True),
        sa.Column("detection_confidence", sa.Float(), nullable=True),
    )
    op.create_index("ix_track_points_tracklet_id", "track_points", ["tracklet_id"])

    # ── events ────────────────────────────────────────────────────────────
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "clip_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clips.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("frame_number", sa.Integer(), nullable=True),
        sa.Column("timestamp_seconds", sa.Float(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "model_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("model_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_events_clip_id", "events", ["clip_id"])

    # ── labels ────────────────────────────────────────────────────────────
    op.create_table(
        "labels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "clip_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clips.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "tracklet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracklets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("label_type", sa.String(100), nullable=False),
        sa.Column("label_value", postgresql.JSONB(), nullable=False),
        sa.Column(
            "annotated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.String(20), nullable=False, server_default="human"),
        sa.Column("dataset_version", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_labels_clip_id", "labels", ["clip_id"])

    # ── coach_corrections ─────────────────────────────────────────────────
    op.create_table(
        "coach_corrections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "clip_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clips.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "correction_type",
            sa.Enum(
                "clip_boundary",
                "player_identity",
                "event_tag",
                "formation_tag",
                name="correction_type",
            ),
            nullable=False,
        ),
        sa.Column("original_value", postgresql.JSONB(), nullable=True),
        sa.Column("corrected_value", postgresql.JSONB(), nullable=False),
        sa.Column(
            "corrected_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("exported_as_label", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_coach_corrections_clip_id", "coach_corrections", ["clip_id"])

    # ── metrics ───────────────────────────────────────────────────────────
    op.create_table(
        "metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "clip_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clips.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_name", sa.String(255), nullable=False),
        sa.Column("metric_value", postgresql.JSONB(), nullable=False),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("is_suppressed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("suppression_reason", sa.Text(), nullable=True),
        sa.Column(
            "model_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("model_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "calibration_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("field_calibrations.id", ondelete="SET NULL"),
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
    op.create_index("ix_metrics_clip_id", "metrics", ["clip_id"])
    op.create_index("ix_metrics_metric_name", "metrics", ["metric_name"])


def downgrade() -> None:
    op.drop_table("metrics")
    op.drop_table("coach_corrections")
    op.drop_table("labels")
    op.drop_table("events")
    op.drop_table("track_points")
    op.drop_table("tracklets")

    op.drop_column("clips", "job_id")
    op.drop_column("clips", "calibration_version_id")
    op.drop_column("clips", "model_version_id")

    op.drop_table("field_calibrations")

    op.execute("DROP TYPE IF EXISTS correction_type")
