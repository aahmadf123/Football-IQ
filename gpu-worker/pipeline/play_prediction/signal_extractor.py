"""Pre-snap signal extractor — the 6 signals of Issue #135.

Orchestrates the six pre-snap signals from already-calibrated, tracked,
team-classified, snap-anchored pipeline output:

    1. Personnel grouping        (``personnel.py``)
    2. Offensive formation       (``formation_mlp.py``)
    3. Backfield depth           (under-center / pistol / shotgun) — here
    4. Receiver split width      (wide / normal / tight)          — here
    5. Pre-snap motion type      (``motion_lstm.py``)
    6. Down-and-distance + zone  (down × distance-bucket × field-zone) — here

Every signal exposes a categorical ``value`` **and** a ``confidence`` in
``[0, 1]`` so the downstream Bayesian ensemble (Issue #136) can confidence-weight
each likelihood ratio. The whole :class:`PreSnapSignals` serializes to a JSON
dict suitable for ``play_predictions.signal_vector`` (JSONB).

The extractor degrades gracefully: any missing input yields a low-confidence /
``"unknown"`` signal rather than an exception, so a partially-analysed play
still produces an (appropriately uncertain) prediction — never a fabricated one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from pipeline.play_prediction.formation_mlp import FormationClassifier, FormationSignal
from pipeline.play_prediction.motion_lstm import MotionClassifier, MotionSignal
from pipeline.play_prediction.per_opponent_prior import distance_bucket, field_zone
from pipeline.play_prediction.personnel import PersonnelSignal, extract_personnel

# NCAA field-frame constant (see docs/calibration-contract.md): south↔north
# sideline at ±26.665 yd.
SIDELINE_Y = 26.665

# Backfield-depth Gaussian bin centres (yards the QB is behind the LOS).
_UNDER_CENTER_DEPTH = 1.0
_PISTOL_DEPTH = 4.0
_SHOTGUN_DEPTH = 6.0


@dataclass
class SignalValue:
    """A single categorical signal with its confidence + raw detail."""

    value: str
    confidence: float
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "confidence": round(self.confidence, 4), **self.detail}


@dataclass
class PreSnapSignals:
    """The 6 pre-snap signals for one play, serializable to JSONB."""

    personnel: SignalValue
    formation: SignalValue
    backfield: SignalValue
    split: SignalValue
    motion: SignalValue
    down_distance_zone: SignalValue
    schema_version: int = 1

    # ── Serialization ──────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable signal vector for ``play_predictions.signal_vector``."""
        return {
            "schema_version": self.schema_version,
            "personnel": self.personnel.to_dict(),
            "formation": self.formation.to_dict(),
            "backfield": self.backfield.to_dict(),
            "split": self.split.to_dict(),
            "motion": self.motion.to_dict(),
            "down_distance_zone": self.down_distance_zone.to_dict(),
        }

    # ── Ensemble adapters ──────────────────────────────────────────────────
    def signal_values(self) -> dict[str, str]:
        """``{signal_name: categorical_value}`` for the naive-Bayes combination."""
        return {
            "personnel": self.personnel.value,
            "formation": self.formation.value,
            "backfield": self.backfield.value,
            "split": self.split.value,
            "motion": self.motion.value,
            "down_distance_zone": self.down_distance_zone.value,
        }

    def signal_confidences(self) -> dict[str, float]:
        """``{signal_name: confidence}`` for confidence-weighting the LRs."""
        return {
            "personnel": self.personnel.confidence,
            "formation": self.formation.confidence,
            "backfield": self.backfield.confidence,
            "split": self.split.confidence,
            "motion": self.motion.confidence,
            "down_distance_zone": self.down_distance_zone.confidence,
        }

    def feature_vector(self) -> np.ndarray:
        """Numeric features for the optional MoE multi-class head."""
        return np.array(
            [
                float(self.personnel.detail.get("n_rb", 0)),
                float(self.personnel.detail.get("n_te", 0)),
                float(self.personnel.detail.get("n_wr", 0)),
                _BACKFIELD_CODE.get(self.backfield.value, 0.0),
                _SPLIT_CODE.get(self.split.value, 0.0),
                _MOTION_CODE.get(self.motion.value, 0.0),
                float(self.down_distance_zone.detail.get("down", 0) or 0),
                float(self.down_distance_zone.detail.get("distance_yards", 0) or 0),
            ],
            dtype=np.float64,
        )

    @property
    def mean_confidence(self) -> float:
        confs = list(self.signal_confidences().values())
        return float(sum(confs) / len(confs)) if confs else 0.0


