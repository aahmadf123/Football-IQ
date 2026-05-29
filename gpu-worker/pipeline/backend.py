"""Backend API helpers for the GPU worker pipeline.

Thin synchronous wrappers around the backend REST API so each pipeline stage
can write results without knowing the HTTP details.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

BACKEND_API_URL = os.environ.get("BACKEND_API_URL", "")


def _client() -> httpx.Client:
    return httpx.Client(base_url=BACKEND_API_URL, timeout=30)


# ── Job status ────────────────────────────────────────────────────────────────


def update_job_status(
    job_id: str,
    status: str,
    error_message: str | None = None,
    output_artifacts: dict[str, Any] | None = None,
) -> None:
    """PATCH /api/v1/jobs/{job_id} to update status + optional artifacts."""
    if not BACKEND_API_URL:
        return
    payload: dict[str, Any] = {"status": status}
    if error_message:
        payload["error_message"] = error_message
    if output_artifacts:
        payload["output_artifacts"] = output_artifacts
    try:
        with _client() as c:
            c.patch(f"/api/v1/jobs/{job_id}", json=payload)
    except Exception as exc:
        log.warning("backend_job_update_failed", job_id=job_id, error=str(exc))


# ── Video ─────────────────────────────────────────────────────────────────────


def patch_video_status(
    video_id: str,
    status: str,
    *,
    duration_seconds: float | None = None,
    fps: float | None = None,
    width: int | None = None,
    height: int | None = None,
    codec: str | None = None,
    capture_regime: str | None = None,
    regime_confidence: float | None = None,
) -> None:
    """PATCH /api/v1/videos/{video_id}/status with probed metadata."""
    payload: dict[str, Any] = {"status": status}
    if duration_seconds is not None:
        payload["duration_seconds"] = duration_seconds
    if fps is not None:
        payload["fps"] = fps
    if width is not None:
        payload["width"] = width
    if height is not None:
        payload["height"] = height
    if codec is not None:
        payload["codec"] = codec
    if capture_regime is not None:
        payload["capture_regime"] = capture_regime
    if regime_confidence is not None:
        payload["regime_confidence"] = regime_confidence
    try:
        with _client() as c:
            c.patch(f"/api/v1/videos/{video_id}/status", json=payload)
    except Exception as exc:
        log.warning("backend_video_patch_failed", video_id=video_id, error=str(exc))


# ── Clips ─────────────────────────────────────────────────────────────────────


def create_clip(
    video_id: str,
    start_time: float,
    end_time: float,
    *,
    boundary_source: str = "model",
    boundary_confidence: float | None = None,
    play_number: int | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """POST /api/v1/videos/{video_id}/clips and return the created clip dict."""
    payload: dict[str, Any] = {
        "start_time": start_time,
        "end_time": end_time,
        "boundary_source": boundary_source,
    }
    if boundary_confidence is not None:
        payload["boundary_confidence"] = boundary_confidence
    if play_number is not None:
        payload["play_number"] = play_number
    if job_id is not None:
        payload["job_id"] = job_id
    with _client() as c:
        resp = c.post(f"/api/v1/videos/{video_id}/clips", json=payload)
        resp.raise_for_status()
        return dict(resp.json())


# ── Calibrations ──────────────────────────────────────────────────────────────


def create_calibration(
    video_id: str,
    homography: list[float] | None,
    confidence: float,
    *,
    confidence_threshold: float | None = None,
    analytics_safe: bool = False,
    reason_codes: list[str] | None = None,
    calibration_points: dict[str, Any] | None = None,
    inlier_ratio: float | None = None,
    line_count: int | None = None,
    parallel_variance: float | None = None,
    temporal_drift: float | None = None,
    kalman_state: list[float] | None = None,
    is_game_anchor: bool = False,
    job_id: str | None = None,
) -> dict[str, Any]:
    """POST /api/v1/calibrations and return the created calibration dict."""
    payload: dict[str, Any] = {
        "video_id": video_id,
        "confidence": confidence,
        "analytics_safe": analytics_safe,
        "is_game_anchor": is_game_anchor,
    }
    if homography is not None:
        payload["homography"] = homography
    if confidence_threshold is not None:
        payload["confidence_threshold"] = confidence_threshold
    if reason_codes is not None:
        payload["reason_codes"] = reason_codes
    if calibration_points is not None:
        payload["calibration_points"] = calibration_points
    if inlier_ratio is not None:
        payload["inlier_ratio"] = inlier_ratio
    if line_count is not None:
        payload["line_count"] = line_count
    if parallel_variance is not None:
        payload["parallel_variance"] = parallel_variance
    if temporal_drift is not None:
        payload["temporal_drift"] = temporal_drift
    if kalman_state is not None:
        payload["kalman_state"] = kalman_state
    if job_id is not None:
        payload["job_id"] = job_id
    with _client() as c:
        resp = c.post("/api/v1/calibrations", json=payload)
        resp.raise_for_status()
        return dict(resp.json())


# ── Tracklets ─────────────────────────────────────────────────────────────────


def create_tracklet(
    clip_id: str,
    start_frame: int,
    end_frame: int,
    track_points: list[dict[str, Any]],
    *,
    track_confidence: float | None = None,
    team_label: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """POST /api/v1/tracklets and return the created tracklet dict."""
    payload: dict[str, Any] = {
        "clip_id": clip_id,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "track_points": track_points,
    }
    if track_confidence is not None:
        payload["track_confidence"] = track_confidence
    if team_label is not None:
        payload["team_label"] = team_label
    if job_id is not None:
        payload["job_id"] = job_id
    with _client() as c:
        resp = c.post("/api/v1/tracklets", json=payload)
        resp.raise_for_status()
        return dict(resp.json())


# ── Events ────────────────────────────────────────────────────────────────────


def create_event(
    clip_id: str,
    event_type: str,
    *,
    frame_number: int | None = None,
    timestamp_seconds: float | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST /api/v1/events and return the created event dict."""
    payload: dict[str, Any] = {"clip_id": clip_id, "event_type": event_type}
    if frame_number is not None:
        payload["frame_number"] = frame_number
    if timestamp_seconds is not None:
        payload["timestamp_seconds"] = timestamp_seconds
    if attributes is not None:
        payload["attributes"] = attributes
    with _client() as c:
        resp = c.post("/api/v1/events", json=payload)
        resp.raise_for_status()
        return dict(resp.json())


