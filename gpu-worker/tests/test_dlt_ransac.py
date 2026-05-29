"""Tests for normalized DLT + RANSAC homography estimation (Issue #127).

All synthetic — no OpenCV / video needed. A random ground-truth homography
warps a grid of source points; the solver must recover it (up to scale) and
RANSAC must reject injected outliers.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.homography.dlt_ransac import (
    dlt_homography,
    normalize_points,
    ransac_homography,
    reprojection_error,
)


def _apply(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    homog = np.hstack([pts, np.ones((len(pts), 1))])
    proj = (H @ homog.T).T
    return proj[:, :2] / proj[:, 2:3]


def _grid(n: int = 5) -> np.ndarray:
    xs, ys = np.meshgrid(np.linspace(0, 100, n), np.linspace(0, 60, n))
    return np.column_stack([xs.ravel(), ys.ravel()]).astype(np.float64)


def _ground_truth_H() -> np.ndarray:
    return np.array(
        [
            [1.2, 0.15, 30.0],
            [-0.1, 0.9, 12.0],
            [0.0005, -0.0003, 1.0],
        ],
        dtype=np.float64,
    )


# ── Normalization ─────────────────────────────────────────────────────────────


def test_normalize_points_centroid_at_origin():
    pts = _grid()
    norm, T = normalize_points(pts)
    assert np.allclose(norm.mean(axis=0), 0.0, atol=1e-9)


def test_normalize_points_rms_distance_is_sqrt2():
    pts = _grid()
    norm, _ = normalize_points(pts)
    rms = float(np.sqrt((norm**2).sum(axis=1)).mean())
    assert rms == pytest.approx(np.sqrt(2.0), abs=1e-6)


# ── Exact DLT recovery ────────────────────────────────────────────────────────


def test_dlt_recovers_known_homography():
    H_true = _ground_truth_H()
    src = _grid()
    dst = _apply(H_true, src)
    H_est = dlt_homography(src, dst)
    assert H_est is not None
    err = reprojection_error(H_est, src, dst)
    assert err.max() < 1e-6


def test_dlt_requires_four_points():
    src = np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float64)
    dst = src.copy()
    assert dlt_homography(src, dst) is None


# ── RANSAC robustness ─────────────────────────────────────────────────────────


def test_ransac_rejects_outliers():
    H_true = _ground_truth_H()
    src = _grid(6)
    dst = _apply(H_true, src)
    # Corrupt 5 correspondences with large offsets.
    rng = np.random.default_rng(1)
    outlier_idx = rng.choice(len(src), size=5, replace=False)
    dst_noisy = dst.copy()
    dst_noisy[outlier_idx] += 50.0

    H_est, inliers = ransac_homography(src, dst_noisy, threshold=2.0, seed=42)
    assert H_est is not None
    # Outliers must be flagged out.
    for idx in outlier_idx:
        assert not inliers[idx]
    # Inlier re-projection error should be small.
    err = reprojection_error(H_est, src[inliers], dst_noisy[inliers])
    assert err.max() < 2.0


def test_ransac_returns_none_for_too_few_points():
    src = np.array([[0, 0], [1, 1], [2, 2]], dtype=np.float64)
    H, inliers = ransac_homography(src, src, threshold=3.0)
    assert H is None
    assert inliers.sum() == 0


def test_ransac_exact_on_clean_minimal_set():
    H_true = _ground_truth_H()
    src = np.array([[0, 0], [100, 0], [100, 60], [0, 60]], dtype=np.float64)
    dst = _apply(H_true, src)
    H, inliers = ransac_homography(src, dst, threshold=1.0)
    assert H is not None
    assert inliers.all()
