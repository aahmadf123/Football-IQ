"""Tests for the play-prediction router (Issues #135 / #136)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

from app.database import get_db
from app.governance import Action, Resource, policy_allows
from app.models import OpponentPrior, PlayPrediction, User, UserRole
from fastapi.testclient import TestClient

from app.main import app  # isort: skip


def _make_user(role: UserRole = UserRole.coach) -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = role
    u.is_active = True
    return u


class _RecordingSession:
    """Async-session stand-in that records added rows and serves canned queries.

    ``require_workload_capacity`` calls ``assess_workload(db)`` directly, which
    issues two ``select(count())`` queries reading ``scalar_one``. We serve
    ``queued_count``/``running_count`` for those first two calls so the gate can
    be driven healthy or saturated, then the endpoint-specific queries follow.
    """

    def __init__(
        self,
        *,
        existing_clip_ids: set[uuid.UUID] | None = None,
        predictions: list[PlayPrediction] | None = None,
        prediction_by_id: PlayPrediction | None = None,
        opponent_prior: OpponentPrior | None = None,
        queued_count: int = 0,
        running_count: int = 0,
        gated: bool = False,
    ) -> None:
        self.added: list[Any] = []
        self._existing_clip_ids = existing_clip_ids or set()
        self._predictions = predictions or []
        self._prediction_by_id = prediction_by_id
        self._opponent_prior = opponent_prior
        # When the batch endpoint is gated, workload runs first (2 count calls).
        needs_counts = gated or queued_count or running_count
        self._counts = [queued_count, running_count] if needs_counts else []
        self._call = 0

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        result = MagicMock()
        if self._counts:
            result.scalar_one.return_value = self._counts.pop(0)
            result.scalar_one_or_none.return_value = None
            result.all.return_value = []
            result.scalars.return_value.all.return_value = []
            return result
        self._call += 1
        result.scalar_one.return_value = 0
        result.all.return_value = [(cid,) for cid in self._existing_clip_ids]
        result.scalars.return_value.all.return_value = self._predictions
        # Correction endpoint: first business call = prediction fetch, second = prior.
        if self._call == 1:
            result.scalar_one_or_none.return_value = self._prediction_by_id
        else:
            result.scalar_one_or_none.return_value = self._opponent_prior
        return result


@contextmanager
def _client(session: _RecordingSession, user: User | None = None) -> Iterator[TestClient]:
    async def _db() -> AsyncGenerator[Any, None]:
        yield session

    from app.deps import get_current_user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user or _make_user()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def _signal_vector() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "personnel": {"value": "11", "confidence": 1.0, "n_rb": 1, "n_te": 1},
        "formation": {"value": "shotgun_empty", "confidence": 0.6},
        "backfield": {"value": "shotgun", "confidence": 0.8},
        "split": {"value": "wide", "confidence": 0.7},
        "motion": {"value": "jet", "confidence": 0.5},
        "down_distance_zone": {
            "value": "3_long_red_zone",
            "confidence": 0.95,
            "down": 3,
            "distance_yards": 9,
            "distance_bucket": "long",
            "field_zone": "red_zone",
        },
    }


# ── Governance ────────────────────────────────────────────────────────────────


def test_policy_play_prediction_read_excludes_player_and_viewer() -> None:
    assert policy_allows(UserRole.coach, Resource.PLAY_PREDICTION, Action.READ)
    assert not policy_allows(UserRole.player, Resource.PLAY_PREDICTION, Action.READ)
    assert not policy_allows(UserRole.viewer, Resource.PLAY_PREDICTION, Action.READ)


def test_policy_play_prediction_write_is_staff_only() -> None:
    assert policy_allows(UserRole.analyst, Resource.PLAY_PREDICTION, Action.WRITE)
    assert not policy_allows(UserRole.sportsperformance, Resource.PLAY_PREDICTION, Action.WRITE)


# ── Batch create ──────────────────────────────────────────────────────────────


def test_batch_create_persists_predictions() -> None:
    clip_id = uuid.uuid4()
    session = _RecordingSession(existing_clip_ids={clip_id})
    with _client(session) as c:
        resp = c.post(
            "/api/v1/play-predictions/batch",
            json={
                "predictions": [
                    {
                        "clip_id": str(clip_id),
                        "signal_vector": _signal_vector(),
                        "predicted_class": "pass",
                        "calibrated_prob": 0.71,
                        "confidence": 0.71,
                        "uncertainty": 0.86,
                        "is_calibrated": True,
                        "opponent_team": "Ohio",
                    }
                ]
            },
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["created"] == 1
    assert len(body["ids"]) == 1
    rows = [r for r in session.added if isinstance(r, PlayPrediction)]
    assert rows[0].predicted_class == "pass"
    assert rows[0].is_calibrated is True


def test_batch_create_rejects_unknown_clip() -> None:
    session = _RecordingSession(existing_clip_ids=set())
    with _client(session) as c:
        resp = c.post(
            "/api/v1/play-predictions/batch",
            json={
                "predictions": [{"clip_id": str(uuid.uuid4()), "signal_vector": _signal_vector()}]
            },
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error_code"] == "unknown_clip"


def test_batch_create_rejects_empty_list() -> None:
    session = _RecordingSession()
    with _client(session) as c:
        resp = c.post("/api/v1/play-predictions/batch", json={"predictions": []})
    assert resp.status_code == 422


def test_batch_create_rejects_bad_predicted_class() -> None:
    clip_id = uuid.uuid4()
    session = _RecordingSession(existing_clip_ids={clip_id})
    with _client(session) as c:
        resp = c.post(
            "/api/v1/play-predictions/batch",
            json={
                "predictions": [
                    {
                        "clip_id": str(clip_id),
                        "signal_vector": _signal_vector(),
                        "predicted_class": "punt",
                    }
                ]
            },
        )
    assert resp.status_code == 422


def test_batch_create_denied_for_player_role() -> None:
    clip_id = uuid.uuid4()
    session = _RecordingSession(existing_clip_ids={clip_id})
    with _client(session, user=_make_user(UserRole.player)) as c:
        resp = c.post(
            "/api/v1/play-predictions/batch",
            json={"predictions": [{"clip_id": str(clip_id), "signal_vector": {}}]},
        )
    assert resp.status_code == 403


def test_batch_create_gated_when_saturated() -> None:
    clip_id = uuid.uuid4()
    # Queue depth far above the default threshold (50) → saturated → 503.
    session = _RecordingSession(
        existing_clip_ids={clip_id}, queued_count=9999, running_count=9999, gated=True
    )
    with _client(session, user=_make_user(UserRole.analyst)) as c:
        resp = c.post(
            "/api/v1/play-predictions/batch",
            json={"predictions": [{"clip_id": str(clip_id), "signal_vector": {}}]},
        )
    assert resp.status_code == 503
    assert resp.json()["detail"]["error_code"] == "workload_gated"


# ── Read + calibration ────────────────────────────────────────────────────────


def _make_prediction(true_class: str | None, calibrated_prob: float) -> PlayPrediction:
    p = MagicMock(spec=PlayPrediction)
    p.id = uuid.uuid4()
    p.clip_id = uuid.uuid4()
    p.play_id = None
    p.opponent_team = "Ohio"
    p.signal_vector = _signal_vector()
    p.logit_score = 0.5
    p.predicted_class = "pass" if calibrated_prob >= 0.5 else "run"
    p.true_class = true_class
    p.confidence = max(calibrated_prob, 1 - calibrated_prob)
    p.calibrated_prob = calibrated_prob
    p.uncertainty = 0.5
    p.is_calibrated = True
    p.model_version_id = None
    p.created_at = datetime.now(UTC)
    return p


def test_list_predictions_for_clip() -> None:
    preds = [_make_prediction("pass", 0.8), _make_prediction("run", 0.2)]
    session = _RecordingSession(predictions=preds)
    with _client(session) as c:
        resp = c.get(f"/api/v1/clips/{uuid.uuid4()}/play-predictions")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_calibration_summary_empty_returns_nulls() -> None:
    session = _RecordingSession(predictions=[])
    with _client(session) as c:
        resp = c.get("/api/v1/play-predictions/calibration")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_count"] == 0
    assert body["brier_score"] is None
    assert body["reliability"] == []


def test_calibration_summary_computes_metrics() -> None:
    # Perfectly-confident, perfectly-correct predictions → Brier 0, ECE 0.
    preds = [_make_prediction("pass", 1.0) for _ in range(5)] + [
        _make_prediction("run", 0.0) for _ in range(5)
    ]
    session = _RecordingSession(predictions=preds)
    with _client(session) as c:
        resp = c.get("/api/v1/play-predictions/calibration")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_count"] == 10
    assert body["brier_score"] == 0.0
    assert body["accuracy"] == 1.0
    assert body["expected_calibration_error"] == 0.0


def test_calibration_read_denied_for_viewer() -> None:
    session = _RecordingSession(predictions=[])
    with _client(session, user=_make_user(UserRole.viewer)) as c:
        resp = c.get("/api/v1/play-predictions/calibration")
    assert resp.status_code == 403


# ── Opponent priors read ──────────────────────────────────────────────────────


def test_list_opponent_priors_returns_posterior_mean() -> None:
    cell = MagicMock(spec=OpponentPrior)
    cell.id = uuid.uuid4()
    cell.opponent_team = "Ohio"
    cell.down = 3
    cell.distance_bucket = "long"
    cell.field_zone = "red_zone"
    cell.alpha_pass = 2.0
    cell.alpha_run = 2.0
    cell.n_pass = 8
    cell.n_run = 0
    cell.updated_at = datetime.now(UTC)
    session = _RecordingSession(predictions=[cell])
    with _client(session) as c:
        resp = c.get("/api/v1/play-predictions/opponent-priors?opponent_team=Ohio")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    # (2+8)/(2+2+8+0) = 0.8333...
    assert body[0]["pass_probability"] > 0.8
    assert body[0]["observation_count"] == 8


# ── Coach-correction flywheel ─────────────────────────────────────────────────


def test_correction_sets_true_class_and_creates_prior_cell() -> None:
    pred = _make_prediction(None, 0.7)
    session = _RecordingSession(prediction_by_id=pred, opponent_prior=None)
    with _client(session) as c:
        resp = c.patch(
            f"/api/v1/play-predictions/{pred.id}",
            json={"true_class": "run"},
        )
    assert resp.status_code == 200
    assert pred.true_class == "run"
    # A new opponent-prior cell was created and incremented (data-backed update).
    new_priors = [r for r in session.added if isinstance(r, OpponentPrior)]
    assert len(new_priors) == 1
    assert new_priors[0].n_run == 1
    assert new_priors[0].field_zone == "red_zone"


def test_correction_updates_existing_prior_cell() -> None:
    pred = _make_prediction(None, 0.7)
    existing = MagicMock(spec=OpponentPrior)
    existing.n_pass = 3
    existing.n_run = 1
    session = _RecordingSession(prediction_by_id=pred, opponent_prior=existing)
    with _client(session) as c:
        resp = c.patch(
            f"/api/v1/play-predictions/{pred.id}",
            json={"true_class": "pass"},
        )
    assert resp.status_code == 200
    assert existing.n_pass == 4


def test_opponent_prior_updated_at_has_onupdate() -> None:
    assert OpponentPrior.__table__.c.updated_at.onupdate is not None


def test_correction_404_when_prediction_missing() -> None:
    session = _RecordingSession(prediction_by_id=None)
    with _client(session) as c:
        resp = c.patch(
            f"/api/v1/play-predictions/{uuid.uuid4()}",
            json={"true_class": "pass"},
        )
    assert resp.status_code == 404


def test_correction_rejects_bad_class() -> None:
    pred = _make_prediction(None, 0.7)
    session = _RecordingSession(prediction_by_id=pred)
    with _client(session) as c:
        resp = c.patch(
            f"/api/v1/play-predictions/{pred.id}",
            json={"true_class": "kickoff"},
        )
    assert resp.status_code == 422
