"""Variable-Threshold-Image (VTI) optical-flow snap signal (Issue #132).

The Oregon State IAAI-2013 snap-detection paper shows that raw optical-flow
magnitude is unreliable for snap detection because broadcast / sideline cameras
pan and zoom — global motion swamps the local burst of player motion at the
snap. Their most robust feature is a *Variable Threshold Image* (VTI): rather
than thresholding flow magnitude with a fixed value, each grid cell keeps its
own running baseline and a cell only counts as "active" when its motion exceeds
that adaptive threshold. The snap shows up as a sudden spike in the number of
active cells inside the line-of-scrimmage band.

This module is intentionally dependency-light and deterministic:

* If OpenCV is available we use dense Farneback flow (matches the paper).
* If OpenCV is missing (e.g. a minimal CI image) we fall back to absolute
  frame differencing, which produces the same *shape* of signal so the snap
  detector and its tests behave identically.

No model weights, no GPU, no router stage — this is a pure-CV signal extractor
that feeds :class:`pipeline.events.snap_detector.BayesianSnapDetector`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import structlog

log = structlog.get_logger(__name__)

try:  # OpenCV is in requirements.txt but guard so the module imports anywhere.
    import cv2

    _HAS_CV2 = True
except Exception:  # pragma: no cover - exercised only on cv2-less images
    cv2 = None  # type: ignore[assignment]
    _HAS_CV2 = False


@dataclass(frozen=True)
class VTIConfig:
    """Tuning for the VTI active-cell counter.

    Attributes:
        cell_size: Square grid-cell edge length in pixels.
        baseline_window: Number of recent frames used for the per-cell running
            mean / std that forms the *variable* threshold.
        threshold_k: A cell is active when its motion exceeds
            ``mean + threshold_k * std`` of its own recent history.
        min_motion: Floor on the activation threshold so a perfectly static
            cell still needs a real burst (not float noise) to fire.
    """

    cell_size: int = 32
    baseline_window: int = 8
    threshold_k: float = 2.5
    min_motion: float = 0.5


def _to_gray(frame: np.ndarray) -> np.ndarray:
    """Return a float32 single-channel view of ``frame``."""
    if frame.ndim == 3:
        if _HAS_CV2:
            gray = cv2.cvtColor(frame.astype(np.uint8), cv2.COLOR_BGR2GRAY)
        else:  # luminosity weights, no cv2 needed
            gray = (
                0.114 * frame[..., 0]
                + 0.587 * frame[..., 1]
                + 0.299 * frame[..., 2]
            )
        return gray.astype(np.float32)
    return frame.astype(np.float32)


def _pair_motion(prev: np.ndarray, curr: np.ndarray) -> np.ndarray:
    """Per-pixel motion magnitude between two grayscale frames."""
    if _HAS_CV2:
        flow = cv2.calcOpticalFlowFarneback(
            prev.astype(np.uint8),
            curr.astype(np.uint8),
            None,
            0.5,
            3,
            15,
            3,
            5,
            1.2,
            0,
        )
        return np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2).astype(np.float32)
    # cv2-less fallback: absolute frame difference is a monotone proxy for flow
    # magnitude for the purpose of detecting a sudden, localized motion burst.
    return np.abs(curr - prev).astype(np.float32)


def _cell_means(motion: np.ndarray, cell_size: int) -> np.ndarray:
    """Down-sample a per-pixel motion map to per-cell mean magnitudes."""
    h, w = motion.shape
    rows = max(1, h // cell_size)
    cols = max(1, w // cell_size)
    out = np.zeros((rows, cols), dtype=np.float32)
    for r in range(rows):
        for c in range(cols):
            block = motion[
                r * cell_size : (r + 1) * cell_size,
                c * cell_size : (c + 1) * cell_size,
            ]
            if block.size:
                out[r, c] = float(block.mean())
    return out


def active_cell_counts(
    frames: list[np.ndarray],
    *,
    config: VTIConfig | None = None,
    los_band_px: tuple[int, int] | None = None,
) -> list[int]:
    """Count VTI-active grid cells for each consecutive frame pair.

    Args:
        frames: Ordered grayscale or BGR frames for one play segment.
        config: VTI tuning; defaults to :class:`VTIConfig`.
        los_band_px: Optional ``(x_min, x_max)`` pixel band around the LOS.
            When given, only grid columns whose centre falls inside the band
            are counted — this is the paper's "±5 yd around LOS" restriction
            and sharply cuts false bursts from sideline / motion-man activity.

    Returns:
        A list of length ``len(frames)``. Index 0 is always ``0`` (no prior
        frame to diff against); index ``t`` is the active-cell count for the
        transition from frame ``t-1`` to frame ``t``.
    """
    cfg = config or VTIConfig()
    if len(frames) < 2:
        return [0] * len(frames)

    grays = [_to_gray(f) for f in frames]
    counts: list[int] = [0]
    history: list[np.ndarray] = []  # recent per-cell motion maps

    col_mask: np.ndarray | None = None
    for prev, curr in zip(grays[:-1], grays[1:]):
        motion = _pair_motion(prev, curr)
        cells = _cell_means(motion, cfg.cell_size)

        if col_mask is None and los_band_px is not None:
            cols = cells.shape[1]
            centres = (np.arange(cols) + 0.5) * cfg.cell_size
            x_min, x_max = los_band_px
            col_mask = (centres >= x_min) & (centres <= x_max)

        if history:
            stack = np.stack(history[-cfg.baseline_window :], axis=0)
            mean = stack.mean(axis=0)
            std = stack.std(axis=0)
            threshold = np.maximum(mean + cfg.threshold_k * std, cfg.min_motion)
        else:
            threshold = np.full_like(cells, cfg.min_motion)

        active = cells > threshold
        if col_mask is not None:
            active = active & col_mask[np.newaxis, :]
        counts.append(int(active.sum()))
        history.append(cells)

    return counts


def burst_strength(active_counts: list[int], *, window: int = 8) -> list[float]:
    """Convert active-cell counts into a per-frame snap-burst strength in [0, 1].

    A snap is a *spike* relative to the local baseline, not an absolute count,
    so we z-score each frame against the preceding ``window`` frames and squash
    the positive part into ``[0, 1]``. Quiet, monotone, or globally-panning
    segments produce near-zero strength everywhere.
    """
    n = len(active_counts)
    out = [0.0] * n
    arr = np.asarray(active_counts, dtype=np.float32)
    for t in range(1, n):
        lo = max(0, t - window)
        base = arr[lo:t]
        if base.size == 0:
            continue
        mu = float(base.mean())
        sigma = float(base.std())
        if sigma < 1e-6:
            # Flat baseline: any jump above it is a clean burst.
            out[t] = 1.0 if arr[t] > mu + 1.0 else 0.0
            continue
        z = (float(arr[t]) - mu) / sigma
        # Map z in [0, 4] → [0, 1]; below baseline → 0.
        out[t] = float(np.clip(z / 4.0, 0.0, 1.0))
    return out
