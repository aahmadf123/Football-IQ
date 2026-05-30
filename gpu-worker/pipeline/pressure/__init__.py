"""Pre-snap pressure prediction (Issue #140).

OL spacing + DL alignment at the snap frame predict whether the QB will be
pressured within 2.5 s. Public surface:

* :func:`~pipeline.pressure.feature_extractor.extract_pressure_features` — the
  snap-frame feature set (OL gap widths, DL gap alignment, LB depth, blitz
  indicator, down-and-distance), built on the shared spatial schema.
* :class:`~pipeline.pressure.classifier.PressureClassifier` — deterministic
  logistic scorer with an optional offline-trained model loaded via
  ``PRESSURE_MODEL``; returns a :class:`~pipeline.calibration.CalibratedOutput`
  that is *calibrated* only when a fitted calibrator is present, else flagged
  experimental (Issue #146).

Like the coverage classifier and the pre-snap run/pass predictor this is
deterministic over the routed stages' outputs and is **not** wired into the
model router (see ``docs/coverage-pressure-features.md``).
"""

from __future__ import annotations

from pipeline.pressure.classifier import PressureClassifier
from pipeline.pressure.feature_extractor import (
    PRESSURE_FEATURE_NAMES,
    PressureFeatures,
    extract_pressure_features,
)

__all__ = [
    "PRESSURE_FEATURE_NAMES",
    "PressureFeatures",
    "extract_pressure_features",
    "PressureClassifier",
]
