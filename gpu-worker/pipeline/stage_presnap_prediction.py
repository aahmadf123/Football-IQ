"""Stage — pre-snap run/pass prediction (Issues #135 + #136).

Runs *after* snap detection (Issue #132): consumes the calibrated, tracked,
team-classified, snap-anchored play state, extracts the six pre-snap signals
(Issue #135), and runs the calibrated Bayesian ensemble (Issue #136) to produce
one calibrated ``P(pass)`` + uncertainty per play, persisted via
``POST /api/v1/play-predictions/batch``.

Like the snap detector and the self-scout stage this is a deterministic /
small-model computation over already-routed stage outputs — it loads no heavy
weights in the default (fallback) path and runs identically in both priority
buckets, so it deliberately registers **no** ``model_router`` stage (same
rationale as ``docs/snap-los-ball-events.md``).

The per-opponent Dirichlet store supplies each play's situational base log-odds.
When no store (or no matching data-backed cell) is available the ensemble falls
back to the documented D1 neutral base rate — never a fabricated opponent
tendency. With ``BACKEND_API_URL`` unset the stage computes predictions and
returns them without persisting (offline / unit-test mode).
"""

from __future__ import annotations

from typing import Any

import structlog

from pipeline import backend
from pipeline.play_prediction.bayesian_ensemble import BayesianEnsemble
from pipeline.play_prediction.per_opponent_prior import OpponentPriorStore
from pipeline.play_prediction.signal_extractor import extract_signals

log = structlog.get_logger(__name__)


def _float_or_default(value: Any, default: float) -> float:
    return default if value is None else float(value)


def _int_or_default(value: Any, default: int) -> int:
    return default if value is None else int(value)


def run(
    plays: list[dict[str, Any]],
    *,
    ensemble: BayesianEnsemble | None = None,
    opponent_prior_store: OpponentPriorStore | None = None,
    model_version_id: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Predict run/pass for a batch of snaps and (optionally) persist them.

    Each ``play`` dict supplies: ``clip_id`` (required), ``offense_players``
    (list of ``{x, y, position?, jersey_number?}``), ``los_x``, optional
    ``down`` / ``distance_yards`` / ``opponent_team`` / ``play_id`` /
    ``motion_trajectory`` / ``qb_position`` / ``hash_y`` / ``offense_direction``.
    Missing fields degrade the relevant signal's confidence rather than failing.
    """
    ensemble = ensemble or BayesianEnsemble()
    log.info("stage_presnap_prediction_start", play_count=len(plays))

    rows: list[dict[str, Any]] = []
    for play in plays:
        clip_id = play.get("clip_id")
        if not clip_id:
            log.warning("presnap_play_missing_clip_id_skipped")
            continue

        los_x = _float_or_default(play.get("los_x"), 50.0)
        down = play.get("down")
        distance = play.get("distance_yards")
        opponent = play.get("opponent_team")

        signals = extract_signals(
            offense_players=play.get("offense_players", []),
            los_x=los_x,
            hash_y=_float_or_default(play.get("hash_y"), 0.0),
            qb_position=play.get("qb_position"),
            receiver_positions=play.get("receiver_positions"),
            motion_trajectory=play.get("motion_trajectory"),
            down=down,
            distance_yards=distance,
            down_distance_from_event_log=bool(play.get("down_distance_from_event_log", True)),
            offense_direction=_int_or_default(play.get("offense_direction"), 1),
        )

        # Situational base log-odds from the per-opponent Dirichlet store. Only
        # a data-backed cell overrides the neutral base rate; otherwise we leave
        # base_log_odds=None so the ensemble uses its documented default.
        base_log_odds: float | None = None
        if opponent_prior_store is not None:
            cell = opponent_prior_store.get(opponent, down, distance, los_x)
            if cell.is_data_backed:
                base_log_odds = cell.log_odds()

        result = ensemble.predict(
            signals.signal_values(),
            base_log_odds=base_log_odds,
            signal_confidences=signals.signal_confidences(),
            feature_vector=signals.feature_vector(),
        )

        row: dict[str, Any] = {
            "clip_id": str(clip_id),
            "signal_vector": signals.to_dict(),
            "logit_score": result.logit_score,
            "predicted_class": result.predicted_class,
            "calibrated_prob": result.calibrated_prob,
            "confidence": result.confidence,
            "uncertainty": result.uncertainty,
            "is_calibrated": result.is_calibrated,
        }
        if opponent is not None:
            row["opponent_team"] = opponent
        if play.get("play_id") is not None:
            row["play_id"] = str(play["play_id"])
        if model_version_id is not None:
            row["model_version_id"] = model_version_id
        rows.append(row)

    persisted = 0
    if persist and rows:
        resp = backend.create_play_predictions_batch(rows)
        if resp is not None:
            persisted = int(resp.get("created", 0))

    log.info(
        "stage_presnap_prediction_done",
        predicted=len(rows),
        persisted=persisted,
    )
    return {
        "prediction_count": len(rows),
        "persisted_count": persisted,
        "predictions": rows,
    }
