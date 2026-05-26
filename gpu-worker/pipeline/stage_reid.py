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

import os
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

    adapter = _get_reid_adapter()
    cap = cv2.VideoCapture(str(video_path))
    assigned = 0

    # Gallery of (embedding, player_id) built from already-identified tracklets.
    gallery: list[tuple[np.ndarray, str]] = []

    for tracklet in tracklets:
        if tracklet.get("player_id"):
            # Seed the gallery so later tracklets can match against known players.
            if adapter is not None:
                emb = _extract_tracklet_embedding(tracklet, cap, adapter)
                if emb is not None:
                    gallery.append((emb, tracklet["player_id"]))
            continue

        player_id = _identify_tracklet(tracklet, cap, jersey_map, adapter, gallery)
        if player_id:
            _patch_tracklet(tracklet["id"], player_id, backend_api_url)
            assigned += 1
            if adapter is not None:
                emb = _extract_tracklet_embedding(tracklet, cap, adapter)
                if emb is not None:
                    gallery.append((emb, player_id))

    cap.release()
    log.info("stage_reid_done", clip_id=clip_id, assigned=assigned)
    return {"assigned": assigned, "total": len(tracklets)}


def _extract_tracklet_embedding(
    tracklet: dict[str, Any],
    cap: Any,
    adapter: "NvidiaReIDAdapter",
) -> "np.ndarray | None":
    """Extract a representative L2-normalised embedding for a tracklet."""
    points = tracklet.get("track_points", [])
    if not points:
        return None
    mid = len(points) // 2
    sample_indices = list({0, mid, len(points) - 1})
    embeddings: list[np.ndarray] = []
    for idx in sample_indices:
        pt = points[idx]
        bbox = pt.get("bbox")
        if not bbox:
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, pt.get("frame_number", 0))
        ret, frame = cap.read()
        if not ret:
            continue
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = frame.shape[:2]
        crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if crop.size == 0:
            continue
        try:
            embeddings.append(adapter.extract_embedding(crop))
        except Exception as exc:
            log.warning("reid_embedding_failed", error=str(exc))
    if not embeddings:
        return None
    avg: np.ndarray = np.mean(embeddings, axis=0)
    norm = float(np.linalg.norm(avg))
    if norm > 1e-6:
        avg = avg / norm
    return avg


def _identify_tracklet(
    tracklet: dict[str, Any],
    cap: Any,
    jersey_map: dict[int, str],
    adapter: "NvidiaReIDAdapter | None" = None,
    gallery: "list[tuple[np.ndarray, str]] | None" = None,
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

    # OCR found nothing — fall back to appearance-based matching via the ReID adapter.
    if adapter is not None and gallery:
        try:
            emb = _extract_tracklet_embedding(tracklet, cap, adapter)
            if emb is not None:
                best_pid: str | None = None
                best_sim = -1.0
                for ref_emb, pid in gallery:
                    sim = adapter.match(emb, ref_emb)
                    if sim >= adapter._threshold and sim > best_sim:
                        best_sim = sim
                        best_pid = pid
                if best_pid is not None:
                    return best_pid
        except Exception as exc:
            log.warning("reid_gallery_match_failed", error=str(exc))

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

    data = pytesseract.image_to_data(
        thresh,
        config="--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789",
        output_type=pytesseract.Output.DICT,
    )
    for text, conf in zip(data["text"], data["conf"]):
        text = text.strip()
        if text and re.fullmatch(r"\d{1,2}", text) and int(conf) >= MIN_OCR_CONFIDENCE:
            return int(text)
    return None


# ── NVIDIA TAO ReIdentificationNet adapter (Phase 2.5 spike) ──────────────


class NvidiaReIDAdapter:
    """Optional Re-ID adapter using NVIDIA TAO ReIdentificationNet.

    Extracts 256-d appearance embeddings from player bounding-box crops and
    compares them across tracklets using cosine similarity.  Falls back
    gracefully to jersey OCR when weights or VRAM are unavailable.

    Activation: set ``REID_MODEL=nvidia-tao:/path/to/resnet50_reid.onnx``.

    The model expects 256×128 RGB crops and outputs a 256-d L2-normalised
    embedding vector.

    Args:
        model_path: Path to the ``.onnx`` weights file.
        device_id:  CUDA device ordinal (default 0).
        threshold:  Cosine-similarity threshold for a positive match (default 0.6).
    """

    def __init__(
        self,
        model_path: str,
        device_id: int = 0,
        threshold: float = 0.6,
    ) -> None:
        from pathlib import Path as _P

        weights = _P(model_path)
        if not weights.is_file():
            raise FileNotFoundError(
                f"TAO ReIdentificationNet weights not found: {weights}. "
                "Download from NGC: ngc registry model download-version "
                "nvidia/tao/reidentificationnet:deployable_onnx_v1.0"
            )

        try:
            import onnxruntime as ort  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "onnxruntime-gpu is required for NvidiaReIDAdapter. "
                "Install with: pip install onnxruntime-gpu"
            ) from exc

        providers = [("CUDAExecutionProvider", {"device_id": device_id})]
        self._session = ort.InferenceSession(str(weights), providers=providers)
        self._input_name = self._session.get_inputs()[0].name
        self._threshold = threshold
        log.info("nvidia_reid_initialized", model_path=model_path, device_id=device_id)

    def extract_embedding(self, crop: np.ndarray) -> np.ndarray:
        """Return a 256-d L2-normalised embedding for a BGR player crop."""
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (128, 256))
        blob = resized.astype(np.float32).transpose(2, 0, 1)[np.newaxis] / 255.0
        outputs = self._session.run(None, {self._input_name: blob})
        emb = outputs[0].flatten().astype(np.float64)
        norm = np.linalg.norm(emb)
        if norm > 1e-6:
            emb /= norm
        return emb

    def match(self, emb_a: np.ndarray, emb_b: np.ndarray) -> float:
        """Return cosine similarity between two embeddings."""
        return float(np.dot(emb_a, emb_b))

    def is_match(self, emb_a: np.ndarray, emb_b: np.ndarray) -> bool:
        return self.match(emb_a, emb_b) >= self._threshold


_NVIDIA_TAO_PREFIX = "nvidia-tao:"


def _get_reid_adapter() -> NvidiaReIDAdapter | None:
    """Return an NvidiaReIDAdapter if configured and available, else None."""
    reid_model = os.environ.get("REID_MODEL", "")
    if not reid_model.startswith(_NVIDIA_TAO_PREFIX):
        return None
    weights = reid_model[len(_NVIDIA_TAO_PREFIX):]
    try:
        return NvidiaReIDAdapter(weights)
    except (ImportError, FileNotFoundError, RuntimeError) as exc:
        log.warning("nvidia_reid_unavailable_fallback", error=str(exc))
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
