"""Stage — Self-Scout Exposure Dashboard (Phase 2).

Analyses Toledo's own tendencies to identify pre-snap tells:
  - Formation-to-play-type tendencies (run vs. pass rate per formation)
  - Motion tendencies (run/pass rate after pre-snap motion)
  - Field-zone tendencies (red zone, backed-up, mid-field)
  - Personnel tendencies (run/pass by personnel grouping)
  - Pre-snap tell exposure view (what opponents would see)

Approach:
  1. Aggregate all labels and metrics across a set of clips.
  2. Compute run/pass ratios grouped by formation, motion, field zone,
     and personnel grouping.
  3. Flag high-tendency outliers as exposure risks.
  4. Return structured tendency data for the dashboard.

This stage operates on a batch of clips rather than a single clip.
Output: tendency analysis results returned as a dict (dashboard data).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import structlog

log = structlog.get_logger(__name__)

TENDENCY_ALERT_THRESHOLD = 0.70


def run(
    clips: list[dict[str, Any]],
    labels_by_clip: dict[str, list[dict[str, Any]]],
    metrics_by_clip: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Compute self-scout tendency analysis across a batch of clips."""
    log.info("stage_self_scout_start", clip_count=len(clips))

    # ── Formation tendencies ──────────────────────────────────────────────
    formation_tendencies = _compute_formation_tendencies(clips, labels_by_clip)

    # ── Motion tendencies ─────────────────────────────────────────────────
    motion_tendencies = _compute_motion_tendencies(clips, labels_by_clip)

    # ── Field zone tendencies ─────────────────────────────────────────────
    field_zone_tendencies = _compute_field_zone_tendencies(clips, labels_by_clip)

    # ── Personnel tendencies ──────────────────────────────────────────────
    personnel_tendencies = _compute_personnel_tendencies(clips, labels_by_clip)

    # ── Pre-snap tell alerts ──────────────────────────────────────────────
    alerts = _generate_alerts(
        formation_tendencies, motion_tendencies,
        field_zone_tendencies, personnel_tendencies,
    )

    result = {
        "formation_tendencies": formation_tendencies,
        "motion_tendencies": motion_tendencies,
        "field_zone_tendencies": field_zone_tendencies,
        "personnel_tendencies": personnel_tendencies,
        "alerts": alerts,
        "clip_count": len(clips),
    }

    log.info("stage_self_scout_done", alert_count=len(alerts))
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_play_type(labels: list[dict[str, Any]]) -> str | None:
    """Infer play type (run/pass) from labels."""
    for lbl in labels:
        lt = lbl.get("label_type", "")
        lv = lbl.get("label_value", {})
        if lt == "play_concept":
            concept = lv.get("concept", "").lower()
            if any(w in concept for w in ("run", "zone", "power", "counter", "draw", "sweep")):
                return "run"
            if any(w in concept for w in ("pass", "screen", "play_action", "rpo")):
                return "pass"
        if lt == "play_direction":
            return "run"
    return None


def _get_formation(labels: list[dict[str, Any]]) -> str | None:
    for lbl in labels:
        if lbl.get("label_type") == "offensive_formation":
            return lbl.get("label_value", {}).get("formation")
    return None


def _get_motion_detected(labels: list[dict[str, Any]]) -> bool:
    for lbl in labels:
        if lbl.get("label_type") == "motion_detected":
            return bool(lbl.get("label_value", {}).get("detected", False))
    return False


