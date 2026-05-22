"""Tests for the self-scout router."""

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.database import get_db
from app.deps import get_current_user
from app.main import app
from app.models import User, UserRole
from fastapi.testclient import TestClient


def _make_user() -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = UserRole.analyst
    u.is_active = True
    return u


def _make_clip(
    video_id: uuid.UUID,
    field_zone: str | None = None,
    personnel_grouping: str | None = None,
    down: int | None = None,
    distance: float | None = None,
) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.video_id = video_id
    c.field_zone = field_zone
    c.personnel_grouping = personnel_grouping
    c.down = down
    c.distance = distance
    c.start_time = 0.0
    return c


def _make_label(clip_id: uuid.UUID, label_type: str, label_value: dict[str, Any]) -> MagicMock:
    lbl = MagicMock()
    lbl.id = uuid.uuid4()
    lbl.clip_id = clip_id
    lbl.label_type = label_type
    lbl.label_value = label_value
    return lbl


def _mock_result(items: list[Any]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


def _mock_db_gen(
    clips: list[Any] | None = None,
    labels: list[Any] | None = None,
):
    async def _db() -> AsyncGenerator[Any, None]:
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[_mock_result(clips or []), _mock_result(labels or [])]
        )
        yield session

    return _db


def _override_auth_and_db(clips: list[Any] | None = None, labels: list[Any] | None = None) -> None:
    app.dependency_overrides[get_current_user] = lambda: _make_user()
    app.dependency_overrides[get_db] = _mock_db_gen(clips=clips, labels=labels)


def test_tendencies_empty_clips() -> None:
    video_id = uuid.uuid4()
    _override_auth_and_db(clips=[], labels=[])

    with TestClient(app) as c:
        resp = c.get("/api/v1/self-scout/tendencies", params={"video_id": str(video_id)})
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["clip_count"] == 0
    assert data["formation_tendencies"] == []
    assert data["field_zone_tendencies"] == []
    assert data["personnel_tendencies"] == []
    assert data["down_distance_tendencies"] == []
    assert data["formation_concept_families"] == {}
    assert data["pre_snap_tells"] == []
    assert data["alerts"] == []
    assert data["motion_tendencies"]["with_motion"]["total"] == 0
    assert data["motion_tendencies"]["without_motion"]["total"] == 0


def test_tendencies_basic_formation() -> None:
    video_id = uuid.uuid4()
    clips = [_make_clip(video_id) for _ in range(3)]
    labels = [
        _make_label(clips[0].id, "offensive_formation", {"formation": "Trips"}),
        _make_label(clips[0].id, "play_concept", {"concept": "inside zone"}),
        _make_label(clips[1].id, "offensive_formation", {"formation": "Trips"}),
        _make_label(clips[1].id, "play_concept", {"concept": "inside zone"}),
        _make_label(clips[2].id, "offensive_formation", {"formation": "Trips"}),
        _make_label(clips[2].id, "play_concept", {"concept": "quick pass"}),
    ]
    _override_auth_and_db(clips=clips, labels=labels)

    with patch("app.routers.self_scout.log.info") as mock_log, TestClient(app) as c:
        resp = c.get("/api/v1/self-scout/tendencies", params={"video_id": str(video_id)})
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["clip_count"] == 3
    assert len(data["formation_tendencies"]) == 1
    entry = data["formation_tendencies"][0]
    assert entry["grouping_key"] == "Trips"
    assert entry["total_plays"] == 3
    assert entry["run_count"] == 2
    assert entry["pass_count"] == 1
    assert entry["run_rate"] == 0.667
    assert entry["pass_rate"] == 0.333
    mock_log.assert_called_once()


def test_tendencies_motion_split() -> None:
    video_id = uuid.uuid4()
    clips = [_make_clip(video_id) for _ in range(4)]
    labels = [
        _make_label(clips[0].id, "motion_detected", {"detected": True}),
        _make_label(clips[0].id, "play_direction", {"direction": "left"}),
        _make_label(clips[1].id, "motion_detected", {"detected": True}),
        _make_label(clips[1].id, "play_direction", {"direction": "right"}),
        _make_label(clips[2].id, "play_concept", {"concept": "screen pass"}),
        _make_label(clips[3].id, "play_concept", {"concept": "mesh pass"}),
    ]
    _override_auth_and_db(clips=clips, labels=labels)

    with TestClient(app) as c:
        resp = c.get("/api/v1/self-scout/tendencies", params={"video_id": str(video_id)})
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    motion = resp.json()["motion_tendencies"]
    assert motion["with_motion"]["total"] == 2
    assert motion["with_motion"]["run_count"] == 2
    assert motion["with_motion"]["pass_count"] == 0
    assert motion["with_motion"]["run_rate"] == 1.0
    assert motion["without_motion"]["total"] == 2
    assert motion["without_motion"]["run_count"] == 0
    assert motion["without_motion"]["pass_count"] == 2
    assert motion["without_motion"]["pass_rate"] == 1.0


