"""Tests for the tendency-break engine + endpoints (Issue #137).

Covers:
  - app.analytics.tendency_break pure functions (build_plays, season tendencies,
    pattern breaks, CFBD baseline)
  - POST /api/v1/self-scout/tendency-break — generate + persist from cached data
  - GET  /api/v1/self-scout/tendency-break — list, player/viewer blocked
"""

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.analytics import tendency_break as tb
from app.main import app
from app.models import Alert, AlertType, User, UserRole
from app.workload import WorkloadSnapshot, WorkloadStatus
from fastapi.testclient import TestClient

# ── Pure-function fixtures ──────────────────────────────────────────────────────


def _clip(
    clip_id: str,
    *,
    formation: str = "Trips",
    personnel: str = "11",
    field_zone: str = "red_zone",
    down: int | None = 3,
    distance: float | None = 8.0,
) -> dict[str, Any]:
    return {
        "id": clip_id,
        "personnel_grouping": personnel,
        "field_zone": field_zone,
        "down": down,
        "distance": distance,
        "_formation": formation,
    }


def _labels_for(clips: list[dict[str, Any]], play_types: list[str]) -> dict[str, list[dict]]:
    """Build labels so each clip resolves to the requested run/pass play type."""
    out: dict[str, list[dict]] = {}
    for clip, pt in zip(clips, play_types, strict=True):
        concept = "inside zone" if pt == "run" else "quick pass"
        out[clip["id"]] = [
            {"label_type": "offensive_formation", "label_value": {"formation": clip["_formation"]}},
            {"label_type": "play_concept", "label_value": {"concept": concept}},
        ]
    return out


# ── Pure-function tests ─────────────────────────────────────────────────────────


def test_build_plays_extracts_dimensions() -> None:
    clips = [_clip("c0")]
    labels = _labels_for(clips, ["pass"])
    plays = tb.build_plays(clips, labels)
    assert len(plays) == 1
    p = plays[0]
    assert p.play_type == "pass"
    assert p.formation == "Trips"
    assert p.personnel == "11"
    assert p.field_zone == "red_zone"
    assert p.down == 3
    assert p.distance_bucket == "long"
    assert p.bucket_key() == ("Trips", "11", "red_zone", "3-long")


def test_build_plays_skips_unlabeled() -> None:
    clips = [_clip("c0")]
    # No play_concept / play_direction → play type undetermined → dropped.
    labels = {"c0": [{"label_type": "offensive_formation", "label_value": {"formation": "I"}}]}
    assert tb.build_plays(clips, labels) == []


def test_season_tendency_alert_fires_for_lopsided_pass() -> None:
    clips = [_clip(f"c{i}") for i in range(10)]
    play_types = ["pass"] * 9 + ["run"]  # 90% pass, n=10 > 8
    plays = tb.build_plays(clips, _labels_for(clips, play_types))
    alerts = tb.season_tendency_alerts(plays)
    assert len(alerts) == 1
    a = alerts[0]
    assert a.tendency_kind == "season_tendency"
    assert a.lean == "pass"
    assert a.pass_rate == 0.9
    assert a.total_plays == 10
    assert a.severity == "high"  # >= 0.90
    assert len(a.evidence_clip_ids) == 3  # EVIDENCE_CLIP_LIMIT
    assert a.source == "toledo_film"


def test_season_tendency_no_alert_below_sample_floor() -> None:
    # 8 plays exactly → not strictly greater than MIN_SAMPLES_TO_ALERT (8) → no alert.
    clips = [_clip(f"c{i}") for i in range(8)]
    plays = tb.build_plays(clips, _labels_for(clips, ["pass"] * 8))
    assert tb.season_tendency_alerts(plays) == []


def test_season_tendency_no_alert_for_balanced_bucket() -> None:
    clips = [_clip(f"c{i}") for i in range(10)]
    play_types = ["pass"] * 5 + ["run"] * 5  # 50% — not lopsided
    plays = tb.build_plays(clips, _labels_for(clips, play_types))
    assert tb.season_tendency_alerts(plays) == []


def test_season_tendency_run_heavy_low_severity() -> None:
    clips = [_clip(f"c{i}") for i in range(12)]
    play_types = ["run"] * 10 + ["pass"] * 2  # pass_rate ~0.167 < 0.20
    plays = tb.build_plays(clips, _labels_for(clips, play_types))
    alerts = tb.season_tendency_alerts(plays)
    assert len(alerts) == 1
    assert alerts[0].lean == "run"
    assert alerts[0].severity == "medium"  # 0.167 not <= 0.10


