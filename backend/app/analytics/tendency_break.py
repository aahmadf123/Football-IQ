"""Tendency-break engine (Issue #137) — pure, deterministic football math.

Coaches care about one thing more than any other vision-pipeline output: "what
does our film *tell* the opponent?". This module turns labeled Toledo plays into
coaching-actionable tendency-break alerts:

1. **Season tendencies** — for each
   ``(formation × personnel × field_zone × down_distance)`` tuple with enough
   samples, compute the pass rate. When a tuple is run-or-pass lopsided beyond
   the alert thresholds (default: pass-rate > 0.80 or < 0.20, with n > 8) it
   becomes a ``season_tendency`` alert.
2. **In-game pattern breaks** — compare the current game's tendency for a tuple
   to the season baseline. When the current-game pass-rate diverges more than
   the threshold (default 20 percentage points, with n ≥ 5 plays this game) it
   becomes a ``pattern_break`` alert the coach can act on *before* the next
   series.

The module is intentionally free of FastAPI/DB/HTTP imports so it can be unit
tested in isolation and reused by the GPU-worker-equivalent engine. It works
entirely from *cached/project data* — the labeled clips the platform already
holds — and can optionally blend a cached CFBD pass-rate baseline (see
:func:`cfbd_pass_rate_baseline`) without ever calling CFBD at request time.

Nothing here is routed through the model router: it is deterministic counting,
exactly like the pre-snap Bayesian math, and loads no model weights.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

# ── Tunable thresholds (Issue #137 algorithm) ──────────────────────────────────

# A tuple needs at least this many plays before we *surface* its tendency.
MIN_SAMPLES_TO_SURFACE = 5
# A tuple needs strictly more than this many plays before it can *alert*.
MIN_SAMPLES_TO_ALERT = 8
# Pass-rate bands that make a tuple coaching-actionable.
HIGH_PASS_RATE = 0.80
LOW_PASS_RATE = 0.20
# Severity escalates when the lean is extreme.
HIGH_SEVERITY_PASS_RATE = 0.90
HIGH_SEVERITY_RUN_RATE = 0.10
# In-game pattern break: minimum plays this game and minimum divergence.
PATTERN_BREAK_MIN_GAME_PLAYS = 5
PATTERN_BREAK_MIN_DIVERGENCE = 0.20
# Representative clips linked per alert (Issue #137: "3 representative clips").
EVIDENCE_CLIP_LIMIT = 3

RUN = "run"
PASS = "pass"  # noqa: S105 — a football pass, not a secret


# ── Play model ─────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class Play:
    """One labeled play reduced to the dimensions tendency-break cares about."""

    clip_id: str
    play_type: str  # "run" | "pass"
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
        """The (formation × personnel × field_zone × down_distance) tuple."""
        return (
            self.formation or "unknown",
            self.personnel or "unknown",
            self.field_zone or "unknown",
            self.down_distance,
        )


@dataclass(slots=True)
class TendencyBreakAlert:
    """A single coaching-actionable tendency or pattern break."""

    grouping_key: str
    tendency_kind: str  # "season_tendency" | "pattern_break"
    lean: str  # "run" | "pass"
    total_plays: int
    run_count: int
    pass_count: int
    run_rate: float
    pass_rate: float
    severity: str  # "low" | "medium" | "high"
    confidence: float
    message: str
    evidence_clip_ids: list[str]
    source: str
    experimental: bool = False
    baseline_pass_rate: float | None = None
    divergence_pp: float | None = None
    baseline_source: str | None = None

    def metric_value(self) -> dict[str, Any]:
        """JSON-serializable payload stored on the persisted alert."""
        payload: dict[str, Any] = {
            "tendency_kind": self.tendency_kind,
            "grouping_key": self.grouping_key,
            "lean": self.lean,
            "total_plays": self.total_plays,
            "run_count": self.run_count,
            "pass_count": self.pass_count,
            "run_rate": self.run_rate,
            "pass_rate": self.pass_rate,
            "evidence_clip_ids": self.evidence_clip_ids,
            "source": self.source,
            "experimental": self.experimental,
            "message": self.message,
        }
        if self.baseline_pass_rate is not None:
            payload["baseline_pass_rate"] = self.baseline_pass_rate
        if self.divergence_pp is not None:
            payload["divergence_pp"] = self.divergence_pp
        if self.baseline_source is not None:
            payload["baseline_source"] = self.baseline_source
        return payload


# ── Label parsing (self-contained; mirrors stage_self_scout conventions) ────────


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
    """Infer run/pass from a clip's labels (None when undetermined)."""
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
    """Reduce cached clips + labels to the Play rows the engine consumes."""
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
    """A bounded confidence that grows with sample size (caps at 0.95)."""
    return round(min(0.95, total / (total + 6.0)), 3)


# ── Alert generation ────────────────────────────────────────────────────────────


def season_tendency_alerts(
    plays: list[Play],
    *,
    min_samples: int = MIN_SAMPLES_TO_ALERT,
    high_pass_rate: float = HIGH_PASS_RATE,
    low_pass_rate: float = LOW_PASS_RATE,
    source: str = "toledo_film",
) -> list[TendencyBreakAlert]:
    """Lopsided season tendencies → ``season_tendency`` alerts.

    A tuple alerts when it has strictly more than ``min_samples`` plays and its
    pass rate is >= ``high_pass_rate`` (pass-heavy) or <= ``low_pass_rate``
    (run-heavy).
    """
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
    """In-game divergence from the season baseline → ``pattern_break`` alerts.

    Fires when, for a tuple, the current game has >= ``min_game_plays`` plays
    and the game pass-rate diverges from the season baseline by more than
    ``min_divergence`` (a fraction, e.g. 0.20 == 20 percentage points).
    """
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


def season_pass_rate_by_bucket(plays: list[Play]) -> dict[tuple[str, str, str, str], float]:
    """Baseline pass-rate per tuple, used as the comparison for pattern breaks."""
    return {key: bucket.pass_rate for key, bucket in aggregate(plays).items() if bucket.total}


# ── Cached CFBD baseline (Issues #161-#163) ─────────────────────────────────────


def cfbd_pass_rate_baseline(cfbd_plays: list[dict[str, Any]]) -> float | None:
    """Overall pass rate derived from cached CFBD play rows.

    CFBD ``play_type`` values are free-text (e.g. "Pass Reception", "Rush",
    "Sack"). We classify pass-vs-run by keyword and ignore non-scrimmage plays
    (kicks, punts, penalties, timeouts) so the baseline reflects offensive
    run/pass split only. Returns ``None`` when there is no usable data so the
    caller can fall back to the project's own film baseline.

    This is *cached* data — read from the project's CFBD cache tables, never a
    live CFBD call — and is always source-labeled "cfbd" when surfaced.
    """
    passes = 0
    runs = 0
    for play in cfbd_plays:
        play_type = str(play.get("play_type") or "").lower()
        if not play_type:
            continue
        if any(k in play_type for k in ("pass", "sack", "interception")):
            passes += 1
        elif any(k in play_type for k in ("rush", "run")):
            runs += 1
        # everything else (kickoff, punt, field goal, penalty, timeout) ignored
    total = passes + runs
    if total == 0:
        return None
    return round(passes / total, 3)
