"""Stage 6 — Identity Association (Re-ID).

Phase 1 MVP approach:
  1. For each tracklet without a player_id, sample representative frames.
  2. Try jersey OCR (Tesseract) on the bounding box region.
  3. Match the OCR result against the roster (jersey_number field).
  4. If no OCR match, leave player_id null (manual assignment via coach UI).

Future: Add biometric ratio matching and gait/appearance embeddings.

Output: Tracklets updated with player_id via PATCH /api/v1/tracklets/{id}.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import structlog

from pipeline import r2

log = structlog.get_logger(__name__)

MIN_OCR_CONFIDENCE = 60  # Tesseract confidence threshold


def run(
    clip_id: str,
    video_path: Path,
    tracklet_ids: list[str],
    tracklets: list[dict[str, Any]],
    roster: list[dict[str, Any]],
    backend_api_url: str,
) -> dict[str, Any]:
    """Attempt to associate player identities with tracklets."""
    log.info("stage_reid_start", clip_id=clip_id, tracklet_count=len(tracklets))

    jersey_map: dict[int, str] = {
        p["jersey_number"]: p["id"]
        for p in roster
        if p.get("jersey_number") is not None
    }

    cap = cv2.VideoCapture(str(video_path))
    assigned = 0

    for tracklet in tracklets:
        if tracklet.get("player_id"):
            continue  # already assigned

        player_id = _identify_tracklet(tracklet, cap, jersey_map)
        if player_id:
            _patch_tracklet(tracklet["id"], player_id, backend_api_url)
            assigned += 1

    cap.release()
    log.info("stage_reid_done", clip_id=clip_id, assigned=assigned)
    return {"assigned": assigned, "total": len(tracklets)}


def _identify_tracklet(
    tracklet: dict[str, Any],
    cap: Any,
    jersey_map: dict[int, str],
) -> str | None:
    """Return a player_id UUID string if we can identify this tracklet, else None."""
    points = tracklet.get("track_points", [])
    if not points:
        return None

    # Sample a few frames near the middle of the track
    mid = len(points) // 2
    sample_indices = list({0, mid, len(points) - 1})
    for idx in sample_indices:
        pt = points[idx]
        bbox = pt.get("bbox")
        if not bbox:
            continue
        frame_number = pt.get("frame_number", 0)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ret, frame = cap.read()
        if not ret:
            continue

        number = _ocr_jersey(frame, bbox)
        if number is not None and number in jersey_map:
            return jersey_map[number]

    return None


def _ocr_jersey(frame: Any, bbox: list[float]) -> int | None:
    """Crop the bbox, run Tesseract on it, return jersey number or None."""
    try:
        import pytesseract  # type: ignore[import-untyped]
    except ImportError:
        return None  # Tesseract not installed in this environment

    x1, y1, x2, y2 = [int(v) for v in bbox]
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

    data = pytesseract.image_to_data(thresh, config="--psm 10 --oem 3 -c tessedit_char_whitelist=0123456789",
                                     output_type=pytesseract.Output.DICT)
    for text, conf in zip(data["text"], data["conf"]):
        text = text.strip()
        if text and re.fullmatch(r"\d{1,2}", text) and int(conf) >= MIN_OCR_CONFIDENCE:
            return int(text)
    return None


def _patch_tracklet(tracklet_id: str, player_id: str, backend_api_url: str) -> None:
    import httpx
    if not backend_api_url:
        return
    try:
        with httpx.Client(base_url=backend_api_url, timeout=10) as c:
            c.patch(f"/api/v1/tracklets/{tracklet_id}", json={"player_id": player_id})
    except Exception as exc:
        log.warning("tracklet_patch_failed", tracklet_id=tracklet_id, error=str(exc))
