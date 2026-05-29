"""Dual-resolution detection merge (Issue #128).

Player pixel size varies a lot between capture regimes (80–200 px tall on
``fixed_sideline``, 30–80 px on ``drone_follow``). Running the same detector
at native resolution *and* a downscaled pass and then merging the two sets
recovers small players the native pass misses while keeping the large-player
recall of the full-resolution pass.

This module provides:

* :func:`iou` / :func:`nms` — class-aware IoU-based non-maximum suppression
  over the detection dicts produced by :mod:`pipeline.detector_models`
  (``{"bbox": [x1,y1,x2,y2], "confidence": float, "class": str, ...}``).
* :func:`merge_dual_resolution` — merge the detections from two scales into a
  single de-duplicated set.
* :class:`DualResolutionDetector` — a router-compatible
  :class:`~pipeline.detector_models.DetectorBase` adapter that wraps an inner
  detector, runs it at native + ``downscale`` resolution, and merges.

No model weights, no new heavy dependency: the inner detector is whatever the
model router selected (YOLO / stub / …). The slicing math is pure NumPy +
OpenCV, so the adapter is fully exercisable with ``StubDetector`` in CI.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import structlog

from pipeline.detector_models import DetectorBase

log = structlog.get_logger(__name__)

# Default IoU threshold for the cross-scale merge. Boxes from different scales
# that overlap above this are treated as the same object; the higher-confidence
# one wins.
DEFAULT_MERGE_IOU = 0.5
# Default downscale factor for the low-resolution pass (Issue #128: 0.5×).
DEFAULT_DOWNSCALE = 0.5


def iou(box_a: list[float], box_b: list[float]) -> float:
    """Intersection-over-union of two ``[x1, y1, x2, y2]`` boxes.

    Returns 0.0 for non-overlapping or degenerate boxes.
    """
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter = inter_w * inter_h
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return float(inter / union)


def nms(
    detections: list[dict[str, Any]],
    iou_threshold: float = DEFAULT_MERGE_IOU,
    *,
    class_aware: bool = True,
) -> list[dict[str, Any]]:
    """Greedy non-maximum suppression over detection dicts.

    Keeps the highest-confidence detection and drops any later detection that
    overlaps it by more than ``iou_threshold``. When ``class_aware`` is True
    (the default) suppression only happens between detections of the same
    ``class`` so a ball sitting on top of a player is never merged away.

    The input list is not mutated; the kept dicts are the original objects.
    """
    if len(detections) <= 1:
        return list(detections)

    # Sort by confidence descending; stable so equal-confidence ordering is
    # deterministic for tests.
    order = sorted(
        range(len(detections)),
        key=lambda i: float(detections[i].get("confidence", 0.0)),
        reverse=True,
    )
    kept: list[int] = []
    suppressed: set[int] = set()
    for i in order:
        if i in suppressed:
            continue
        kept.append(i)
        box_i = detections[i]["bbox"]
        cls_i = detections[i].get("class")
        for j in order:
            if j == i or j in suppressed:
                continue
            if class_aware and detections[j].get("class") != cls_i:
                continue
            if iou(box_i, detections[j]["bbox"]) > iou_threshold:
                suppressed.add(j)
    return [detections[i] for i in kept]


def merge_dual_resolution(
    native: list[dict[str, Any]],
    downscaled: list[dict[str, Any]],
    scale: float,
    iou_threshold: float = DEFAULT_MERGE_IOU,
) -> list[dict[str, Any]]:
    """Merge native-scale and downscaled detections into one set.

    ``downscaled`` detections were produced on a frame shrunk by ``scale``
    (e.g. 0.5). Their boxes are first rescaled back to native coordinates,
    then both sets are concatenated and de-duplicated with class-aware NMS so
    the merged output has *fewer* duplicates than a naive concat.

    Masks (when present) are scaled back consistently so mask-aware
    downstream stages keep working.
    """
    if scale <= 0.0:
        raise ValueError(f"scale must be > 0, got {scale}")
    inv = 1.0 / scale
    rescaled: list[dict[str, Any]] = []
    for det in downscaled:
        new_det = dict(det)
        x1, y1, x2, y2 = det["bbox"]
        new_det["bbox"] = [x1 * inv, y1 * inv, x2 * inv, y2 * inv]
        mask = det.get("mask")
        if isinstance(mask, dict) and isinstance(mask.get("points"), list):
            new_det["mask"] = {
                "format": mask.get("format"),
                "points": [[p[0] * inv, p[1] * inv] for p in mask["points"]],
            }
        rescaled.append(new_det)
    return nms(list(native) + rescaled, iou_threshold)


class DualResolutionDetector(DetectorBase):
    """Run an inner detector at native + downscaled resolution and merge.

    Router-compatible adapter: it wraps whatever :class:`DetectorBase` the
    model router resolved (never instantiates YOLO/SAM itself), so it inherits
    the inner detector's same-session safety. ``produces_masks`` mirrors the
    inner detector.
    """

    def __init__(
        self,
        inner: DetectorBase,
        *,
        downscale: float = DEFAULT_DOWNSCALE,
        iou_threshold: float = DEFAULT_MERGE_IOU,
    ) -> None:
        if not 0.0 < downscale < 1.0:
            raise ValueError(f"downscale must be in (0, 1), got {downscale}")
        self._inner = inner
        self._downscale = downscale
        self._iou = iou_threshold
        self.produces_masks = inner.produces_masks

    def detect(self, frame: np.ndarray) -> list[dict[str, Any]]:
        native = self._inner.detect(frame)
        small = self._resize(frame, self._downscale)
        if small is None:
            return native
        downscaled = self._inner.detect(small)
        return merge_dual_resolution(native, downscaled, self._downscale, self._iou)

    @staticmethod
    def _resize(frame: np.ndarray, scale: float) -> np.ndarray | None:
        h, w = frame.shape[:2]
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        if new_w == w and new_h == h:
            return None
        try:
            import cv2

            return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        except Exception:
            ys = np.linspace(0, h - 1, new_h).astype(np.int32)
            xs = np.linspace(0, w - 1, new_w).astype(np.int32)
            return frame[ys][:, xs]
