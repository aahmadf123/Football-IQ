"""Stage 7 — Event Detection.

Detects key play events by analysing frame-level detection signals:
  - snap: first frame with high-density player cluster movement after huddle
  - motion_start/end: pre-snap receiver/back motion
  - throw: sudden ball-separation from backfield region
  - contact/tackle: high-overlap bounding boxes in the skill-player zone
  - end_of_play: post-tackle cluster stillness

Phase 1: heuristic rule-based detectors on top of tracking data.
Manual correction is expected — coaches can PATCH events via the API.

Output: `events` rows written to the backend.
"""

from __future__ import annotations

from typing import Any

import structlog

from pipeline import backend

log = structlog.get_logger(__name__)

# Heuristic tuning
SNAP_MOTION_THRESHOLD = 15.0    # pixels of mean bbox displacement in one frame step
TACKLE_OVERLAP_THRESHOLD = 0.4  # IoU between two player bboxes → contact
STILLNESS_FRAMES = 10           # consecutive low-motion frames → end_of_play


def run(
    clip_id: str,
    detections: dict[str, list[dict[str, Any]]],
    fps: float,
    job_id: str,
) -> dict[str, Any]:
    """Detect events in a clip from frame-level detections."""
    log.info("stage_events_start", clip_id=clip_id)

    sorted_frames = sorted(int(f) for f in detections)
    events: list[dict[str, Any]] = []

    # Track centroid history for motion detection
    prev_centroids: list[tuple[float, float]] = []
    motion_history: list[float] = []
    in_motion = False
    motion_start_frame = 0
    low_motion_streak = 0
    snap_detected = False

    for frame_idx in sorted_frames:
        frame_dets = [d for d in detections.get(str(frame_idx), [])
                      if d.get("class") == "player"]
        centroids = [_centroid(d["bbox"]) for d in frame_dets]

        if prev_centroids and centroids:
            mean_disp = _mean_displacement(prev_centroids, centroids)
            motion_history.append(mean_disp)

            # ── Snap detection ────────────────────────────────────────────
            if not snap_detected and mean_disp > SNAP_MOTION_THRESHOLD:
                snap_detected = True
                events.append({
                    "event_type": "snap",
                    "frame_number": frame_idx,
                    "timestamp_seconds": frame_idx / fps,
                    "attributes": {"mean_displacement": mean_disp},
                })

            # ── Pre-snap motion detection ─────────────────────────────────
            if not snap_detected:
                if not in_motion and mean_disp > SNAP_MOTION_THRESHOLD * 0.4:
                    in_motion = True
                    motion_start_frame = frame_idx
                    events.append({
                        "event_type": "motion_start",
                        "frame_number": frame_idx,
                        "timestamp_seconds": frame_idx / fps,
                        "attributes": {},
                    })
                elif in_motion and mean_disp < SNAP_MOTION_THRESHOLD * 0.2:
                    in_motion = False
                    events.append({
                        "event_type": "motion_end",
                        "frame_number": frame_idx,
                        "timestamp_seconds": frame_idx / fps,
                        "attributes": {"duration_frames": frame_idx - motion_start_frame},
                    })

            # ── Contact / tackle detection ────────────────────────────────
            if snap_detected:
                bboxes = [d["bbox"] for d in frame_dets]
                for i in range(len(bboxes)):
                    for j in range(i + 1, len(bboxes)):
                        iou = _iou(bboxes[i], bboxes[j])
                        if iou > TACKLE_OVERLAP_THRESHOLD:
                            events.append({
                                "event_type": "contact",
                                "frame_number": frame_idx,
                                "timestamp_seconds": frame_idx / fps,
                                "attributes": {"iou": iou},
                            })

            # ── End-of-play detection ─────────────────────────────────────
            if snap_detected:
                if mean_disp < SNAP_MOTION_THRESHOLD * 0.15:
                    low_motion_streak += 1
                else:
                    low_motion_streak = 0
                if low_motion_streak == STILLNESS_FRAMES:
                    events.append({
                        "event_type": "end_of_play",
                        "frame_number": frame_idx,
                        "timestamp_seconds": frame_idx / fps,
                        "attributes": {},
                    })
                    snap_detected = False
                    low_motion_streak = 0

        prev_centroids = centroids

    # Write events to backend
    event_ids: list[str] = []
    for ev in events:
        try:
            resp = backend.create_event(
                clip_id,
                ev["event_type"],
                frame_number=ev.get("frame_number"),
                timestamp_seconds=ev.get("timestamp_seconds"),
                attributes=ev.get("attributes"),
            )
            event_ids.append(resp["id"])
        except Exception as exc:
            log.warning("event_write_failed", event_type=ev.get("event_type"), error=str(exc))

    log.info("stage_events_done", clip_id=clip_id, event_count=len(event_ids))
    return {"event_count": len(event_ids), "event_ids": event_ids}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _centroid(bbox: list[float]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _mean_displacement(
    prev: list[tuple[float, float]], curr: list[tuple[float, float]]
) -> float:
    """Mean Euclidean distance between nearest-neighbour centroid pairs."""
    if not prev or not curr:
        return 0.0
    total = 0.0
    n = min(len(prev), len(curr))
    for i in range(n):
        dx = curr[i][0] - prev[i][0]
        dy = curr[i][1] - prev[i][1]
        total += (dx * dx + dy * dy) ** 0.5
    return total / n


def _iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)
