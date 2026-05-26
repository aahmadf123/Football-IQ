"""Stage 4 — Player Detection.

Delegates to the detector adapters in :mod:`pipeline.detector_models` so
the same code path serves YOLO (production same-session), SAM 3.1
(experimental nightly), and the deterministic stub used in tests.

Output: per-frame detection dicts stored in the job output_artifacts.
Schema is backward compatible — adapters that produce masks add an
optional ``mask`` field; everything that consumes detections downstream
treats ``mask`` as optional and continues to work on bbox-only input.

  {
    "<frame_number>": [
      {"bbox": [x1,y1,x2,y2], "confidence": 0.82, "class": "player"},
      {"bbox": [...], "confidence": ..., "class": "player",
       "mask": {"format": "polygon", "points": [[x, y], ...]}},
      ...
    ]
  }

Note: This stage does NOT write to tracklets — that is Stage 5.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import cv2
import structlog

from pipeline import r2
from pipeline.detector_models import DetectorBase, get_detector

log = structlog.get_logger(__name__)

MODEL_PATH = os.environ.get("MODEL_DETECT_PATH", "yolov8n.pt")
DETECTION_CONF = float(os.environ.get("DETECTION_CONF", "0.35"))
FRAME_STEP = int(os.environ.get("DETECT_FRAME_STEP", "3"))  # run every N frames


def run(
    video_id: str,
    input_uri: str,
    job_id: str,
    *,
    detector: DetectorBase | None = None,
    variant: str | None = None,
) -> dict[str, Any]:
    """Run Stage 4 detection and return per-frame bounding boxes.

    Args:
        video_id, input_uri, job_id: pipeline-standard arguments.
        detector: Pre-built detector adapter; overrides ``variant``.
                  Tests inject a ``StubDetector`` here.
        variant:  Routing variant id (e.g. ``"yolov8n"``, ``"sam3.1"``).
                  When omitted, the legacy ``MODEL_DETECT_PATH`` env var
                  selects a YOLO adapter — preserving prior behaviour.
    """
    log.info("stage_detect_start", video_id=video_id, variant=variant)

    if detector is None:
        selected_variant = variant or "yolov8n"
        detector_kwargs: dict[str, Any] = {
            "confidence_threshold": DETECTION_CONF,
        }
        if variant is None or selected_variant.startswith("yolo"):
            detector_kwargs["model_path"] = MODEL_PATH

        detector = get_detector(selected_variant, **detector_kwargs)

    r2_key = _uri_to_r2_key(input_uri)
    video_path = r2.download_to_temp(r2_key)
    try:
        return _detect(video_path, detector)
    finally:
        video_path.unlink(missing_ok=True)


def _uri_to_r2_key(uri: str) -> str:
    if uri.startswith("r2://"):
        return "/".join(uri.split("/")[3:])
    return uri


def _detect(video_path: Path, detector: DetectorBase) -> dict[str, Any]:
    cap = cv2.VideoCapture(str(video_path))
    fps: float = cap.get(cv2.CAP_PROP_FPS) or 30.0

    detections: dict[str, list[dict[str, Any]]] = {}
    frame_idx = 0
    masked_frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % FRAME_STEP == 0:
            frame_dets = detector.detect(frame)
            if frame_dets:
                detections[str(frame_idx)] = frame_dets
                if any("mask" in d for d in frame_dets):
                    masked_frame_count += 1

        frame_idx += 1

    cap.release()
    log.info(
        "stage_detect_done",
        frame_count=frame_idx,
        detection_frame_count=len(detections),
        masked_frame_count=masked_frame_count,
        produces_masks=detector.produces_masks,
    )
    return {
        "fps": fps,
        "total_frames": frame_idx,
        "detections": detections,
        "produces_masks": detector.produces_masks,
    }
