"""Tests for the /health and /ready endpoints."""

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_503_when_db_unavailable(client: TestClient) -> None:
    # In the unit-test environment there is no real database, so /ready
    # should return 503.
    response = client.get("/ready")
    assert response.status_code == 503
