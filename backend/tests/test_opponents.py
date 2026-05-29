"""Tests for the opponents router (Issue #105)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.database import get_db
from app.deps import get_current_user
from app.main import app
from app.models import SessionKind, User, UserRole, Video, VideoStatus
from fastapi.testclient import TestClient


def _make_user() -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = UserRole.analyst
    u.is_active = True
    return u


def _make_game_video(
    opponent_team: str,
    recorded_at: datetime | None,
    filename: str = "film.mp4",
) -> MagicMock:
    v = MagicMock(spec=Video)
    v.id = uuid.uuid4()
    v.filename = filename
    v.session_kind = SessionKind.game
    v.opponent_team = opponent_team
    v.status = VideoStatus.uploaded
    v.recorded_at = recorded_at
    v.created_at = recorded_at or datetime.now(UTC)
    return v


def _mock_db_with_videos(videos: list[Any]):
    async def _db() -> AsyncGenerator[Any, None]:
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = videos
        session.execute = AsyncMock(return_value=result)
        yield session

    return _db


def _override(videos: list[Any]) -> None:
    app.dependency_overrides[get_current_user] = lambda: _make_user()
    app.dependency_overrides[get_db] = _mock_db_with_videos(videos)


@contextmanager
def _client_with_overrides(videos: list[Any]) -> Iterator[TestClient]:
    _override(videos)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_list_opponents_empty() -> None:
    with _client_with_overrides(videos=[]) as c:
        resp = c.get("/api/v1/opponents")

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_opponents_groups_and_sorts_by_latest_film() -> None:
    today = datetime(2026, 5, 27, tzinfo=UTC)
    last_week = today - timedelta(days=7)
    last_month = today - timedelta(days=30)
    videos = [
        _make_game_video("Northern Illinois", today, "niu-1.mp4"),
        _make_game_video("Northern Illinois", last_month, "niu-2.mp4"),
        _make_game_video("Ohio", last_week, "ohio-1.mp4"),
    ]
    with _client_with_overrides(videos=videos) as c:
        resp = c.get("/api/v1/opponents")

    assert resp.status_code == 200
    data = resp.json()
    assert [entry["opponent_team"] for entry in data] == [
        "Northern Illinois",
        "Ohio",
    ]
    niu = data[0]
    assert niu["video_count"] == 2
    assert {v["filename"] for v in niu["videos"]} == {"niu-1.mp4", "niu-2.mp4"}
    ohio = data[1]
    assert ohio["video_count"] == 1
    assert ohio["videos"][0]["filename"] == "ohio-1.mp4"


def test_list_opponents_sorts_null_recorded_at_last() -> None:
    today = datetime(2026, 5, 27, tzinfo=UTC)
    videos = [
        _make_game_video("Northern Illinois", None, "niu-undated.mp4"),
        _make_game_video("Ohio", today, "ohio-1.mp4"),
    ]

    with _client_with_overrides(videos=videos) as c:
        resp = c.get("/api/v1/opponents")

    assert resp.status_code == 200
    assert [entry["opponent_team"] for entry in resp.json()] == ["Ohio", "Northern Illinois"]


def test_list_opponents_skips_blank_opponent_field() -> None:
    today = datetime(2026, 5, 27, tzinfo=UTC)
    videos = [
        _make_game_video("Ohio", today, "ohio-1.mp4"),
        _make_game_video("   ", today, "blank.mp4"),
    ]
    with _client_with_overrides(videos=videos) as c:
        resp = c.get("/api/v1/opponents")

    assert resp.status_code == 200
    data = resp.json()
    assert [entry["opponent_team"] for entry in data] == ["Ohio"]


def test_get_opponent_returns_videos_for_team() -> None:
    today = datetime(2026, 5, 27, tzinfo=UTC)
    videos = [
        _make_game_video("Ohio", today, "ohio-1.mp4"),
        _make_game_video("Ohio", today - timedelta(days=14), "ohio-2.mp4"),
    ]
    with _client_with_overrides(videos=videos) as c:
        resp = c.get("/api/v1/opponents/Ohio")

    assert resp.status_code == 200
    body = resp.json()
    assert body["opponent_team"] == "Ohio"
    assert body["video_count"] == 2
    assert len(body["videos"]) == 2


def test_get_opponent_404_when_no_film() -> None:
    with _client_with_overrides(videos=[]) as c:
        resp = c.get("/api/v1/opponents/Ohio")

    assert resp.status_code == 404


def test_get_opponent_400_when_blank_team() -> None:
    with _client_with_overrides(videos=[]) as c:
        resp = c.get("/api/v1/opponents/%20")

    assert resp.status_code == 400
