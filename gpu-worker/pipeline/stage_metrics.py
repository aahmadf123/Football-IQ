"""Stage 9 — Metric Computation.

Computes initial analytics metrics from tracking + calibration data.
Metrics are suppressed (is_suppressed=True) when analytics_safe is False.

Metrics computed:
  - cushion_at_snap          — defender distance to nearest WR at snap
  - separation_at_throw      — WR distance from nearest defender at throw event
  - max_speed                — max speed (yd/s) per tracklet
  - distance_traveled        — total distance (yd) per tracklet
  - time_to_throw            — frames from snap to throw event
  - dropback_depth           — QB field_x change from snap to throw

All metric_value dicts include a `confidence` field.
Metrics with field coords require analytics_safe=True on the calibration.

Output: `metrics` rows written to the backend.
"""

from __future__ import annotations

import math
import os
from typing import Any

import httpx
import structlog

from pipeline import backend

log = structlog.get_logger(__name__)


def run(
    clip_id: str,
    tracklets: list[dict[str, Any]],
    events: list[dict[str, Any]],
    analytics_safe: bool,
    fps: float,
    job_id: str,
) -> dict[str, Any]:
    """Compute metrics for a clip and write them to the backend."""
    log.info("stage_metrics_start", clip_id=clip_id, analytics_safe=analytics_safe)

    snap_event = next((e for e in events if e.get("event_type") == "snap"), None)
    throw_event = next((e for e in events if e.get("event_type") == "throw"), None)
    snap_frame = snap_event.get("frame_number", 0) if snap_event else 0
    throw_frame = throw_event.get("frame_number") if throw_event else None

    metrics: list[dict[str, Any]] = []

    # ── Time to throw ─────────────────────────────────────────────────────
    if throw_frame is not None and snap_frame is not None:
        ttt = (throw_frame - snap_frame) / max(fps, 1)
        metrics.append({
            "metric_name": "time_to_throw",
            "metric_value": {"seconds": round(ttt, 3), "confidence": 0.75},
            "unit": "s",
            "is_suppressed": False,
            "suppression_reason": None,
        })

    # ── Per-tracklet metrics (require field coords → analytics_safe) ──────
    for t in tracklets:
        pts = sorted(t.get("track_points", []), key=lambda p: p.get("frame_number", 0))
        if len(pts) < 2:
            continue
        track_id = t.get("id", "unknown")
        suppressed = not analytics_safe
        reason = "calibration_not_safe" if suppressed else None

        # Distance traveled
        dist = _distance_traveled(pts)
        metrics.append({
            "metric_name": "distance_traveled",
            "metric_value": {"yards": round(dist, 2), "track_id": track_id, "confidence": 0.7},
            "unit": "yd",
            "is_suppressed": suppressed,
            "suppression_reason": reason,
        })

        # Max speed
        speeds = _frame_speeds(pts, fps)
        if speeds:
            max_spd = max(speeds)
            metrics.append({
                "metric_name": "max_speed",
                "metric_value": {
                    "yards_per_second": round(max_spd, 2),
                    "track_id": track_id,
                    "confidence": 0.65,
                },
                "unit": "yd/s",
                "is_suppressed": suppressed,
                "suppression_reason": reason,
            })

        # Dropback depth (for backfield player moving away from LOS after snap)
        snap_pt = _point_at_frame(pts, snap_frame)
        if throw_frame is not None and snap_pt and not suppressed:
            throw_pt = _point_at_frame(pts, throw_frame)
            if throw_pt:
                depth = abs(
                    (throw_pt.get("field_x") or 0) - (snap_pt.get("field_x") or 0)
                )
                if depth > 1.0:  # only meaningful for QBs dropping back
                    metrics.append({
                        "metric_name": "dropback_depth",
                        "metric_value": {
                            "yards": round(depth, 2),
                            "track_id": track_id,
                            "confidence": 0.65,
                        },
                        "unit": "yd",
                        "is_suppressed": False,
                        "suppression_reason": None,
                    })

    # ── Cushion at snap ───────────────────────────────────────────────────
    snap_positions = [
        _point_at_frame(
            sorted(t.get("track_points", []),
                   key=lambda p: p.get("frame_number", 0)),
            snap_frame,
        )
        for t in tracklets
    ]
    snap_positions = [p for p in snap_positions if p and p.get("field_x") is not None]
    if len(snap_positions) >= 4:
        cushions = _compute_cushions(snap_positions)
        for cushion in cushions:
            metrics.append({
                "metric_name": "cushion_at_snap",
                "metric_value": {"yards": round(cushion, 2), "confidence": 0.6},
                "unit": "yd",
                "is_suppressed": not analytics_safe,
                "suppression_reason": "calibration_not_safe" if not analytics_safe else None,
            })

    # Write to backend
    metric_ids: list[str] = []
    for m in metrics:
        try:
            payload: dict[str, Any] = {
                "clip_id": clip_id,
                "metric_name": m["metric_name"],
                "metric_value": m["metric_value"],
                "unit": m.get("unit"),
                "is_suppressed": m.get("is_suppressed", False),
                "suppression_reason": m.get("suppression_reason"),
                "job_id": job_id,
            }
            api_url = os.environ.get("BACKEND_API_URL", "")
            if api_url:
                import httpx

                with httpx.Client(base_url=api_url, timeout=15) as c:
                    resp = c.post("/api/v1/metrics", json=payload)
                    resp.raise_for_status()
                    metric_ids.append(resp.json()["id"])
        except Exception as exc:
            log.warning("metric_write_failed", name=m.get("metric_name"), error=str(exc))

    log.info("stage_metrics_done", clip_id=clip_id, metric_count=len(metric_ids))
    return {"metric_count": len(metric_ids), "metric_ids": metric_ids}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _distance_traveled(pts: list[dict[str, Any]]) -> float:
    total = 0.0
    for i in range(1, len(pts)):
        x0 = pts[i - 1].get("field_x") or 0
        y0 = pts[i - 1].get("field_y") or 0
        x1 = pts[i].get("field_x") or 0
        y1 = pts[i].get("field_y") or 0
        total += math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
    return total


def _frame_speeds(pts: list[dict[str, Any]], fps: float) -> list[float]:
    speeds: list[float] = []
    for i in range(1, len(pts)):
        f0 = pts[i - 1].get("frame_number", 0)
        f1 = pts[i].get("frame_number", 0)
        dt = (f1 - f0) / max(fps, 1)
        if dt <= 0:
            continue
        x0 = pts[i - 1].get("field_x") or 0
        y0 = pts[i - 1].get("field_y") or 0
        x1 = pts[i].get("field_x") or 0
        y1 = pts[i].get("field_y") or 0
        dist = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
        speeds.append(dist / dt)
    return speeds


def _point_at_frame(
    pts: list[dict[str, Any]], frame: int
) -> dict[str, Any] | None:
    for pt in pts:
        if pt.get("frame_number") == frame:
            return pt
    # Return closest frame
    if pts:
        return min(pts, key=lambda p: abs(p.get("frame_number", 0) - frame))
    return None


def _compute_cushions(
    snap_positions: list[dict[str, Any]],
) -> list[float]:
    """Approximate cushion as min distance between adjacent players (sorted by y)."""
    ys = sorted(
        (float(p.get("field_y") or 0), float(p.get("field_x") or 0))
        for p in snap_positions
    )
    cushions: list[float] = []
    for i in range(1, len(ys)):
        dy = ys[i][0] - ys[i - 1][0]
        dx = ys[i][1] - ys[i - 1][1]
        cushions.append(math.sqrt(dx * dx + dy * dy))
    return cushions
