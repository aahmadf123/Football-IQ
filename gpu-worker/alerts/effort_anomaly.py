"""Effort anomaly alert (Issue #16).

Flags a player whose sprint-to-ball is significantly below the session average.
Uses a configurable SD threshold (default: 1.5 SD below mean).

Alert governance (non-negotiable):
  - Alerts are NEVER shown to players.
  - Every alert carries: confidence, clip_uri, player_id, timestamp,
    position_group.

Input:
    sprint_value    — player's sprint-to-ball max speed (yards/second) for
                      the current period/rep.
    session_sprints — all sprint-to-ball values collected this session
                      (including the current rep, so len >= 2 is required
                      before anomaly detection runs).
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime
from typing import Any

import structlog

log = structlog.get_logger(__name__)

DEFAULT_THRESHOLD_SD: float = 1.5
DEFAULT_MIN_SESSION_REPS: int = 3


def run(
    player_id: str,
    clip_id: str,
    clip_uri: str,
    position_group: str,
    sprint_value: float,
    session_sprints: list[float],
    *,
    threshold_sd: float = DEFAULT_THRESHOLD_SD,
    min_session_reps: int = DEFAULT_MIN_SESSION_REPS,
    confidence: float = 0.60,
) -> list[dict[str, Any]]:
    """Flag an effort anomaly if sprint-to-ball is below session average.

    Args:
        player_id:       DB UUID of the player.
        clip_id:         DB UUID of the current clip.
        clip_uri:        Evidence clip URI.
        position_group:  e.g. "WR", "DB".
        sprint_value:    Current sprint-to-ball value (yd/s).
        session_sprints: All sprint values from this session (yd/s list).
        threshold_sd:    SDs below mean to trigger alert (default 1.5).
        min_session_reps: Minimum reps before detection runs (default 3).
        confidence:      Confidence score carried on the alert.

    Returns:
        List with one alert dict if anomaly detected; empty list otherwise.
    """
    if len(session_sprints) < min_session_reps:
        return []

    try:
        mean = statistics.mean(session_sprints)
        stdev = statistics.stdev(session_sprints)
    except statistics.StatisticsError:
        return []

    if stdev < 1e-6:
        return []

    z_score = (sprint_value - mean) / stdev

    if z_score > -threshold_sd:
        return []

    deviation = abs(z_score)
    severity = "high" if deviation >= 2.5 else "medium"
    log.info(
        "effort_anomaly_alert",
        player_id=player_id,
        sprint_value=sprint_value,
        session_mean=round(mean, 3),
        deviation_sd=round(deviation, 2),
        severity=severity,
    )
    return [
        {
            "alert_type": "effort_anomaly",
            "player_id": player_id,
            "clip_id": clip_id,
            "clip_uri": clip_uri,
            "position_group": position_group,
            "metric_name": "sprint_to_ball",
            "metric_value": round(sprint_value, 3),
            "session_mean": round(mean, 3),
            "session_stdev": round(stdev, 3),
            "deviation_sd": round(deviation, 3),
            "threshold_sd": threshold_sd,
            "confidence": round(confidence, 3),
            "severity": severity,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    ]
