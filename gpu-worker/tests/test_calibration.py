"""Tests for the calibration module (Issue #136)."""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.play_prediction.calibration import (
    IsotonicCalibrator,
    PlattScaler,
    binary_entropy,
    brier_score,
    expected_calibration_error,
    reliability_curve,
    sigmoid,
)


def test_sigmoid_is_stable_for_large_inputs() -> None:
    assert np.isclose(sigmoid(0.0), 0.5)
    assert sigmoid(1000.0) <= 1.0
    assert sigmoid(-1000.0) >= 0.0
    assert np.isclose(sigmoid(1000.0), 1.0)
    assert np.isclose(sigmoid(-1000.0), 0.0)


def test_platt_unfitted_is_identity_on_probabilities() -> None:
    scaler = PlattScaler()
    assert not scaler.is_fitted
    for p in (0.1, 0.5, 0.9):
        assert np.isclose(scaler.transform_prob(p), p)


def test_platt_fit_recovers_separable_mapping() -> None:
    rng = np.random.default_rng(0)
    # Scores strongly separate the two classes.
    pos = rng.normal(2.0, 0.5, 200)
    neg = rng.normal(-2.0, 0.5, 200)
    scores = np.concatenate([pos, neg])
    labels = np.concatenate([np.ones(200), np.zeros(200)])
    scaler = PlattScaler().fit(scores, labels)
    assert scaler.is_fitted
    # A high score should calibrate to a high probability, low to low.
    assert scaler.transform_score(2.0) > 0.8
    assert scaler.transform_score(-2.0) < 0.2


def test_platt_fit_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        PlattScaler().fit([1.0, 2.0], [1])


def test_platt_roundtrip_dict() -> None:
    scaler = PlattScaler(a=1.5, b=-0.3, is_fitted=True)
    restored = PlattScaler.from_dict(scaler.to_dict())
    assert restored.a == scaler.a
    assert restored.b == scaler.b
    assert restored.is_fitted


def test_isotonic_unfitted_is_identity() -> None:
    cal = IsotonicCalibrator()
    for p in (0.0, 0.4, 1.0):
        assert np.isclose(cal.transform_prob(p), p)


def test_isotonic_is_monotone_nondecreasing() -> None:
    rng = np.random.default_rng(1)
    probs = rng.uniform(0, 1, 500)
    labels = (rng.uniform(0, 1, 500) < probs).astype(int)
    cal = IsotonicCalibrator().fit(probs, labels)
    xs = np.linspace(0, 1, 50)
    ys = np.array([cal.transform_prob(x) for x in xs])
    assert np.all(np.diff(ys) >= -1e-9)


def test_brier_score_perfect_is_zero() -> None:
    assert np.isclose(brier_score([1.0, 0.0, 1.0], [1, 0, 1]), 0.0)


def test_brier_score_worst_is_one() -> None:
    assert np.isclose(brier_score([0.0, 1.0], [1, 0]), 1.0)


def test_reliability_curve_omits_empty_bins() -> None:
    probs = [0.05, 0.06, 0.95, 0.96]
    labels = [0, 0, 1, 1]
    curve = reliability_curve(probs, labels, n_bins=10)
    # Only the first and last bins are populated.
    assert len(curve) == 2
    assert all(b["count"] > 0 for b in curve)
    assert all(isinstance(b["count"], int) for b in curve)


def test_ece_low_for_well_calibrated() -> None:
    rng = np.random.default_rng(2)
    probs = rng.uniform(0, 1, 5000)
    labels = (rng.uniform(0, 1, 5000) < probs).astype(int)
    ece = expected_calibration_error(probs, labels, n_bins=10)
    assert ece < 0.05


def test_ece_high_for_miscalibrated() -> None:
    # Always predict 0.5 but outcomes are deterministic 1 → big gap.
    probs = [0.5] * 100
    labels = [1] * 100
    assert expected_calibration_error(probs, labels) > 0.4


def test_binary_entropy_peaks_at_half() -> None:
    assert np.isclose(binary_entropy(0.5), 1.0)
    assert binary_entropy(0.99) < 0.2
    assert binary_entropy(0.01) < 0.2
    # Clamped at the extremes (no NaN/inf).
    assert binary_entropy(0.0) >= 0.0
    assert binary_entropy(1.0) >= 0.0
