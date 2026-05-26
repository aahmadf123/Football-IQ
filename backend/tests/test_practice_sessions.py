"""Tests for the practice sessions router."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.database import get_db
from app.deps import get_current_user
from app.main import app
from app.models import User, UserRole
from fastapi.testclient import TestClient


def _make_user() -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = UserRole.coach
    u.is_active = True
    return u


def test_list_practice_sessions_groups_by_practice_session_id_key() -> None:
    seen_query: dict[str, str] = {}

    async def _db() -> AsyncGenerator[Any, None]:
        session = AsyncMock()

        async def _execute(stmt: Any) -> Any:
            seen_query["sql"] = str(stmt.compile(compile_kwargs={"literal_binds": False}))
            result = MagicMock()
            result.mappings.return_value = []
            return result

        session.execute = AsyncMock(side_effect=_execute)
        yield session

    app.dependency_overrides[get_current_user] = lambda: _make_user()
    app.dependency_overrides[get_db] = _db
    try:
        with TestClient(app) as c:
            resp = c.get("/api/v1/practice-sessions")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    sql = seen_query["sql"]
    assert "GROUP BY videos.practice_session_id" in sql
    assert "CASE WHEN (videos.practice_session_id IS NULL)" in sql
    assert "max(videos.session_kind)" in sql
    assert "max(videos.opponent_team)" in sql


def test_list_practice_sessions_applies_filters_and_maps_result() -> None:
    row = {
        "practice_session_id": uuid.uuid4(),
        "session_date": datetime(2026, 5, 26, 0, 0, tzinfo=UTC),
        "session_kind": "practice",
        "opponent_team": "Ohio",
        "video_count": 2,
        "first_recorded_at": datetime(2026, 5, 26, 14, 0, tzinfo=UTC),
        "last_recorded_at": datetime(2026, 5, 26, 15, 0, tzinfo=UTC),
    }
    seen_query: dict[str, str] = {}

    async def _db() -> AsyncGenerator[Any, None]:
        session = AsyncMock()

        async def _execute(stmt: Any) -> Any:
            seen_query["sql"] = str(stmt.compile(compile_kwargs={"literal_binds": False}))
            result = MagicMock()
            result.mappings.return_value = [row]
            return result

        session.execute = AsyncMock(side_effect=_execute)
        yield session

    app.dependency_overrides[get_current_user] = lambda: _make_user()
    app.dependency_overrides[get_db] = _db
    try:
        with TestClient(app) as c:
            resp = c.get(
                "/api/v1/practice-sessions",
                params={
                    "recorded_after": "2026-05-20T00:00:00+00:00",
                    "recorded_before": "2026-05-27T00:00:00+00:00",
                    "session_kind": "practice",
                    "opponent_team": "Ohio",
                    "limit": 25,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body[0]["session_date"] == "2026-05-26"
    assert body[0]["video_count"] == 2
    sql = seen_query["sql"]
    assert "videos.recorded_at >=" in sql
    assert "videos.recorded_at <=" in sql
    assert "videos.session_kind =" in sql
    assert "videos.opponent_team =" in sql
    assert "LIMIT :param_1" in sql
