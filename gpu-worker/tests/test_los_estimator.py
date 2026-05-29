"""Tests for the LOS estimator (Issue #132)."""

from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.events.los_estimator import LOSEstimate, LOSEstimator, _dbscan_1d

SNAP = 5


def _player(tid: str, fx: float, fy: float) -> dict[str, Any]:
    return {"id": tid, "track_points": [{"frame_number": SNAP, "field_x": fx, "field_y": fy}]}


def _line_and_defense() -> list[dict[str, Any]]:
    # 5 OL tightly clustered at x≈30, spread in y. Defenders ahead at x≈32.
    ol = [_player(f"o{i}", 30.0 + 0.1 * (i - 2), float(i - 2)) for i in range(5)]
    dl = [_player(f"d{i}", 32.5, float(i - 1)) for i in range(4)]
    return ol + dl


def test_dbscan_1d_groups_dense_runs() -> None:
    clusters = _dbscan_1d([30.0, 30.1, 30.0, 29.9, 30.05, 40.0], eps=2.0, min_samples=5)
    assert len(clusters) == 1
    assert len(clusters[0]) == 5


def test_dbscan_1d_rejects_sparse() -> None:
    assert _dbscan_1d([1.0, 5.0, 9.0], eps=2.0, min_samples=5) == []


def test_ol_cluster_estimate() -> None:
    est = LOSEstimator().estimate(_line_and_defense(), SNAP)
    assert est.method == "ol_cluster"
    assert abs(est.los_x - 30.0) < 0.5
    assert est.support == 5
    assert est.confidence > 0.5


def test_ball_fallback_when_no_line() -> None:
    sparse = [_player("o0", 25.0, 0.0), _player("o1", 40.0, 3.0)]
    est = LOSEstimator().estimate(sparse, SNAP, ball_field_x=33.0)
    assert est.method == "ball"
    assert est.los_x == 33.0


def test_none_when_no_data() -> None:
    est = LOSEstimator().estimate([], SNAP)
    assert est.method == "none"
    assert est.confidence == 0.0


def test_recursive_propagation_shifts_by_gain() -> None:
    prior = LOSEstimate(30.0, 0.8, "ol_cluster")
    measured = LOSEstimate(37.0, 0.4, "ol_cluster")
    fused = LOSEstimator().propagate(prior, measured, gain_yards=7.0)
    assert fused.method == "bayesian"
    # Prior (shifted to 37) and measurement (37) agree → ~37.
    assert abs(fused.los_x - 37.0) < 1.0
    assert fused.confidence >= prior.confidence
