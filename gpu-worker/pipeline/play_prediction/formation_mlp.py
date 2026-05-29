"""Signal 2 — offensive formation classifier (Issue #135).

The router's contract is satisfied without adding a model-router stage: like the
Bayesian snap detector (``docs/snap-los-ball-events.md``), this is a small
classifier that consumes already-routed stage outputs (calibrated, tracked,
team-classified positions). It runs identically in both priority buckets and
loads no heavy weights, so it is intentionally **not** in ``DEFAULT_ROUTING``.

Two paths, mirroring the PARSeq fallback pattern (Issue #131):

* **MLP path** — when a trained checkpoint is available (``torch`` + a weights
  file via ``PLAY_PREDICTION_FORMATION_MODEL``), a 22→128→64→12 MLP scores the
  normalized snap-frame positions. The acceptance target is ≥80% top-1 on a
  12-class holdout; the trained weights are produced offline and are **not**
  committed.
* **Geometric fallback** — a deterministic, explainable classifier over the
  normalized receiver/back distribution. It never fabricates a high-confidence
  call: its confidence is capped and ``method="geometric"`` so downstream
  weighting (and the UI) knows it is the fallback.

Inputs are normalized to a LOS- and hash-relative frame so the classifier is
translation/!hash invariant.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import numpy as np
import structlog

log = structlog.get_logger(__name__)

# 12 formation classes (Issue #135). Geometric fallback can only assert the
# subset it can defend; the MLP can emit any of the 12.
FORMATION_CLASSES: tuple[str, ...] = (
    "i_form",
    "singleback",
    "shotgun_2x2",
    "shotgun_3x1",
    "shotgun_empty",
    "pistol",
    "trips",
    "bunch",
    "wildcat",
    "goalline",
    "spread",
    "unknown",
)

# Confidence ceiling for the deterministic fallback — we never present a
# heuristic guess with model-grade certainty.
_GEOMETRIC_CONF_CAP = 0.6
_ENV_WEIGHTS = "PLAY_PREDICTION_FORMATION_MODEL"


@dataclass
class FormationSignal:
    label: str
    confidence: float
    method: str                      # "mlp" | "geometric"
    probabilities: dict[str, float]
    n_players: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "method": self.method,
            "probabilities": self.probabilities,
            "n_players": self.n_players,
        }


def normalize_positions(
    positions: list[tuple[float, float]],
    los_x: float,
    hash_y: float = 0.0,
) -> np.ndarray:
    """LOS/hash-relative, sorted feature vector for ``positions``.

    ``positions`` are field-frame ``(x, y)`` (yards). Output is a flat array of
    (x - los_x, y - hash_y) sorted by depth then width so the vector is
    permutation-stable. Padded/truncated to 11 players (22 dims).
    """
    pts = np.asarray(positions, dtype=np.float64).reshape(-1, 2)
    rel = pts - np.array([los_x, hash_y], dtype=np.float64)
    if rel.shape[0] == 0:
        return np.zeros(22, dtype=np.float64)
    order = np.lexsort((rel[:, 1], rel[:, 0]))
    rel = rel[order]
    flat = rel.reshape(-1)
    if flat.size >= 22:
        return flat[:22]
    return np.concatenate([flat, np.zeros(22 - flat.size)])


class FormationClassifier:
    """Trained-MLP-or-geometric formation classifier."""

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
            log.info("formation_mlp_loaded", path=self._weights_path)
            return True
        except Exception as exc:  # pragma: no cover - env-dependent
            log.warning("formation_mlp_load_failed", path=self._weights_path, error=str(exc))
            self._model = None
            return False

    def classify(
        self,
        positions: list[tuple[float, float]],
        los_x: float,
        hash_y: float = 0.0,
        *,
        offense_direction: int = 1,
    ) -> FormationSignal:
        n = len(positions)
        if self._maybe_load():
            try:
                return self._classify_mlp(positions, los_x, hash_y, n)
            except Exception as exc:  # pragma: no cover - env-dependent
                log.warning("formation_mlp_infer_failed_fallback_geometric", error=str(exc))
        return self._classify_geometric(positions, los_x, hash_y, n, offense_direction=offense_direction)

    def _classify_mlp(
        self,
        positions: list[tuple[float, float]],
        los_x: float,
        hash_y: float,
        n: int,
    ) -> FormationSignal:  # pragma: no cover - requires torch + weights
        import torch  # type: ignore[import-not-found]

        x = normalize_positions(positions, los_x, hash_y)
        with torch.no_grad():
            logits = self._model(torch.tensor(x, dtype=torch.float32).unsqueeze(0))
            probs = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()
        idx = int(np.argmax(probs))
        prob_map = {FORMATION_CLASSES[i]: float(probs[i]) for i in range(min(len(probs), len(FORMATION_CLASSES)))}
        return FormationSignal(
            label=FORMATION_CLASSES[idx] if idx < len(FORMATION_CLASSES) else "unknown",
            confidence=float(probs[idx]),
            method="mlp",
            probabilities=prob_map,
            n_players=n,
        )

    def _classify_geometric(
        self,
        positions: list[tuple[float, float]],
        los_x: float,
        hash_y: float,
        n: int,
        *,
        offense_direction: int = 1,
    ) -> FormationSignal:
        """Deterministic fallback over the normalized position distribution."""
        if n < 6:
            return FormationSignal("unknown", 0.1, "geometric", {"unknown": 1.0}, n)

        rel = np.asarray(positions, dtype=np.float64).reshape(-1, 2) - np.array([los_x, hash_y])
        # Backfield = offense players clearly behind the LOS (negative x toward
        # own goal). Width = lateral spread of skill players.
        depth = offense_direction * rel[:, 0]
        width = rel[:, 1]
        # Players >1.5 yd behind LOS are "backfield" (QB/RB); treat the rest as
        # on/near the line (OL + WR/TE split out wide).
        backfield = rel[depth < -1.5]
        n_back = int(backfield.shape[0])
        # Count receivers split wide (|y| > 8 yd from the ball / hash).
        n_wide = int(np.sum(np.abs(width) > 8.0))

        label = "singleback"
        conf = 0.45
        if n_back >= 4:
            label, conf = "shotgun_empty", 0.5
        elif n_wide >= 4:
            label, conf = "spread", 0.5
        elif n_back == 3:
            label, conf = "i_form", 0.5
        elif n_wide >= 3:
            label, conf = "trips", 0.5
        elif n_back <= 1:
            label, conf = "shotgun_2x2", 0.4

        conf = min(conf, _GEOMETRIC_CONF_CAP)
        probs = {c: 0.0 for c in FORMATION_CLASSES}
        probs[label] = conf
        probs["unknown"] = round(1.0 - conf, 3)
        return FormationSignal(label, conf, "geometric", probs, n)
