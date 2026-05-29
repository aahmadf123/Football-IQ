"""Tests for the ball trajectory fitter (Issue #134)."""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.ball.trajectory_fitter import (
    apply_homography,
    compensate_affine,
    field_plane_distance,
    fit_parabola,
    hang_time_seconds,
    is_realistic_throw,
)


def test_fit_recovers_parabola_coefficients() -> None:
    # y(t) = 100 - 40 t + 5 t^2  ⇒  y0=100, v_y=-40, alpha = -2*5 = -10.
    times = [i * 0.1 for i in range(11)]
    ys = [100.0 - 40.0 * t + 5.0 * t * t for t in times]
    fit = fit_parabola(times, ys)
    assert fit is not None
    assert abs(fit.y0 - 100.0) < 1e-6
    assert abs(fit.v_y + 40.0) < 1e-6
    assert abs(fit.alpha + 10.0) < 1e-6
    assert fit.well_formed
    # Vertex at t = 40/(2*5) = 4.0.
    assert abs(fit.apex_t - 4.0) < 1e-6


def test_fit_returns_none_when_underdetermined() -> None:
    assert fit_parabola([0.0, 1.0], [1.0, 2.0]) is None


def test_line_is_not_well_formed() -> None:
    times = [0.0, 1.0, 2.0, 3.0]
    ys = [0.0, 1.0, 2.0, 3.0]
    fit = fit_parabola(times, ys)
    assert fit is not None
    assert not fit.well_formed


def test_apply_homography_identity() -> None:
    H = np.eye(3)
    assert apply_homography(H, (5.0, 7.0)) == (5.0, 7.0)


def test_field_plane_distance_with_scaling_homography() -> None:
    # Homography that scales pixels by 0.01 (100 px = 1 yd).
    H = np.diag([0.01, 0.01, 1.0])
    d = field_plane_distance(H, (0.0, 0.0), (300.0, 400.0))  # 3,4 yd → 5 yd
    assert abs(d - 5.0) < 1e-6


def test_compensate_affine_subtracts_camera_pan() -> None:
    points = {0: (10.0, 10.0), 1: (12.0, 10.0)}
    # Frame 1 shifted +5 px by camera pan; affine maps it back.
    affines = {1: np.array([[1.0, 0.0, -5.0], [0.0, 1.0, 0.0]])}
    out = compensate_affine(points, affines)
    assert out[0] == (10.0, 10.0)
    assert abs(out[1][0] - 7.0) < 1e-6


def test_physics_regularizer_envelope() -> None:
    assert is_realistic_throw(25.0, 38.0)
    assert not is_realistic_throw(10.0, 38.0)   # too slow
    assert not is_realistic_throw(25.0, 60.0)   # too steep


def test_hang_time() -> None:
    assert abs(hang_time_seconds(10, 40, 30.0) - 1.0) < 1e-9
    assert hang_time_seconds(40, 10, 30.0) == 0.0
