"""Tests for the settings router (Issue #112).

Uses dependency overrides on ``get_db`` and ``get_current_user`` to swap in
a fake DB session, mirroring the pattern used in ``test_players.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.main import app
from app.models import SystemSetting, User, UserRole, UserSetting
from fastapi.testclient import TestClient


def _make_user(role: UserRole = UserRole.admin, user_id: uuid.UUID | None = None) -> User:
    u = MagicMock(spec=User)
    u.id = user_id or uuid.uuid4()
    u.role = role
    u.is_active = True
    return u


class _FakeDB:
    """Stand-in async session whose execute returns pre-seeded rows by key.

    Persists ``add()`` calls into the same backing dicts so subsequent
    selects in the same request see the upserted rows.
    """

    def __init__(self) -> None:
        # key -> {value, updated_by}
        self.system: dict[str, dict[str, Any]] = {}
        # (user_id, key) -> {value}
        self.user: dict[tuple[Any, str], dict[str, Any]] = {}
        self.added: list[Any] = []

    async def execute(self, stmt: Any) -> Any:
        sql = str(stmt).lower()
        result = MagicMock()
        if "system_settings" in sql:
            row = self._load_system(stmt)
            result.scalar_one_or_none.return_value = row
        elif "user_settings" in sql:
            row = self._load_user(stmt)
            result.scalar_one_or_none.return_value = row
        else:
            result.scalar_one_or_none.return_value = None
        return result

    def _load_system(self, stmt: Any) -> Any:
        key = _grab_param(stmt, prefer_prefix="key")
        if key is None or key not in self.system:
            return None
        return _mock_row(SystemSetting, key=key, value=self.system[key]["value"])

    def _load_user(self, stmt: Any) -> Any:
        params = _grab_all_params(stmt)
        user_id = params.get("user_id_1")
        key = params.get("key_1")
        if key is None:
            # Fall back to scanning every param name.
            for k, v in params.items():
                if "user_id" in k:
                    user_id = v
                elif "key" in k:
                    key = v
        if user_id is None or key is None or (user_id, key) not in self.user:
            return None
        row = _mock_row(UserSetting, value=self.user[(user_id, key)]["value"])
        row.user_id = user_id
        row.key = key
        return row

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        if isinstance(obj, SystemSetting):
            self.system[obj.key] = {"value": dict(obj.value), "updated_by": obj.updated_by}
        elif isinstance(obj, UserSetting):
            self.user[(obj.user_id, obj.key)] = {"value": dict(obj.value)}

    async def flush(self) -> None:
        # Capture in-place mutations to existing rows that the router does
        # via ``row.value = new_value``.  We can't observe MagicMock writes
        # directly, but we don't need to: every PATCH path in this router
        # also calls back into the GET handler at the end, which re-issues
        # a SELECT — and our SELECT returns a *fresh* mock built from the
        # backing dict.  So mutations of existing rows only matter if the
        # backing dict gets updated; we rely on add() for that.
        pass

    async def commit(self) -> None:
        await self.flush()

    async def rollback(self) -> None:
        pass

    async def close(self) -> None:
        pass


def _mock_row(spec_cls: type, **attrs: Any) -> Any:
    row = MagicMock(spec=spec_cls)
    for k, v in attrs.items():
        setattr(row, k, v)
    return row


def _grab_param(stmt: Any, *, prefer_prefix: str) -> Any:
    params = _grab_all_params(stmt)
    for name, value in params.items():
        if name.startswith(prefer_prefix):
            return value
    return next(iter(params.values()), None)


def _grab_all_params(stmt: Any) -> dict[str, Any]:
    try:
        compiled = stmt.compile()
        return dict(compiled.params)
    except Exception:  # noqa: BLE001
        return {}


def _install_db(fake: _FakeDB) -> None:
    async def _gen() -> AsyncGenerator[_FakeDB, None]:
        yield fake

    app.dependency_overrides[get_db] = _gen


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    yield
    app.dependency_overrides.clear()


# ── System settings ───────────────────────────────────────────────────────────


def test_get_system_returns_defaults_when_empty() -> None:
    fake = _FakeDB()
    _install_db(fake)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach)

    with TestClient(app) as c:
        resp = c.get("/api/v1/settings/system")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["system_config"]["team_name"] == "Toledo Rockets"
    assert body["system_config"]["auto_export_access"] == "staff"
    assert body["model_sensitivity"]["boundary_sensitivity"] == 68


def test_patch_system_as_admin_persists() -> None:
    fake = _FakeDB()
    _install_db(fake)
    admin = _make_user(UserRole.admin)
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[require_admin] = lambda: admin

    with TestClient(app) as c:
        resp = c.patch(
            "/api/v1/settings/system",
            json={
                "system_config": {"team_name": "Toledo Rockets 2.0"},
                "model_sensitivity": {"boundary_sensitivity": 91},
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["system_config"]["team_name"] == "Toledo Rockets 2.0"
    # Unspecified fields fall back to defaults.
    assert body["system_config"]["capture_camera"] == "Drone (primary)"
    assert body["model_sensitivity"]["boundary_sensitivity"] == 91

    assert fake.system["system_config"]["value"]["team_name"] == "Toledo Rockets 2.0"
    assert fake.system["model_sensitivity"]["value"]["boundary_sensitivity"] == 91
    assert fake.system["system_config"]["updated_by"] == admin.id


def test_patch_system_rejects_out_of_range() -> None:
    fake = _FakeDB()
    _install_db(fake)
    admin = _make_user(UserRole.admin)
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[require_admin] = lambda: admin

    with TestClient(app) as c:
        resp = c.patch(
            "/api/v1/settings/system",
            json={"model_sensitivity": {"boundary_sensitivity": 250}},
        )
    assert resp.status_code == 422


def test_patch_system_as_coach_forbidden() -> None:
    fake = _FakeDB()
    _install_db(fake)
    coach = _make_user(UserRole.coach)
    app.dependency_overrides[get_current_user] = lambda: coach
    # Intentionally do NOT override require_admin — the real guard rejects.

    with TestClient(app) as c:
        resp = c.patch(
            "/api/v1/settings/system",
            json={"system_config": {"team_name": "hijack"}},
        )
    assert resp.status_code == 403


# ── User preferences ──────────────────────────────────────────────────────────


def test_get_my_preferences_returns_defaults() -> None:
    fake = _FakeDB()
    _install_db(fake)
    user = _make_user(UserRole.coach)
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as c:
        resp = c.get("/api/v1/settings/me")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["theme"] == "system"
    assert body["default_session_kind"] == "all"


def test_patch_my_preferences_round_trips() -> None:
    fake = _FakeDB()
    _install_db(fake)
    user = _make_user(UserRole.coach)
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as c:
        resp = c.patch("/api/v1/settings/me", json={"theme": "dark"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["theme"] == "dark"

        resp2 = c.get("/api/v1/settings/me")
        assert resp2.status_code == 200
        assert resp2.json()["theme"] == "dark"

    assert fake.user[(user.id, "user_preferences")]["value"]["theme"] == "dark"


def test_user_preferences_are_isolated_per_user() -> None:
    fake = _FakeDB()
    _install_db(fake)
    user_a = _make_user(UserRole.coach)
    user_b = _make_user(UserRole.coach)

    app.dependency_overrides[get_current_user] = lambda: user_a
    with TestClient(app) as c:
        resp = c.patch("/api/v1/settings/me", json={"theme": "dark"})
        assert resp.status_code == 200

    app.dependency_overrides[get_current_user] = lambda: user_b
    with TestClient(app) as c:
        resp = c.get("/api/v1/settings/me")
        assert resp.status_code == 200
        assert resp.json()["theme"] == "system"