def _compute_formation_tendencies(
    clips: list[dict[str, Any]],
    labels_by_clip: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Run/pass rate per formation."""
    formation_plays: dict[str, Counter[str]] = defaultdict(Counter)

    for clip in clips:
        clip_id = clip.get("id", "")
        labels = labels_by_clip.get(clip_id, [])
        formation = _get_formation(labels)
        play_type = _get_play_type(labels)
        if formation and play_type:
            formation_plays[formation][play_type] += 1

    results: list[dict[str, Any]] = []
    for formation, counts in formation_plays.items():
        total = sum(counts.values())
        if total < 3:
            continue
        run_rate = counts.get("run", 0) / total
        pass_rate = counts.get("pass", 0) / total
        results.append({
            "formation": formation,
            "total_plays": total,
            "run_count": counts.get("run", 0),
            "pass_count": counts.get("pass", 0),
            "run_rate": round(run_rate, 3),
            "pass_rate": round(pass_rate, 3),
        })

    return sorted(results, key=lambda r: r["total_plays"], reverse=True)


def _compute_motion_tendencies(
    clips: list[dict[str, Any]],
    labels_by_clip: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Run/pass rate with and without pre-snap motion."""
    motion_plays: Counter[str] = Counter()
    no_motion_plays: Counter[str] = Counter()

    for clip in clips:
        clip_id = clip.get("id", "")
        labels = labels_by_clip.get(clip_id, [])
        has_motion = _get_motion_detected(labels)
        play_type = _get_play_type(labels)
        if play_type:
            if has_motion:
                motion_plays[play_type] += 1
            else:
                no_motion_plays[play_type] += 1

    motion_total = sum(motion_plays.values())
    no_motion_total = sum(no_motion_plays.values())

    return {
        "with_motion": {
            "total": motion_total,
            "run_count": motion_plays.get("run", 0),
            "pass_count": motion_plays.get("pass", 0),
            "run_rate": round(motion_plays.get("run", 0) / max(motion_total, 1), 3),
            "pass_rate": round(motion_plays.get("pass", 0) / max(motion_total, 1), 3),
        },
        "without_motion": {
            "total": no_motion_total,
            "run_count": no_motion_plays.get("run", 0),
            "pass_count": no_motion_plays.get("pass", 0),
            "run_rate": round(no_motion_plays.get("run", 0) / max(no_motion_total, 1), 3),
            "pass_rate": round(no_motion_plays.get("pass", 0) / max(no_motion_total, 1), 3),
        },
    }


def _compute_field_zone_tendencies(
    clips: list[dict[str, Any]],
    labels_by_clip: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Run/pass rate by field zone."""
    zone_plays: dict[str, Counter[str]] = defaultdict(Counter)

    for clip in clips:
        clip_id = clip.get("id", "")
        labels = labels_by_clip.get(clip_id, [])
        play_type = _get_play_type(labels)
        field_zone = clip.get("field_zone", "mid_field")
        if play_type:
            zone_plays[field_zone][play_type] += 1

    results: list[dict[str, Any]] = []
    for zone, counts in zone_plays.items():
        total = sum(counts.values())
        if total < 2:
            continue
        results.append({
            "field_zone": zone,
            "total_plays": total,
            "run_count": counts.get("run", 0),
            "pass_count": counts.get("pass", 0),
            "run_rate": round(counts.get("run", 0) / total, 3),
            "pass_rate": round(counts.get("pass", 0) / total, 3),
        })

    return sorted(results, key=lambda r: r["total_plays"], reverse=True)


def _compute_personnel_tendencies(
    clips: list[dict[str, Any]],
    labels_by_clip: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Run/pass rate by personnel grouping."""
    personnel_plays: dict[str, Counter[str]] = defaultdict(Counter)

    for clip in clips:
        clip_id = clip.get("id", "")
        labels = labels_by_clip.get(clip_id, [])
        play_type = _get_play_type(labels)
        personnel = clip.get("personnel_grouping", "unknown")
        if play_type and personnel:
            personnel_plays[personnel][play_type] += 1

    results: list[dict[str, Any]] = []
    for personnel, counts in personnel_plays.items():
        total = sum(counts.values())
        if total < 2:
            continue
        results.append({
            "personnel": personnel,
            "total_plays": total,
            "run_count": counts.get("run", 0),
            "pass_count": counts.get("pass", 0),
            "run_rate": round(counts.get("run", 0) / total, 3),
            "pass_rate": round(counts.get("pass", 0) / total, 3),
        })

    return sorted(results, key=lambda r: r["total_plays"], reverse=True)


def _generate_alerts(
    formation_tendencies: list[dict[str, Any]],
    motion_tendencies: dict[str, Any],
    field_zone_tendencies: list[dict[str, Any]],
    personnel_tendencies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flag high-tendency outliers as exposure risks."""
    alerts: list[dict[str, Any]] = []

    for ft in formation_tendencies:
        if ft["total_plays"] >= 5:
            if ft["run_rate"] >= TENDENCY_ALERT_THRESHOLD:
                alerts.append({
                    "alert_type": "formation_tendency",
                    "message": (
                        f"High run tendency from {ft['formation']}: "
                        f"{ft['run_rate']:.0%} run rate ({ft['total_plays']} plays)"
                    ),
                    "severity": "high" if ft["run_rate"] >= 0.85 else "medium",
                    "data": ft,
                })
            if ft["pass_rate"] >= TENDENCY_ALERT_THRESHOLD:
                alerts.append({
                    "alert_type": "formation_tendency",
                    "message": (
                        f"High pass tendency from {ft['formation']}: "
                        f"{ft['pass_rate']:.0%} pass rate ({ft['total_plays']} plays)"
                    ),
                    "severity": "high" if ft["pass_rate"] >= 0.85 else "medium",
                    "data": ft,
                })

    # Motion tendency alert
    motion_data = motion_tendencies.get("with_motion", {})
    if motion_data.get("total", 0) >= 5:
        if motion_data["run_rate"] >= TENDENCY_ALERT_THRESHOLD:
            alerts.append({
                "alert_type": "motion_tendency",
                "message": (
                    f"High run tendency after motion: "
                    f"{motion_data['run_rate']:.0%} run rate"
                ),
                "severity": "medium",
                "data": motion_data,
            })
        if motion_data["pass_rate"] >= TENDENCY_ALERT_THRESHOLD:
            alerts.append({
                "alert_type": "motion_tendency",
                "message": (
                    f"High pass tendency after motion: "
                    f"{motion_data['pass_rate']:.0%} pass rate"
                ),
                "severity": "medium",
                "data": motion_data,
            })

    for zt in field_zone_tendencies:
        if zt["total_plays"] >= 5:
            if zt["run_rate"] >= TENDENCY_ALERT_THRESHOLD:
                alerts.append({
                    "alert_type": "field_zone_tendency",
                    "message": (
                        f"High run tendency in {zt['field_zone']}: "
                        f"{zt['run_rate']:.0%} run rate"
                    ),
                    "severity": "medium",
                    "data": zt,
                })

    return alerts
