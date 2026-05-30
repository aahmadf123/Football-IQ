"""Coverage classification with calibrated uncertainty (Issue #139).

Public surface:

* :data:`~pipeline.coverage.gnn_classifier.COVERAGE_CLASSES` — the 9-class
  coverage taxonomy.
* :class:`~pipeline.coverage.gnn_classifier.CoverageClassifier` — builds the
  shared spatial graph (``pipeline.spatial``), runs the graph model when an
  offline-trained checkpoint is configured (``COVERAGE_GNN_MODEL``) and falls
  back to a deterministic heuristic otherwise, and returns a
  :class:`~pipeline.calibration.CalibratedOutput` (Issue #146).
* :func:`~pipeline.coverage.gnn_classifier.coverage_bust_flag` — fires when
  post-snap alignment diverges from the pre-snap cluster.

The classifier is deterministic in its default (no-checkpoint) path and is not
wired into the model router — see ``docs/coverage-pressure-features.md`` and the
"Not routed" section of ``docs/model-routing.md`` for the rationale (same as the
pre-snap predictor and frontier analytics).
"""

from __future__ import annotations

from pipeline.coverage.gnn_classifier import (
    COVERAGE_CLASSES,
    CoverageClassifier,
    CoverageGNN,
    DeterministicCoverageBaseline,
    coverage_bust_flag,
)

__all__ = [
    "COVERAGE_CLASSES",
    "CoverageClassifier",
    "CoverageGNN",
    "DeterministicCoverageBaseline",
    "coverage_bust_flag",
]
