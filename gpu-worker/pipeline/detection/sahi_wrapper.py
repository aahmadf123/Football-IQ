"""Slicing-Aided Hyper Inference adapter (Issue #128 / #133).

SAHI (https://arxiv.org/abs/2202.06934) recovers tiny objects by slicing the
frame into overlapping tiles, running the detector on each tile at full
effective resolution, then mapping the per-tile boxes back to frame
coordinates and de-duplicating across tile seams.

We implement the slicing/merge logic in-house rather than depending on the
``sahi`` PyPI package: the geometry is a few lines of NumPy, it adds no new
dependency or weight download, and — crucially — it stays fully testable with
``StubDetector`` in CI. The inner detector is whatever the model router
resolved, so the adapter never instantiates YOLO/SAM directly and inherits the
inner detector's same-session safety.

Tile presets (from the issues):

* Player class (Issue #128, ``drone_follow``): 400×400 tiles, 0.2 overlap.
* Ball class   (Issue #133, ``drone_follow``): 128×128 tiles, 0.2 overlap.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import structlog

from pipeline.detection.dual_res_merger import DEFAULT_MERGE_IOU, nms
from pipeline.detector_models import DetectorBase

log = structlog.get_logger(__name__)

# Player preset (Issue #128).
PLAYER_TILE = 400
# Ball preset (Issue #133).
BALL_TILE = 128
DEFAULT_OVERLAP = 0.2


def slice_offsets(
    width: int,
    height: int,
    tile: int,
    overlap: float,
) -> list[tuple[int, int, int, int]]:
    """Compute ``(x1, y1, x2, y2)`` tile windows covering a ``width×height``
    frame with ``tile``-sized tiles and fractional ``overlap``.

    The last tile in each row/column is clamped to the frame edge so the whole
    image is covered without running off the boundary. When the frame is
    smaller than a tile a single full-frame window is returned.
    """
    if tile <= 0:
        raise ValueError(f"tile must be > 0, got {tile}")
    if not 0.0 <= overlap < 1.0:
        raise ValueError(f"overlap must be in [0, 1), got {overlap}")
    if width <= tile and height <= tile:
        return [(0, 0, width, height)]

    step = max(1, int(round(tile * (1.0 - overlap))))
    xs = _axis_starts(width, tile, step)
    ys = _axis_starts(height, tile, step)
    windows: list[tuple[int, int, int, int]] = []
    for y in ys:
        for x in xs:
            windows.append((x, y, min(x + tile, width), min(y + tile, height)))
    return windows


def _axis_starts(length: int, tile: int, step: int) -> list[int]:
    if length <= tile:
        return [0]
    starts: list[int] = list(range(0, length - tile + 1, step))
    last = length - tile
    if not starts or starts[-1] != last:
        starts.append(last)
    return starts


def _offset_detection(
    det: dict[str, Any], dx: int, dy: int
) -> dict[str, Any]:
    """Shift a tile-local detection back into frame coordinates."""
    out = dict(det)
    x1, y1, x2, y2 = det["bbox"]
    out["bbox"] = [x1 + dx, y1 + dy, x2 + dx, y2 + dy]
    mask = det.get("mask")
    if isinstance(mask, dict) and isinstance(mask.get("points"), list):
        out["mask"] = {
            "format": mask.get("format"),
            "points": [[p[0] + dx, p[1] + dy] for p in mask["points"]],
        }
    return out


class SAHIDetectorAdapter(DetectorBase):
    """Slice a frame into overlapping tiles, detect per tile, merge.

    Args:
        inner:   The router-resolved detector to run on each tile.
        tile:    Square tile side in pixels (``PLAYER_TILE`` / ``BALL_TILE``).
        overlap: Fractional tile overlap in ``[0, 1)``.
        iou_threshold: IoU above which boxes from adjacent tiles are merged.
        full_frame_pass: When True, also run the inner detector once on the
            whole frame and merge it in. This keeps recall on large objects
            that a single tile can't fully contain (e.g. a close player in a
            drone zoom-in). Defaults to True.
    """

    def __init__(
        self,
        inner: DetectorBase,
        *,
        tile: int = PLAYER_TILE,
        overlap: float = DEFAULT_OVERLAP,
        iou_threshold: float = DEFAULT_MERGE_IOU,
        full_frame_pass: bool = True,
    ) -> None:
        self._inner = inner
        self._tile = tile
        self._overlap = overlap
        self._iou = iou_threshold
        self._full_frame_pass = full_frame_pass
        self.produces_masks = inner.produces_masks

    def detect(self, frame: np.ndarray) -> list[dict[str, Any]]:
        h, w = frame.shape[:2]
        collected: list[dict[str, Any]] = []
        if self._full_frame_pass:
            collected.extend(self._inner.detect(frame))
        for x1, y1, x2, y2 in slice_offsets(w, h, self._tile, self._overlap):
            tile_img = frame[y1:y2, x1:x2]
            if tile_img.size == 0:
                continue
            for det in self._inner.detect(tile_img):
                collected.append(_offset_detection(det, x1, y1))
        merged = nms(collected, self._iou)
        log.debug(
            "sahi_detect",
            tile=self._tile,
            overlap=self._overlap,
            raw=len(collected),
            merged=len(merged),
        )
        return merged
