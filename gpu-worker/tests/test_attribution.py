"""Tests for throw/catch attribution (Issue #134)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.ball.attribution import (
    attribute_catch,
    attribute_throw,
    positions_by_frame,
)
from pipeline.ball.ball_tracker import BallTrackPoint


def _pt(frame: int, x: float, y: float) -> BallTrackPoint:
    return BallTrackPoint(frame, x, y, 0.0, 0.0, observed=True)


def test_throw_attributed_to_nearest_qb() -> None:
    ball = [_pt(2, 26.0, 5.0)]
    players = {2: {"qb": (26.5, 5.2), "wr": (40.0, 10.0)}}
    assert attribute_throw(ball, players, 2) == "qb"


def test_throw_unmatched_when_too_far() -> None:
    ball = [_pt(2, 26.0, 5.0)]
    players = {2: {"qb": (40.0, 20.0)}}  # > 3 yd away
    assert attribute_throw(ball, players, 2) is None


def test_catch_attributed_to_nearest_receiver() -> None:
    ball = [_pt(6, 35.0, 10.0)]
    players = {6: {"wr": (35.2, 10.1), "cb": (38.0, 12.0)}}
    assert attribute_catch(ball, players, 6) == "wr"


def test_catch_uses_velocity_prediction_to_disambiguate() -> None:
    ball = [_pt(6, 35.0, 10.0)]
    # Two players equidistant now, but only 'wr' is closing on the ball.
    players = {6: {"wr": (33.0, 10.0), "cb": (37.0, 10.0)}}
    vels = {"wr": (2.0, 0.0), "cb": (0.0, 0.0)}
    assert attribute_catch(ball, players, 6, player_velocities=vels) == "wr"


def test_positions_by_frame_index() -> None:
    tracklets = [
        {"id": "a", "track_points": [
            {"frame_number": 1, "field_x": 10.0, "field_y": 2.0},
            {"frame_number": 2, "field_x": 11.0, "field_y": 2.5},
        ]},
        {"id": "b", "track_points": [
            {"frame_number": 1, "field_x": 20.0, "field_y": -3.0},
        ]},
    ]
    idx = positions_by_frame(tracklets)
    assert idx[1]["a"] == (10.0, 2.0)
    assert idx[1]["b"] == (20.0, -3.0)
    assert idx[2]["a"] == (11.0, 2.5)
