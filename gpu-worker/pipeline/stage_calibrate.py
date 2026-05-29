"""Stage 3 — Regime-aware field calibration (Issues #127, #138).

Replaces the original 4-corner stub homography with a real yard-line
calibration that branches on the capture regime detected at ingest
(Issue #126):

* **FIXED_SIDELINE** (game film) — the elevated camera is effectively
  bolted down, so a single homography is fit once on the cleanest frame and
  flagged ``is_game_anchor``. Same-session jobs can reuse the cached anchor;
  this stage produces it.
* **DRONE_FOLLOW / unknown** (practice film) — the operator pans/zooms, so
  the clip is calibrated per window. Nightly jobs additionally Kalman-smooth
  the per-window homographies and use chained-ECC drift (Issue #138) as the
  temporal-stability signal.

Shared math core (all pixel-only, single-camera, no GPS/IMU/SRT):
  white-paint detection → Hough → angle clustering → labeled yard-line
  correspondences → normalized DLT + RANSAC → 5-component confidence.

Coordinate system (NCAA template, see ``homography/field_template.py``):
  X: 0–100 yards (goal line to goal line)
  Y: -26.665 to +26.665 yards (south sideline to north sideline)

Output: a ``field_calibrations`` row with the homography, the blended
confidence, the five confidence sub-components, the per-regime diagnostics
(inlier_ratio, line_count, parallel_variance, temporal_drift), the Kalman
state, ``is_game_anchor``, and ``analytics_safe``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import structlog

from pipeline import backend, r2
from pipeline.homography import confidence_scorer as cs
from pipeline.homography import dlt_ransac, kalman_smoother
from pipeline.homography import yardline_keypoints as yk

log = structlog.get_logger(__name__)

CONFIDENCE_THRESHOLD = 0.75   # Issue #127 gate: analytics_safe at ≥ 0.75
RANSAC_THRESHOLD_PX = 3.0     # Issue #127 §7.1 re-projection threshold
SAMPLE_INTERVAL_S = 5.0
N_SAMPLE_FRAMES_FIXED = 6     # fixed camera: pick the single cleanest frame
N_SAMPLE_FRAMES_DRONE = 12    # drone: sample more for a per-window series

# Routing variants registered for the ``calibrate`` stage (model_router).
VARIANT_LITE = "calib-hough-dlt"          # same-session: Hough + DLT, no Kalman
VARIANT_KALMAN = "calib-hough-dlt-kalman"  # nightly: + Kalman temporal smoothing

FIXED_SIDELINE = "fixed_sideline"
DRONE_FOLLOW = "drone_follow"
UNKNOWN = "unknown"


def run(
    video_id: str,
    input_uri: str,
    job_id: str,
    *,
    variant: str = VARIANT_KALMAN,
    capture_regime: str | None = None,
) -> dict[str, Any]:
    """Run Stage 3 for the given clip and return output artifacts.

    Args:
        capture_regime: regime from ingest (``fixed_sideline`` /
            ``drone_follow`` / ``unknown``). ``None`` is treated as
            ``unknown`` and uses the per-window drone path.
        variant: model-router variant. ``calib-hough-dlt-kalman`` enables
            Kalman smoothing of the per-window series (nightly); the lite
            variant skips it (same-session).
    """
    regime = capture_regime or UNKNOWN
    log.info(
        "stage_calibrate_start",
        video_id=video_id,
        capture_regime=regime,
        variant=variant,
    )

    r2_key = _uri_to_r2_key(input_uri)
    video_path = r2.download_to_temp(r2_key)
    try:
        return _calibrate(video_id, video_path, job_id, regime, variant)
    finally:
        video_path.unlink(missing_ok=True)


def _uri_to_r2_key(uri: str) -> str:
    if uri.startswith("r2://"):
        return "/".join(uri.split("/")[3:])
    return uri


def _calibrate(
    video_id: str,
    video_path: Path,
    job_id: str,
    regime: str,
    variant: str,
) -> dict[str, Any]:
    n_frames = N_SAMPLE_FRAMES_FIXED if regime == FIXED_SIDELINE else N_SAMPLE_FRAMES_DRONE
    frames = _sample_frames(video_path, n_frames)
    if not frames:
        return _persist_and_return(
            video_id, job_id,
            homography=None, breakdown=None, regime=regime,
            inlier_ratio=0.0, line_count=0, parallel_variance=None,
            temporal_drift=None, kalman_state=None, is_game_anchor=False,
            reason_codes=["no_frames"],
        )

    if regime == FIXED_SIDELINE:
        return _calibrate_fixed_sideline(video_id, job_id, frames, regime)
    return _calibrate_drone(video_id, job_id, frames, regime, variant)


# ── FIXED_SIDELINE: one anchor homography for the whole clip ───────────────────


def _calibrate_fixed_sideline(
    video_id: str, job_id: str, frames: list[np.ndarray], regime: str
) -> dict[str, Any]:
    """Fit a single homography on the cleanest frame and flag it as the anchor."""
    best = _best_frame_fit(frames)
    if best is None:
        return _persist_and_return(
            video_id, job_id,
            homography=None, breakdown=None, regime=regime,
            inlier_ratio=0.0, line_count=0, parallel_variance=None,
            temporal_drift=None, kalman_state=None, is_game_anchor=False,
            reason_codes=["no_calibration"],
        )
    H, kp, inlier_ratio, reason_codes = best
    parallel = cs.parallel_line_score(kp.yardline_angles)
    # A single bolted-down anchor has no temporal drift by construction.
    breakdown = cs.compute_confidence(
        inlier_ratio=inlier_ratio,
        line_count=kp.line_count,
        parallel_line_score=parallel,
        temporal_stability=cs.temporal_stability_from_drift(0.0),
        field_coverage=kp.field_coverage,
    )
    return _persist_and_return(
        video_id, job_id,
        homography=H, breakdown=breakdown, regime=regime,
        inlier_ratio=inlier_ratio, line_count=kp.line_count,
        parallel_variance=_variance(kp.yardline_angles),
        temporal_drift=0.0, kalman_state=None, is_game_anchor=True,
        reason_codes=reason_codes,
    )


# ── DRONE_FOLLOW / unknown: per-window series + optional Kalman ────────────────


def _calibrate_drone(
    video_id: str, job_id: str, frames: list[np.ndarray], regime: str, variant: str
) -> dict[str, Any]:
    """Per-window calibration; nightly variant adds Kalman temporal smoothing."""
    fits: list[tuple[np.ndarray, yk.KeypointResult, float] | None] = []
    for frame in frames:
        best = _best_frame_fit([frame])
        if best is None:
            fits.append(None)
            continue
        H, kp, inlier_ratio, _ = best
        fits.append((H, kp, inlier_ratio))

    valid = [f for f in fits if f is not None]
    if not valid:
        return _persist_and_return(
            video_id, job_id,
            homography=None, breakdown=None, regime=regime,
            inlier_ratio=0.0, line_count=0, parallel_variance=None,
            temporal_drift=None, kalman_state=None, is_game_anchor=False,
            reason_codes=["no_calibration"],
        )

    homographies = [f[0] for f in valid]
    confidences = [f[2] for f in valid]
    # Temporal drift = mean pairwise re-projection gap (px) between
    # consecutive per-window homographies over the frame corners.
    # Low drift ⇒ stable.
    temporal_drift = _series_drift(homographies, frames[0].shape[:2])
    temporal_stability = cs.temporal_stability_from_drift(temporal_drift)

    kalman_state: list[float] | None = None
    chosen_H = homographies[len(homographies) // 2]  # median-index window
    use_kalman = variant == VARIANT_KALMAN
    if use_kalman and len(homographies) >= 2:
        kf = kalman_smoother.HomographyKalman(
            sigma_q=kalman_smoother.process_noise_for_regime(regime)
        )
        smoothed = None
        for H, conf in zip(homographies, confidences):
            smoothed = kf.update(H, conf)
        if smoothed is not None:
            chosen_H = smoothed
        kalman_state = kf.state_vector()

    # Representative diagnostics from the strongest window.
    best_idx = int(np.argmax(confidences))
    best_kp = valid[best_idx][1]
    best_inlier = valid[best_idx][2]
    parallel = cs.parallel_line_score(best_kp.yardline_angles)
    breakdown = cs.compute_confidence(
        inlier_ratio=best_inlier,
        line_count=best_kp.line_count,
        parallel_line_score=parallel,
        temporal_stability=temporal_stability,
        field_coverage=best_kp.field_coverage,
    )
    return _persist_and_return(
        video_id, job_id,
        homography=chosen_H, breakdown=breakdown, regime=regime,
        inlier_ratio=best_inlier, line_count=best_kp.line_count,
        parallel_variance=_variance(best_kp.yardline_angles),
        temporal_drift=temporal_drift, kalman_state=kalman_state,
        is_game_anchor=False, reason_codes=list(best_kp.reason_codes),
    )


# ── Shared single-frame fit ────────────────────────────────────────────────────


def _best_frame_fit(
    frames: list[np.ndarray],
) -> tuple[np.ndarray, yk.KeypointResult, float, list[str]] | None:
    """Detect keypoints + fit a RANSAC homography on the best of ``frames``.

    Returns ``(H, KeypointResult, inlier_ratio, reason_codes)`` for the frame
    that yields the most inliers, or ``None`` if no frame produces a fit.
    """
    best: tuple[np.ndarray, yk.KeypointResult, float, list[str]] | None = None
    best_inliers = -1
    for frame in frames:
        kp = yk.detect_keypoints(frame)
        if not kp.has_enough():
            continue
        H, mask = dlt_ransac.ransac_homography(
            kp.src_pts, kp.dst_pts, threshold=RANSAC_THRESHOLD_PX
        )
        if H is None:
            continue
        n_in = int(np.count_nonzero(mask))
        inlier_ratio = n_in / max(len(mask), 1)
        if n_in > best_inliers:
            best_inliers = n_in
            reason_codes = list(kp.reason_codes)
            if inlier_ratio < 0.5:
                reason_codes.append("low_inlier_ratio")
            best = (H, kp, inlier_ratio, reason_codes)
    return best


# ── Helpers ─────────────────────────────────────────────────────────────────


def _series_drift(homographies: list[np.ndarray], shape: tuple[int, int]) -> float:
    """Mean pairwise re-projection gap (px) across consecutive homographies."""
    if len(homographies) < 2:
        return 0.0
    h, w = shape
    corners = np.array(
        [[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float64
    )
    gaps: list[float] = []
    for a, b in zip(homographies[:-1], homographies[1:]):
        gaps.append(_reproj_gap(a, b, corners))
    return float(np.mean(gaps)) if gaps else 0.0


def _reproj_gap(H_a: np.ndarray, H_b: np.ndarray, pts: np.ndarray) -> float:
    homog = np.hstack([pts, np.ones((len(pts), 1))])
    try:
        inv_b = np.linalg.inv(H_b)
    except np.linalg.LinAlgError:
        inv_b = np.linalg.pinv(H_b)
    rel = inv_b @ H_a
    warped = (rel @ homog.T).T
    denom = np.where(np.abs(warped[:, 2:3]) < 1e-12, 1e-12, warped[:, 2:3])
    warped_xy = warped[:, :2] / denom
    return float(np.sqrt(((warped_xy - pts) ** 2).sum(axis=1)).mean())


def _variance(angles: list[float]) -> float | None:
    if len(angles) < 2:
        return None
    return float(np.var([float(a) for a in angles]))


def _sample_frames(video_path: Path, n: int) -> list[np.ndarray]:
    """Extract up to ``n`` evenly spaced BGR frames; empty list on failure."""
    try:
        import cv2
    except Exception:
        return []
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        duration = total / fps if fps > 0 else 0.0
        if total <= 0 or duration <= 0:
            return []
        times = np.linspace(
            0.05 * duration, 0.95 * duration, num=max(1, n), endpoint=True
        )
        frames: list[np.ndarray] = []
        for t in times:
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
            ok, frame = cap.read()
            if ok and frame is not None:
                frames.append(frame)
        return frames
    finally:
        cap.release()


def _persist_and_return(
    video_id: str,
    job_id: str,
    *,
    homography: np.ndarray | None,
    breakdown: cs.ConfidenceBreakdown | None,
    regime: str,
    inlier_ratio: float,
    line_count: int,
    parallel_variance: float | None,
    temporal_drift: float | None,
    kalman_state: list[float] | None,
    is_game_anchor: bool,
    reason_codes: list[str],
) -> dict[str, Any]:
    """Write the calibration record and return the stage output artifacts."""
    confidence = breakdown.confidence if breakdown is not None else 0.0
    components = breakdown.as_dict() if breakdown is not None else {}
    # Disqualifying reason codes block analytics regardless of score.
    blocking = {
        "no_frames", "no_calibration", "cv2_unavailable",
        "insufficient_lines", "insufficient_structured_lines",
        "insufficient_yard_lines", "insufficient_intersections",
    }
    has_blocking = any(rc in blocking for rc in reason_codes)
    analytics_safe = (confidence >= CONFIDENCE_THRESHOLD) and not has_blocking

    homography_list = (
        [float(v) for v in np.asarray(homography, dtype=np.float64).flatten()]
        if homography is not None
        else None
    )
    calibration_points: dict[str, Any] = {
        "capture_regime": regime,
        "confidence_components": components,
    }

    try:
        backend.create_calibration(
            video_id,
            homography=homography_list,
            confidence=float(confidence),
            confidence_threshold=CONFIDENCE_THRESHOLD,
            analytics_safe=analytics_safe,
            reason_codes=reason_codes or None,
            calibration_points=calibration_points,
            inlier_ratio=float(inlier_ratio),
            line_count=int(line_count),
            parallel_variance=parallel_variance,
            temporal_drift=temporal_drift,
            kalman_state=kalman_state,
            is_game_anchor=is_game_anchor,
            job_id=job_id,
        )
    except Exception as exc:
        log.error("write_calibration_failed", video_id=video_id, error=str(exc))

    log.info(
        "stage_calibrate_done",
        video_id=video_id,
        capture_regime=regime,
        confidence=round(float(confidence), 4),
        analytics_safe=analytics_safe,
        is_game_anchor=is_game_anchor,
    )
    return {
        "analytics_safe": analytics_safe,
        "confidence": float(confidence),
        "capture_regime": regime,
        "confidence_components": components,
        "is_game_anchor": is_game_anchor,
        "reason_codes": reason_codes,
    }
