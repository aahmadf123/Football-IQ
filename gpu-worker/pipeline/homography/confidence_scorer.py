"""Multi-component calibration confidence (Issue #127).

A single homography confidence in ``[0, 1]`` is a weighted blend of five
sub-scores. All five are persisted alongside the calibration so the
clip-review UI and downstream gating (``analytics_safe``) can reason about
*why* a calibration is weak, not just that it is.

    confidence = 0.30 * inlier_ratio
               + 0.25 * min(line_count / 15, 1)
               + 0.20 * parallel_line_score
               + 0.15 * temporal_stability
               + 0.10 * field_coverage
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

WEIGHTS = {
    "inlier_ratio": 0.30,
    "line_count_score": 0.25,
    "parallel_line_score": 0.20,
    "temporal_stability": 0.15,
    "field_coverage": 0.10,
}

# Number of detected field lines that saturates the line-count sub-score.
LINE_COUNT_SATURATION = 15.0


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


@dataclass(frozen=True)
class ConfidenceBreakdown:
    """The five sub-scores plus the blended confidence."""

    inlier_ratio: float
    line_count_score: float
    parallel_line_score: float
    temporal_stability: float
    field_coverage: float
    confidence: float

    def as_dict(self) -> dict[str, float]:
        return {k: float(v) for k, v in asdict(self).items()}


def parallel_line_score(angles_rad: list[float]) -> float:
    """Score how cleanly yard lines share a single orientation.

    Yard lines projected by a good homography are near-parallel (small angular
    spread). Returns ``1 - clamp(std / tolerance)`` where ``tolerance`` is
    ~8.6° (0.15 rad). Fewer than two lines ⇒ 0.0 (no evidence).
    """
    if len(angles_rad) < 2:
        return 0.0
    import statistics

    spread = statistics.pstdev([float(a) for a in angles_rad])
    return _clamp(1.0 - spread / 0.15)


def temporal_stability_from_drift(drift_px: float, *, tolerance_px: float = 4.0) -> float:
    """Map inter-anchor re-projection drift (px) to a ``[0, 1]`` stability score.

    Zero drift ⇒ 1.0; drift ≥ ``tolerance_px`` ⇒ 0.0. For a single-frame
    (FIXED_SIDELINE anchor) calibration with no temporal evidence, pass
    ``drift_px=0.0`` to assert full stability.
    """
    return _clamp(1.0 - float(drift_px) / tolerance_px)


def compute_confidence(
    *,
    inlier_ratio: float,
    line_count: int,
    parallel_line_score: float,
    temporal_stability: float,
    field_coverage: float,
) -> ConfidenceBreakdown:
    """Blend the five sub-scores into a single confidence in ``[0, 1]``."""
    line_count_score = _clamp(line_count / LINE_COUNT_SATURATION)
    inlier = _clamp(inlier_ratio)
    parallel = _clamp(parallel_line_score)
    temporal = _clamp(temporal_stability)
    coverage = _clamp(field_coverage)

    confidence = (
        WEIGHTS["inlier_ratio"] * inlier
        + WEIGHTS["line_count_score"] * line_count_score
        + WEIGHTS["parallel_line_score"] * parallel
        + WEIGHTS["temporal_stability"] * temporal
        + WEIGHTS["field_coverage"] * coverage
    )
    return ConfidenceBreakdown(
        inlier_ratio=inlier,
        line_count_score=line_count_score,
        parallel_line_score=parallel,
        temporal_stability=temporal,
        field_coverage=coverage,
        confidence=_clamp(confidence),
    )