def test_pattern_break_fires_on_divergence() -> None:
    bucket = ("Trips", "11", "red_zone", "3-long")
    baseline = {bucket: 0.5}
    clips = [_clip(f"g{i}") for i in range(6)]
    plays = tb.build_plays(clips, _labels_for(clips, ["pass"] * 6))  # 100% pass this game
    alerts = tb.pattern_break_alerts(plays, baseline)
    assert len(alerts) == 1
    a = alerts[0]
    assert a.tendency_kind == "pattern_break"
    assert a.divergence_pp == 0.5
    assert a.baseline_pass_rate == 0.5
    assert a.lean == "pass"


def test_pattern_break_requires_min_game_plays() -> None:
    bucket = ("Trips", "11", "red_zone", "3-long")
    baseline = {bucket: 0.5}
    clips = [_clip(f"g{i}") for i in range(4)]  # only 4 < 5
    plays = tb.build_plays(clips, _labels_for(clips, ["pass"] * 4))
    assert tb.pattern_break_alerts(plays, baseline) == []


def test_pattern_break_skips_unknown_bucket() -> None:
    clips = [_clip(f"g{i}") for i in range(6)]
    plays = tb.build_plays(clips, _labels_for(clips, ["pass"] * 6))
    # Baseline has no entry for this bucket → cannot compare → no alert.
    assert tb.pattern_break_alerts(plays, {}) == []


def test_cfbd_pass_rate_baseline_classifies_play_types() -> None:
    cfbd = [
        {"play_type": "Pass Reception"},
        {"play_type": "Passing Touchdown"},
        {"play_type": "Rush"},
        {"play_type": "Sack"},  # counts as pass (dropback)
        {"play_type": "Kickoff"},  # ignored
        {"play_type": "Penalty"},  # ignored
    ]
    rate = tb.cfbd_pass_rate_baseline(cfbd)
    # passes = 3 (reception, td, sack), runs = 1 → 3/4
    assert rate == 0.75


def test_cfbd_pass_rate_baseline_none_when_empty() -> None:
    assert tb.cfbd_pass_rate_baseline([]) is None
    assert tb.cfbd_pass_rate_baseline([{"play_type": "Timeout"}]) is None


def test_metric_value_round_trips_json() -> None:
    import json

    clips = [_clip(f"c{i}") for i in range(10)]
    plays = tb.build_plays(clips, _labels_for(clips, ["pass"] * 9 + ["run"]))
    alert = tb.season_tendency_alerts(plays)[0]
    mv = alert.metric_value()
    assert json.loads(json.dumps(mv)) == mv
    assert mv["tendency_kind"] == "season_tendency"
    assert mv["source"] == "toledo_film"


# ── Endpoint fixtures ────────────────────────────────────────────────────────────


def _make_user(role: UserRole) -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = role
    u.is_active = True
    u.position_group = None
    return u


def _orm_clip(clip_id: uuid.UUID, *, formation: str = "Trips") -> MagicMock:
    c = MagicMock()
    c.id = clip_id
    c.personnel_grouping = "11"
    c.field_zone = "red_zone"
    c.down = 3
    c.distance = 8.0
    c.start_time = 0.0
    c._formation = formation
    return c


def _orm_label(clip_id: uuid.UUID, label_type: str, label_value: dict) -> MagicMock:
    lbl = MagicMock()
    lbl.clip_id = clip_id
    lbl.label_type = label_type
    lbl.label_value = label_value
    return lbl


def _result(scalars_all: list | None = None, all_rows: list | None = None) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = scalars_all or []
    r.all.return_value = all_rows or []
    return r


def _healthy_snapshot() -> WorkloadSnapshot:
    return WorkloadSnapshot(
        queued=0,
        running=0,
        queue_threshold=50,
        running_threshold=20,
        status=WorkloadStatus.healthy,
        gating_disabled=False,
    )


# ── Endpoint tests ───────────────────────────────────────────────────────────────


