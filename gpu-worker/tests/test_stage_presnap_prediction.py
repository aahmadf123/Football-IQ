"""Tests for the pre-snap prediction stage (Issues #135 / #136)."""

from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline import stage_presnap_prediction as stage
from pipeline.play_prediction.bayesian_ensemble import BayesianEnsemble
from pipeline.play_prediction.per_opponent_prior import OpponentPriorStore


def _offense() -> list[dict[str, Any]]:
    players: list[dict[str, Any]] = [
        {"position": "OL", "jersey_number": 50 + i, "x": 50.0, "y": -2.0 + i} for i in range(5)
    ]
    players.append({"position": "QB", "jersey_number": 12, "x": 44.0, "y": 0.0})
    players.append({"position": "RB", "jersey_number": 22, "x": 43.0, "y": 0.0})
    players.append({"position": "TE", "jersey_number": 88, "x": 50.0, "y": 3.0})
    players += [
        {"position": "WR", "jersey_number": 80, "x": 50.0, "y": 20.0},
        {"position": "WR", "jersey_number": 81, "x": 50.0, "y": -18.0},
        {"position": "WR", "jersey_number": 82, "x": 50.0, "y": 12.0},
    ]
    return players


def _play(clip_id: str = "clip-1") -> dict[str, Any]:
    return {
        "clip_id": clip_id,
        "offense_players": _offense(),
        "los_x": 50.0,
        "down": 3,
        "distance_yards": 8.0,
        "opponent_team": "Ohio",
        "motion_trajectory": [(40.0, -10.0), (45.0, -4.0), (50.0, 2.0)],
    }


def test_stage_runs_offline_without_persisting() -> None:
    # BACKEND_API_URL unset (default in tests) → persist is a no-op.
    result = stage.run([_play()], persist=True)
    assert result["prediction_count"] == 1
    assert result["persisted_count"] == 0
    pred = result["predictions"][0]
    assert pred["clip_id"] == "clip-1"
    assert pred["predicted_class"] in ("run", "pass")
    assert 0.0 <= pred["calibrated_prob"] <= 1.0
    assert 0.0 <= pred["uncertainty"] <= 1.0
    # The full 6-signal vector is attached (JSONB-bound).
    for key in ("personnel", "formation", "backfield", "split", "motion", "down_distance_zone"):
        assert key in pred["signal_vector"]


def test_stage_skips_plays_without_clip_id() -> None:
    result = stage.run([{"offense_players": _offense(), "los_x": 50.0}], persist=False)
    assert result["prediction_count"] == 0


def test_stage_uses_data_backed_opponent_prior() -> None:
    store = OpponentPriorStore()
    # Build a strongly pass-leaning, data-backed cell for the exact situation.
    for _ in range(20):
        store.update("Ohio", 3, 8.0, 50.0, "pass")

    ensemble = BayesianEnsemble()  # no learned LRs → base rate + prior only
    with_prior = stage.run(
        [_play()], ensemble=ensemble, opponent_prior_store=store, persist=False
    )["predictions"][0]
    without_prior = stage.run([_play()], ensemble=ensemble, persist=False)["predictions"][0]

    # The data-backed pass-leaning prior pushes P(pass) higher than the neutral
    # default base rate.
    assert with_prior["calibrated_prob"] > without_prior["calibrated_prob"]
    assert with_prior["predicted_class"] == "pass"


def test_stage_ignores_non_data_backed_prior() -> None:
    store = OpponentPriorStore()  # all cells are the safe Beta(2,2) default
    ensemble = BayesianEnsemble()
    with_store = stage.run(
        [_play()], ensemble=ensemble, opponent_prior_store=store, persist=False
    )["predictions"][0]
    without_store = stage.run([_play()], ensemble=ensemble, persist=False)["predictions"][0]
    # A non-data-backed cell must NOT override the neutral base rate.
    assert with_store["calibrated_prob"] == without_store["calibrated_prob"]


def test_stage_persists_via_backend(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, Any] = {}

    def _fake_post(rows: list[dict[str, Any]]) -> dict[str, Any]:
        captured["rows"] = rows
        return {"created": len(rows), "ids": ["x"] * len(rows)}

    monkeypatch.setattr(stage.backend, "create_play_predictions_batch", _fake_post)
    result = stage.run([_play(), _play("clip-2")], persist=True)
    assert result["persisted_count"] == 2
    assert len(captured["rows"]) == 2
    assert captured["rows"][0]["clip_id"] == "clip-1"


def test_stage_defaults_none_numeric_fields() -> None:
    play = _play()
    play.update({"los_x": None, "hash_y": None, "offense_direction": None})
    result = stage.run([play], persist=False)
    assert result["prediction_count"] == 1
