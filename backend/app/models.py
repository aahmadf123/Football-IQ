"""ORM models for Football-IQ.

Tables:
    users              — platform user accounts and roles
    players            — Toledo athlete roster
    videos             — raw uploaded video records
    clips              — per-play clip segments
    clip_players       — many-to-many: clips ↔ players
    processing_jobs    — async job tracking for the CV pipeline
    model_versions     — ML model lineage and promotion tracking
    field_calibrations — homography matrix + confidence for each video
    tracklets          — player track segments within a clip
    track_points       — individual (frame, x, y) observations in a tracklet
    events             — tagged game events within a clip
    labels             — ground-truth labels for model training
    coach_corrections  — human overrides of model outputs
    metrics            — computed analytics metrics linked to clips
    training_datasets  — versioned snapshots exported for model training
    active_learning_queue — prioritized samples for human relabeling
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.types import Vector

# ── Enumerations ──────────────────────────────────────────────────────────────


class UserRole(enum.StrEnum):
    admin = "admin"
    analyst = "analyst"
    coach = "coach"
    sportsperformance = "sportsperformance"
    player = "player"
    viewer = "viewer"


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class JobType(enum.StrEnum):
    ingest = "ingest"
    segment = "segment"
    calibrate = "calibrate"
    detect = "detect"
    track = "track"
    pose = "pose"
    labels = "labels"
    metrics = "metrics"
    render = "render"
    routes = "routes"
    coverage = "coverage"
    oline = "oline"
    self_scout = "self_scout"
    embeddings = "embeddings"


class ModelStage(enum.StrEnum):
    experimental = "experimental"
    staging = "staging"
    production = "production"
    retired = "retired"


class VideoStatus(enum.StrEnum):
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class CorrectionType(enum.StrEnum):
    clip_boundary = "clip_boundary"
    player_identity = "player_identity"
    event_tag = "event_tag"
    formation_tag = "formation_tag"
    route_tag = "route_tag"
    coverage_tag = "coverage_tag"
    personnel_tag = "personnel_tag"
    leverage_tag = "leverage_tag"
    effort_tag = "effort_tag"
    pose_biomechanics_tag = "pose_biomechanics_tag"


class ActiveLearningReason(enum.StrEnum):
    low_confidence = "low_confidence"
    uncertainty_sampling = "uncertainty_sampling"
    regression = "regression"
    hard_negative = "hard_negative"


class ActiveLearningStatus(enum.StrEnum):
    queued = "queued"
    in_review = "in_review"
    resolved = "resolved"


class AlertType(enum.StrEnum):
    bio_deviation = "bio_deviation"
    effort_anomaly = "effort_anomaly"
    formation_anomaly = "formation_anomaly"


class AlertSeverity(enum.StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


# ── Models ────────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False, default=UserRole.viewer
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Player(Base):
    __tablename__ = "players"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    jersey_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Link to platform account (optional — players may not have login)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User | None"] = relationship("User", foreign_keys=[user_id])
    clips: Mapped[list["Clip"]] = relationship(
        "Clip", secondary="clip_players", back_populates="players"
    )


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, name="video_status"), nullable=False, default=VideoStatus.uploaded
    )
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    codec: Mapped[str | None] = mapped_column(String(50), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    uploader: Mapped["User | None"] = relationship("User", foreign_keys=[uploaded_by])
    clips: Mapped[list["Clip"]] = relationship("Clip", back_populates="video")
    jobs: Mapped[list["ProcessingJob"]] = relationship("ProcessingJob", back_populates="video")
    calibrations: Mapped[list["FieldCalibration"]] = relationship(
        "FieldCalibration", back_populates="video"
    )


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)  # seconds
    end_time: Mapped[float] = mapped_column(Float, nullable=False)  # seconds
    play_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Boundary source/confidence — set by Stage 2 (segmentation)
    # "model" = auto-proposed, "manual" = coach override
    boundary_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    boundary_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Version lineage
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True
    )
    calibration_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("field_calibrations.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_jobs.id", ondelete="SET NULL"), nullable=True
    )
    # ── Phase 2 columns ───────────────────────────────────────────────────
    personnel_grouping: Mapped[str | None] = mapped_column(String(20), nullable=True)
    down: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    field_zone: Mapped[str | None] = mapped_column(String(30), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    video: Mapped["Video"] = relationship("Video", back_populates="clips")
    reviewer: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by])
    players: Mapped[list["Player"]] = relationship(
        "Player", secondary="clip_players", back_populates="clips"
    )
    jobs: Mapped[list["ProcessingJob"]] = relationship(
        "ProcessingJob", back_populates="clip", foreign_keys="ProcessingJob.clip_id"
    )
    tracklets: Mapped[list["Tracklet"]] = relationship("Tracklet", back_populates="clip")
    events: Mapped[list["Event"]] = relationship("Event", back_populates="clip")
    metrics: Mapped[list["Metric"]] = relationship("Metric", back_populates="clip")
    corrections: Mapped[list["CoachCorrection"]] = relationship(
        "CoachCorrection", back_populates="clip"
    )


class ClipPlayer(Base):
    """Association table linking clips to the players appearing in them."""

    __tablename__ = "clip_players"

    clip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clips.id", ondelete="CASCADE"),
        primary_key=True,
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("players.id", ondelete="CASCADE"),
        primary_key=True,
    )


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="SET NULL"), nullable=True
    )
    clip_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clips.id", ondelete="SET NULL"), nullable=True
    )
    job_type: Mapped[JobType] = mapped_column(Enum(JobType, name="job_type"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), nullable=False, default=JobStatus.queued
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_artifacts: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output_artifacts: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    training_dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_datasets.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    video: Mapped["Video | None"] = relationship("Video", back_populates="jobs")
    clip: Mapped["Clip | None"] = relationship(
        "Clip", back_populates="jobs", foreign_keys=[clip_id]
    )
    model_version: Mapped["ModelVersion | None"] = relationship(
        "ModelVersion", back_populates="jobs"
    )


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_type: Mapped[str] = mapped_column(String(100), nullable=False)
    artifact_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    training_dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_datasets.id", ondelete="SET NULL"),
        nullable=True,
    )
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    promoted_stage: Mapped[ModelStage] = mapped_column(
        Enum(ModelStage, name="model_stage"),
        nullable=False,
        default=ModelStage.experimental,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    jobs: Mapped[list["ProcessingJob"]] = relationship(
        "ProcessingJob", back_populates="model_version"
    )


# ── Phase 1 tables ────────────────────────────────────────────────────────────


class FieldCalibration(Base):
    """Homography matrix mapping pixel coordinates to standardized field coords."""

    __tablename__ = "field_calibrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Homography matrix stored as a flat 9-element JSON array (row-major)
    homography: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    # 0.0–1.0 confidence from calibration pipeline; metrics are suppressed below threshold
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    # True when confidence >= threshold AND no disqualifying reason codes
    analytics_safe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Calibration failure/warning reason codes (e.g. ["low_contrast", "partial_field"])
    reason_codes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    # Key pixel-to-field point pairs used for calibration
    calibration_points: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    video: Mapped["Video"] = relationship("Video", back_populates="calibrations")


class Tracklet(Base):
    """A continuous track for a single player within a clip."""

    __tablename__ = "tracklets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    # Frame range within the clip
    start_frame: Mapped[int] = mapped_column(Integer, nullable=False)
    end_frame: Mapped[int] = mapped_column(Integer, nullable=False)
    # 0.0–1.0 track confidence from the tracking model
    track_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Team label ("home" / "away" / "unknown") for team-level tracking before identity
    team_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Phase 2: position group and side of ball for downstream analytics
    position_group: Mapped[str | None] = mapped_column(String(20), nullable=True)
    side_of_ball: Mapped[str | None] = mapped_column(String(10), nullable=True)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    clip: Mapped["Clip"] = relationship("Clip", back_populates="tracklets")
    player: Mapped["Player | None"] = relationship("Player")
    track_points: Mapped[list["TrackPoint"]] = relationship(
        "TrackPoint", back_populates="tracklet", order_by="TrackPoint.frame_number"
    )


class TrackPoint(Base):
    """A single (frame, x, y, bbox) observation within a tracklet."""

    __tablename__ = "track_points"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tracklet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracklets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    frame_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Field coordinates (yards) — null when calibration confidence is below threshold
    field_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    field_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Pixel bounding box [x1, y1, x2, y2]
    bbox: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    detection_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    tracklet: Mapped["Tracklet"] = relationship("Tracklet", back_populates="track_points")


class Event(Base):
    """A tagged game event (snap, motion, penalty, etc.) within a clip."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    frame_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    attributes: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    clip: Mapped["Clip"] = relationship("Clip", back_populates="events")
    creator: Mapped["User | None"] = relationship("User", foreign_keys=[created_by])