def test_generate_tendency_break_persists_alerts() -> None:
    from app.database import get_db
    from app.deps import get_current_user

    coach = _make_user(UserRole.coach)

    clip_ids = [uuid.uuid4() for _ in range(10)]
    clips = [_orm_clip(cid) for cid in clip_ids]
    labels: list[MagicMock] = []
    for i, cid in enumerate(clip_ids):
        labels.append(_orm_label(cid, "offensive_formation", {"formation": "Trips"}))
        concept = "quick pass" if i < 9 else "inside zone"
        labels.append(_orm_label(cid, "play_concept", {"concept": concept}))

    added: list[Alert] = []

    async def _db() -> AsyncGenerator[Any, None]:
        session = AsyncMock()
        # Order of execute(): season Clip, season Label, dedup Alert.
        session.execute = AsyncMock(
            side_effect=[
                _result(scalars_all=clips),
                _result(scalars_all=labels),
                _result(all_rows=[]),
            ]
        )
        session.add = MagicMock(side_effect=added.append)
        session.flush = AsyncMock()
        yield session

    app.dependency_overrides[get_current_user] = lambda: coach
    app.dependency_overrides[get_db] = _db

    with (
        patch("app.workload.assess_workload", AsyncMock(return_value=_healthy_snapshot())),
        patch("app.routers.self_scout.publish_alert") as mock_publish,
        TestClient(app) as c,
    ):
        resp = c.post("/api/v1/self-scout/tendency-break")
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["generated"] == 1
    assert data["season_tendency_count"] == 1
    assert data["season_clip_count"] == 10
    assert len(data["alerts"]) == 1
    assert data["alerts"][0]["tendency_kind"] == "season_tendency"
    assert data["alerts"][0]["lean"] == "pass"
    # Persisted as a formation_tendency alert in the OFFENSE group.
    assert len(added) == 1
    assert added[0].alert_type == AlertType.formation_tendency
    assert added[0].position_group == "OFFENSE"
    mock_publish.assert_called_once()


def test_generate_tendency_break_workload_gated() -> None:
    from app.database import get_db
    from app.deps import get_current_user

    coach = _make_user(UserRole.coach)

    async def _db() -> AsyncGenerator[Any, None]:
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_result())
        yield session

    gated = WorkloadSnapshot(
        queued=99,
        running=0,
        queue_threshold=50,
        running_threshold=20,
        status=WorkloadStatus.saturated,
        gating_disabled=False,
    )

    app.dependency_overrides[get_current_user] = lambda: coach
    app.dependency_overrides[get_db] = _db

    with (
        patch("app.workload.assess_workload", AsyncMock(return_value=gated)),
        TestClient(app) as c,
    ):
        resp = c.post("/api/v1/self-scout/tendency-break")
    app.dependency_overrides.clear()

    assert resp.status_code == 503
    assert resp.json()["detail"]["error_code"] == "workload_gated"


def test_list_tendency_break_player_blocked() -> None:
    from app.database import get_db
    from app.deps import get_current_user

    player = _make_user(UserRole.player)

    async def _db() -> AsyncGenerator[Any, None]:
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_result())
        yield session

    app.dependency_overrides[get_current_user] = lambda: player
    app.dependency_overrides[get_db] = _db

    with TestClient(app) as c:
        resp = c.get("/api/v1/self-scout/tendency-break")
    app.dependency_overrides.clear()
    assert resp.status_code == 403


def test_list_tendency_break_returns_persisted() -> None:
    from datetime import UTC, datetime

    from app.database import get_db
    from app.deps import get_current_user
    from app.models import AlertSeverity

    analyst = _make_user(UserRole.analyst)

    alert = MagicMock(spec=Alert)
    alert.id = uuid.uuid4()
    alert.severity = AlertSeverity.high
    alert.confidence = 0.83
    alert.session_id = "season"
    alert.is_actioned = False
    alert.actioned_at = None
    alert.created_at = datetime(2026, 5, 8, tzinfo=UTC)
    alert.metric_name = "Trips · 11 pers · red zone · 3-long"
    alert.metric_value = {
        "grouping_key": "Trips · 11 pers · red zone · 3-long",
        "tendency_kind": "season_tendency",
        "lean": "pass",
        "run_rate": 0.1,
        "pass_rate": 0.9,
        "total_plays": 10,
        "evidence_clip_ids": [str(uuid.uuid4())],
        "source": "toledo_film",
        "experimental": False,
        "message": "lopsided",
    }

    async def _db() -> AsyncGenerator[Any, None]:
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_result(scalars_all=[alert]))
        yield session

    app.dependency_overrides[get_current_user] = lambda: analyst
    app.dependency_overrides[get_db] = _db

    with TestClient(app) as c:
        resp = c.get("/api/v1/self-scout/tendency-break")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["alerts"][0]["tendency_kind"] == "season_tendency"
    assert data["alerts"][0]["pass_rate"] == 0.9
