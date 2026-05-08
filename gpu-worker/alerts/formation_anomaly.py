"""Formation execution anomaly alert (Issue #16).

Flags a player whose calibrated field position at snap deviates significantly
from the expected position in the called formation baseline.  Uses Euclidean
displacement (yards) as the metric.

Alert governance (non-negotiable):
  - Alerts are NEVER shown to players.
  - Every alert carries: confidence, clip_uri, player_id, timestamp,
    position_group.

Input:
    observed_x / observed_y   — calibrated field coordinates of the player
                                 at snap (yards).
    expected_x / expected_y   — expected coordinates from the formation
                                 baseline template.
    formation_name            — called formation label (e.g. "11 Spread").
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

import structlog

log = structlog.get_logger(__name__)

DEFAULT_THRESHOLD_YARDS: float = 3.0


def run(
    player_id: str,
    clip_id: str,
    clip_uri: str,
    position_group: str,
    observed_x: float,
    observed_y: float,
    expected_x: float,
    expected_y: float,
    formation_name: str,
    *,
    threshold_yards: float = DEFAULT_THRESHOLD_YARDS,
    confidence: float = 0.55,
) -> list[dict[str, Any]]:
    """Flag a formation alignment anomaly.

    Args:
        player_id:       DB UUID of the player.
        clip_id:         DB UUID of the current clip.
        clip_uri:        Evidence clip URI.
        position_group:  e.g. "OL", "WR".
        observed_x/y:    Calibrated field coordinates at snap.
        expected_x/y:    Expected formation baseline coordinates.
        formation_name:  Label of the called formation.
        threshold_yards: Yards off-position to trigger alert (default 3.0).
        confidence:      Confidence score carried on the alert.

    Returns:
        List with one alert dict if displacement >= threshold; empty otherwise.
    """
    displacement = math.sqrt(
        (observed_x - expected_x) ** 2 + (observed_y - expected_y) ** 2
    )

    if displacement < threshold_yards:
        return []

    severity = "high" if displacement >= threshold_yards * 1.5 else "medium"
    log.info(
        "formation_anomaly_alert",
        player_id=player_id,
        formation_name=formation_name,
        displacement_yards=round(displacement, 2),
        severity=severity,
    )
    return [
        {
            "alert_type": "formation_anomaly",
            "player_id": player_id,
            "clip_id": clip_id,
            "clip_uri": clip_uri,
            "position_group": position_group,
            "metric_name": "formation_alignment",
            "metric_value": round(displacement, 3),
            "formation_name": formation_name,
            "expected_position": {"x": round(expected_x, 3), "y": round(expected_y, 3)},
            "observed_position": {"x": round(observed_x, 3), "y": round(observed_y, 3)},
            "displacement_yards": round(displacement, 3),
            "threshold_yards": threshold_yards,
            "confidence": round(confidence, 3),
            "severity": severity,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    ]
