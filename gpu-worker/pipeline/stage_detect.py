"""Stage 4 — Player Detection.

Uses the Ultralytics YOLO family (yolov8n by default — swap for a fine-tuned
football model by setting the MODEL_DETECT_PATH env var).

Detects per-frame bounding boxes for:
  - players (class ≈ "person" in COCO; map to "player" in our schema)
  - officials (same class, but uniform colour differs — handled in Stage 6)
  - ball (class "sports ball")

Output: raw detections stored in the job output_artifacts for Stage 5 to consume.
The detections dict structure:
  {
    "<frame_number>": [
      {"bbox": [x1,y1,x2,y2], "confidence": 0.82, "class": "player"},
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

log = structlog.get_logger(__name__)

MODEL_PATH = os.environ.get("MODEL_DETECT_PATH", "yolov8n.pt")
DETECTION_CONF = float(os.environ.get("DETECTION_CONF", "0.35"))
DETECT_CLASSES = {0: "player", 32: "ball"}  # COCO class ids
FRAME_STEP = int(os.environ.get("DETECT_FRAME_STEP", "3"))  # run every N frames


def run(video_id: str, input_uri: str, job_id: str) -> dict[str, Any]:
    """Run Stage 4 detection and return per-frame bounding boxes."""
    log.info("stage_detect_start", video_id=video_id)

    r2_key = _uri_to_r2_key(input_uri)
    video_path = r2.download_to_temp(r2_key)
    try:
        return _detect(video_path)
    finally:
        video_path.unlink(missing_ok=True)


def _uri_to_r2_key(uri: str) -> str:
    if uri.startswith("r2://"):
        return "/".join(uri.split("/")[3:])
    return uri


def _detect(video_path: Path) -> dict[str, Any]:
    from ultralytics import YOLO  # type: ignore[import-untyped]

    model = YOLO(MODEL_PATH)
    cap = cv2.VideoCapture(str(video_path))
    fps: float = cap.get(cv2.CAP_PROP_FPS) or 30.0

    detections: dict[str, list[dict[str, Any]]] = {}
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % FRAME_STEP == 0:
            results = model(frame, conf=DETECTION_CONF, verbose=False)
            frame_dets: list[dict[str, Any]] = []
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    if cls_id not in DETECT_CLASSES:
                        continue
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    frame_dets.append({
                        "bbox": [x1, y1, x2, y2],
                        "confidence": float(box.conf[0]),
                        "class": DETECT_CLASSES[cls_id],
                    })
            if frame_dets:
                detections[str(frame_idx)] = frame_dets

        frame_idx += 1

    cap.release()
    log.info("stage_detect_done", frame_count=frame_idx,
             detection_frame_count=len(detections))
    return {"fps": fps, "total_frames": frame_idx, "detections": detections}
