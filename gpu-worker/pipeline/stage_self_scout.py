"""Stage — Self-Scout Exposure Dashboard (Phase 2).

Analyses Toledo's own tendencies to identify pre-snap tells:
  - Formation-to-play-type tendencies (run vs. pass rate per formation)
  - Motion tendencies (run/pass rate after pre-snap motion)
  - Field-zone tendencies (red zone, backed-up, mid-field)
  - Personnel tendencies (run/pass by personnel grouping)
  - Down-and-distance breakdown
  - Play concept family distribution per formation
  - Pre-snap tell exposure view (what opponents would see)
  - Evidence clip IDs for every tendency bucket

This stage operates on a batch of clips rather than a single clip.
Output: tendency analysis results returned as a dict (dashboard data).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import structlog

log = structlog.get_logger(__name__)

TENDENCY_ALERT_THRESHOLD = 0.70
PRE_SNAP_TELL_THRESHOLD = 0.80
PRE_SNAP_TELL_HIGH_SEVERITY_THRESHOLD = 0.90
LOW_SAMPLE_THRESHOLD = 10
EVIDENCE_CLIP_LIMIT = 10
DISTANCE_BUCKET_ORDER = {"short": 0, "medium": 1, "long": 2}
MOTION_STATE_LABELS = {
    "with_motion": "with motion",
    "without_motion": "without motion",
}


def run(
    clips: list[dict[str, Any]],
    labels_by_clip: dict[str, list[dict[str, Any]]],
    metrics_by_clip: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Compute self-scout tendency analysis across a batch of clips."""
    del metrics_by_clip  # Unused in this stage for now.

    log.info("stage_self_scout_start", clip_count=len(clips))

    formation_tendencies = _compute_formation_tendencies(clips, labels_by_clip)
    motion_tendencies = _compute_motion_tendencies(clips, labels_by_clip)
    field_zone_tendencies = _compute_field_zone_tendencies(clips, labels_by_clip)
    personnel_tendencies = _compute_personnel_tendencies(clips, labels_by_clip)
    down_distance_tendencies = _compute_down_distance_tendencies(clips, labels_by_clip)
    formation_concept_families = _compute_concept_family_distribution(clips, labels_by_clip)
    pre_snap_tells = _compute_pre_snap_tells(clips, labels_by_clip)
    alerts = _generate_alerts(
        formation_tendencies,
        motion_tendencies,
        field_zone_tendencies,
        personnel_tendencies,
    )

    result = {
        "formation_tendencies": formation_tendencies,
        "motion_tendencies": motion_tendencies,
        "field_zone_tendencies": field_zone_tendencies,
        "personnel_tendencies": personnel_tendencies,
        "down_distance_tendencies": down_distance_tendencies,
        "formation_concept_families": formation_concept_families,
        "pre_snap_tells": pre_snap_tells,
        "alerts": alerts,
        "clip_count": len(clips),
    }

    log.info("stage_self_scout_done", alert_count=len(alerts))
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_play_type(labels: list[dict[str, Any]]) -> str | None:
    """Infer play type (run/pass) from labels."""
    for lbl in labels:
        label_type = lbl.get("label_type", "")
        label_value = lbl.get("label_value", {}) or {}
        if label_type == "play_concept":
            concept = _get_label_text(label_value)
            if _contains_any_phrase(concept, ("run", "zone", "power", "counter", "draw", "sweep")):
                return "run"
            if _contains_any_phrase(concept, ("pass", "screen", "play_action", "rpo")):
                return "pass"
        if label_type == "play_direction":
            return "run"
    return None



def _get_formation(labels: list[dict[str, Any]]) -> str | None:
    for lbl in labels:
        if lbl.get("label_type") == "offensive_formation":
            formation = (lbl.get("label_value", {}) or {}).get("formation")
            if isinstance(formation, str) and formation:
                return formation
    return None



def _get_motion_detected(labels: list[dict[str, Any]]) -> bool:
    for lbl in labels:
        if lbl.get("label_type") == "motion_detected":
            return bool((lbl.get("label_value", {}) or {}).get("detected", False))
    return False



