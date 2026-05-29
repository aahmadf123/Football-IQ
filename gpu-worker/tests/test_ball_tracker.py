"""Tests for the Kalman ball tracker (Issue #134)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.ball.ball_tracker import (
    BallKalman2D,
    observations_from_detections,
    track_ball,
)

FPS = 30.0


def test_interpolates_across_five_frame_gap() -> None:
    # Constant-velocity ground truth: x = 2*f, y = 100.
    truth = {f: (2.0 * f, 100.0) for f in range(0, 13)}
    # Drop a 5-frame run (frames 5..9) to simulate a detection dropout.
    observed = {f: p for f, p in truth.items() if f not in range(5, 10)}
    track = track_ball(observed, FPS, process_var=1.0, measurement_var=1.0)
    by_frame = {p.frame: p for p in track}
    for f in range(5, 10):
        assert not by_frame[f].observed
        assert abs(by_frame[f].x - truth[f][0]) <= 2.0
        assert abs(by_frame[f].y - truth[f][1]) <= 2.0


def test_velocity_reported_per_second() -> None:
    obs = {f: (3.0 * f, 0.0) for f in range(0, 10)}  # 3 px/frame → 90 px/s
    track = track_ball(obs, FPS)
    # After warm-up the x-velocity should approach 3 px/frame * 30 fps.
    assert abs(track[-1].vx - 90.0) < 15.0


def test_empty_observations() -> None:
    assert track_ball({}, FPS) == []


def test_long_gap_breaks_track() -> None:
    obs = {0: (0.0, 0.0), 1: (1.0, 0.0), 30: (30.0, 0.0)}
    track = track_ball(obs, FPS, max_gap=5)
    frames = {p.frame for p in track}
    # Frames inside the long gap are not fabricated.
    assert 15 not in frames
    assert 30 in frames


def test_observations_from_detections_picks_best() -> None:
    dets = {
        "4": [
            {"class": "ball", "bbox": [10, 10, 20, 20], "confidence": 0.3},
            {"class": "ball", "bbox": [40, 40, 50, 50], "confidence": 0.9},
            {"class": "player", "bbox": [0, 0, 5, 5], "confidence": 0.99},
        ]
    }
    obs = observations_from_detections(dets)
    assert obs == {4: (45.0, 45.0)}


def test_kalman_predict_update_cycle() -> None:
    kf = BallKalman2D()
    kf.init(0.0, 0.0)
    for i in range(1, 6):
        kf.predict(1.0)
        kf.update(float(i), float(2 * i))
    x, y, vx, vy = kf.state
    assert abs(x - 5.0) < 1.0
    assert abs(vx - 1.0) < 0.5
    assert abs(vy - 2.0) < 0.5
