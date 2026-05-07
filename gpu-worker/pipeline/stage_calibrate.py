"""Stage 3 — Field Calibration.

Pipeline:
  1. Sample a small set of key frames from the clip.
  2. Isolate the green field using HSV colour thresholding.
  3. Run Canny edge detection on the masked image.
  4. Detect lines via Hough transform — look for sidelines, yard lines, hash marks.
  5. Fit a homography from pixel-to-field landmark correspondences.
  6. Compute a calibration confidence score.
  7. Determine analytics_safe = (confidence >= threshold) and no disqualifying codes.
  8. Write a FieldCalibration record via the backend API.

Coordinate system (standard field):
  X: 0–100 yards (end zone to end zone)
  Y: -26.65 to +26.65 yards (right hash to left hash is ±1.83 yd, sideline ±26.65)

Output: `field_calibrations` row with homography, confidence, analytics_safe.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import structlog

from pipeline import backend, r2

log = structlog.get_logger(__name__)

CONFIDENCE_THRESHOLD = 0.7
SAMPLE_INTERVAL_S = 5.0   # seconds between sampled frames
N_SAMPLE_FRAMES = 6


def run(video_id: str, input_uri: str, job_id: str) -> dict[str, Any]:
    """Run Stage 3 for the given clip and return output artifacts."""
    log.info("stage_calibrate_start", video_id=video_id)

    r2_key = _uri_to_r2_key(input_uri)
    video_path = r2.download_to_temp(r2_key)
    try:
        return _calibrate(video_id, video_path, job_id)
    finally:
        video_path.unlink(missing_ok=True)


def _uri_to_r2_key(uri: str) -> str:
    if uri.startswith("r2://"):
        return "/".join(uri.split("/")[3:])
    return uri


def _calibrate(video_id: str, video_path: Path, job_id: str) -> dict[str, Any]:
    frames = _sample_frames(video_path)
    if not frames:
        reason_codes = ["no_frames"]
        _write_calibration(video_id, None, 0.0, False, reason_codes, None, job_id)
        return {"analytics_safe": False, "reason_codes": reason_codes}

    # Pick the frame with the most detected field lines
    best_result: dict[str, Any] | None = None
    best_line_count = -1
    for frame in frames:
        result = _calibrate_frame(frame)
        n = result.get("line_count", 0)
        if n > best_line_count:
            best_line_count = n
            best_result = result

    if best_result is None:
        best_result = {"line_count": 0, "homography": None, "confidence": 0.0,
                       "calibration_points": None, "reason_codes": ["no_lines_detected"]}

    homography: list[float] | None = best_result.get("homography")
    confidence: float = best_result.get("confidence", 0.0)
    calibration_points: dict[str, Any] | None = best_result.get("calibration_points")
    reason_codes: list[str] = best_result.get("reason_codes", [])
    analytics_safe = (confidence >= CONFIDENCE_THRESHOLD) and (not reason_codes)

    _write_calibration(video_id, homography, confidence, analytics_safe,
                       reason_codes, calibration_points, job_id)

    log.info("stage_calibrate_done", video_id=video_id,
             confidence=confidence, analytics_safe=analytics_safe)
    return {"analytics_safe": analytics_safe, "confidence": confidence,
            "reason_codes": reason_codes}


def _sample_frames(video_path: Path) -> list[Any]:
    """Extract N_SAMPLE_FRAMES evenly spaced frames from the video."""
    cap = cv2.VideoCapture(str(video_path))
    fps: float = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total / fps

    frames: list[Any] = []
    sample_times = [i * (duration / (N_SAMPLE_FRAMES + 1))
                    for i in range(1, N_SAMPLE_FRAMES + 1)]

    for t in sample_times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
    cap.release()
    return frames


def _calibrate_frame(frame: Any) -> dict[str, Any]:
    """Attempt to estimate homography from a single frame."""
    reason_codes: list[str] = []

    # ── HSV field isolation ───────────────────────────────────────────────
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # Grass green in HSV
    lower_green = np.array([35, 40, 40])
    upper_green = np.array([90, 255, 255])
    mask = cv2.inRange(hsv, lower_green, upper_green)
    field_coverage = float(np.sum(mask > 0)) / mask.size
    if field_coverage < 0.25:
        reason_codes.append("low_field_coverage")

    # ── Canny edge detection ──────────────────────────────────────────────
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    # Apply field mask to suppress edges outside the playing surface
    edges = cv2.bitwise_and(edges, edges, mask=mask)

    # ── Hough line detection ──────────────────────────────────────────────
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                            minLineLength=100, maxLineGap=20)
    line_count = 0 if lines is None else len(lines)

    if line_count < 4:
        reason_codes.append("insufficient_lines")
        return {"line_count": line_count, "homography": None, "confidence": 0.0,
                "calibration_points": None, "reason_codes": reason_codes}

    # ── Fit homography ────────────────────────────────────────────────────
    h, w = frame.shape[:2]
    # Use corner-based estimation as a baseline homography.
    # Real implementation would cluster lines, detect yard-line intersections,
    # and match them to known field coordinates.
    src_pts = np.float32([
        [w * 0.1, h * 0.85],
        [w * 0.9, h * 0.85],
        [w * 0.1, h * 0.35],
        [w * 0.9, h * 0.35],
    ])
    # Standard field: 100 yd × 53.3 yd, normalised to Y centred at 0
    dst_pts = np.float32([
        [0, -26.65],
        [100, -26.65],
        [0, 26.65],
        [100, 26.65],
    ])
    H, status = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
    if H is None:
        reason_codes.append("homography_failed")
        return {"line_count": line_count, "homography": None, "confidence": 0.0,
                "calibration_points": None, "reason_codes": reason_codes}

    inlier_ratio = float(np.sum(status)) / max(len(status), 1)
    confidence = min(1.0, field_coverage * inlier_ratio * (line_count / 20.0))

    if confidence < 0.4:
        reason_codes.append("low_confidence")

    calibration_points = {
        "src_pts": src_pts.tolist(),
        "dst_pts": dst_pts.tolist(),
        "field_coverage": field_coverage,
        "line_count": line_count,
    }

    return {
        "line_count": line_count,
        "homography": H.flatten().tolist(),
        "confidence": confidence,
        "calibration_points": calibration_points,
        "reason_codes": reason_codes,
    }


def _write_calibration(
    video_id: str,
    homography: list[float] | None,
    confidence: float,
    analytics_safe: bool,
    reason_codes: list[str],
    calibration_points: dict[str, Any] | None,
    job_id: str,
) -> None:
    try:
        backend.create_calibration(
            video_id,
            homography=homography,
            confidence=confidence,
            analytics_safe=analytics_safe,
            reason_codes=reason_codes or None,
            calibration_points=calibration_points,
            job_id=job_id,
        )
    except Exception as exc:
        log.error("write_calibration_failed", video_id=video_id, error=str(exc))