def _get_concept_family(labels: list[dict[str, Any]]) -> str | None:
    for lbl in labels:
        if lbl.get("label_type") != "play_concept":
            continue
        concept = _get_label_text(lbl.get("label_value", {}) or {})
        if _contains_any_phrase(concept, ("pass", "screen", "mesh", "smash", "stick", "rpo")):
            return "pass_concept"
        if _contains_any_phrase(concept, ("inside_zone", "inside zone", "duo", "split zone")):
            return "inside_zone"
        if _contains_any_phrase(
            concept,
            ("outside_zone", "outside zone", "wide zone", "stretch", "toss"),
        ):
            return "outside_zone"
        if _contains_any_phrase(concept, ("gap", "power", "counter", "trap", "wham", "dart")):
            return "gap"
    return None



def _get_label_text(label_value: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in label_value.values():
        if isinstance(value, str | int | float | bool):
            parts.append(str(value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str | int | float | bool):
                    parts.append(str(item))
    return " ".join(parts).lower().replace("_", " ")



def _contains_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    tokens = set(text.split())
    for phrase in phrases:
        normalized_phrase = phrase.lower().replace("_", " ")
        if " " in normalized_phrase:
            if normalized_phrase in text:
                return True
        elif normalized_phrase in tokens:
            return True
    return False



def _get_distance_bucket(distance: Any) -> str | None:
    """Bucket yards-to-go into short (1-3), medium (4-6), and long (7+) bands."""
    try:
        distance_value = float(distance)
    except (TypeError, ValueError):
        return None

    if distance_value <= 3:
        return "short"
    if distance_value <= 6:
        return "medium"
    return "long"



def _get_down_distance_key(clip: dict[str, Any]) -> tuple[int, str] | None:
    try:
        down = int(clip.get("down"))
    except (TypeError, ValueError):
        return None

    if down < 1 or down > 4:
        return None

    distance_bucket = _get_distance_bucket(clip.get("distance"))
    if distance_bucket is None:
        return None

    return (down, distance_bucket)



def _limit_evidence(clip_ids: list[str]) -> list[str]:
    return clip_ids[:EVIDENCE_CLIP_LIMIT]



def _build_tendency_results(
    plays: dict[str, Counter[str]],
    evidence: dict[str, list[str]],
    grouping_key_name: str,
    min_plays: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for grouping_key, counts in plays.items():
        total = sum(counts.values())
        if total < min_plays:
            continue
        results.append(
            {
                grouping_key_name: grouping_key,
                "grouping_key": grouping_key,
                "total_plays": total,
                "run_count": counts.get("run", 0),
                "pass_count": counts.get("pass", 0),
                "run_rate": round(counts.get("run", 0) / total, 3),
                "pass_rate": round(counts.get("pass", 0) / total, 3),
                "evidence_clip_ids": _limit_evidence(evidence.get(grouping_key, [])),
                "low_sample": total < LOW_SAMPLE_THRESHOLD,
            }
        )

    return sorted(results, key=lambda result: result["total_plays"], reverse=True)



def _compute_formation_tendencies(
    clips: list[dict[str, Any]],
    labels_by_clip: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    formation_plays: dict[str, Counter[str]] = defaultdict(Counter)
    formation_evidence: dict[str, list[str]] = defaultdict(list)

    for clip in clips:
        clip_id = clip.get("id", "")
        labels = labels_by_clip.get(clip_id, [])
        formation = _get_formation(labels)
        play_type = _get_play_type(labels)
        if formation and play_type:
            formation_plays[formation][play_type] += 1
            formation_evidence[formation].append(clip_id)

    return _build_tendency_results(
        formation_plays,
        formation_evidence,
        grouping_key_name="formation",
        min_plays=3,
    )



def _compute_motion_tendencies(
    clips: list[dict[str, Any]],
    labels_by_clip: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Run/pass rate with and without pre-snap motion."""
    motion_plays: Counter[str] = Counter()
    no_motion_plays: Counter[str] = Counter()
    motion_evidence: list[str] = []
    no_motion_evidence: list[str] = []

    for clip in clips:
        clip_id = clip.get("id", "")
        labels = labels_by_clip.get(clip_id, [])
        has_motion = _get_motion_detected(labels)
        play_type = _get_play_type(labels)
        if not play_type:
            continue
        if has_motion:
            motion_plays[play_type] += 1
            motion_evidence.append(clip_id)
        else:
            no_motion_plays[play_type] += 1
            no_motion_evidence.append(clip_id)

    motion_total = sum(motion_plays.values())
    no_motion_total = sum(no_motion_plays.values())

    return {
        "with_motion": {
            "total": motion_total,
            "run_count": motion_plays.get("run", 0),
            "pass_count": motion_plays.get("pass", 0),
            "run_rate": round(motion_plays.get("run", 0) / max(motion_total, 1), 3),
            "pass_rate": round(motion_plays.get("pass", 0) / max(motion_total, 1), 3),
            "evidence_clip_ids": _limit_evidence(motion_evidence),
            "low_sample": motion_total < LOW_SAMPLE_THRESHOLD,
        },
        "without_motion": {
            "total": no_motion_total,
            "run_count": no_motion_plays.get("run", 0),
            "pass_count": no_motion_plays.get("pass", 0),
            "run_rate": round(no_motion_plays.get("run", 0) / max(no_motion_total, 1), 3),
            "pass_rate": round(no_motion_plays.get("pass", 0) / max(no_motion_total, 1), 3),
            "evidence_clip_ids": _limit_evidence(no_motion_evidence),
            "low_sample": no_motion_total < LOW_SAMPLE_THRESHOLD,
        },
    }



def _compute_field_zone_tendencies(
    clips: list[dict[str, Any]],
    labels_by_clip: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    zone_plays: dict[str, Counter[str]] = defaultdict(Counter)
    zone_evidence: dict[str, list[str]] = defaultdict(list)

    for clip in clips:
        clip_id = clip.get("id", "")
        labels = labels_by_clip.get(clip_id, [])
        play_type = _get_play_type(labels)
        field_zone = clip.get("field_zone", "mid_field") or "mid_field"
        if play_type:
            zone_plays[field_zone][play_type] += 1
            zone_evidence[field_zone].append(clip_id)

    return _build_tendency_results(
        zone_plays,
        zone_evidence,
        grouping_key_name="field_zone",
        min_plays=2,
    )



def _compute_personnel_tendencies(
    clips: list[dict[str, Any]],
    labels_by_clip: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    personnel_plays: dict[str, Counter[str]] = defaultdict(Counter)
    personnel_evidence: dict[str, list[str]] = defaultdict(list)

    for clip in clips:
        clip_id = clip.get("id", "")
        labels = labels_by_clip.get(clip_id, [])
        play_type = _get_play_type(labels)
        personnel = clip.get("personnel_grouping", "unknown") or "unknown"
        if play_type:
            personnel_plays[personnel][play_type] += 1
            personnel_evidence[personnel].append(clip_id)

    return _build_tendency_results(
        personnel_plays,
        personnel_evidence,
        grouping_key_name="personnel",
        min_plays=2,
    )



def _compute_down_distance_tendencies(
    clips: list[dict[str, Any]],
    labels_by_clip: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    plays: dict[tuple[int, str], Counter[str]] = defaultdict(Counter)
    evidence: dict[tuple[int, str], list[str]] = defaultdict(list)

    for clip in clips:
        clip_id = clip.get("id", "")
        labels = labels_by_clip.get(clip_id, [])
        play_type = _get_play_type(labels)
        down_distance_key = _get_down_distance_key(clip)
        if play_type and down_distance_key is not None:
            plays[down_distance_key][play_type] += 1
            evidence[down_distance_key].append(clip_id)

    results: list[dict[str, Any]] = []
    for (down, distance_bucket), counts in plays.items():
        total = sum(counts.values())
        if total < 2:
            continue
        results.append(
            {
                "down": down,
                "distance_bucket": distance_bucket,
                "total_plays": total,
                "run_count": counts.get("run", 0),
                "pass_count": counts.get("pass", 0),
                "run_rate": round(counts.get("run", 0) / total, 3),
                "pass_rate": round(counts.get("pass", 0) / total, 3),
                "evidence_clip_ids": _limit_evidence(evidence.get((down, distance_bucket), [])),
                "low_sample": total < LOW_SAMPLE_THRESHOLD,
            }
        )

    return sorted(
        results,
        key=lambda result: (result["down"], DISTANCE_BUCKET_ORDER.get(result["distance_bucket"], 99)),
    )



def _compute_concept_family_distribution(
    clips: list[dict[str, Any]],
    labels_by_clip: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    plays: dict[str, Counter[str]] = defaultdict(Counter)
    evidence: dict[tuple[str, str], list[str]] = defaultdict(list)

    for clip in clips:
        clip_id = clip.get("id", "")
        labels = labels_by_clip.get(clip_id, [])
        formation = _get_formation(labels)
        concept_family = _get_concept_family(labels)
        if formation and concept_family:
            plays[formation][concept_family] += 1
            evidence[(formation, concept_family)].append(clip_id)

    formation_totals = {formation: sum(counts.values()) for formation, counts in plays.items()}
    results: dict[str, list[dict[str, Any]]] = {}

    for formation, _ in sorted(
        formation_totals.items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        counts = plays[formation]
        total = sum(counts.values())
        if total == 0:
            continue

        entries: list[dict[str, Any]] = []
        for concept_family, count in counts.items():
            entries.append(
                {
                    "formation": formation,
                    "concept_family": concept_family,
                    "total_plays": count,
                    "rate": round(count / total, 3),
                    "evidence_clip_ids": _limit_evidence(evidence.get((formation, concept_family), [])),
                    "low_sample": count < LOW_SAMPLE_THRESHOLD,
                }
            )

        results[formation] = sorted(entries, key=lambda entry: entry["total_plays"], reverse=True)

    return results



def _compute_pre_snap_tells(
    clips: list[dict[str, Any]],
    labels_by_clip: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    plays: dict[str, Counter[str]] = defaultdict(Counter)
    evidence: dict[str, list[str]] = defaultdict(list)
    exposure_meta: dict[str, tuple[str, str]] = {}

    for clip in clips:
        clip_id = clip.get("id", "")
        labels = labels_by_clip.get(clip_id, [])
        play_type = _get_play_type(labels)
        formation = _get_formation(labels)
        if not play_type or not formation:
            continue

        motion_state = "with_motion" if _get_motion_detected(labels) else "without_motion"
        grouping_key = f"{formation}|{motion_state}"
        exposure_meta[grouping_key] = (formation, motion_state)
        plays[grouping_key][play_type] += 1
        evidence[grouping_key].append(clip_id)

    results: list[dict[str, Any]] = []
    for grouping_key, counts in plays.items():
        total = sum(counts.values())
        if total == 0:
            continue

        run_rate = round(counts.get("run", 0) / total, 3)
        pass_rate = round(counts.get("pass", 0) / total, 3)
        if run_rate < PRE_SNAP_TELL_THRESHOLD and pass_rate < PRE_SNAP_TELL_THRESHOLD:
            continue

        formation, motion_state = exposure_meta[grouping_key]
        lean = "run" if run_rate >= PRE_SNAP_TELL_THRESHOLD else "pass"
        lean_rate = run_rate if lean == "run" else pass_rate
        results.append(
            {
                "grouping_key": grouping_key,
                "formation": formation,
                "motion_state": motion_state,
                "total_plays": total,
                "lean": lean,
                "severity": "high" if lean_rate >= PRE_SNAP_TELL_HIGH_SEVERITY_THRESHOLD else "medium",
                "run_rate": run_rate,
                "pass_rate": pass_rate,
                "evidence_clip_ids": _limit_evidence(evidence.get(grouping_key, [])),
                "low_sample": total < LOW_SAMPLE_THRESHOLD,
                "message": (
                    f"Pre-snap tell from {formation} "
                    f"{MOTION_STATE_LABELS.get(motion_state, motion_state.replace('_', ' '))}: "
                    f"{lean_rate:.0%} {lean} ({total} plays)"
                ),
            }
        )

    return sorted(results, key=lambda result: result["total_plays"], reverse=True)



def _generate_alerts(
    formation_tendencies: list[dict[str, Any]],
    motion_tendencies: dict[str, Any],
    field_zone_tendencies: list[dict[str, Any]],
    personnel_tendencies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flag high-tendency outliers as exposure risks."""
    alerts: list[dict[str, Any]] = []

    for tendency in formation_tendencies:
        if tendency["total_plays"] >= 5:
            if tendency["run_rate"] >= TENDENCY_ALERT_THRESHOLD:
                alerts.append(
                    {
                        "alert_type": "formation_tendency",
                        "message": (
                            f"High run tendency from {tendency['formation']}: "
                            f"{tendency['run_rate']:.0%} ({tendency['total_plays']} plays)"
                        ),
                        "severity": "high" if tendency["run_rate"] >= 0.85 else "medium",
                        "data": tendency,
                    }
                )
            if tendency["pass_rate"] >= TENDENCY_ALERT_THRESHOLD:
                alerts.append(
                    {
                        "alert_type": "formation_tendency",
                        "message": (
                            f"High pass tendency from {tendency['formation']}: "
                            f"{tendency['pass_rate']:.0%} ({tendency['total_plays']} plays)"
                        ),
                        "severity": "high" if tendency["pass_rate"] >= 0.85 else "medium",
                        "data": tendency,
                    }
                )

    motion_data = motion_tendencies.get("with_motion", {})
    if motion_data.get("total", 0) >= 5:
        if motion_data.get("run_rate", 0) >= TENDENCY_ALERT_THRESHOLD:
            alerts.append(
                {
                    "alert_type": "motion_tendency",
                    "message": f"High run tendency after motion: {motion_data['run_rate']:.0%}",
                    "severity": "medium",
                    "data": motion_data,
                }
            )
        if motion_data.get("pass_rate", 0) >= TENDENCY_ALERT_THRESHOLD:
            alerts.append(
                {
                    "alert_type": "motion_tendency",
                    "message": f"High pass tendency after motion: {motion_data['pass_rate']:.0%}",
                    "severity": "medium",
                    "data": motion_data,
                }
            )

    for tendency in field_zone_tendencies:
        if tendency["total_plays"] >= 5:
            if tendency["run_rate"] >= TENDENCY_ALERT_THRESHOLD:
                alerts.append(
                    {
                        "alert_type": "field_zone_tendency",
                        "message": (
                            f"High run tendency in {tendency['field_zone']}: "
                            f"{tendency['run_rate']:.0%}"
                        ),
                        "severity": "medium",
                        "data": tendency,
                    }
                )
            if tendency["pass_rate"] >= TENDENCY_ALERT_THRESHOLD:
                alerts.append(
                    {
                        "alert_type": "field_zone_tendency",
                        "message": (
                            f"High pass tendency in {tendency['field_zone']}: "
                            f"{tendency['pass_rate']:.0%}"
                        ),
                        "severity": "medium",
                        "data": tendency,
                    }
                )

    for tendency in personnel_tendencies:
        if tendency["total_plays"] >= 5:
            if tendency["run_rate"] >= TENDENCY_ALERT_THRESHOLD:
                alerts.append(
                    {
                        "alert_type": "personnel_tendency",
                        "message": (
                            f"High run tendency from {tendency['personnel']}: "
                            f"{tendency['run_rate']:.0%}"
                        ),
                        "severity": "medium",
                        "data": tendency,
                    }
                )
            if tendency["pass_rate"] >= TENDENCY_ALERT_THRESHOLD:
                alerts.append(
                    {
                        "alert_type": "personnel_tendency",
                        "message": (
                            f"High pass tendency from {tendency['personnel']}: "
                            f"{tendency['pass_rate']:.0%}"
                        ),
                        "severity": "medium",
                        "data": tendency,
                    }
                )

    return alerts
