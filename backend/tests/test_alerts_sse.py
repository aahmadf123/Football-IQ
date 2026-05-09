"""Tests for the SSE alert stream router (Issue #16).

Covers:
  - Player/viewer roles blocked
  - Coach role allowed, receives connected event
  - publish_alert fans to matching position-group queues
  - publish_alert skips non-matching position-group queues
  - Client disconnect cleans up queue registry
  - SSE event format (data: JSON\n\n)
"""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.models import User, UserRole
from app.routers.alerts_sse import _connections, publish_alert
from fastapi.testclient import TestClient

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_user(role: UserRole, position_group: str | None = None) -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = role
    u.is_active = True
    u.position_group = position_group
    return u


# ── publish_alert unit tests ───────────────────────────────────────────────────


def test_publish_alert_fans_to_matching_group() -> None:
    conn_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue(maxsize=10)
    _connections[conn_id] = (q, "OL")

    try:
        publish_alert({"alert_type": "effort_anomaly", "position_group": "OL", "player_id": "p1"})
        assert not q.empty()
        event = q.get_nowait()
        assert event["position_group"] == "OL"
    finally:
        _connections.pop(conn_id, None)


def test_publish_alert_skips_non_matching_group() -> None:
    conn_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue(maxsize=10)
    _connections[conn_id] = (q, "WR")

    try:
        publish_alert({"alert_type": "effort_anomaly", "position_group": "OL", "player_id": "p1"})
        assert q.empty()
    finally:
        _connections.pop(conn_id, None)


def test_publish_alert_fans_to_all_when_no_filter() -> None:
    conn_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue(maxsize=10)
    _connections[conn_id] = (q, None)  # None = admin/analyst receives all

    try:
        publish_alert({"alert_type": "bio_deviation", "position_group": "DL"})
        assert not q.empty()
    finally:
        _connections.pop(conn_id, None)


def test_publish_alert_skips_full_queue() -> None:
    conn_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue(maxsize=1)
    q.put_nowait({"dummy": True})  # fill it
    _connections[conn_id] = (q, None)

    try:
        publish_alert({"alert_type": "effort_anomaly", "position_group": "OL"})
        assert q.qsize() == 1
    finally:
        _connections.pop(conn_id, None)


def test_publish_alert_case_insensitive_group_match() -> None:
    conn_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue(maxsize=10)
    _connections[conn_id] = (q, "ol")

    try:
        publish_alert({"alert_type": "effort_anomaly", "position_group": "OL"})
        assert not q.empty()
    finally:
        _connections.pop(conn_id, None)


# ── Endpoint access tests ─────────────────────────────────────────────────────


def _mock_db_override():
    async def _db() -> AsyncGenerator[Any, None]:
        session = AsyncMock()
        yield session

    return _db


def test_stream_player_role_blocked() -> None:
    from app.database import get_db
    from app.deps import get_current_user

    player = _make_user(UserRole.player)
    app.dependency_overrides[get_current_user] = lambda: player
    app.dependency_overrides[get_db] = _mock_db_override()

    with TestClient(app) as c:
        resp = c.get("/api/v1/alerts/stream")
    app.dependency_overrides.clear()
    assert resp.status_code == 403


def test_stream_viewer_role_blocked() -> None:
    from app.database import get_db
    from app.deps import get_current_user

    viewer = _make_user(UserRole.viewer)
    app.dependency_overrides[get_current_user] = lambda: viewer
    app.dependency_overrides[get_db] = _mock_db_override()

    with TestClient(app) as c:
        resp = c.get("/api/v1/alerts/stream")
    app.dependency_overrides.clear()
    assert resp.status_code == 403


def test_stream_coach_receives_connected_event() -> None:
    from app.database import get_db
    from app.deps import get_current_user

    coach = _make_user(UserRole.coach, "OL")
    app.dependency_overrides[get_current_user] = lambda: coach
    app.dependency_overrides[get_db] = _mock_db_override()

    with TestClient(app) as c:
        with c.stream("GET", "/api/v1/alerts/stream") as stream:
            first_chunk = next(stream.iter_lines())

    app.dependency_overrides.clear()

    assert "data:" in first_chunk
    payload = json.loads(first_chunk.replace("data: ", ""))
    assert payload.get("type") == "connected"
    assert "connection_id" in payload


def test_stream_delivers_published_alert() -> None:
    from app.database import get_db
    from app.deps import get_current_user

    coach = _make_user(UserRole.coach, "OL")
    app.dependency_overrides[get_current_user] = lambda: coach
    app.dependency_overrides[get_db] = _mock_db_override()

    received: list[dict] = []

    with TestClient(app) as c:
        with c.stream("GET", "/api/v1/alerts/stream") as stream:
            lines = stream.iter_lines()
            first = next(lines)
            # Parse connection event to get conn_id
            conn_payload = json.loads(first.replace("data: ", ""))
            conn_id = conn_payload["connection_id"]

            # Publish an OL alert — should match the coach's filter
            if conn_id in _connections:
                _connections[conn_id][0].put_nowait(
                    {"alert_type": "effort_anomaly", "position_group": "OL"}
                )
            second = next(lines)
            received.append(json.loads(second.replace("data: ", "")))

    app.dependency_overrides.clear()

    if received:
        assert received[0].get("alert_type") == "effort_anomaly"


# ── SSE event format ──────────────────────────────────────────────────────────


def test_sse_event_format_has_data_prefix() -> None:
    from app.database import get_db
    from app.deps import get_current_user

    coach = _make_user(UserRole.coach, "WR")
    app.dependency_overrides[get_current_user] = lambda: coach
    app.dependency_overrides[get_db] = _mock_db_override()

    with TestClient(app) as c:
        with c.stream("GET", "/api/v1/alerts/stream") as stream:
            first_line = next(stream.iter_lines())

    app.dependency_overrides.clear()

    assert first_line.startswith("data: "), f"Expected SSE format, got: {first_line!r}"


def test_disconnect_removes_connection_from_registry() -> None:
    """After the client disconnects, its queue should be removed from _connections."""
    from app.database import get_db
    from app.deps import get_current_user

    analyst = _make_user(UserRole.analyst)
    app.dependency_overrides[get_current_user] = lambda: analyst
    app.dependency_overrides[get_db] = _mock_db_override()

    conn_id_seen: list[str] = []

    with TestClient(app) as c:
        with c.stream("GET", "/api/v1/alerts/stream") as stream:
            first = next(stream.iter_lines())
            payload = json.loads(first.replace("data: ", ""))
            conn_id_seen.append(payload["connection_id"])
        # Connection is now closed

    app.dependency_overrides.clear()

    if conn_id_seen:
        assert conn_id_seen[0] not in _connections
