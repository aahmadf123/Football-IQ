"""Governance — RBAC policy, visibility shaping, and visibility transitions.

Exercises the new governance foundation introduced for issues #113 and #114:

* ``app.governance.policy_allows`` matrix.
* ``shape_player`` for each visibility mode and visibility state combination.
* The new ``PATCH /api/v1/players/{id}/visibility`` workflow and 404 behaviour
  when a record is not approved for the caller's mode.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.database import get_db
from app.deps import get_current_user
from app.governance import (
    Action,
    Resource,
    VisibilityMode,
    VisibilityState,
    default_mode_for_role,
    policy_allows,
    resolve_visibility_mode,
    shape_player,
)
from app.main import app
from app.models import Player, PlayerVisibilityState, User, UserRole
from fastapi import HTTPException
from fastapi.testclient import TestClient

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_user(role: UserRole = UserRole.coach) -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = role
    u.is_active = True
    return u


def _make_player(
    state: PlayerVisibilityState = PlayerVisibilityState.staff_only,
) -> Player:
    p = MagicMock(spec=Player)
    p.id = uuid.uuid4()
    p.first_name = "Marcus"
    p.last_name = "Carter"
    p.jersey_number = 11
    p.position = "WR"
    p.position_group = "Skill"
    p.is_active = True
    p.user_id = None
    p.metadata_ = {"secret": "should not leak"}
    p.created_at = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    p.visibility_state = state
    p.visibility_updated_by = None
    p.visibility_updated_at = None
    return p


def _override_db(
    list_rows: list[Player] | None = None,
    detail_row: Player | None = None,
    audit_rows: list[Any] | None = None,
) -> None:
    async def _db() -> AsyncGenerator[Any, None]:
        session = AsyncMock()

        async def _execute(_stmt: Any) -> Any:
            result = MagicMock()
            result.scalar_one_or_none.return_value = detail_row
            scalars = MagicMock()
            scalars.all.return_value = list_rows if list_rows is not None else (audit_rows or [])
            result.scalars.return_value = scalars
            return result

        session.execute = AsyncMock(side_effect=_execute)
        session.flush = AsyncMock()
        session.add = MagicMock()
        yield session

    app.dependency_overrides[get_db] = _db


# ── Policy matrix ────────────────────────────────────────────────────────────


def test_policy_default_deny_for_unknown_pair() -> None:
    """An unmapped (resource, action) pair must default to deny."""
    # PLAYER_PROFILE / TRIGGER is not in the policy table.
    assert policy_allows(UserRole.admin, Resource.PLAYER_PROFILE, Action.TRIGGER) is False


def test_policy_allows_expected_roles() -> None:
    assert policy_allows(UserRole.sportsperformance, Resource.HEALTH_WORKLOAD, Action.READ)
    assert not policy_allows(UserRole.coach, Resource.HEALTH_WORKLOAD, Action.READ)
    assert policy_allows(UserRole.admin, Resource.PLAYER_VISIBILITY, Action.APPROVE)
    assert not policy_allows(UserRole.coach, Resource.PLAYER_VISIBILITY, Action.APPROVE)


def test_default_mode_for_role() -> None:
    assert default_mode_for_role(UserRole.coach) == VisibilityMode.STAFF
    assert default_mode_for_role(UserRole.player) == VisibilityMode.PLAYER
    assert default_mode_for_role(UserRole.viewer) == VisibilityMode.RECRUITING


def test_resolve_visibility_mode_player_cannot_request_staff() -> None:
    user = _make_user(role=UserRole.player)
    with pytest.raises(HTTPException) as exc:
        resolve_visibility_mode(user, VisibilityMode.STAFF)
    assert exc.value.status_code == 403


def test_resolve_visibility_mode_admin_can_request_any() -> None:
    user = _make_user(role=UserRole.admin)
    assert resolve_visibility_mode(user, VisibilityMode.RECRUITING) == VisibilityMode.RECRUITING


# ── Visibility shaping ───────────────────────────────────────────────────────


def test_shape_staff_view_returns_full_payload() -> None:
    p = _make_player(state=PlayerVisibilityState.staff_only)
    out = shape_player(p, VisibilityMode.STAFF)
    assert out is not None
    assert out["view"] == "staff"
    assert out["metadata"] == {"secret": "should not leak"}
    assert out["visibility_state"] == "staff_only"


def test_shape_player_view_blocked_when_staff_only() -> None:
    p = _make_player(state=PlayerVisibilityState.staff_only)
    assert shape_player(p, VisibilityMode.PLAYER) is None


def test_shape_player_view_strips_sensitive_fields_after_approval() -> None:
    p = _make_player(state=PlayerVisibilityState.player_approved)
    out = shape_player(p, VisibilityMode.PLAYER)
    assert out is not None
    assert out["view"] == "player"
    assert "metadata" not in out
    assert "user_id" not in out
    # Identity fields are preserved.
    assert out["jersey_number"] == 11
    assert out["position"] == "WR"


def test_shape_player_view_requires_ownership_for_player_role() -> None:
    p = _make_player(state=PlayerVisibilityState.player_approved)
    p.user_id = uuid.uuid4()
    actor = _make_user(role=UserRole.player)
    out = shape_player(p, VisibilityMode.PLAYER, actor=actor)
    assert out is None


def test_shape_recruiting_requires_recruiting_approval() -> None:
    not_yet = _make_player(state=PlayerVisibilityState.player_approved)
    assert shape_player(not_yet, VisibilityMode.RECRUITING) is None

    ok = _make_player(state=PlayerVisibilityState.recruiting_approved)
    out = shape_player(ok, VisibilityMode.RECRUITING)
    assert out is not None
    assert out["view"] == "recruiting"
    # Recruiting view drops metadata and non-public fields entirely.
    assert "metadata" not in out
    assert "user_id" not in out
    assert "is_active" not in out
    assert "created_at" not in out
    assert "visibility_state" not in out


def test_shape_archived_is_hidden_from_non_staff() -> None:
    p = _make_player(state=PlayerVisibilityState.archived)
    assert shape_player(p, VisibilityMode.PLAYER) is None
    assert shape_player(p, VisibilityMode.RECRUITING) is None
    # Staff still see the record so they can un-archive.
    staff = shape_player(p, VisibilityMode.STAFF)
    assert staff is not None
    assert staff["visibility_state"] == "archived"


# ── Router behaviour ─────────────────────────────────────────────────────────


def test_list_filters_out_players_not_approved_for_recruiting_mode() -> None:
    approved = _make_player(state=PlayerVisibilityState.recruiting_approved)
    pending = _make_player(state=PlayerVisibilityState.staff_only)
    _override_db(list_rows=[approved, pending])
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.admin)
    try:
        with TestClient(app) as c:
            resp = c.get("/api/v1/players", params={"mode": "recruiting"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["view"] == "recruiting"
    assert "metadata" not in body[0]


def test_player_list_only_includes_own_record() -> None:
    actor = _make_user(UserRole.player)
    own = _make_player(state=PlayerVisibilityState.player_approved)
    own.user_id = actor.id
    teammate = _make_player(state=PlayerVisibilityState.player_approved)
    teammate.user_id = uuid.uuid4()
    _override_db(list_rows=[own, teammate])
    app.dependency_overrides[get_current_user] = lambda: actor
    try:
        with TestClient(app) as c:
            resp = c.get("/api/v1/players")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == str(own.id)


def test_get_player_returns_404_when_not_approved_for_recruiting() -> None:
    p = _make_player(state=PlayerVisibilityState.staff_only)
    _override_db(detail_row=p)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.admin)
    try:
        with TestClient(app) as c:
            resp = c.get(
                f"/api/v1/players/{p.id}",
                params={"mode": "recruiting"},
            )
    finally:
        app.dependency_overrides.clear()
    # 404 (not 403) so we don't leak whether the record exists.
    assert resp.status_code == 404


def test_player_cannot_view_other_player_identity() -> None:
    p = _make_player(state=PlayerVisibilityState.player_approved)
    p.user_id = uuid.uuid4()
    _override_db(detail_row=p)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.player)
    try:
        with TestClient(app) as c:
            resp = c.get(f"/api/v1/players/{p.id}")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 404


def test_visibility_patch_denied_for_viewer_role() -> None:
    p = _make_player()
    _override_db(detail_row=p)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.viewer)
    try:
        with TestClient(app) as c:
            resp = c.patch(
                f"/api/v1/players/{p.id}/visibility",
                json={"state": "player_approved"},
            )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 403


def test_visibility_patch_recruiting_requires_approve_role() -> None:
    p = _make_player()
    _override_db(detail_row=p)
    # Coach has WRITE but not APPROVE for recruiting state.
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach)
    try:
        with TestClient(app) as c:
            resp = c.patch(
                f"/api/v1/players/{p.id}/visibility",
                json={"state": "recruiting_approved"},
            )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 403
    body = resp.json()
    assert body["detail"]["error_code"] == "approval_required"


def test_visibility_patch_succeeds_for_analyst() -> None:
    p = _make_player(state=PlayerVisibilityState.staff_only)
    _override_db(detail_row=p)
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.analyst)
    try:
        with TestClient(app) as c:
            resp = c.patch(
                f"/api/v1/players/{p.id}/visibility",
                json={
                    "state": "recruiting_approved",
                    "reason": "Profile reviewed for recruiting packet",
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["previous_state"] == "staff_only"
    assert body["next_state"] == "recruiting_approved"
    # The ORM row should have been updated server-side, including updated_by.
    assert p.visibility_state == PlayerVisibilityState.recruiting_approved
    assert p.visibility_updated_by is not None


def test_visibility_state_enum_matches_governance_enum() -> None:
    """Schema enum and governance enum must stay in lock-step."""
    schema = {s.value for s in PlayerVisibilityState}
    governance = {s.value for s in VisibilityState}
    assert schema == governance
