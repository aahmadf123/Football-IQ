"""Snap / LOS event-detection support package (Issues #132, #134).

This package holds the *deterministic, model-free* event-analysis primitives
that turn upstream pipeline artifacts (player tracklets in field coordinates,
the dedicated ball detections, optional pose keypoints, and raw frames) into
play events:

* :mod:`pipeline.events.optical_flow_vti` — Variable-Threshold-Image active
  cell counter (Oregon State IAAI-2013 snap-burst signal).
* :mod:`pipeline.events.snap_detector` — multi-signal naive-Bayes snap
  detector that fuses up to five independent signals into a calibrated
  per-frame ``P(snap)``.
* :mod:`pipeline.events.los_estimator` — line-of-scrimmage estimator
  (OL-cluster centroid → ball fallback → recursive Bayesian propagation).

Nothing here loads model weights or runs neural inference — these are
OpenCV / NumPy / pure-Python algorithms that consume the *outputs* of the
routed stages (``detect``, ``ball``, ``track``, ``calibrate``, ``pose``).
They therefore do not register a new model-router stage; see
``docs/model-routing.md``.
"""

from __future__ import annotations

from pipeline.events.los_estimator import LOSEstimate, LOSEstimator
from pipeline.events.snap_detector import (
    BASE_RATE,
    BayesianSnapDetector,
    SnapInputs,
    SnapResult,
)

__all__ = [
    "BASE_RATE",
    "BayesianSnapDetector",
    "LOSEstimate",
    "LOSEstimator",
    "SnapInputs",
    "SnapResult",
]
