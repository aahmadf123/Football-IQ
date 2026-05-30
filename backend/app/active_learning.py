"""Active-learning prioritization for the coach-correction queue (Issue #145).

This module is the small, dependency-light policy core behind
``GET /api/v1/corrections/queue``. It does **not** introduce a separate
annotation product: the queue is a prioritized view over existing ``clips``,
and the existing ``coach_corrections`` flow remains the source of truth.

Prioritization uses the clip-level **calibrated** uncertainty written by the
GPU worker (``clips.uncertainty_score``, ``clips.uncertainty_calibrated``),
which is the normalized entropy of the Phase-2 ensemble (#145 algorithm:
``score(x) = -Σ P(y=c|x) log P(y=c|x)``). Higher entropy ⇒ the model is less
sure ⇒ the clip bubbles to the top for coach review.

Safety rules (Issue #146):

* A *missing* (NULL) uncertainty score is never fabricated into a confident
  number. It is given a sentinel priority that sorts **below** any real score
  so unscored clips do not masquerade as high-confidence review targets, while
  still being surfacable (``include_unscored``) as "needs a first look".
* The ``uncertainty_calibrated`` flag travels with every item so a caller/UI
  never renders an *uncalibrated* entropy as a trusted confidence.
"""

from __future__ import annotations

# Default number of clips returned by the annotation queue.
DEFAULT_QUEUE_LIMIT = 25
MAX_QUEUE_LIMIT = 200

# Priority assigned to a clip with no uncertainty score. Negative so it always
# sorts below any real score in the closed unit interval [0, 1].
UNSCORED_PRIORITY = -1.0

# Per-item reason codes (mirror the spirit of ``ActiveLearningReason`` without
# coupling the read-only queue to that write-side enum).
REASON_UNSCORED = "unscored"
REASON_CALIBRATED = "uncertainty_calibrated"
REASON_UNCALIBRATED = "uncertainty_uncalibrated"


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def effective_priority(
    uncertainty_score: float | None,
    uncertainty_calibrated: bool = False,
) -> float:
    """Return the ranking value for one clip (higher = review first).

    A real score is clamped to ``[0, 1]``. A missing score returns
    :data:`UNSCORED_PRIORITY` so it sorts below every scored clip — an unknown
    uncertainty is never inflated into a confident-looking number (#146).

    Calibration does **not** change the ranking value: entropy is the
    active-learning signal regardless of calibration. The
    ``uncertainty_calibrated`` flag governs *honest presentation*, not order,
    and is surfaced separately on each queue item.
    """
    if uncertainty_score is None:
        return UNSCORED_PRIORITY
    return _clamp01(float(uncertainty_score))


def queue_reason(uncertainty_score: float | None, uncertainty_calibrated: bool) -> str:
    """Classify why a clip is in the queue (drives the UI badge)."""
    if uncertainty_score is None:
        return REASON_UNSCORED
    return REASON_CALIBRATED if uncertainty_calibrated else REASON_UNCALIBRATED


def normalize_limit(limit: int | None) -> int:
    """Clamp a requested queue ``limit`` into ``[1, MAX_QUEUE_LIMIT]``."""
    if limit is None:
        return DEFAULT_QUEUE_LIMIT
    return max(1, min(int(limit), MAX_QUEUE_LIMIT))
