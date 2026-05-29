"""Tests for the multi-signal Bayesian snap detector (Issue #132)."""

from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.events.snap_detector import (
    BASE_RATE,
    BayesianSnapDetector,
    SnapInputs,
    signal_center_ball_separation,
    signal_formation_stability,
    signal_ol_stance_break,
)

FPS = 30.0
SNAP = 10


def _static_then_move(tid: str, fx0: float, fy0: float) -> dict[str, Any]:
    pts = []
    for f in range(0, 25):
        # Static through SNAP-1, then drift forward each frame.
        fx = fx0 + (0.0 if f < SNAP else 0.4 * (f - SNAP + 1))
        pts.append({"frame_number": f, "field_x": fx, "field_y": fy0,
                    "bbox": [fx0 * 10, fy0 * 10, fx0 * 10 + 5, fy0 * 10 + 5]})
    return {"id": tid, "track_points": pts}


def _formation(n: int = 11) -> list[dict[str, Any]]:
    return [_static_then_move(f"p{i}", 50.0, float(i - n // 2)) for i in range(n)]


def _ol_pose() -> dict[int, dict[str, dict[str, tuple[float, float]]]]:
    """4 OL whose torso angle snaps >30° at frame SNAP and holds."""
    pose: dict[int, dict[str, dict[str, tuple[float, float]]]] = {}
    for f in range(0, 25):
        broken = f >= SNAP
        frame_players: dict[str, dict[str, tuple[float, float]]] = {}
        for i in range(4):
            tid = f"p{i}"
            # Pre-snap: upright (shoulders above hips). Post-snap: lurch forward.
            sx = 100.0 + (40.0 if broken else 0.0)
            frame_players[tid] = {
                "left_shoulder": (sx - 5, 50.0),
                "right_shoulder": (sx + 5, 50.0),
                "left_hip": (100.0 - 5, 100.0),
                "right_hip": (100.0 + 5, 100.0),
            }
        pose[f] = frame_players
    return pose


# ── Individual signal evaluators ────────────────────────────────────────────


def test_formation_stability_fires_at_snap() -> None:
    s = signal_formation_stability(_formation(), FPS)
    assert s, "expected non-empty signal series"
    peak = max(s, key=lambda f: s[f])
    assert SNAP - 2 <= peak <= SNAP + 2
    assert s[peak] > 0.0


def test_ol_stance_break_requires_min_ol() -> None:
    s = signal_ol_stance_break(_ol_pose(), ["p0", "p1", "p2", "p3"])
    assert s
    assert max(s.values()) >= 1.0  # all 4 OL broke ⇒ full strength


def test_no_ol_ids_yields_empty() -> None:
    assert signal_ol_stance_break(_ol_pose(), []) == {}


def test_center_ball_separation() -> None:
    ball = {SNAP - 1: (50.0, 0.0), SNAP: (50.0, 0.0), SNAP + 1: (49.0, -1.0)}
    center = {SNAP - 1: (50.0, 0.0), SNAP: (50.0, 0.0), SNAP + 1: (50.0, 0.0)}
    s = signal_center_ball_separation(ball, center, FPS)
    assert s.get(SNAP + 1, 0.0) > 0.0


# ── Fused detector ──────────────────────────────────────────────────────────


def test_two_signals_detect_snap() -> None:
    inputs = SnapInputs(
        tracklets=_formation(),
        fps=FPS,
        pose_by_frame=_ol_pose(),
        ol_track_ids=["p0", "p1", "p2", "p3"],
    )
    result = BayesianSnapDetector().detect(inputs)
    assert result.snap_frame is not None
    assert SNAP - 2 <= result.snap_frame <= SNAP + 2
    assert result.confidence > 0.5
    assert "formation_break" in result.signals_present
    assert "ol_stance_break" in result.signals_present
    # Explainability: per-signal strengths recorded at the snap frame.
    assert result.explain(result.snap_frame)


def test_single_weak_signal_no_false_snap() -> None:
    # Only one player (a motion man) moves; the median-based formation signal
    # stays quiet and no snap should be asserted.
    tracks = [_static_then_move("p0", 50.0, 0.0)]
    tracks += [
        {"id": f"p{i}", "track_points": [
            {"frame_number": f, "field_x": 50.0, "field_y": float(i)} for f in range(25)
        ]}
        for i in range(1, 11)
    ]
    result = BayesianSnapDetector().detect(SnapInputs(tracklets=tracks, fps=FPS))
    assert result.snap_frame is None
    assert result.confidence < 0.5


def test_no_signals_returns_none() -> None:
    result = BayesianSnapDetector().detect(SnapInputs(tracklets=[], fps=FPS))
    assert result.snap_frame is None
    assert result.signals_present == []


def test_base_rate_is_low() -> None:
    assert 0.0 < BASE_RATE < 0.1
