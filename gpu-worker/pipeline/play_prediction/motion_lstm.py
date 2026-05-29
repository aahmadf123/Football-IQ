"""Signal 5 — pre-snap motion-type classifier (Issue #135).

Classifies the trajectory of the motion man over a window (default 30 frames)
before the snap into one of: ``jet``, ``orbit``, ``return``, ``shift``,
``across`` (plus ``none`` when no meaningful motion is detected).

Same two-path design as the formation classifier:

* **LSTM path** — a trained sequence model loaded from
  ``PLAY_PREDICTION_MOTION_MODEL`` (``torch``). Acceptance target ≥75% on a
  5-class holdout. Weights are produced offline and are **not** committed.
* **Rule-based fallback** — deterministic features over the trajectory (net
  lateral displacement, direction reversals, speed, and whether the player
  returns near its start) classify the motion. Confidence is capped so the
  fallback never masquerades as a trained model.

This consumes tracklet field-coordinate trajectories from the routed ``track``
stage; like the snap detector it adds no model-router stage.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import numpy as np
import structlog

log = structlog.get_logger(__name__)

MOTION_CLASSES: tuple[str, ...] = ("none", "jet", "orbit", "return", "shift", "across")

_RULE_CONF_CAP = 0.6
_ENV_WEIGHTS = "PLAY_PREDICTION_MOTION_MODEL"

# Below this lateral displacement (yards) over the window there is no motion.
_MIN_MOTION_YARDS = 2.0


@dataclass
class MotionSignal:
    label: str
    confidence: float
    method: str                     # "lstm" | "rule"
    probabilities: dict[str, float]
    n_frames: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "method": self.method,
            "probabilities": self.probabilities,
            "n_frames": self.n_frames,
        }


class MotionClassifier:
    """Trained-LSTM-or-rule-based motion-type classifier."""

    def __init__(self, weights_path: str | None = None) -> None:
        self._weights_path = weights_path if weights_path is not None else os.environ.get(_ENV_WEIGHTS)
        self._model: Any = None
        self._tried_load = False

    def _maybe_load(self) -> bool:
        if self._model is not None:
            return True
        if self._tried_load or not self._weights_path:
            return False
        self._tried_load = True
        try:
            import torch  # type: ignore[import-not-found]

            self._model = torch.jit.load(self._weights_path)  # type: ignore[no-untyped-call]
            self._model.eval()
            log.info("motion_lstm_loaded", path=self._weights_path)
            return True
        except Exception as exc:  # pragma: no cover - env-dependent
            log.warning("motion_lstm_load_failed", path=self._weights_path, error=str(exc))
            self._model = None
            return False

    def classify(self, trajectory: list[tuple[float, float]]) -> MotionSignal:
        """Classify a field-frame ``(x, y)`` trajectory (oldest → snap)."""
        n = len(trajectory)
        if self._maybe_load():
            try:
                return self._classify_lstm(trajectory, n)
            except Exception as exc:  # pragma: no cover - env-dependent
                log.warning("motion_lstm_infer_failed_fallback_rule", error=str(exc))
        return self._classify_rule(trajectory, n)

    def _classify_lstm(
        self, trajectory: list[tuple[float, float]], n: int
    ) -> MotionSignal:  # pragma: no cover - requires torch + weights
        import torch  # type: ignore[import-not-found]

        seq = np.asarray(trajectory, dtype=np.float64).reshape(-1, 2)
        with torch.no_grad():
            logits = self._model(torch.tensor(seq, dtype=torch.float32).unsqueeze(0))
            probs = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()
        idx = int(np.argmax(probs))
        prob_map = {MOTION_CLASSES[i]: float(probs[i]) for i in range(min(len(probs), len(MOTION_CLASSES)))}
        return MotionSignal(
            label=MOTION_CLASSES[idx] if idx < len(MOTION_CLASSES) else "none",
            confidence=float(probs[idx]),
            method="lstm",
            probabilities=prob_map,
            n_frames=n,
        )

    def _classify_rule(self, trajectory: list[tuple[float, float]], n: int) -> MotionSignal:
        if n < 3:
            return self._single("none", 0.2, n)

        seq = np.asarray(trajectory, dtype=np.float64).reshape(-1, 2)
        dx = seq[:, 0] - seq[0, 0]         # depth change vs start
        dy = seq[:, 1] - seq[0, 1]         # lateral change vs start
        lateral_range = float(np.max(seq[:, 1]) - np.min(seq[:, 1]))
        net_lateral = float(dy[-1])
        end_to_start = float(np.hypot(seq[-1, 0] - seq[0, 0], seq[-1, 1] - seq[0, 1]))
        # Direction reversals in the lateral axis.
        steps = np.diff(seq[:, 1])
        signs = np.sign(steps[np.abs(steps) > 1e-3])
        reversals = int(np.sum(np.abs(np.diff(signs)) > 0)) if signs.size > 1 else 0
        depth_gain = float(np.max(np.abs(dx)))

        if lateral_range < _MIN_MOTION_YARDS and depth_gain < _MIN_MOTION_YARDS:
            return self._single("none", 0.4, n)

        # Returns near the starting spot → "return".
        if end_to_start < 2.0 and lateral_range >= _MIN_MOTION_YARDS:
            label, conf = "return", 0.5
        # Curved path with depth excursion → "orbit".
        elif reversals >= 1 and depth_gain >= 2.0:
            label, conf = "orbit", 0.45
        # Fast, flat, long lateral motion across the formation → "jet".
        elif abs(net_lateral) >= 6.0 and depth_gain < 2.5:
            label, conf = "jet", 0.5
        # Crosses the ball (sign change of absolute y across midline) → "across".
        elif np.sign(seq[0, 1]) != np.sign(seq[-1, 1]) and abs(net_lateral) >= 3.0:
            label, conf = "across", 0.45
        else:
            label, conf = "shift", 0.4

        conf = min(conf, _RULE_CONF_CAP)
        return self._single(label, conf, n)

    @staticmethod
    def _single(label: str, conf: float, n: int) -> MotionSignal:
        probs = {c: 0.0 for c in MOTION_CLASSES}
        probs[label] = conf
        if label != "none":
            probs["none"] = round(1.0 - conf, 3)
        return MotionSignal(label, conf, "rule", probs, n)
