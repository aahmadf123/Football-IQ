"""Tests for the embedding-cluster review router (Issue #8 §10).

Coverage focuses on the governance contract: nothing is promoted out of
"experimental" without a coach action, accepting a proposal flips the
member embeddings, and a rejected/accepted proposal cannot have its
status overwritten by the inverse action.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.database import get_db
from app.deps import get_current_user
from app.main import app
from app.models import (
    PLAY_EMBEDDING_DIM,
    EmbeddingClusterProposal,
    User,
    UserRole,
)
from app.routers.concept_proposals import ProposalCreate, ProposalResponse
from fastapi.testclient import TestClient


def _make_user(role: UserRole = UserRole.coach) -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = role
    u.is_active = True
    return u


def _proposal(
    *,
    status_value: str = "pending",
    is_experimental: bool = True,
    member_clip_ids: list[uuid.UUID] | None = None,
    accepted_label_name: str | None = None,
) -> MagicMock:
    p = MagicMock(spec=EmbeddingClusterProposal)
    p.id = uuid.uuid4()
    p.model_version_id = uuid.uuid4()
    p.cluster_label = "0"
    p.proposed_name = "embedding_cluster_0"
    p.description = None
    p.member_clip_ids = member_clip_ids or [uuid.uuid4(), uuid.uuid4()]
    p.member_count = len(p.member_clip_ids)
    p.cohesion_score = 0.71
    p.status = status_value
    p.is_experimental = is_experimental
    p.reviewed_by = None
    p.reviewed_at = None
    p.review_notes = None
    p.accepted_label_name = accepted_label_name
    p.created_at = datetime.now(timezone.utc)
    return p


def _scalar_result(value: Any) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    r.scalar_one.return_value = value
    return r


# ── Schema sanity ─────────────────────────────────────────────────────────────


def test_proposal_create_rejects_wrong_centroid_dim() -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        ProposalCreate(
            model_version_id=uuid.uuid4(),
            cluster_label="0",
            proposed_name="cluster",
            member_clip_ids=[uuid.uuid4()],
            centroid=[0.0] * 10,
        )


def test_proposal_create_accepts_full_centroid() -> None:
    payload = ProposalCreate(
        model_version_id=uuid.uuid4(),
        cluster_label="0",
        proposed_name="cluster",
        member_clip_ids=[uuid.uuid4()],
        centroid=[0.0] * PLAY_EMBEDDING_DIM,
    )
    assert payload.centroid is not None
    assert len(payload.centroid) == PLAY_EMBEDDING_DIM


def test_proposal_response_round_trip() -> None:
    p = _proposal()
    resp = ProposalResponse.from_orm_proposal(p)
    assert resp.status == "pending"
    assert resp.is_experimental is True
    assert resp.member_count == len(p.member_clip_ids)
    assert all(isinstance(s, str) for s in resp.member_clip_ids)
    # Accepted name is null until a coach promotes the cluster.
    assert resp.accepted_label_name is None


# ── Accept / reject flow with a mocked DB ────────────────────────────────────


def _make_db_with_proposal(p: MagicMock):
    async def _db() -> AsyncGenerator[Any, None]:
        session = AsyncMock()
        # First execute (load proposal) → scalar result.
        # Subsequent executes (UPDATE PlayEmbedding) → MagicMock noop.
        session.execute = AsyncMock(side_effect=[_scalar_result(p), MagicMock()])
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        yield session

    return _db


def test_accept_proposal_flips_status_experimental_and_records_reviewer() -> None:
    p = _proposal()
    user = _make_user(UserRole.coach)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _make_db_with_proposal(p)
    try:
        with TestClient(app) as c:
            resp = c.post(
                f"/api/v1/concept-proposals/{p.id}/accept",
                json={"label_name": "mesh-like RPO read", "notes": "matches Wk3 reps"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["is_experimental"] is False
    assert body["accepted_label_name"] == "mesh-like RPO read"
    # Side effects on the proposal we mocked.
    assert p.status == "accepted"
    assert p.is_experimental is False
    assert p.reviewed_by == user.id
    assert p.accepted_label_name == "mesh-like RPO read"


def test_reject_proposal_keeps_embeddings_experimental() -> None:
    p = _proposal()
    user = _make_user(UserRole.coach)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _make_db_with_proposal(p)
    try:
        with TestClient(app) as c:
            resp = c.post(
                f"/api/v1/concept-proposals/{p.id}/reject",
                json={"notes": "noisy cluster"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    # Rejection must NOT clear the experimental flag (governance contract).
    assert body["is_experimental"] is True
    assert p.is_experimental is True


def test_accept_after_reject_is_conflict() -> None:
    p = _proposal(status_value="rejected", is_experimental=True)
    user = _make_user(UserRole.coach)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _make_db_with_proposal(p)
    try:
        with TestClient(app) as c:
            resp = c.post(
                f"/api/v1/concept-proposals/{p.id}/accept",
                json={"label_name": "noisy"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 409


def test_reject_after_accept_is_conflict() -> None:
    p = _proposal(
        status_value="accepted",
        is_experimental=False,
        accepted_label_name="concept",
    )
    user = _make_user(UserRole.coach)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _make_db_with_proposal(p)
    try:
        with TestClient(app) as c:
            resp = c.post(
                f"/api/v1/concept-proposals/{p.id}/reject",
                json={"notes": "actually no"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 409


def test_accept_idempotent_on_already_accepted_proposal() -> None:
    p = _proposal(
        status_value="accepted",
        is_experimental=False,
        accepted_label_name="already-named",
    )
    user = _make_user(UserRole.coach)

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = _make_db_with_proposal(p)
    try:
        with TestClient(app) as c:
            resp = c.post(
                f"/api/v1/concept-proposals/{p.id}/accept",
                json={"label_name": "overwrite-attempt"},
            )
    finally:
        app.dependency_overrides.clear()

    # Re-accept returns 200 and leaves the canonical name intact rather
    # than re-running the side effects.
    assert resp.status_code == 200
    assert resp.json()["accepted_label_name"] == "already-named"


def test_list_proposals_requires_coach_or_above(client) -> None:
    resp = client.get("/api/v1/concept-proposals")
    assert resp.status_code == 401
