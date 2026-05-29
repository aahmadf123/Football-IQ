"""Pre-snap run/pass prediction (Issues #135 + #136).

Feature extraction (the 6 pre-snap signals) and the calibrated Bayesian
prediction ensemble are shipped together so the signal schema, model
calibration, and uncertainty semantics stay aligned.

Public surface:

* :mod:`signal_extractor` — the 6 pre-snap signals → :class:`PreSnapSignals`.
* :mod:`bayesian_ensemble` — naive-Bayes log-odds + Platt + MoE multi-class.
* :mod:`calibration` — Platt / isotonic calibrators + diagnostics (Brier, ECE,
  reliability curve, calibrated uncertainty).
* :mod:`per_opponent_prior` — per-opponent situational Dirichlet posteriors.
"""

from __future__ import annotations

from pipeline.play_prediction.bayesian_ensemble import (
    BayesianEnsemble,
    LikelihoodRatioModel,
    MixtureOfExperts,
    PredictionResult,
)
from pipeline.play_prediction.calibration import (
    IsotonicCalibrator,
    PlattScaler,
    binary_entropy,
    brier_score,
    expected_calibration_error,
    reliability_curve,
)
from pipeline.play_prediction.per_opponent_prior import (
    DirichletPrior,
    OpponentPriorStore,
)
from pipeline.play_prediction.signal_extractor import (
    PreSnapSignals,
    SignalValue,
    extract_signals,
)

__all__ = [
    "BayesianEnsemble",
    "LikelihoodRatioModel",
    "MixtureOfExperts",
    "PredictionResult",
    "PlattScaler",
    "IsotonicCalibrator",
    "binary_entropy",
    "brier_score",
    "expected_calibration_error",
    "reliability_curve",
    "DirichletPrior",
    "OpponentPriorStore",
    "PreSnapSignals",
    "SignalValue",
    "extract_signals",
]
