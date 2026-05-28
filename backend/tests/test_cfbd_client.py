"""Unit tests for the backend-only CFBD client (Issue #161).

Covers auth-header injection, secret safety in logs, retry/backoff, rate-limit
handling, and error classification — all with a mocked httpx transport so no
real CFBD call is made.
"""

from __future__ import annotations

import logging

import httpx
import pytest
from app.cfbd.client import CFBDClient
from app.cfbd.errors import (
    CFBDAuthError,
    CFBDClientError,
    CFBDConfigError,
    CFBDRateLimitError,
    CFBDServerError,
    CFBDTransportError,
)

FAKE_KEY = "super-secret-cfbd-key-1234567890"


async def _noop_sleep(_seconds: float) -> None:
    """Replace asyncio.sleep so retry tests don't actually wait."""


def _client(handler: object, **kwargs: object) -> CFBDClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return CFBDClient(
        FAKE_KEY,
        base_url="https://api.example.test",
        transport=transport,
        backoff_base=0.0,
        sleep=_noop_sleep,
        **kwargs,  # type: ignore[arg-type]
    )


async def test_missing_key_fails_safely() -> None:
    with pytest.raises(CFBDConfigError) as exc_info:
        CFBDClient("")
    # Backend-only message points at the env var, not at any value.
    assert "CFBD_API_KEY" in str(exc_info.value)
    assert FAKE_KEY not in str(exc_info.value)


async def test_auth_header_injected_without_logging_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json=[{"id": 333, "school": "Toledo"}])

    with caplog.at_level(logging.DEBUG):
        client = _client(handler)
        teams = await client.get_teams(conference="MAC")
        await client.aclose()

    assert seen["auth"] == f"Bearer {FAKE_KEY}"
    assert teams[0].school == "Toledo"
    # The raw key must never appear in any captured log record.
    assert FAKE_KEY not in caplog.text


async def test_retry_then_success_on_rate_limit() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=[{"id": 1, "school": "Toledo"}])

    client = _client(handler, max_retries=3)
    teams = await client.get_teams()
    await client.aclose()

    assert calls["n"] == 3
    assert teams[0].school == "Toledo"


async def test_rate_limit_exhausted_raises() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "0"})

    client = _client(handler, max_retries=2)
    with pytest.raises(CFBDRateLimitError):
        await client.get_teams()
    await client.aclose()


async def test_server_error_retried_then_raised() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    client = _client(handler, max_retries=2)
    with pytest.raises(CFBDServerError):
        await client.get_teams()
    await client.aclose()
    assert calls["n"] == 3  # initial + 2 retries


async def test_transport_error_retried_then_raised() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("boom")

    client = _client(handler, max_retries=2)
    with pytest.raises(CFBDTransportError):
        await client.get_teams()
    await client.aclose()
    assert calls["n"] == 3


async def test_auth_error_not_retried() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401)

    client = _client(handler)
    with pytest.raises(CFBDAuthError):
        await client.get_teams()
    await client.aclose()
    assert calls["n"] == 1  # 401 is permanent — no retry


async def test_other_4xx_raises_client_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = _client(handler)
    with pytest.raises(CFBDClientError) as exc_info:
        await client.get_teams()
    await client.aclose()
    assert exc_info.value.status_code == 404


async def test_endpoint_param_serialization() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = str(request.url.query.decode())
        return httpx.Response(200, json=[])

    client = _client(handler)
    await client.get_games(year=2024, team="Toledo", season_type="regular")
    await client.aclose()

    assert captured["path"] == "/games"
    assert "year=2024" in captured["query"]
    assert "team=Toledo" in captured["query"]
    assert "seasonType=regular" in captured["query"]


async def test_win_probability_parses_typed_rows() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"gameId": 401, "playNumber": 1, "homeWinProb": 0.55, "homeBall": True},
                {"gameId": 401, "playNumber": 2, "homeWinProb": 0.61, "homeBall": False},
            ],
        )

    client = _client(handler)
    rows = await client.get_win_probability(game_id=401)
    await client.aclose()

    assert [r.play_number for r in rows] == [1, 2]
    assert rows[0].home_win_prob == 0.55
    assert rows[0].home_ball is True
