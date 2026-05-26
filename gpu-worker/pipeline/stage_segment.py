"""Stage 2 — Play Segmentation.

Heuristic approach:
  - Compute per-frame mean optical-flow magnitude with OpenCV.
  - Identify "quiet" periods (low motion) as candidate play breaks.
  - Cluster consecutive quiet frames into gap regions.
  - Treat the midpoint of each gap as a boundary.
  - Post each proposed clip to the backend via the clips API.

All boundaries are tagged boundary_source="model" with a boundary_confidence.
Manual overrides are handled by coaches via the PATCH /api/v1/clips/{id} endpoint.

Output: `clips` rows for each proposed play segment.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import structlog

from pipeline import backend, r2

log = structlog.get_logger(__name__)

# Tuning knobs
SAMPLE_FPS = 2          # frames per second to sample for motion
QUIET_THRESHOLD = 1.5   # mean flow magnitude below which a frame is "quiet"
MIN_QUIET_FRAMES = 4    # need at least this many consecutive quiet frames to form a gap
MIN_PLAY_DURATION = 3.0  # seconds — ignore very short segments


def run(video_id: str, input_uri: str, job_id: str) -> dict[str, Any]:
    """Run Stage 2: propose clip boundaries and write them to the backend."""
    log.info("stage_segment_start", video_id=video_id)

    r2_key = _uri_to_r2_key(input_uri)
    video_path = r2.download_to_temp(r2_key)
    try:
        return _segment(video_id, video_path, job_id)
    finally:
        video_path.unlink(missing_ok=True)


def _uri_to_r2_key(uri: str) -> str:
    if uri.startswith("r2://"):
        return "/".join(uri.split("/")[3:])
    return uri


def _segment(video_id: str, video_path: Path, job_id: str) -> dict[str, Any]:
    from pipeline.hwaccel import nvdec_video_capture

    cap = nvdec_video_capture(video_path)
    native_fps: float = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / native_fps

    step = max(1, int(native_fps / SAMPLE_FPS))
    quiet_frames: list[int] = []
    prev_gray: "np.ndarray | None" = None

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
                )
                mag = float(np.mean(np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)))
                if mag < QUIET_THRESHOLD:
                    quiet_frames.append(frame_idx)
            prev_gray = gray
        frame_idx += 1
    cap.release()

    boundaries = _find_boundaries(quiet_frames, native_fps)
    clips = _write_clips(video_id, boundaries, duration, native_fps, job_id)

    log.info("stage_segment_done", video_id=video_id, clip_count=len(clips))
    return {"clip_count": len(clips), "clip_ids": [c["id"] for c in clips]}


def _find_boundaries(quiet_frames: list[int], fps: float) -> list[float]:
    """Convert list of quiet frame indices into boundary timestamps (seconds)."""
    if not quiet_frames:
        return []

    boundaries: list[float] = []
    group_start = quiet_frames[0]
    group_end = quiet_frames[0]

    for f in quiet_frames[1:]:
        if f - group_end <= int(fps):  # consecutive within 1 s
            group_end = f
        else:
            if (group_end - group_start) >= MIN_QUIET_FRAMES:
                mid = (group_start + group_end) // 2
                boundaries.append(mid / fps)
            group_start = f
            group_end = f

    if (group_end - group_start) >= MIN_QUIET_FRAMES:
        boundaries.append(((group_start + group_end) // 2) / fps)

    return sorted(boundaries)


def _write_clips(
    video_id: str,
    boundaries: list[float],
    duration: float,
    fps: float,
    job_id: str,
) -> list[dict[str, Any]]:
    """Post one clip per segment to the backend."""
    # Build segment list from boundary timestamps
    pivots = [0.0, *boundaries, duration]
    clips: list[dict[str, Any]] = []

    for i, (start, end) in enumerate(zip(pivots, pivots[1:])):
        if end - start < MIN_PLAY_DURATION:
            continue
        confidence = 0.7  # flat placeholder; will improve with a trained model
        clip = backend.create_clip(
            video_id,
            start_time=start,
            end_time=end,
            boundary_source="model",
            boundary_confidence=confidence,
            play_number=i + 1,
            job_id=job_id,
        )
        clips.append(clip)

    return clips
