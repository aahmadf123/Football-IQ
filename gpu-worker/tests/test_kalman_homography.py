"""Tests for the 9-DoF homography Kalman smoother (Issue #127).

Synthetic — verifies stability over a 100-frame sequence, per-regime process
noise, and that a clean constant signal converges to that signal.
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.homography.kalman_smoother import (
    SIGMA_Q_DRONE_FOLLOW,
    SIGMA_Q_FIXED_SIDELINE,
    HomographyKalman,
    process_noise_for_regime,
    smooth_series,
)


def _base_H() -> np.ndarray:
    return np.array(
        [[1.1, 0.05, 20.0], [-0.05, 0.95, 8.0], [0.0002, 0.0001, 1.0]],
        dtype=np.float64,
    )


def test_process_noise_per_regime():
    assert process_noise_for_regime("fixed_sideline") == SIGMA_Q_FIXED_SIDELINE
    assert process_noise_for_regime("drone_follow") == SIGMA_Q_DRONE_FOLLOW
    # Unknown defaults to the looser drone value.
    assert process_noise_for_regime("unknown") == SIGMA_Q_DRONE_FOLLOW


def test_kalman_converges_to_constant_signal():
    H = _base_H()
    kf = HomographyKalman(sigma_q=SIGMA_Q_DRONE_FOLLOW)
    out = None
    for _ in range(20):
        out = kf.update(H, confidence=1.0)
    assert out is not None
    # Normalized so [2,2] == 1.
    assert out[2, 2] == 1.0
    assert np.allclose(out, H, atol=1e-2)


def test_kalman_smooths_noisy_100_frame_sequence():
    rng = np.random.default_rng(7)
    H = _base_H()
    flat = H.flatten()
    series: list[np.ndarray] = []
    for _ in range(100):
        noisy = flat + rng.normal(0.0, 0.03, size=9)
        noisy = noisy / noisy[8]
        series.append(noisy.reshape(3, 3))

    smoothed = smooth_series(series, regime="drone_follow")
    assert len(smoothed) == 100

    # The smoothed estimate must be closer to ground truth than the raw input.
    raw_err = np.mean([np.abs(s.flatten() / s.flatten()[8] - flat).mean() for s in series])
    sm_err = np.mean([np.abs(s.flatten() / s.flatten()[8] - flat).mean() for s in smoothed[10:]])
    assert sm_err < raw_err


def test_kalman_skips_none_windows_preserving_estimate():
    H = _base_H()
    series = [H, None, H, None, H]
    smoothed = smooth_series(series, regime="drone_follow")
    assert len(smoothed) == 5
    # None slots reuse the last good estimate, not identity.
    assert not np.allclose(smoothed[1], np.eye(3))


def test_fixed_sideline_noise_tighter_than_drone():
    """Tighter process noise ⇒ slower to follow a jump (more smoothing)."""
    H0 = _base_H()
    H1 = H0.copy()
    H1[0, 2] += 40.0  # large translation jump

    fixed = HomographyKalman(sigma_q=SIGMA_Q_FIXED_SIDELINE)
    drone = HomographyKalman(sigma_q=SIGMA_Q_DRONE_FOLLOW)
    fixed.update(H0)
    drone.update(H0)
    fixed_out = fixed.update(H1)
    drone_out = drone.update(H1)
    # The looser drone filter tracks the jump faster (closer to H1).
    assert abs(drone_out[0, 2] - H1[0, 2]) <= abs(fixed_out[0, 2] - H1[0, 2])