class Label(Base):
    """Ground-truth label for model training, linked to a clip or tracklet."""

    __tablename__ = "labels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clip_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clips.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tracklet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tracklets.id", ondelete="SET NULL"), nullable=True
    )
    label_type: Mapped[str] = mapped_column(String(100), nullable=False)
    label_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    annotated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Source: "model" (auto-label) or "human" (coach/analyst correction)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="human")
    dataset_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    training_dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_datasets.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    annotator: Mapped["User | None"] = relationship("User", foreign_keys=[annotated_by])


class CoachCorrection(Base):
    """A human override of a model output — becomes a training label."""

    __tablename__ = "coach_corrections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    correction_type: Mapped[CorrectionType] = mapped_column(
        Enum(CorrectionType, name="correction_type"), nullable=False
    )
    # Original model output before correction
    original_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Corrected value provided by the coach/analyst
    corrected_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    corrected_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    training_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Whether this correction has been exported as a training label
    exported_as_label: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    clip: Mapped["Clip"] = relationship("Clip", back_populates="corrections")
    corrector: Mapped["User"] = relationship("User", foreign_keys=[corrected_by])


class Metric(Base):
    """A computed analytics metric for a clip, always linked to its evidence."""

    __tablename__ = "metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Optional link to the specific player tracklet this metric belongs to
    tracklet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracklets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    metric_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Suppressed when field calibration confidence is below threshold
    is_suppressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suppression_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Head orientation and other experimental metrics: must be reviewed by a position
    # coach before being surfaced in player-facing views.
    experimental_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # True only after a position coach explicitly approves this metric for staff views
    analytics_safe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 0.0–1.0 model confidence for this specific metric value
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # URI to the evidence artifact (e.g. annotated frame, track overlay)
    evidence_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Full version lineage for every metric
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    calibration_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("field_calibrations.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    clip: Mapped["Clip"] = relationship("Clip", back_populates="metrics")
    tracklet: Mapped["Tracklet | None"] = relationship("Tracklet")
    reviews: Mapped[list["HeadOrientationReview"]] = relationship(
        "HeadOrientationReview", back_populates="metric"
    )


# ── Head orientation tables ────────────────────────────────────────────────────


class PoseKeypoints(Base):
    """Per-frame pose keypoints extracted from a player tracklet.

    Used to derive head-direction vectors (yaw angle) for QB progression reads,
    safety eye discipline, CB technique, and LB play-action response analysis.
    This is head-orientation estimation — not true eye tracking.
    """

    __tablename__ = "pose_keypoints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tracklet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracklets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    frame_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Full keypoint array: list of {name, x, y, confidence} dicts from RTMPose/ViTPose
    keypoints: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    # Derived head-direction yaw angle in degrees (0° = facing field direction)
    head_yaw_degrees: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 0.0–1.0 confidence based on keypoint visibility and head occlusion
    head_orientation_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Per-frame computed biomechanics angles (hip_flexion_degrees, torso_angle_degrees, etc.)
    biomechanics: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tracklet: Mapped["Tracklet"] = relationship("Tracklet")


class HeadOrientationReview(Base):
    """Position-coach review of an experimental head-orientation metric.

    A metric with experimental_flag=True must be approved by the relevant
    position coach before analytics_safe is set and staff views are unlocked.
    Player-facing views never show experimental metrics regardless of this status.
    """

    __tablename__ = "head_orientation_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metrics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # "approve" → sets metric.analytics_safe=True
    # "reject"  → metric stays suppressed; model team is notified
    # "flag"    → routed to model review queue
    review_action: Mapped[str] = mapped_column(String(20), nullable=False)
    # Position group this review applies to: "QB", "Safety", "CB", "LB"
    position_group: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    metric: Mapped["Metric"] = relationship("Metric", back_populates="reviews")
    reviewer: Mapped["User"] = relationship("User", foreign_keys=[reviewer_id])


# ── MLOps tables ───────────────────────────────────────────────────────────────


class TrainingDataset(Base):
    """Versioned snapshot of labels exported for a specific model scope."""

    __tablename__ = "training_datasets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    model_scope: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_label_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_correction_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    changelog: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Alert(Base):
    """Real-time coaching alert generated by anomaly detection.

    Governance:
      - Never shown to players.
      - Bio deviation alerts require pose pipeline active + coach-approved
        for the position group.
      - Every alert carries: confidence, clip_uri, player_id, timestamp,
        position_group.
    """

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True, index=True
    )
    clip_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clips.id", ondelete="SET NULL"), nullable=True, index=True
    )
    position_group: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    alert_type: Mapped[AlertType] = mapped_column(
        Enum(AlertType, name="alert_type"), nullable=False, index=True
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, name="alert_severity"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    metric_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    deviation_sd: Mapped[float | None] = mapped_column(Float, nullable=True)
    clip_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    player: Mapped["Player | None"] = relationship("Player")
    clip: Mapped["Clip | None"] = relationship("Clip")
    acknowledger: Mapped["User | None"] = relationship("User", foreign_keys=[acknowledged_by])


class ActiveLearningQueueItem(Base):
    """Queue entry for low-confidence, regressed, or hard-negative samples."""

    __tablename__ = "active_learning_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clip_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clips.id", ondelete="SET NULL"), nullable=True, index=True
    )
    label_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    queue_reason: Mapped[ActiveLearningReason] = mapped_column(
        Enum(ActiveLearningReason, name="active_learning_reason"),
        nullable=False,
    )
    priority_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    model_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    correction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("coach_corrections.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[ActiveLearningStatus] = mapped_column(
        Enum(ActiveLearningStatus, name="active_learning_status"),
        nullable=False,
        default=ActiveLearningStatus.queued,
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── Phase 3: learned play embeddings (Issue #8, design in #77) ────────────────


# Embedding-vector dimensions are pinned to the design doc shape so the
# pgvector column DDL, the fusion arithmetic in ``stage_embed`` and the
# similarity search router all agree on the same numbers without having to
# read schema metadata at runtime.
PLAY_EMBEDDING_DIM: int = 256
PLAY_EMBEDDING_VISUAL_DIM: int = 192
PLAY_EMBEDDING_STRUCTURED_DIM: int = 64


class PlayEmbedding(Base):
    """A learned 256-d embedding describing one play (or play sub-chunk).

    The primary retrievable vector is the fused ``vector`` column; the
    sub-embeddings are retained so the retrieval router can re-weight
    structured vs. visual contribution at query time without re-running
    the encoder. ``UNIQUE (clip_id, chunk_kind, model_version_id)`` is the
    upsert key.

    ``is_experimental`` defaults to True — embeddings only flip to False
    when a derived concept cluster has been reviewed and accepted by a
    coach via ``EmbeddingClusterProposal``.
    """

    __tablename__ = "playembeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="play")
    snap_anchor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Retrievable fused vector + retained sub-embeddings.
    vector: Mapped[list[float]] = mapped_column(Vector(PLAY_EMBEDDING_DIM), nullable=False)
    visual_vector: Mapped[list[float] | None] = mapped_column(
        Vector(PLAY_EMBEDDING_VISUAL_DIM), nullable=True
    )
    structured_vector: Mapped[list[float] | None] = mapped_column(
        Vector(PLAY_EMBEDDING_STRUCTURED_DIM), nullable=True
    )

    # Lineage
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    calibration_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("field_calibrations.id", ondelete="SET NULL"),
        nullable=True,
    )
    # IDs of ``labels`` rows that fed the structured encoder; lets us
    # target-re-embed only clips whose labels have since been corrected.
    source_label_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    used_sam_masks: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Quality / governance
    embedding_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_experimental: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    clip: Mapped["Clip"] = relationship("Clip")
    model_version: Mapped["ModelVersion"] = relationship("ModelVersion")


class EmbeddingClusterProposal(Base):
    """An experimental concept cluster surfaced from playembeddings.

    Produced by an offline clustering job over ``playembeddings.vector``
    (HDBSCAN in v1). Each row is one cluster; ``member_clip_ids`` lists
    the clips that fell into it.  Proposals are coach-reviewed: an
    ``accept`` flips affiliated embeddings to ``is_experimental=False``
    and is expected to be followed by ``coach_corrections`` rows for the
    member clips.  A ``reject`` hides the proposal from further review.

    All proposals carry ``status='pending'`` until reviewed, and nothing
    in this table is ever surfaced on production dashboards — it lives
    behind the coach review surface only.
    """

    __tablename__ = "embedding_cluster_proposals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Cluster discriminator — usually the HDBSCAN cluster label as a string,
    # so a single batch produces ``"0"``, ``"1"``, ... unique within the run.
    cluster_label: Mapped[str] = mapped_column(String(64), nullable=False)
    # Working name the discovery job assigned (e.g. "embedding_cluster_3");
    # coach renames it on accept.
    proposed_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    member_clip_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    # Cluster centroid in the same 256-d space as PlayEmbedding.vector.
    centroid: Mapped[list[float] | None] = mapped_column(Vector(PLAY_EMBEDDING_DIM), nullable=True)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cohesion_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Review workflow
    # status: "pending" | "accepted" | "rejected"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    # is_experimental stays True until an accept also exports it as a
    # coach correction; the search router relies on this flag to keep
    # cluster output out of production results.
    is_experimental: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # On accept, the name the coach chose for the concept (e.g. "mesh-like
    # RPO read"). Null while pending.
    accepted_label_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    model_version: Mapped["ModelVersion"] = relationship("ModelVersion")
    reviewer: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by])