# ── Labels ────────────────────────────────────────────────────────────────────


def create_label(
    label_type: str,
    label_value: dict[str, Any],
    *,
    clip_id: str | None = None,
    tracklet_id: str | None = None,
    source: str = "model",
) -> dict[str, Any]:
    """POST /api/v1/labels and return the created label dict."""
    payload: dict[str, Any] = {
        "label_type": label_type,
        "label_value": label_value,
        "source": source,
    }
    if clip_id is not None:
        payload["clip_id"] = clip_id
    if tracklet_id is not None:
        payload["tracklet_id"] = tracklet_id
    with _client() as c:
        resp = c.post("/api/v1/labels", json=payload)
        resp.raise_for_status()
        return dict(resp.json())


# ── Metrics (Phase 2 + Pose-Lite) ────────────────────────────────────────────


def create_metric(
    clip_id: str,
    metric_name: str,
    metric_value: dict[str, Any],
    *,
    tracklet_id: str | None = None,
    unit: str | None = None,
    is_suppressed: bool = False,
    suppression_reason: str | None = None,
    experimental_flag: bool = False,
    analytics_safe: bool = False,
    confidence: float | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """POST /api/v1/metrics and return the created metric dict."""
    payload: dict[str, Any] = {
        "clip_id": clip_id,
        "metric_name": metric_name,
        "metric_value": metric_value,
    }
    if tracklet_id is not None:
        payload["tracklet_id"] = tracklet_id
    if unit is not None:
        payload["unit"] = unit
    if is_suppressed:
        payload["is_suppressed"] = is_suppressed
    if suppression_reason is not None:
        payload["suppression_reason"] = suppression_reason
    if experimental_flag:
        payload["experimental_flag"] = experimental_flag
    if analytics_safe:
        payload["analytics_safe"] = analytics_safe
    if confidence is not None:
        payload["confidence"] = confidence
    if job_id is not None:
        payload["job_id"] = job_id
    with _client() as c:
        resp = c.post("/api/v1/metrics", json=payload)
        resp.raise_for_status()
        return dict(resp.json())


# ── Pose Keypoints (Phase 2 / Issue #6) ──────────────────────────────────────


def create_pose_keypoints(
    tracklet_id: str | None,
    frame_number: int,
    keypoints: list[dict[str, Any]],
    *,
    head_yaw_degrees: float | None = None,
    head_orientation_confidence: float | None = None,
    biomechanics: dict[str, Any] | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """POST /api/v1/pose/keypoints and return the created row dict."""
    payload: dict[str, Any] = {
        "frame_number": frame_number,
        "keypoints": keypoints,
    }
    if tracklet_id is not None:
        payload["tracklet_id"] = tracklet_id
    if head_yaw_degrees is not None:
        payload["head_yaw_degrees"] = head_yaw_degrees
    if head_orientation_confidence is not None:
        payload["head_orientation_confidence"] = head_orientation_confidence
    if biomechanics is not None:
        payload["biomechanics"] = biomechanics
    if job_id is not None:
        payload["job_id"] = job_id
    with _client() as c:
        resp = c.post("/api/v1/pose/keypoints", json=payload)
        resp.raise_for_status()
        return dict(resp.json())


# ── Play embeddings (Phase 3 / Issue #8) ─────────────────────────────────────


def create_play_embedding(
    clip_id: str,
    model_version_id: str,
    vector: list[float],
    *,
    visual_vector: list[float] | None = None,
    structured_vector: list[float] | None = None,
    chunk_kind: str = "play",
    snap_anchor: bool = True,
    used_sam_masks: bool = False,
    embedding_confidence: float | None = None,
    source_label_ids: list[str] | None = None,
    calibration_version_id: str | None = None,
    is_experimental: bool = True,
    job_id: str | None = None,
) -> dict[str, Any]:
    """POST /api/v1/embeddings/play and return the created embedding dict."""
    payload: dict[str, Any] = {
        "clip_id": clip_id,
        "model_version_id": model_version_id,
        "vector": vector,
        "chunk_kind": chunk_kind,
        "snap_anchor": snap_anchor,
        "used_sam_masks": used_sam_masks,
        "is_experimental": is_experimental,
    }
    if visual_vector is not None:
        payload["visual_vector"] = visual_vector
    if structured_vector is not None:
        payload["structured_vector"] = structured_vector
    if embedding_confidence is not None:
        payload["embedding_confidence"] = embedding_confidence
    if source_label_ids:
        payload["source_label_ids"] = source_label_ids
    if calibration_version_id is not None:
        payload["calibration_version_id"] = calibration_version_id
    if job_id is not None:
        payload["job_id"] = job_id
    with _client() as c:
        resp = c.post("/api/v1/embeddings/play", json=payload)
        resp.raise_for_status()
        return dict(resp.json())


# ── Self-Scout (Phase 2) ─────────────────────────────────────────────────────


def fetch_clips_with_labels(
    video_id: str | None = None,
    limit: int = 500,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Fetch clips and their labels for self-scout analysis."""
    if limit <= 0:
        return [], {}

    clips: list[dict[str, Any]] = []
    with _client() as c:
        if video_id:
            clip_offset = 0
            while len(clips) < limit:
                remaining = limit - len(clips)
                clips_resp = c.get(
                    f"/api/v1/videos/{video_id}/clips",
                    params={"limit": min(500, remaining), "offset": clip_offset},
                )
                clips_resp.raise_for_status()
                batch: list[dict[str, Any]] = clips_resp.json()
                if not batch:
                    break
                clips.extend(batch[:remaining])
                if len(batch) < min(500, remaining):
                    break
                clip_offset += len(batch)
        else:
            video_offset = 0
            video_page_limit = 200
            while len(clips) < limit:
                videos_resp = c.get(
                    "/api/v1/videos",
                    params={"limit": video_page_limit, "offset": video_offset},
                )
                videos_resp.raise_for_status()
                videos: list[dict[str, Any]] = videos_resp.json()
                if not videos:
                    break

                for video in videos:
                    vid = video.get("id")
                    if not vid:
                        continue
                    remaining = limit - len(clips)
                    clips_resp = c.get(
                        f"/api/v1/videos/{vid}/clips",
                        params={"limit": min(500, remaining), "offset": 0},
                    )
                    clips_resp.raise_for_status()
                    batch = clips_resp.json()
                    if batch:
                        clips.extend(batch[:remaining])
                    if len(clips) >= limit:
                        break

                if len(videos) < video_page_limit:
                    break
                video_offset += len(videos)

        labels_by_clip: dict[str, list[dict[str, Any]]] = {}
        for clip in clips:
            clip_id = clip.get("id", "")
            try:
                labels_resp = c.get("/api/v1/labels", params={"clip_id": clip_id})
                labels_resp.raise_for_status()
                labels_by_clip[clip_id] = labels_resp.json()
            except Exception:
                labels_by_clip[clip_id] = []

    return clips, labels_by_clip