_BACKFIELD_CODE = {"under_center": 0.0, "pistol": 1.0, "shotgun": 2.0, "unknown": -1.0}
_SPLIT_CODE = {"tight": 0.0, "normal": 1.0, "wide": 2.0, "unknown": -1.0}
_MOTION_CODE = {"none": 0.0, "jet": 1.0, "orbit": 2.0, "return": 3.0, "shift": 4.0, "across": 5.0}


# ── Signal 3: backfield depth ─────────────────────────────────────────────────


def extract_backfield(
    qb_position: tuple[float, float] | None,
    los_x: float,
    *,
    offense_direction: int = 1,
) -> SignalValue:
    """Classify QB alignment from depth behind the LOS via Gaussian binning.

    ``offense_direction`` is +1 when the offense moves toward increasing x
    (so "behind the LOS" is x < los_x) and -1 otherwise.
    """
    if qb_position is None:
        return SignalValue("unknown", 0.1, {"qb_depth_yd": None})
    depth = offense_direction * (los_x - qb_position[0])
    if depth < 0:
        return SignalValue("unknown", 0.1, {"qb_depth_yd": round(depth, 2)})
    centres = {
        "under_center": _UNDER_CENTER_DEPTH,
        "pistol": _PISTOL_DEPTH,
        "shotgun": _SHOTGUN_DEPTH,
    }
    # Soft Gaussian responsibilities (sigma 1.5 yd) → label + calibrated conf.
    sigma = 1.5
    resp = {k: float(np.exp(-((depth - c) ** 2) / (2 * sigma**2))) for k, c in centres.items()}
    total = sum(resp.values()) or 1.0
    label = max(resp, key=lambda k: resp[k])
    confidence = round(resp[label] / total, 4)
    return SignalValue(label, confidence, {"qb_depth_yd": round(depth, 2)})


# ── Signal 4: receiver split width ────────────────────────────────────────────


def extract_split(receiver_positions: list[tuple[float, float]]) -> SignalValue:
    """Classify the outermost receiver's distance from the nearest sideline.

    Wide (>6 yd off the sideline) / Normal (3–6) / Tight (<3), per Issue #135.
    """
    if not receiver_positions:
        return SignalValue("unknown", 0.1, {"min_sideline_distance_yd": None})
    ys = np.asarray([p[1] for p in receiver_positions], dtype=np.float64)
    # Outermost receiver = closest to a sideline (max |y|).
    outermost_idx = int(np.argmax(np.abs(ys)))
    outermost_y = float(ys[outermost_idx])
    distance_from_sideline = SIDELINE_Y - abs(outermost_y)
    distance_from_sideline = max(distance_from_sideline, 0.0)
    if distance_from_sideline > 6.0:
        label = "wide"
    elif distance_from_sideline >= 3.0:
        label = "normal"
    else:
        label = "tight"
    return SignalValue(
        label,
        0.7,
        {"min_sideline_distance_yd": round(distance_from_sideline, 2)},
    )


# ── Signal 6: down-and-distance + field zone ──────────────────────────────────


def extract_down_distance_zone(
    down: int | None,
    distance_yards: float | None,
    los_x: float | None,
    *,
    from_event_log: bool = True,
) -> SignalValue:
    """Combine down × distance-bucket × field-zone into one categorical value."""
    if down is None or distance_yards is None:
        return SignalValue(
            "unknown",
            0.1,
            {"down": down, "distance_yards": distance_yards, "from_event_log": from_event_log},
        )
    bucket = distance_bucket(distance_yards)
    zone = field_zone(los_x)
    value = f"{down}_{bucket}_{zone}"
    # High confidence when sourced from the event log; lower when auto-inferred.
    confidence = 0.95 if from_event_log else 0.5
    if zone == "unknown":
        confidence *= 0.8
    return SignalValue(
        value,
        round(confidence, 4),
        {
            "down": down,
            "distance_yards": distance_yards,
            "distance_bucket": bucket,
            "field_zone": zone,
            "from_event_log": from_event_log,
        },
    )


