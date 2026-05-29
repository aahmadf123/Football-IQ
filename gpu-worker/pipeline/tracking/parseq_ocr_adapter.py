"""PARSeq jersey-number OCR adapter (Issue #131).

Tesseract (``stage_reid._ocr_jersey``) sits at ~40–55% on practice film.
PARSeq reads small, rotated, motion-blurred jersey text far better. This
adapter wraps a PARSeq checkpoint behind a tiny, model-agnostic interface and
**falls back gracefully** to ``None`` whenever torch or the weights are
unavailable — exactly like ``NvidiaReIDAdapter`` and the ``pytesseract``
import-guard in ``stage_reid``. The caller (``stage_reid``) then keeps using
Tesseract, so a missing checkpoint never fails a job.

Activation: ``REID_OCR_MODEL=parseq:/path/to/parseq.pt`` (or a directory the
loader understands). No weights are committed to the repository; the file is
mounted / downloaded at runtime, and the adapter logs a warning when it is
absent.

Routing: PARSeq is the nightly ``reid`` variant (``parseq-ocr``) and is on
``NIGHTLY_ONLY_VARIANTS``; same-session re-ID keeps Tesseract.
"""

from __future__ import annotations

import os
import re
from typing import Any

import numpy as np
import structlog

log = structlog.get_logger(__name__)

PARSEQ_PREFIX = "parseq:"
_JERSEY_RE = re.compile(r"\d{1,2}")
# Below this PARSeq softmax confidence we treat the read as a miss and let the
# downstream trajectory-prior layer take over.
MIN_PARSEQ_CONFIDENCE = 0.5


class PARSeqOCRAdapter:
    """Wrap a PARSeq checkpoint for jersey-number recognition.

    The heavy imports (torch, the PARSeq model) happen inside ``__init__`` so
    that importing this module never drags torch into ``pytest`` collection.

    Args:
        model_path: filesystem path to the PARSeq checkpoint.
        device: ``"cuda"`` or ``"cpu"``.
        min_confidence: softmax-confidence floor for a positive read.
    """

    def __init__(
        self,
        model_path: str,
        device: str = "cuda",
        min_confidence: float = MIN_PARSEQ_CONFIDENCE,
    ) -> None:
        from pathlib import Path

        weights = Path(model_path)
        if not weights.exists():
            raise FileNotFoundError(
                f"PARSeq checkpoint not found: {weights}. Mount or download it "
                "at runtime; weights are never committed to the repository."
            )
        try:
            import torch  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise ImportError(
                "torch is required for PARSeqOCRAdapter. Same-session re-ID "
                "uses Tesseract and needs no torch."
            ) from exc

        self._torch = torch
        self._min_confidence = min_confidence
        self._device = device if torch.cuda.is_available() else "cpu"
        # ``torch.jit``/``torch.load`` of a scripted PARSeq export keeps the
        # adapter independent of any specific PARSeq package layout.
        self._model = torch.jit.load(str(weights), map_location=self._device)
        self._model.eval()
        log.info("parseq_ocr_initialized", model_path=model_path, device=self._device)

    def recognize(self, crop: np.ndarray) -> tuple[int | None, float]:
        """Return ``(jersey_number | None, confidence)`` for a BGR crop."""
        if crop is None or crop.size == 0:
            return None, 0.0
        torch = self._torch
        try:
            import cv2

            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            resized = cv2.resize(rgb, (128, 32))
            blob = (
                torch.from_numpy(resized.astype(np.float32).transpose(2, 0, 1) / 255.0)
                .unsqueeze(0)
                .to(self._device)
            )
            with torch.no_grad():
                logits = self._model(blob)
            text, confidence = self._decode(logits)
        except Exception as exc:  # pragma: no cover - inference is env-dependent
            log.warning("parseq_recognize_failed", error=str(exc))
            return None, 0.0
        match = _JERSEY_RE.fullmatch(text.strip())
        if match is not None and confidence >= self._min_confidence:
            return int(match.group()), confidence
        return None, confidence

    def _decode(self, logits: Any) -> tuple[str, float]:
        """Greedy-decode a PARSeq logit tensor into ``(text, confidence)``."""
        torch = self._torch
        probs = torch.softmax(logits, dim=-1)
        conf, idx = probs.max(dim=-1)
        chars = idx.squeeze(0).tolist()
        confidence = float(conf.squeeze(0).mean().item())
        # PARSeq exports typically reserve index 0 for the end-of-sequence /
        # pad token; map the remaining indices to digits for jersey OCR.
        digits = "".join(str((c - 1) % 10) for c in chars if c > 0)
        return digits, confidence

    @property
    def min_confidence(self) -> float:
        return self._min_confidence


def get_parseq_adapter() -> PARSeqOCRAdapter | None:
    """Return a :class:`PARSeqOCRAdapter` if configured + available, else None.

    Reads ``REID_OCR_MODEL``; only the ``parseq:`` scheme activates PARSeq.
    Any failure (no torch, missing weights) downgrades to ``None`` so the
    caller falls back to Tesseract.
    """
    raw = os.environ.get("REID_OCR_MODEL", "")
    if not raw.startswith(PARSEQ_PREFIX):
        return None
    path = raw[len(PARSEQ_PREFIX):]
    try:
        return PARSeqOCRAdapter(path)
    except (ImportError, FileNotFoundError, RuntimeError) as exc:
        log.warning("parseq_unavailable_fallback_to_tesseract", error=str(exc))
        return None
