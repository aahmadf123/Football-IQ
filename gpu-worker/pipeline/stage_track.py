"""Stage 5 — Player Tracking.

Implements a lightweight ByteTrack-style IoU-based tracker using only OpenCV
and numpy (no external tracker dependency required for MVP).

Algorithm:
  1. Consume per-frame detections from Stage 4 output artifacts.
  2. Associate detections across frames using IoU matching (Hungarian algorithm).
  3. Maintain a track buffer to keep short-occlusion tracks alive.
  4. Write one Tracklet + N TrackPoints per continuous player track.

For production: swap the IoU tracker for BoT-SORT with Re-ID embeddings.

Output: `tracklets` and `track_points` rows written to the backend.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import structlog

from pipeline import backend

log = structlog.get_logger(__name__)

MAX_LOST_FRAMES = 30  # frames a track can be "lost" before it is closed
IOU_THRESHOLD = 0.3


# ── Simple track state ────────────────────────────────────────────────────────

class _Track:
    _next_id = 1

    def __init__(self, bbox: list[float], frame: int) -> None:
        self.track_id = _Track._next_id
        _Track._next_id += 1
        self.bbox = bbox
        self.start_frame = frame
        self.last_frame = frame
        self.lost_count = 0
        self.points: list[dict[str, Any]] = [
            {"frame_number": frame, "bbox": bbox}
        ]

    def update(self, bbox: list[float], frame: int) -> None:
        self.bbox = bbox
        self.last_frame = frame
        self.lost_count = 0
        self.points.append({"frame_number": frame, "bbox": bbox})


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


def _hungarian(cost: list[list[float]]) -> list[tuple[int, int]]:
    """Simple greedy assignment (O(n²)) — good enough for ≤50 players."""
    n_rows = len(cost)
    n_cols = len(cost[0]) if cost else 0
    used_cols: set[int] = set()
    matches: list[tuple[int, int]] = []
    for r in range(n_rows):
        best_col = -1
        best_val = IOU_THRESHOLD
        for c in range(n_cols):
            if c not in used_cols and cost[r][c] > best_val:
                best_val = cost[r][c]
                best_col = c
        if best_col >= 0:
            matches.append((r, best_col))
            used_cols.add(best_col)
    return matches


def run(
    clip_id: str,
    detections: dict[str, list[dict[str, Any]]],
    fps: float,
    job_id: str,
) -> dict[str, Any]:
    """Run tracking and write tracklets to the backend."""
    log.info("stage_track_start", clip_id=clip_id)
    _Track._next_id = 1  # reset for each clip

    active_tracks: list[_Track] = []
    closed_tracks: list[_Track] = []

    sorted_frames = sorted(int(f) for f in detections)
    for frame_idx in sorted_frames:
        frame_dets = detections.get(str(frame_idx), [])
        player_bboxes = [d["bbox"] for d in frame_dets if d.get("class") == "player"]

        # Build IoU cost matrix
        if active_tracks and player_bboxes:
            cost = [
                [_iou(t.bbox, b) for b in player_bboxes]
                for t in active_tracks
            ]
            matches = _hungarian(cost)
            matched_tracks = {m[0] for m in matches}
            matched_dets = {m[1] for m in matches}

            for ti, di in matches:
                active_tracks[ti].update(player_bboxes[di], frame_idx)

            # Unmatched detections → new tracks
            for di, bbox in enumerate(player_bboxes):
                if di not in matched_dets:
                    active_tracks.append(_Track(bbox, frame_idx))

            # Unmatched tracks → increment lost counter
            for ti, track in enumerate(active_tracks):
                if ti not in matched_tracks:
                    track.lost_count += 1
        else:
            # No detections this frame — all active tracks are unmatched
            for track in active_tracks:
                track.lost_count += 1
            for bbox in player_bboxes:
                active_tracks.append(_Track(bbox, frame_idx))

        # Close tracks that have been lost too long
        still_active: list[_Track] = []
        for track in active_tracks:
            if track.lost_count > MAX_LOST_FRAMES:
                closed_tracks.append(track)
            else:
                still_active.append(track)
        active_tracks = still_active

    # Close remaining active tracks at end of video
    closed_tracks.extend(active_tracks)

    # Write to backend
    tracklet_ids: list[str] = []
    for track in closed_tracks:
        if len(track.points) < 2:
            continue
        try:
            resp = backend.create_tracklet(
                clip_id,
                start_frame=track.start_frame,
                end_frame=track.last_frame,
                track_points=track.points,
                team_label="unknown",
                job_id=job_id,
            )
            tracklet_ids.append(resp["id"])
        except Exception as exc:
            log.warning("tracklet_write_failed", track_id=track.track_id, error=str(exc))

    log.info("stage_track_done", clip_id=clip_id, tracklet_count=len(tracklet_ids))
    return {"tracklet_count": len(tracklet_ids), "tracklet_ids": tracklet_ids}
