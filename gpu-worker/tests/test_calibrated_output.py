"""Tests for the CalibratedOutput envelope + temperature scaling (Issue #146)."""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.calibration import (
    CalibratedOutput,
    TemperatureScaler,
    multiclass_ece,
)
from pipeline.calibration.calibrated_output import normalized_entropy


def test_from_multiclass_normalizes_and_picks_argmax() -> None:
    out = CalibratedOutput.from_multiclass({"a": 2.0, "b": 1.0, "c": 1.0})
    assert out.value == "a"
    assert out.probabilities is not None
    assert sum(out.probabilities.values()) == pytest.approx(1.0)
    assert out.confidence == pytest.approx(0.5)
    # Uncalibrated by default → experimental, calibration_method == uncalibrated.
    assert out.is_calibrated is False
    assert out.experimental is True
    assert out.calibration_method == "uncalibrated"


def test_to_dict_matches_issue_146_contract() -> None:
    out = CalibratedOutput.from_binary(
        0.82, positive_label="pressure", negative_label="no_pressure",
        calibration_method="platt", is_calibrated=True, ece=0.03,
    )
    d = out.to_dict()
    # The three contract fields from §5.10.
    assert d["value"] == "pressure"
    assert d["confidence"] == pytest.approx(0.82)
    assert d["calibration_method"] == "platt"
    assert d["is_calibrated"] is True
    assert d["experimental"] is False
    assert d["ece"] == pytest.approx(0.03)


def test_normalized_entropy_bounds() -> None:
    assert normalized_entropy([0.25, 0.25, 0.25, 0.25]) == pytest.approx(1.0)
    assert normalized_entropy([1.0, 0.0, 0.0, 0.0]) == pytest.approx(0.0, abs=1e-9)
    mid = normalized_entropy([0.7, 0.3])
    assert 0.0 < mid < 1.0


def test_temperature_scaler_identity_when_unfitted() -> None:
    ts = TemperatureScaler()
    logits = np.array([2.0, 1.0, 0.0])
    probs = ts.transform_logits(logits)
    assert probs.sum() == pytest.approx(1.0)
    # T == 1 → plain softmax.
    expected = np.exp(logits - logits.max())
    expected /= expected.sum()
    assert np.allclose(probs, expected)


def test_temperature_scaling_reduces_overconfident_ece() -> None:
    rng = np.random.default_rng(0)
    n, k = 600, 3
    y = rng.integers(0, k, size=n)
    # Build deliberately *over-confident* logits: correct class favoured but
    # scaled up so confidence >> accuracy (high ECE before calibration).
    logits = rng.normal(size=(n, k))
    logits[np.arange(n), y] += 1.0
    correct = rng.random(n) < 0.7  # only 70% actually correct
    # Where "incorrect", move the argmax onto a wrong class.
    for i in range(n):
        if not correct[i]:
            wrong = (y[i] + 1) % k
            logits[i, wrong] = logits[i].max() + 0.5
    logits *= 4.0  # inflate confidence

    def softmax(z: np.ndarray) -> np.ndarray:
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)

    before = multiclass_ece(softmax(logits), y)
    ts = TemperatureScaler().fit(logits, y)
    after = multiclass_ece(ts.transform_logits(logits), y)
    assert ts.is_fitted
    assert ts.temperature > 1.0  # needs to soften overconfident logits
    assert after < before


def test_temperature_scaler_roundtrip() -> None:
    ts = TemperatureScaler(temperature=2.3, is_fitted=True)
    restored = TemperatureScaler.from_dict(ts.to_dict())
    assert restored.temperature == pytest.approx(2.3)
    assert restored.is_fitted is True


def test_from_multiclass_rejects_empty() -> None:
    with pytest.raises(ValueError):
        CalibratedOutput.from_multiclass({})