def test_tendencies_down_distance() -> None:
    video_id = uuid.uuid4()
    clips = [
        _make_clip(video_id, down=1, distance=2.0),
        _make_clip(video_id, down=1, distance=2.0),
    ]
    labels = [
        _make_label(clips[0].id, "play_direction", {"direction": "left"}),
        _make_label(clips[1].id, "play_concept", {"concept": "screen pass"}),
    ]
    _override_auth_and_db(clips=clips, labels=labels)

    with TestClient(app) as c:
        resp = c.get("/api/v1/self-scout/tendencies", params={"video_id": str(video_id)})
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    entries = resp.json()["down_distance_tendencies"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["down"] == 1
    assert entry["distance_bucket"] == "short"
    assert entry["total_plays"] == 2
    assert entry["run_count"] == 1
    assert entry["pass_count"] == 1
    assert entry["evidence_clip_ids"] == [str(clips[0].id), str(clips[1].id)]


def test_tendencies_alerts_generated() -> None:
    video_id = uuid.uuid4()
    clips = [_make_clip(video_id) for _ in range(5)]
    labels = []
    for clip in clips[:4]:
        labels.extend(
            [
                _make_label(clip.id, "offensive_formation", {"formation": "I-Form"}),
                _make_label(clip.id, "play_direction", {"direction": "left"}),
            ]
        )
    labels.extend(
        [
            _make_label(clips[4].id, "offensive_formation", {"formation": "I-Form"}),
            _make_label(clips[4].id, "play_concept", {"concept": "screen pass"}),
        ]
    )
    _override_auth_and_db(clips=clips, labels=labels)

    with TestClient(app) as c:
        resp = c.get("/api/v1/self-scout/tendencies", params={"video_id": str(video_id)})
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    alerts = resp.json()["alerts"]
    assert len(alerts) >= 1
    formation_alert = next(a for a in alerts if a["grouping_key"] == "I-Form")
    assert formation_alert["alert_type"] == "formation_tendency"
    assert formation_alert["run_rate"] == 0.8
    assert formation_alert["severity"] == "medium"


def test_tendencies_pre_snap_tells() -> None:
    video_id = uuid.uuid4()
    clips = [_make_clip(video_id) for _ in range(5)]
    labels = []
    for clip in clips[:4]:
        labels.extend(
            [
                _make_label(clip.id, "offensive_formation", {"formation": "Trips"}),
                _make_label(clip.id, "motion_detected", {"detected": True}),
                _make_label(clip.id, "play_direction", {"direction": "left"}),
            ]
        )
    labels.extend(
        [
            _make_label(clips[4].id, "offensive_formation", {"formation": "Trips"}),
            _make_label(clips[4].id, "motion_detected", {"detected": True}),
            _make_label(clips[4].id, "play_concept", {"concept": "mesh pass"}),
        ]
    )
    _override_auth_and_db(clips=clips, labels=labels)

    with TestClient(app) as c:
        resp = c.get("/api/v1/self-scout/tendencies", params={"video_id": str(video_id)})
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    tells = resp.json()["pre_snap_tells"]
    assert len(tells) == 1
    tell = tells[0]
    assert tell["grouping_key"] == "Trips|with_motion"
    assert tell["formation"] == "Trips"
    assert tell["motion_state"] == "with_motion"
    assert tell["lean"] == "run"
    assert tell["run_rate"] == 0.8
    assert tell["severity"] == "medium"
    assert len(tell["evidence_clip_ids"]) == 5
    assert "Pre-snap tell from Trips with motion" in tell["message"]


def test_tendencies_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/self-scout/tendencies")
    assert resp.status_code == 401


def test_opponent_tendencies_requires_video_id() -> None:
    _override_auth_and_db(clips=[], labels=[])

    with TestClient(app) as c:
        resp = c.get("/api/v1/self-scout/opponent-tendencies")
    app.dependency_overrides.clear()

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any(err["loc"][-1] == "opponent_video_id" for err in detail)


def test_tendencies_concept_family() -> None:
    video_id = uuid.uuid4()
    clips = [_make_clip(video_id) for _ in range(3)]
    labels = [
        _make_label(clips[0].id, "offensive_formation", {"formation": "Gun"}),
        _make_label(clips[0].id, "play_concept", {"concept": "inside zone"}),
        _make_label(clips[1].id, "offensive_formation", {"formation": "Gun"}),
        _make_label(clips[1].id, "play_concept", {"concept": "inside zone"}),
        _make_label(clips[2].id, "offensive_formation", {"formation": "Gun"}),
        _make_label(clips[2].id, "play_concept", {"concept": "mesh pass"}),
    ]
    _override_auth_and_db(clips=clips, labels=labels)

    with TestClient(app) as c:
        resp = c.get("/api/v1/self-scout/tendencies", params={"video_id": str(video_id)})
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    families = resp.json()["formation_concept_families"]
    assert "Gun" in families
    entries = {entry["concept_family"]: entry for entry in families["Gun"]}
    assert entries["inside_zone"]["total_plays"] == 2
    assert entries["inside_zone"]["rate"] == 0.667
    assert entries["pass_concept"]["total_plays"] == 1
    assert entries["pass_concept"]["rate"] == 0.333


def test_tendencies_evidence_clip_ids() -> None:
    video_id = uuid.uuid4()
    clips = [_make_clip(video_id) for _ in range(3)]
    labels = [
        _make_label(clips[0].id, "offensive_formation", {"formation": "Ace"}),
        _make_label(clips[0].id, "play_direction", {"direction": "left"}),
        _make_label(clips[1].id, "offensive_formation", {"formation": "Ace"}),
        _make_label(clips[1].id, "play_direction", {"direction": "right"}),
        _make_label(clips[2].id, "offensive_formation", {"formation": "Ace"}),
        _make_label(clips[2].id, "play_concept", {"concept": "screen pass"}),
    ]
    _override_auth_and_db(clips=clips, labels=labels)

    with TestClient(app) as c:
        resp = c.get("/api/v1/self-scout/tendencies", params={"video_id": str(video_id)})
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    entry = resp.json()["formation_tendencies"][0]
    assert entry["evidence_clip_ids"] == [str(clips[0].id), str(clips[1].id), str(clips[2].id)]
