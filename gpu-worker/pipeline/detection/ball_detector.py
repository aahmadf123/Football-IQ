"""Dedicated ball detector (Issue #133).

The ball is trained as its *own* model, not as a class on the player detector:
the player/ball class imbalance is brutal and a shared head misses the ball
constantly. Ball pixel size is entirely regime-driven:

* ``fixed_sideline`` 1080p: ball is 20–40 px — run the nano model full-frame
  (~3× faster, no slicing needed).
* ``drone_follow`` 1080p: ball is 6–18 px — wrap the nano model in SAHI with
  128×128 tiles + 0.2 overlap (Issue #133, the P2 tiny-object head).

This adapter is router-compatible: the model router picks the base ball
variant via ``select_model("ball", priority)`` and the *regime* (detected at
ingest, Issue #126) decides whether SAHI is applied. No new heavy dependency
and no committed weights — when the dedicated weights / ultralytics are absent
the factory falls back to a deterministic stub so CI runs without a GPU.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np
import structlog

from pipeline.detection.sahi_wrapper import BALL_TILE, DEFAULT_OVERLAP, SAHIDetectorAdapter
from pipeline.detector_models import DetectorBase, YOLODetector

log = structlog.get_logger(__name__)

BALL_CLASS = "ball"

# Router variant id for the dedicated nano ball model.
YOLO_BALL = "yolov8n-ball"
# Path to the dedicated ball weights (never committed; supplied at deploy time).
MODEL_BALL_PATH = os.environ.get("MODEL_BALL_PATH", "yolov8n-ball.pt")
BALL_DETECTION_CONF = float(os.environ.get("BALL_DETECTION_CONF", "0.25"))

# Regimes (kept in sync with pipeline.homography.regime_detector).
DRONE_FOLLOW = "drone_follow"


class BallDetectorAdapter(DetectorBase):
    """Wrap an inner detector and emit only ``ball`` detections.

    The dedicated ball model reports its single foreground class as id 0; we
    normalise every kept detection to ``class = "ball"`` regardless of the
    inner model's labelling so downstream code has one canonical ball class.
    """

    produces_masks = False

    def __init__(self, inner: DetectorBase) -> None:
        self._inner = inner

    def detect(self, frame: np.ndarray) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for det in self._inner.detect(frame):
            # Accept the inner model's ball-ish output; force canonical class.
            new_det = {
                "bbox": list(det["bbox"]),
                "confidence": float(det.get("confidence", 0.0)),
                "class": BALL_CLASS,
            }
            out.append(new_det)
        return out


class _StubBallDetector(DetectorBase):
    """Deterministic single-ball detector for CI (no weights, no GPU)."""

    produces_masks = False

    def detect(self, frame: np.ndarray) -> list[dict[str, Any]]:
        h, w = frame.shape[:2] if frame.ndim >= 2 else (720, 1280)
        cx, cy = w * 0.5, h * 0.45
        r = max(3.0, min(w, h) * 0.01)
        return [
            {
                "bbox": [cx - r, cy - r, cx + r, cy + r],
                "confidence": 0.7,
                "class": BALL_CLASS,
            }
        ]


def get_ball_detector(
    variant: str = YOLO_BALL,
    *,
    model_path: str | None = None,
    confidence_threshold: float = BALL_DETECTION_CONF,
) -> DetectorBase:
    """Build the base ball detector for a routing variant.

    ``yolov8n-ball`` → a YOLO model loaded from the dedicated ball weights,
    its single class normalised to ``ball``. On ImportError (ultralytics /
    weights absent) it falls back to the deterministic stub — the same
    self-configuring behaviour as :func:`pipeline.detector_models.get_detector`.
    """
    v = (variant or "").lower()
    if v.startswith("yolo") and "ball" in v:
        try:
            base = YOLODetector(
                model_path=model_path or MODEL_BALL_PATH,
                confidence_threshold=confidence_threshold,
                class_map={0: BALL_CLASS},
            )
            return BallDetectorAdapter(base)
        except ImportError:
            log.warning("ball_model_unavailable_using_stub", variant=variant)
            return _StubBallDetector()
    log.warning("unknown_ball_variant_using_stub", variant=variant)
    return _StubBallDetector()


def ball_strategy(regime: str | None) -> str:
    """Return the slicing strategy label for the routing artifact."""
    return f"sahi-{BALL_TILE}" if regime == DRONE_FOLLOW else "full-frame"


def build_ball_detector(
    variant: str = YOLO_BALL,
    regime: str | None = None,
    *,
    base: DetectorBase | None = None,
) -> DetectorBase:
    """Compose the regime-appropriate ball detector.

    ``drone_follow`` → SAHI (128 px tiles, 0.2 overlap) for the 6–18 px ball.
    Everything else  → the base nano model run full-frame.
    """
    detector = base if base is not None else get_ball_detector(variant)
    if regime == DRONE_FOLLOW:
        return SAHIDetectorAdapter(
            detector,
            tile=BALL_TILE,
            overlap=DEFAULT_OVERLAP,
            full_frame_pass=False,
        )
    return detector
