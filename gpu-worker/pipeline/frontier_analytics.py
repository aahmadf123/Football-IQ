"""Frontier analytics scaffolds (Issue #10) — xSep / xYards / xPressure.

These are **experimental** advanced metrics computed from calibrated tracking
(Issues #127/#128/#129). They are scaffolds, not validated Toledo results, so
every metric this module emits is:

* ``experimental=True`` and ``analytics_safe=False`` — a coach must review it
  before it leaves the experimental surface;
* source-labeled (``source="tracking"``) and carries a ``sample_size`` and
  ``stability_note`` so a coach can judge how far to trust it;
* suppressed (returns ``None`` / ``suppressed``) when its required inputs are
  missing — field calibration is not analytics-safe (#127) or there aren't
  enough tracked frames. It never fabricates a value.

SAM masks (#74) and play embeddings (#8) are *enrichment only*: passing them
nudges confidence up, but every metric still computes without them. Nothing
here is routed through the model router — it is deterministic geometry over the
outputs of the routed stages, like the pre-snap predictor.

The backend forces these metric names experimental on ingest as defense in
depth (see ``app.routers.clips.create_metric``); this module is the producer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# Minimum tracked points (per track) before a metric is trustworthy enough to
# emit at all. Below this we suppress rather than guess.
MIN_TRACK_POINTS = 3
# How many reps a coach should see before trusting the trend.
STABILITY_REPS = 30

XSEP = "xsep"
XYARDS = "xyards"
XPRESSURE = "xpressure"

_STABILITY_NOTE = (
    f"Experimental — single-clip estimate. Trust trends only after ~{STABILITY_REPS}+ "
    "clean reps; needs calibrated tracking (#127/#128/#129)."
)


# ── Result model ─────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class FrontierMetric:
    metric_name: str
    metric_value: dict[str, Any]
    unit: str | None
    confidence: float
    suppressed: bool = False
    suppression_reason: str | None = None
    tracklet_id: str | None = None
    # Always experimental scaffolds (Issue #10).
    experimental: bool = field(default=True)
    analytics_safe: bool = field(default=False)

    def to_metric_payload(self, clip_id: str, *, job_id: str | None = None) -> dict[str, Any]:
        """Shape into a ``backend.create_metric`` call's kwargs."""
        payload: dict[str, Any] = {
            "clip_id": clip_id,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "unit": self.unit,
            "experimental_flag": True,
            "analytics_safe": False,
            "confidence": self.confidence,
            "is_suppressed": self.suppressed,
        }
        if self.suppression_reason is not None:
            payload["suppression_reason"] = self.suppression_reason
        if self.tracklet_id is not None:
            payload["tracklet_id"] = self.tracklet_id
        if job_id is not None:
            payload["job_id"] = job_id
        return payload


# ── Geometry helpers ─────────────────────────────────────────────────────────────


def _point_at_frame(track: list[dict[str, Any]], frame: int) -> dict[str, Any] | None:
    """Return the track point nearest ``frame`` (None for an empty track)."""
    best: dict[str, Any] | None = None
    best_gap = math.inf
    for pt in track:
        fn = pt.get("frame_number")
        if fn is None:
            continue
        gap = abs(int(fn) - frame)
        if gap < best_gap:
            best_gap = gap
            best = pt
    return best


def _distance(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    try:
        return math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))
    except (KeyError, TypeError, ValueError):
        return None


def _enrichment_bonus(used_sam: bool, used_embeddings: bool) -> float:
    bonus = 0.0
    if used_sam:
        bonus += 0.1
    if used_embeddings:
        bonus += 0.05
    return bonus


def _suppressed(metric_name: str, reason: str, *, tracklet_id: str | None = None) -> FrontierMetric:
    return FrontierMetric(
        metric_name=metric_name,
        metric_value={"suppressed": True, "reason": reason, "source": "tracking"},
        unit=None,
        confidence=0.0,
        suppressed=True,
        suppression_reason=reason,
        tracklet_id=tracklet_id,
    )


# ── xSep — expected separation at the throw/decision point ───────────────────────


def compute_xsep(
    receiver_track: list[dict[str, Any]],
    defender_track: list[dict[str, Any]],
    *,
    throw_frame: int,
    calibration_analytics_safe: bool = True,
    receiver_tracklet_id: str | None = None,
    used_sam: bool = False,
    used_embeddings: bool = False,
) -> FrontierMetric:
    """Yards of separation between a receiver and the nearest defender at the throw.

    Suppressed (never guessed) when field calibration is not analytics-safe or
    either track is too short.
    """
    if not calibration_analytics_safe:
        return _suppressed(XSEP, "calibration_not_analytics_safe", tracklet_id=receiver_tracklet_id)
    if len(receiver_track) < MIN_TRACK_POINTS or len(defender_track) < MIN_TRACK_POINTS:
        return _suppressed(XSEP, "insufficient_track_points", tracklet_id=receiver_tracklet_id)

    rcv = _point_at_frame(receiver_track, throw_frame)
    dfn = _point_at_frame(defender_track, throw_frame)
    if rcv is None or dfn is None:
        return _suppressed(XSEP, "no_point_at_throw", tracklet_id=receiver_tracklet_id)
    separation = _distance(rcv, dfn)
    if separation is None:
        return _suppressed(XSEP, "non_numeric_coordinates", tracklet_id=receiver_tracklet_id)

    sample = min(len(receiver_track), len(defender_track))
    confidence = round(
        min(0.7, 0.3 + 0.4 * (sample / (sample + 10.0)))
        + _enrichment_bonus(used_sam, used_embeddings),
        3,
    )
    return FrontierMetric(
        metric_name=XSEP,
        metric_value={
            "yards": round(separation, 2),
            "throw_frame": throw_frame,
            "source": "tracking",
            "sample_size": sample,
            "stability_note": _STABILITY_NOTE,
            "used_sam": used_sam,
            "used_embeddings": used_embeddings,
        },
        unit="yd",
        confidence=confidence,
        tracklet_id=receiver_tracklet_id,
    )


