"""Tendency-break engine (Issue #137) — the canonical pipeline-side engine.

The single most coaching-actionable output of the vision pipeline: it turns the
labels coming out of the signal extractor (#135) into statements like
*"On 2nd-and-7+ in your own territory you run 81% of the time from 11 personnel"*
and surfaces them as alerts the coach can act on before next practice.

Two alert families (both deterministic counting — no model weights, not routed
through the model router, runs identically in both priority buckets):

1. **Season tendencies** — for each
   ``(formation × personnel × field_zone × down_distance)`` tuple with > 8
   plays whose pass-rate is > 0.80 or < 0.20, emit a ``season_tendency`` alert.
2. **In-game pattern breaks** — when the current game's pass-rate for a tuple
   diverges from the season baseline by more than 20 percentage points (with
   n ≥ 5 plays this game), emit a ``pattern_break`` alert.

:func:`to_alert_payload` shapes an alert into the body the backend
``POST /api/v1/alerts`` endpoint accepts (``alert_type="formation_tendency"``),
so :mod:`pipeline.stage_self_scout` can persist them via ``backend.create_alert``.

This mirrors the backend's ``app.analytics.tendency_break`` module — the two
services cannot share code, so the deterministic football math lives in both,
kept intentionally small and identical.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

# ── Thresholds (Issue #137 algorithm) ──────────────────────────────────────────

MIN_SAMPLES_TO_ALERT = 8  # strictly greater than this many plays
HIGH_PASS_RATE = 0.80
LOW_PASS_RATE = 0.20
HIGH_SEVERITY_PASS_RATE = 0.90
HIGH_SEVERITY_RUN_RATE = 0.10
PATTERN_BREAK_MIN_GAME_PLAYS = 5
PATTERN_BREAK_MIN_DIVERGENCE = 0.20
EVIDENCE_CLIP_LIMIT = 3  # 3 representative clips per alert

TENDENCY_POSITION_GROUP = "OFFENSE"
TENDENCY_ALERT_TYPE = "formation_tendency"

RUN = "run"
PASS = "pass"  # noqa: S105 — a football pass, not a secret


# ── Play model ─────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class Play:
    clip_id: str
    play_type: str
    formation: str | None = None
    personnel: str | None = None
    field_zone: str | None = None
    down: int | None = None
    distance_bucket: str | None = None

    @property
    def down_distance(self) -> str:
        if self.down is None or self.distance_bucket is None:
            return "any"
        return f"{self.down}-{self.distance_bucket}"

    def bucket_key(self) -> tuple[str, str, str, str]:
        return (
            self.formation or "unknown",
            self.personnel or "unknown",
            self.field_zone or "unknown",
            self.down_distance,
        )


@dataclass(slots=True)
class TendencyBreakAlert:
    grouping_key: str
    tendency_kind: str
    lean: str
    total_plays: int
    run_count: int
    pass_count: int
    run_rate: float
    pass_rate: float
    severity: str
    confidence: float
    message: str
    evidence_clip_ids: list[str]
    source: str
    baseline_pass_rate: float | None = None
    divergence_pp: float | None = None
    baseline_source: str | None = None


# ── Label parsing (self-contained; mirrors stage_self_scout) ────────────────────


def _label_text(label_value: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in label_value.values():
        if isinstance(value, str | int | float | bool):
            parts.append(str(value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str | int | float | bool):
                    parts.append(str(item))
    return " ".join(parts).lower().replace("_", " ")


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    tokens = set(text.split())
    for phrase in phrases:
        normalized = phrase.lower().replace("_", " ")
        if " " in normalized:
            if normalized in text:
                return True
        elif normalized in tokens:
            return True
    return False


def play_type_from_labels(labels: list[dict[str, Any]]) -> str | None:
    for lbl in labels:
        label_type = lbl.get("label_type", "")
        label_value = lbl.get("label_value", {}) or {}
        if label_type == "play_concept":
            concept = _label_text(label_value)
            if _contains_any(concept, ("run", "zone", "power", "counter", "draw", "sweep")):
                return RUN
            if _contains_any(concept, ("pass", "screen", "play_action", "rpo")):
                return PASS
        if label_type == "play_direction":
            return RUN
    return None


def formation_from_labels(labels: list[dict[str, Any]]) -> str | None:
    for lbl in labels:
        if lbl.get("label_type") == "offensive_formation":
            formation = (lbl.get("label_value", {}) or {}).get("formation")
            if isinstance(formation, str) and formation:
                return formation
    return None


def distance_bucket(distance: Any) -> str | None:
    try:
        value = float(distance)
    except (TypeError, ValueError):
        return None
    if value <= 3:
        return "short"
    if value <= 6:
        return "medium"
    return "long"


def build_plays(
    clips: list[dict[str, Any]],
    labels_by_clip: dict[str, list[dict[str, Any]]],
) -> list[Play]:
    plays: list[Play] = []
    for clip in clips:
        clip_id = str(clip.get("id", ""))
        if not clip_id:
            continue
        labels = labels_by_clip.get(clip_id, [])
        play_type = play_type_from_labels(labels)
        if play_type is None:
            continue
        down_raw = clip.get("down")
        try:
            down = int(down_raw) if down_raw is not None else None
        except (TypeError, ValueError):
            down = None
        if down is not None and (down < 1 or down > 4):
            down = None
        plays.append(
            Play(
                clip_id=clip_id,
                play_type=play_type,
                formation=formation_from_labels(labels),
                personnel=clip.get("personnel_grouping") or None,
                field_zone=clip.get("field_zone") or None,
                down=down,
                distance_bucket=distance_bucket(clip.get("distance")) if down is not None else None,
            )
        )
    return plays


# ── Aggregation ────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class _Bucket:
    counts: Counter[str] = field(default_factory=Counter)
    clip_ids: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.counts.get(RUN, 0) + self.counts.get(PASS, 0)

    @property
    def pass_rate(self) -> float:
        return self.counts.get(PASS, 0) / self.total if self.total else 0.0

    @property
    def run_rate(self) -> float:
        return self.counts.get(RUN, 0) / self.total if self.total else 0.0


def aggregate(plays: list[Play]) -> dict[tuple[str, str, str, str], _Bucket]:
    buckets: dict[tuple[str, str, str, str], _Bucket] = defaultdict(_Bucket)
    for play in plays:
        bucket = buckets[play.bucket_key()]
        bucket.counts[play.play_type] += 1
        bucket.clip_ids.append(play.clip_id)
    return buckets


def season_pass_rate_by_bucket(plays: list[Play]) -> dict[tuple[str, str, str, str], float]:
    return {key: bucket.pass_rate for key, bucket in aggregate(plays).items() if bucket.total}


def _grouping_label(key: tuple[str, str, str, str]) -> str:
    formation, personnel, field_zone, down_distance = key
    parts = [formation]
    if personnel and personnel != "unknown":
        parts.append(f"{personnel} pers")
    if field_zone and field_zone != "unknown":
        parts.append(field_zone.replace("_", " "))
    if down_distance and down_distance != "any":
        parts.append(down_distance)
    return " · ".join(parts)


def _severity_for_pass_rate(pass_rate: float) -> str:
    if pass_rate >= HIGH_SEVERITY_PASS_RATE or pass_rate <= HIGH_SEVERITY_RUN_RATE:
        return "high"
    return "medium"


def _confidence_from_samples(total: int) -> float:
    return round(min(0.95, total / (total + 6.0)), 3)


# ── Alert generation ─────────────────────────────────────────────────────────────


def season_tendency_alerts(
    plays: list[Play],
    *,
    min_samples: int = MIN_SAMPLES_TO_ALERT,
    high_pass_rate: float = HIGH_PASS_RATE,
    low_pass_rate: float = LOW_PASS_RATE,
    source: str = "toledo_film",
) -> list[TendencyBreakAlert]:
    alerts: list[TendencyBreakAlert] = []
    for key, bucket in aggregate(plays).items():
        if bucket.total <= min_samples:
            continue
        pass_rate = bucket.pass_rate
        if low_pass_rate < pass_rate < high_pass_rate:
            continue
        lean = PASS if pass_rate >= high_pass_rate else RUN
        lean_rate = pass_rate if lean == PASS else bucket.run_rate
        label = _grouping_label(key)
        alerts.append(
            TendencyBreakAlert(
                grouping_key=label,
                tendency_kind="season_tendency",
                lean=lean,
                total_plays=bucket.total,
                run_count=bucket.counts.get(RUN, 0),
                pass_count=bucket.counts.get(PASS, 0),
                run_rate=round(bucket.run_rate, 3),
                pass_rate=round(pass_rate, 3),
                severity=_severity_for_pass_rate(pass_rate),
                confidence=_confidence_from_samples(bucket.total),
                message=(
                    f"{label}: {lean_rate:.0%} {lean} on {bucket.total} plays — "
                    f"opponents can key this tendency."
                ),
                evidence_clip_ids=bucket.clip_ids[:EVIDENCE_CLIP_LIMIT],
                source=source,
            )
        )
    return sorted(alerts, key=lambda a: a.total_plays, reverse=True)


def pattern_break_alerts(
    game_plays: list[Play],
    season_baseline: dict[tuple[str, str, str, str], float],
    *,
    min_game_plays: int = PATTERN_BREAK_MIN_GAME_PLAYS,
    min_divergence: float = PATTERN_BREAK_MIN_DIVERGENCE,
    source: str = "toledo_film",
    baseline_source: str = "season_baseline",
) -> list[TendencyBreakAlert]:
    alerts: list[TendencyBreakAlert] = []
    for key, bucket in aggregate(game_plays).items():
        if bucket.total < min_game_plays:
            continue
        baseline = season_baseline.get(key)
        if baseline is None:
            continue
        divergence = bucket.pass_rate - baseline
        if abs(divergence) <= min_divergence:
            continue
        lean = PASS if divergence > 0 else RUN
        label = _grouping_label(key)
        direction = "more pass-heavy" if divergence > 0 else "more run-heavy"
        alerts.append(
            TendencyBreakAlert(
                grouping_key=label,
                tendency_kind="pattern_break",
                lean=lean,
                total_plays=bucket.total,
                run_count=bucket.counts.get(RUN, 0),
                pass_count=bucket.counts.get(PASS, 0),
                run_rate=round(bucket.run_rate, 3),
                pass_rate=round(bucket.pass_rate, 3),
                severity="high" if abs(divergence) >= 0.35 else "medium",
                confidence=_confidence_from_samples(bucket.total),
                message=(
                    f"{label}: this game is {abs(divergence):.0%} {direction} "
                    f"than the season baseline ({baseline:.0%} → {bucket.pass_rate:.0%} pass, "
                    f"{bucket.total} plays)."
                ),
                evidence_clip_ids=bucket.clip_ids[:EVIDENCE_CLIP_LIMIT],
                source=source,
                baseline_pass_rate=round(baseline, 3),
                divergence_pp=round(divergence, 3),
                baseline_source=baseline_source,
            )
        )
    return sorted(alerts, key=lambda a: abs(a.divergence_pp or 0), reverse=True)


def _first_evidence_uuid(clip_ids: list[str]) -> str | None:
    """Best-effort: the first evidence clip id, used to link the alert."""
    return clip_ids[0] if clip_ids else None


def to_alert_payload(alert: TendencyBreakAlert, *, session_id: str | None = None) -> dict[str, Any]:
    """Shape a tendency-break alert into a ``POST /api/v1/alerts`` body."""
    metric_value: dict[str, Any] = {
        "tendency_kind": alert.tendency_kind,
        "grouping_key": alert.grouping_key,
        "lean": alert.lean,
        "total_plays": alert.total_plays,
        "run_count": alert.run_count,
        "pass_count": alert.pass_count,
        "run_rate": alert.run_rate,
        "pass_rate": alert.pass_rate,
        "evidence_clip_ids": alert.evidence_clip_ids,
        "source": alert.source,
        "experimental": False,
        "message": alert.message,
    }
    if alert.baseline_pass_rate is not None:
        metric_value["baseline_pass_rate"] = alert.baseline_pass_rate
    if alert.divergence_pp is not None:
        metric_value["divergence_pp"] = alert.divergence_pp
    if alert.baseline_source is not None:
        metric_value["baseline_source"] = alert.baseline_source

    payload: dict[str, Any] = {
        "position_group": TENDENCY_POSITION_GROUP,
        "alert_type": TENDENCY_ALERT_TYPE,
        "severity": alert.severity,
        "confidence": alert.confidence,
        "metric_name": alert.grouping_key[:255],
        "metric_value": metric_value,
    }
    clip_id = _first_evidence_uuid(alert.evidence_clip_ids)
    if clip_id is not None:
        payload["clip_id"] = clip_id
    if session_id is not None:
        payload["session_id"] = session_id
    return payload


def generate_alert_payloads(
    season_clips: list[dict[str, Any]],
    labels_by_clip: dict[str, list[dict[str, Any]]],
    *,
    game_clip_ids: set[str] | None = None,
    season_session_id: str = "season",
    game_session_id: str | None = None,
) -> list[dict[str, Any]]:
    """End-to-end: cached clips/labels → persistable alert payloads.

    ``game_clip_ids`` (if given) selects the subset of clips that make up the
    current game, so in-game pattern breaks are computed against the season
    baseline derived from the full set.
    """
    season_plays = build_plays(season_clips, labels_by_clip)
    payloads = [
        to_alert_payload(a, session_id=season_session_id)
        for a in season_tendency_alerts(season_plays)
    ]

    if game_clip_ids:
        game_clips = [c for c in season_clips if str(c.get("id", "")) in game_clip_ids]
        game_plays = build_plays(game_clips, labels_by_clip)
        baseline = season_pass_rate_by_bucket(season_plays)
        payloads.extend(
            to_alert_payload(a, session_id=game_session_id)
            for a in pattern_break_alerts(game_plays, baseline)
        )
    return payloads