# ── Orchestrator ──────────────────────────────────────────────────────────────


def extract_signals(
    *,
    offense_players: list[dict[str, Any]],
    los_x: float,
    hash_y: float = 0.0,
    qb_position: tuple[float, float] | None = None,
    receiver_positions: list[tuple[float, float]] | None = None,
    motion_trajectory: list[tuple[float, float]] | None = None,
    down: int | None = None,
    distance_yards: float | None = None,
    down_distance_from_event_log: bool = True,
    offense_direction: int = 1,
    formation_classifier: FormationClassifier | None = None,
    motion_classifier: MotionClassifier | None = None,
) -> PreSnapSignals:
    """Extract all 6 pre-snap signals for a single snap.

    ``offense_players`` are the 11 offensive players at the snap frame, each a
    dict with field-frame ``x``/``y`` and optional ``position``/``jersey_number``
    /``role``. Missing optional inputs degrade the relevant signal's confidence
    rather than failing.
    """
    formation_classifier = formation_classifier or FormationClassifier()
    motion_classifier = motion_classifier or MotionClassifier()

    # Signal 1 — personnel.
    personnel_sig: PersonnelSignal = extract_personnel(offense_players)
    personnel = SignalValue(
        personnel_sig.grouping,
        personnel_sig.confidence,
        {k: v for k, v in personnel_sig.to_dict().items() if k != "grouping"},
    )

    # Signal 2 — formation.
    positions = [
        (float(p["x"]), float(p["y"]))
        for p in offense_players
        if p.get("x") is not None and p.get("y") is not None
    ]
    formation_res: FormationSignal = formation_classifier.classify(
        positions, los_x, hash_y, offense_direction=offense_direction
    )
    formation = SignalValue(
        formation_res.label,
        formation_res.confidence,
        {"method": formation_res.method, "n_players": formation_res.n_players},
    )

    # Signal 3 — backfield depth. Infer QB if not supplied.
    qb = qb_position or _infer_qb_position(offense_players)
    backfield = extract_backfield(qb, los_x, offense_direction=offense_direction)

    # Signal 4 — receiver split width. Infer receivers if not supplied.
    receivers = receiver_positions if receiver_positions is not None else _infer_receivers(offense_players)
    split = extract_split(receivers)

    # Signal 5 — motion type.
    if motion_trajectory:
        motion_res: MotionSignal = motion_classifier.classify(motion_trajectory)
        motion = SignalValue(
            motion_res.label,
            motion_res.confidence,
            {"method": motion_res.method, "n_frames": motion_res.n_frames},
        )
    else:
        motion = SignalValue("none", 0.3, {"method": "none", "n_frames": 0})

    # Signal 6 — down-distance + zone.
    down_distance_zone = extract_down_distance_zone(
        down, distance_yards, los_x, from_event_log=down_distance_from_event_log
    )

    return PreSnapSignals(
        personnel=personnel,
        formation=formation,
        backfield=backfield,
        split=split,
        motion=motion,
        down_distance_zone=down_distance_zone,
    )


def _infer_qb_position(offense_players: list[dict[str, Any]]) -> tuple[float, float] | None:
    for p in offense_players:
        pos = (p.get("position") or "").upper().strip()
        if pos == "QB" and p.get("x") is not None and p.get("y") is not None:
            return (float(p["x"]), float(p["y"]))
    return None


def _infer_receivers(offense_players: list[dict[str, Any]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for p in offense_players:
        pos = (p.get("position") or "").upper().strip()
        if pos in {"WR", "TE"} and p.get("x") is not None and p.get("y") is not None:
            out.append((float(p["x"]), float(p["y"])))
    return out
