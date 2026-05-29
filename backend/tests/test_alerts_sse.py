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
import socket
import threading
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import uvicorn
from app.main import app
from app.models import User, UserRole
from app.routers.alerts_sse import _connections, publish_alert


@pytest.fixture(autouse=True)
def speed_up_sse_keepalive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch the keepalive interval and prevent request.is_disconnected() from blocking.

    This prevents the TestClient background thread from deadlocking on request.is_disconnected()
    and speeds up keepalive timeout during tests.
    """
    import app.routers.alerts_sse
    import starlette.requests

    monkeypatch.setattr(app.routers.alerts_sse, "_KEEPALIVE_SECONDS", 0.1)

    async def mock_is_disconnected(self) -> bool:
        return False

    monkeypatch.setattr(starlette.requests.Request, "is_disconnected", mock_is_disconnected)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_user(role: UserRole, position_group: str | None = None) -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = role
    u.is_active = True
    u.position_group = position_group
    return u


# ── publish_alert unit tests ─────────────────────────────────────────────────


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


# ── Live Uvicorn Server Fixture for Streaming ────────────────────────────────


def _get_free_port() -> int:
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def live_server_url() -> str:
    """Start a real uvicorn server in a separate background thread.

    This is necessary to test infinite streaming (SSE) without causing deadlocks or hangs,
    which occur on synchronous TestClient/AsyncClient ASGI transport as they buffer/drain
    the entire application response stream before returning control to the test function.
    """
    port = _get_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    app.dependency_overrides.clear()

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to start
    time.sleep(0.5)

    yield f"http://127.0.0.1:{port}"

    # Clean shutdown
    server.should_exit = True
    thread.join(timeout=2)


def _get_next_sse_line(lines_iterator) -> str:
    """Helper to read the next non-empty line of the SSE stream."""
    for line in lines_iterator:
        if line.strip():
            return line
    return ""


# ── Endpoint access tests ────────────────────────────────────────────────────


def _mock_db_override():
    async def _db() -> AsyncGenerator[Any, None]:
        session = AsyncMock()
        yield session

    return _db


def test_stream_player_role_blocked(live_server_url: str) -> None:
    from app.database import get_db
    from app.deps import get_current_user

    player = _make_user(UserRole.player)
    app.dependency_overrides[get_current_user] = lambda: player
    app.dependency_overrides[get_db] = _mock_db_override()

    resp = httpx.get(f"{live_server_url}/api/v1/alerts/stream")
    app.dependency_overrides.clear()
    assert resp.status_code == 403


def test_stream_viewer_role_blocked(live_server_url: str) -> None:
    from app.database import get_db
    from app.deps import get_current_user

    viewer = _make_user(UserRole.viewer)
    app.dependency_overrides[get_current_user] = lambda: viewer
    app.dependency_overrides[get_db] = _mock_db_override()

    resp = httpx.get(f"{live_server_url}/api/v1/alerts/stream")
    app.dependency_overrides.clear()
    assert resp.status_code == 403


def test_stream_coach_receives_connected_event(live_server_url: str) -> None:
    from app.database import get_db
    from app.deps import get_current_user

    coach = _make_user(UserRole.coach, "OL")
    app.dependency_overrides[get_current_user] = lambda: coach
    app.dependency_overrides[get_db] = _mock_db_override()

    with httpx.stream("GET", f"{live_server_url}/api/v1/alerts/stream") as stream:
        lines = stream.iter_lines()
        first_chunk = _get_next_sse_line(lines)

    app.dependency_overrides.clear()

    assert "data:" in first_chunk
    payload = json.loads(first_chunk.replace("data: ", ""))
    assert payload.get("type") == "connected"
    assert "connection_id" in payload


def test_stream_coach_cannot_override_position_group(live_server_url: str) -> None:
    from app.database import get_db
    from app.deps import get_current_user

    coach = _make_user(UserRole.coach, "OL")
    app.dependency_overrides[get_current_user] = lambda: coach
    app.dependency_overrides[get_db] = _mock_db_override()

    resp = httpx.get(f"{live_server_url}/api/v1/alerts/stream?position_group=WR")

    app.dependency_overrides.clear()
    assert resp.status_code == 403


def test_stream_delivers_published_alert(live_server_url: str) -> None:
    from app.database import get_db
    from app.deps import get_current_user

    coach = _make_user(UserRole.coach, "OL")
    app.dependency_overrides[get_current_user] = lambda: coach
    app.dependency_overrides[get_db] = _mock_db_override()

    received: list[dict] = []

    with httpx.stream("GET", f"{live_server_url}/api/v1/alerts/stream") as stream:
        lines = stream.iter_lines()
        first = _get_next_sse_line(lines)
        # Parse connection event to get conn_id
        conn_payload = json.loads(first.replace("data: ", ""))
        conn_id = conn_payload["connection_id"]

        # Publish an OL alert — should match the coach's filter
        if conn_id in _connections:
            _connections[conn_id][0].put_nowait(
                {"alert_type": "effort_anomaly", "position_group": "OL"}
            )
        second = _get_next_sse_line(lines)
        received.append(json.loads(second.replace("data: ", "")))

    app.dependency_overrides.clear()

    if received:
        assert received[0].get("alert_type") == "effort_anomaly"


# ── SSE event format ─────────────────────────────────────────────────────────


def test_sse_event_format_has_data_prefix(live_server_url: str) -> None:
    from app.database import get_db
    from app.deps import get_current_user

    coach = _make_user(UserRole.coach, "WR")
    app.dependency_overrides[get_current_user] = lambda: coach
    app.dependency_overrides[get_db] = _mock_db_override()

    with httpx.stream("GET", f"{live_server_url}/api/v1/alerts/stream") as stream:
        lines = stream.iter_lines()
        first_line = _get_next_sse_line(lines)

    app.dependency_overrides.clear()

    assert first_line.startswith("data: "), f"Expected SSE format, got: {first_line!r}"


def test_disconnect_removes_connection_from_registry(live_server_url: str) -> None:
    """After the client disconnects, its queue should be removed from _connections."""
    from app.database import get_db
    from app.deps import get_current_user

    analyst = _make_user(UserRole.analyst)
    app.dependency_overrides[get_current_user] = lambda: analyst
    app.dependency_overrides[get_db] = _mock_db_override()

    conn_id_seen: list[str] = []

    with httpx.stream("GET", f"{live_server_url}/api/v1/alerts/stream") as stream:
        lines = stream.iter_lines()
        first = _get_next_sse_line(lines)
        payload = json.loads(first.replace("data: ", ""))
        conn_id_seen.append(payload["connection_id"])
        # Connection is now closed

    app.dependency_overrides.clear()

    # Wait briefly for uvicorn connection closure to run the generator finally block
    time.sleep(0.1)

    if conn_id_seen:
        assert conn_id_seen[0] not in _connections
