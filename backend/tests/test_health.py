"""Tests for the /health, /live, and /ready endpoints."""

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "football-iq-backend"
    assert "uptime_seconds" in data
    assert "environment" in data


def test_live_returns_ok(client: TestClient) -> None:
    response = client.get("/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_503_when_db_unavailable(client_no_db: TestClient) -> None:
    # client_no_db overrides the DB dependency to always raise, so /ready must 503.
    response = client_no_db.get("/ready")
    assert response.status_code == 503
