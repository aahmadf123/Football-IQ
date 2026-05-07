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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# ── Enumerations ──────────────────────────────────────────────────────────────


class UserRole(str, enum.Enum):
    admin = "admin"
    analyst = "analyst"
    coach = "coach"
    sportsperformance = "sportsperformance"
    player = "player"
    viewer = "viewer"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class JobType(str, enum.Enum):
    ingest = "ingest"
    segment = "segment"
    calibrate = "calibrate"
    detect = "detect"
    track = "track"
    pose = "pose"
    labels = "labels"
    metrics = "metrics"
    render = "render"


class ModelStage(str, enum.Enum):
    experimental = "experimental"
    staging = "staging"
    production = "production"
    retired = "retired"


class VideoStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class CorrectionType(str, enum.Enum):
    clip_boundary = "clip_boundary"
    player_identity = "player_identity"
    event_tag = "event_tag"
    formation_tag = "formation_tag"


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
    training_dataset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
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
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    metric_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Suppressed when field calibration confidence is below threshold
    is_suppressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suppression_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
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
