"""Tests for the ball state machine (Issue #134)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.ball.ball_state_machine import (
    BallState,
    BallStateMachine,
    validate,
)
from pipeline.ball.ball_tracker import BallTrackPoint


def _pt(frame: int, x: float, y: float, vx: float, vy: float) -> BallTrackPoint:
    return BallTrackPoint(frame, x, y, vx, vy, observed=True)


def _pass_track() -> list[BallTrackPoint]:
    return [
        _pt(0, 20.0, 0.0, 0.0, 0.0),     # snap, at QB
        _pt(1, 22.0, 2.0, 18.0, 12.0),   # accelerating, still near QB
        _pt(2, 26.0, 5.0, 18.0, 12.0),   # fast + clear of QB → throw
        _pt(3, 30.0, 8.0, 16.0, 10.0),
        _pt(4, 33.0, 9.0, 10.0, 6.0),
        _pt(5, 35.0, 10.0, 4.0, 2.0),
        _pt(6, 35.0, 10.0, 1.0, 0.0),    # settled at receiver → catch
        _pt(7, 35.0, 10.0, 0.5, 0.0),
    ]


def _players(receiver_at_catch: tuple[float, float] = (35.0, 10.0)) -> dict:
    pos = {}
    for f in range(0, 9):
        pos[f] = {
            "qb": (20.0, 0.0),
            "wr": receiver_at_catch,
            "cb": (45.0, 12.0),
        }
    return pos


def test_pass_completion_path() -> None:
    sm = BallStateMachine()
    result = sm.run(0, _pass_track(), _players(), qb_id="qb")
    states = result.states
    assert states[0] == BallState.SNAP
    assert BallState.THROWN in states
    assert BallState.IN_AIR in states
    assert result.final_state == BallState.CAUGHT
    assert result.throw_frame == 2
    assert result.catch_frame is not None
    assert validate([BallState.PRE_SNAP, *states])


def test_interception_when_defender_catches() -> None:
    sm = BallStateMachine()
    # Receiver pulled away; defender 'cb' sits on the landing point.
    players = _players()
    for f in players:
        players[f]["wr"] = (60.0, 20.0)
        players[f]["cb"] = (35.0, 10.0)
    result = sm.run(0, _pass_track(), players, qb_id="qb", defender_ids={"cb"})
    assert result.final_state == BallState.INT


def test_incomplete_when_nobody_near() -> None:
    sm = BallStateMachine()
    players = {f: {"qb": (20.0, 0.0)} for f in range(0, 9)}  # nobody downfield
    result = sm.run(0, _pass_track(), players, qb_id="qb")
    assert result.final_state == BallState.INCOMPLETE


def test_run_play_ends_in_tackle() -> None:
    sm = BallStateMachine()
    track = [_pt(f, 20.0 + 1.0 * f, 0.0, 8.0, 0.0) for f in range(0, 9)]
    players = {f: {"rb": (20.0 + 1.0 * f, 0.0)} for f in range(0, 9)}
    result = sm.run(0, track, players, end_of_play_frame=8)
    states = result.states
    assert BallState.CARRIED in states
    assert BallState.RUNNING in states
    assert result.final_state == BallState.TACKLE
    assert validate([BallState.PRE_SNAP, *states])


def test_run_play_touchdown_crosses_goal_line() -> None:
    sm = BallStateMachine()
    track = [_pt(f, 90.0 + 1.0 * f, 0.0, 8.0, 0.0) for f in range(0, 9)]
    players = {f: {"rb": (90.0 + 1.0 * f, 0.0)} for f in range(0, 9)}
    result = sm.run(0, track, players, end_of_play_frame=8, goal_line_x=95.0)
    assert result.final_state == BallState.TD


def test_validate_rejects_illegal_sequence() -> None:
    assert not validate([BallState.SNAP, BallState.CAUGHT])
    assert validate([BallState.PRE_SNAP, BallState.SNAP, BallState.THROWN, BallState.IN_AIR])
