"""Throw / catch attribution (Issue #134).

Attribution rules (research report §3.6.4):

* **Throw origin → QB.** The thrower is the player nearest the ball at the
  first airborne frame; the match is rejected if that player is more than
  3 yd away (the ball was not actually released from a passer).
* **Catch point → receiver.** The catcher is the player whose predicted
  position best intersects the ball's landing point. When the prediction is
  ambiguous we fall back to the player nearest the ball at the catch frame.

All positions are field-plane yards. Pure Python — no weights, no router.
"""

from __future__ import annotations

import math
from typing import Any

import structlog

from pipeline.ball.ball_tracker import BallTrackPoint

log = structlog.get_logger(__name__)

THROW_MAX_DIST_YD: float = 3.0
CATCH_MAX_DIST_YD: float = 3.0


def _ball_at(ball_track: list[BallTrackPoint], frame: int) -> BallTrackPoint | None:
    for p in ball_track:
        if p.frame == frame:
            return p
    return None


def _nearest(
    point: tuple[float, float], players: dict[str, tuple[float, float]]
) -> tuple[str | None, float]:
    best_id: str | None = None
    best_d = math.inf
    for tid, (px, py) in players.items():
        d = math.hypot(px - point[0], py - point[1])
        if d < best_d:
            best_id, best_d = tid, d
    return best_id, best_d


def attribute_throw(
    ball_track: list[BallTrackPoint],
    player_positions: dict[int, dict[str, tuple[float, float]]],
    first_airborne_frame: int,
    *,
    max_dist_yd: float = THROW_MAX_DIST_YD,
) -> str | None:
    """Return the QB track id, or ``None`` if no player is within range."""
    ball = _ball_at(ball_track, first_airborne_frame)
    if ball is None:
        return None
    players = player_positions.get(first_airborne_frame, {})
    who, dist = _nearest((ball.x, ball.y), players)
    if who is None or dist > max_dist_yd:
        log.info("throw_attribution_unmatched", frame=first_airborne_frame, dist=dist)
        return None
    log.info("throw_attributed", qb_id=who, frame=first_airborne_frame, dist=round(dist, 3))
    return who


def attribute_catch(
    ball_track: list[BallTrackPoint],
    player_positions: dict[int, dict[str, tuple[float, float]]],
    catch_frame: int,
    *,
    max_dist_yd: float = CATCH_MAX_DIST_YD,
    player_velocities: dict[str, tuple[float, float]] | None = None,
) -> str | None:
    """Return the receiver track id at the catch point.

    When ``player_velocities`` (yd/s) are supplied we project each player one
    frame toward the ball and pick the closest predicted intersection; this
    disambiguates two players converging on the same point. Otherwise we use
    the player nearest the ball at the catch frame.
    """
    ball = _ball_at(ball_track, catch_frame)
    if ball is None:
        return None
    players = player_positions.get(catch_frame, {})
    if not players:
        return None

    if player_velocities:
        # Predict where each player will be when the ball arrives (one step).
        predicted: dict[str, tuple[float, float]] = {}
        for tid, (px, py) in players.items():
            vx, vy = player_velocities.get(tid, (0.0, 0.0))
            predicted[tid] = (px + vx, py + vy)
        who, dist = _nearest((ball.x, ball.y), predicted)
    else:
        who, dist = _nearest((ball.x, ball.y), players)

    if who is None or dist > max_dist_yd:
        log.info("catch_attribution_unmatched", frame=catch_frame, dist=dist)
        return None
    log.info("catch_attributed", receiver_id=who, frame=catch_frame, dist=round(dist, 3))
    return who


def positions_by_frame(
    tracklets: list[dict[str, Any]],
) -> dict[int, dict[str, tuple[float, float]]]:
    """Index tracklets as ``frame → track_id → (field_x, field_y)``."""
    out: dict[int, dict[str, tuple[float, float]]] = {}
    for t in tracklets:
        tid = str(t.get("id", ""))
        if not tid:
            continue
        for pt in t.get("track_points", []):
            fx, fy, fn = pt.get("field_x"), pt.get("field_y"), pt.get("frame_number")
            if fx is None or fy is None or fn is None:
                continue
            out.setdefault(int(fn), {})[tid] = (float(fx), float(fy))
    return out
