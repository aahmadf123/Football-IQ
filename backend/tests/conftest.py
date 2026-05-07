"""Pytest configuration and shared fixtures for the backend test suite."""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_no_db() -> TestClient:
    """Client with the DB dependency overridden to always raise on execute.

    This simulates an unreachable database so that /ready returns 503.
    """
    from app.database import get_db

    class _FailingSession:
        """Minimal async-session stand-in that raises on every DB call."""

        async def execute(self, *args: Any, **kwargs: Any) -> None:
            raise OSError("DB unavailable")

        async def commit(self) -> None:  # pragma: no cover
            pass

        async def rollback(self) -> None:  # pragma: no cover
            pass

        async def close(self) -> None:
            pass

    async def _unavailable_db() -> AsyncGenerator[_FailingSession, None]:
        yield _FailingSession()

    app.dependency_overrides[get_db] = _unavailable_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
