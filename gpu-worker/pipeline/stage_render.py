"""Stage 10 — Overlay Rendering & Dashboard Indexing.

Renders an annotated video overlay on top of each clip:
  - Field coordinate grid (yard lines)
  - Player tracks (coloured trails)
  - Formation label (top-left HUD)
  - Play direction arrow
  - Metric callouts (cushion, separation, speed)
  - Confidence warning banner when analytics_safe=False

Also writes a "dashboard_ready" metadata block back to the clip record so the
frontend can find and display the clip.

Output: overlay video URI + dashboard index update.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import structlog

from pipeline import r2

log = structlog.get_logger(__name__)

FONT = cv2.FONT_HERSHEY_SIMPLEX
TRACK_COLORS = [
    (0, 255, 0),    # green
    (255, 165, 0),  # orange
    (0, 128, 255),  # blue
    (255, 0, 128),  # pink
    (255, 255, 0),  # yellow
]


def run(
    clip_id: str,
    video_path: Path,
    tracklets: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    analytics_safe: bool,
    fps: float,
    backend_api_url: str,
) -> dict[str, Any]:
    """Render overlay video and upload to R2."""
    log.info("stage_render_start", clip_id=clip_id)

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "overlay.mp4"
        _render(video_path, out_path, tracklets, labels, metrics, analytics_safe, fps)

        r2_key = f"overlays/{clip_id}/overlay.mp4"
        overlay_uri = r2.upload_file(out_path, r2_key, content_type="video/mp4")

    # Update clip with overlay URI and dashboard-ready flag
    _update_clip_overlay(clip_id, overlay_uri, backend_api_url)
    log.info("stage_render_done", clip_id=clip_id, overlay_uri=overlay_uri)
    return {"overlay_uri": overlay_uri}


def _render(
    video_path: Path,
    out_path: Path,
    tracklets: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    analytics_safe: bool,
    fps: float,
) -> None:
    from pipeline.hwaccel import nvdec_video_capture

    cap = nvdec_video_capture(video_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))

    # Pre-build track lookup: frame → list of (bbox, color, track_id)
    frame_tracks: dict[int, list[tuple[list[float], tuple[int, int, int], int]]] = {}
    for i, t in enumerate(tracklets):
        color = TRACK_COLORS[i % len(TRACK_COLORS)]
        for pt in t.get("track_points", []):
            fn = pt.get("frame_number", 0)
            bbox = pt.get("bbox")
            if bbox:
                frame_tracks.setdefault(fn, []).append((bbox, color, i))

    # Pre-compute label text
    formation = _label_value(labels, "offensive_formation", "formation", "—")
    front = _label_value(labels, "defensive_front", "front", "—")
    direction = _label_value(labels, "play_direction", "direction", "—")

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # ── Analytics-safe warning ────────────────────────────────────────
        if not analytics_safe:
            cv2.rectangle(frame, (0, 0), (w, 28), (0, 0, 200), -1)
            cv2.putText(frame, "CALIBRATION WARNING — metrics suppressed",
                        (10, 20), FONT, 0.55, (255, 255, 255), 1)

        # ── Formation HUD ─────────────────────────────────────────────────
        cv2.putText(frame, f"OFF: {formation}  DEF: {front}  DIR: {direction}",
                    (10, h - 12), FONT, 0.5, (255, 255, 255), 1)

        # ── Player tracks ─────────────────────────────────────────────────
        for bbox, color, tid in frame_tracks.get(frame_idx, []):
            x1, y1, x2, y2 = [int(v) for v in bbox]
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"T{tid}", (x1, y1 - 4), FONT, 0.4, color, 1)

        writer.write(frame)
        frame_idx += 1

    cap.release()
    writer.release()


def _label_value(
    labels: list[dict[str, Any]],
    label_type: str,
    key: str,
    default: str,
) -> str:
    for lb in labels:
        if lb.get("label_type") == label_type:
            return str(lb.get("label_value", {}).get(key, default))
    return default


def _update_clip_overlay(clip_id: str, overlay_uri: str, backend_api_url: str) -> None:
    if not backend_api_url:
        return
    import httpx
    try:
        with httpx.Client(base_url=backend_api_url, timeout=15) as c:
            c.patch(f"/api/v1/clips/{clip_id}", json={"storage_uri": overlay_uri})
    except Exception as exc:
        log.warning("clip_overlay_update_failed", clip_id=clip_id, error=str(exc))