# ── xPressure — expected pressure on the QB ──────────────────────────────────────


def compute_xpressure(
    qb_track: list[dict[str, Any]],
    rusher_tracks: list[list[dict[str, Any]]],
    *,
    snap_frame: int,
    throw_frame: int,
    fps: float = 30.0,
    pressure_radius_yd: float = 2.0,
    calibration_analytics_safe: bool = True,
    used_sam: bool = False,
) -> FrontierMetric:
    """Expected pressure proxy from rusher proximity and time-to-throw (defense).

    A rusher within ``pressure_radius_yd`` of the QB before the throw counts as
    pressure. ``xpressure`` here is the fraction of rushers that closed inside
    the radius, scaled by how quickly the QB had to get rid of it. Suppressed
    when calibration is not analytics-safe, the QB track is too short, or the
    snap/throw window is degenerate.
    """
    if not calibration_analytics_safe:
        return _suppressed(XPRESSURE, "calibration_not_analytics_safe")
    if len(qb_track) < MIN_TRACK_POINTS or not rusher_tracks:
        return _suppressed(XPRESSURE, "insufficient_tracks")
    if throw_frame <= snap_frame or fps <= 0:
        return _suppressed(XPRESSURE, "degenerate_snap_throw_window")

    qb_at_throw = _point_at_frame(qb_track, throw_frame)
    if qb_at_throw is None:
        return _suppressed(XPRESSURE, "no_qb_point_at_throw")

    closed = 0
    nearest = math.inf
    counted = 0
    for rusher in rusher_tracks:
        pt = _point_at_frame(rusher, throw_frame)
        if pt is None:
            continue
        dist = _distance(qb_at_throw, pt)
        if dist is None:
            continue
        counted += 1
        nearest = min(nearest, dist)
        if dist <= pressure_radius_yd:
            closed += 1
    if counted == 0:
        return _suppressed(XPRESSURE, "no_rusher_points_at_throw")

    time_to_throw_s = (throw_frame - snap_frame) / fps
    # Quick throws (< 2.5s) reduce realized pressure even if a rusher is close.
    time_factor = min(1.0, time_to_throw_s / 2.5)
    pressure = round(min(1.0, (closed / counted) * (0.5 + 0.5 * time_factor)), 3)

    confidence = round(
        min(0.65, 0.25 + 0.4 * (counted / (counted + 4.0))) + _enrichment_bonus(used_sam, False),
        3,
    )
    return FrontierMetric(
        metric_name=XPRESSURE,
        metric_value={
            "xpressure": pressure,
            "rushers_closed": closed,
            "rushers_counted": counted,
            "nearest_rusher_yd": round(nearest, 2) if nearest != math.inf else None,
            "time_to_throw_s": round(time_to_throw_s, 2),
            "source": "tracking",
            "sample_size": counted,
            "stability_note": _STABILITY_NOTE,
            "used_sam": used_sam,
        },
        unit="rate",
        confidence=confidence,
    )


# ── xYards — expected yards after catch (documented stub) ────────────────────────


def compute_xyards(
    receiver_track: list[dict[str, Any]],
    *,
    catch_frame: int | None = None,
    calibration_analytics_safe: bool = True,
    receiver_tracklet_id: str | None = None,
) -> FrontierMetric:
    """Expected yards-after-catch — deliberately a low-confidence scaffold.

    A trustworthy xYards needs spacing + leverage + pursuit modeling that the
    tracking layer does not yet expose. Rather than fabricate a number, this
    emits a clearly-flagged placeholder that records only the downfield distance
    actually travelled after the catch, with very low confidence — or suppresses
    when the inputs are absent.
    """
    if not calibration_analytics_safe:
        return _suppressed(XYARDS, "calibration_not_analytics_safe", tracklet_id=receiver_tracklet_id)
    if catch_frame is None or len(receiver_track) < MIN_TRACK_POINTS:
        return _suppressed(XYARDS, "insufficient_inputs", tracklet_id=receiver_tracklet_id)

    catch_pt = _point_at_frame(receiver_track, catch_frame)
    after = [p for p in receiver_track if int(p.get("frame_number", -1)) >= catch_frame]
    if catch_pt is None or len(after) < 2:
        return _suppressed(XYARDS, "no_post_catch_track", tracklet_id=receiver_tracklet_id)

    end_pt = after[-1]
    try:
        downfield = abs(float(end_pt["x"]) - float(catch_pt["x"]))
    except (KeyError, TypeError, ValueError):
        return _suppressed(XYARDS, "non_numeric_coordinates", tracklet_id=receiver_tracklet_id)

    return FrontierMetric(
        metric_name=XYARDS,
        metric_value={
            "observed_yac_yd": round(downfield, 2),
            "model": "placeholder_observed_only",
            "source": "tracking",
            "sample_size": len(after),
            "stability_note": (
                "Scaffold only — reports observed YAC, NOT a modeled expectation. "
                "Do not use as a trusted xYards until the spacing/pursuit model lands."
            ),
        },
        unit="yd",
        confidence=0.1,
        tracklet_id=receiver_tracklet_id,
    )
