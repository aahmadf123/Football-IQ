"""Tests for the similar-rep search router (Issue #8).

The pgvector ``<=>`` ORDER BY runs in Postgres, so these tests:

* Verify the request/response schemas accept the documented payloads.
* Verify the ``_resolve_production_model_version`` picker prefers
  production over staging and falls back to staging when no production
  version is registered.
* Verify the SQL builder for the vector query includes the
  experimental-filter clause by default and excludes the anchor clip.
* Mock the DB session to assert the search router returns the canonical
  "no model" envelope rather than crashing when there is no embedding
  model version.
* Verify that ``/api/v1/search/text`` 503s when the experimental flag
  is unset — keeping the surface gated.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.database import get_db
from app.deps import get_current_user
from app.main import app
from app.models import PLAY_EMBEDDING_DIM, ModelStage, ModelVersion, User, UserRole
from app.routers.search import (
    SearchFilters,
    SimilarSearchRequest,
    VectorSearchRequest,
    _format_vector_for_sql,
    _resolve_production_model_version,
    _run_vector_search,
)
from fastapi.testclient import TestClient


def _make_user() -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.role = UserRole.coach
    u.is_active = True
    return u


def _model_version(stage: ModelStage, created_at: datetime | None = None) -> MagicMock:
    mv = MagicMock(spec=ModelVersion)
    mv.id = uuid.uuid4()
    mv.model_name = "play-embed-clip-vitb32-baseline"
    mv.version = "1.0"
    mv.model_type = "play_embedding"
    mv.promoted_stage = stage
    mv.created_at = created_at or datetime.now(UTC)
    return mv


def _mock_scalars(items: list[Any]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


# ── Schema sanity ─────────────────────────────────────────────────────────────


def test_similar_search_request_defaults() -> None:
    req = SimilarSearchRequest(clip_id=uuid.uuid4())
    assert req.k == 20
    assert req.chunk_kind == "play"
    assert isinstance(req.filters, SearchFilters)
    assert req.filters.include_experimental is False


def test_vector_search_request_rejects_wrong_dim() -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        VectorSearchRequest(vector=[0.0] * 10)


def test_vector_search_request_accepts_full_dim() -> None:
    req = VectorSearchRequest(vector=[0.0] * PLAY_EMBEDDING_DIM)
    assert len(req.vector) == PLAY_EMBEDDING_DIM


# ── pgvector textual formatter ───────────────────────────────────────────────


def test_format_vector_for_sql_round_trips_floats() -> None:
    s = _format_vector_for_sql([1.0, 2.5, -3.25])
    assert s.startswith("[") and s.endswith("]")
    # The textual form is what pgvector accepts as a bind value.
    assert "1.0" in s and "2.5" in s and "-3.25" in s


# ── Production model version picker ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_production_model_version_prefers_production() -> None:
    staging = _model_version(ModelStage.staging)
    production = _model_version(ModelStage.production)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_mock_scalars([staging, production]))
    chosen = await _resolve_production_model_version(session)
    assert chosen is production


@pytest.mark.asyncio
async def test_resolve_production_model_version_falls_back_to_staging() -> None:
    staging = _model_version(ModelStage.staging)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_mock_scalars([staging]))
    chosen = await _resolve_production_model_version(session)
    assert chosen is staging


@pytest.mark.asyncio
async def test_resolve_production_model_version_returns_none_when_empty() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_mock_scalars([]))
    chosen = await _resolve_production_model_version(session)
    assert chosen is None


# ── SQL builder for the vector ORDER BY ──────────────────────────────────────


@pytest.mark.asyncio
async def test_run_vector_search_default_filters_out_experimental_rows() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_empty_mapping_result())
    await _run_vector_search(
        session,
        anchor_vector=[0.0] * PLAY_EMBEDDING_DIM,
        k=5,
        chunk_kind="play",
        model_version_id=uuid.uuid4(),
        candidate_clip_ids=None,
        include_experimental=False,
    )
    assert session.execute.await_count == 1
    sql_clause, params = session.execute.await_args.args
    assert "pe.is_experimental = false" in str(sql_clause)
    assert params["chunk_kind"] == "play"
    assert params["k"] == 5


@pytest.mark.asyncio
async def test_run_vector_search_drops_experimental_clause_when_requested() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_empty_mapping_result())
    await _run_vector_search(
        session,
        anchor_vector=[0.0] * PLAY_EMBEDDING_DIM,
        k=5,
        chunk_kind="play",
        model_version_id=uuid.uuid4(),
        candidate_clip_ids=None,
        include_experimental=True,
    )
    sql_clause, _ = session.execute.await_args.args
    assert "pe.is_experimental = false" not in str(sql_clause)


@pytest.mark.asyncio
async def test_run_vector_search_short_circuits_empty_candidate_set() -> None:
    """Filter pre-pass returned no candidates → skip pgvector entirely."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_empty_mapping_result())
    results = await _run_vector_search(
        session,
        anchor_vector=[0.0] * PLAY_EMBEDDING_DIM,
        k=5,
        chunk_kind="play",
        model_version_id=uuid.uuid4(),
        candidate_clip_ids=[],
        include_experimental=False,
    )
    assert results == []
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_run_vector_search_appends_anchor_exclusion_clause() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_empty_mapping_result())
    anchor = uuid.uuid4()
    await _run_vector_search(
        session,
        anchor_vector=[0.0] * PLAY_EMBEDDING_DIM,
        k=5,
        chunk_kind="play",
        model_version_id=uuid.uuid4(),
        candidate_clip_ids=None,
        include_experimental=False,
        exclude_clip_ids=[anchor],
    )
    sql_clause, params = session.execute.await_args.args
    assert "pe.clip_id <> ALL(:exclude_clip_ids)" in str(sql_clause)
    assert params["exclude_clip_ids"] == [str(anchor)]


def _empty_mapping_result() -> MagicMock:
    result = MagicMock()
    result.mappings.return_value = []
    return result


# ── Router-level behaviour with a mocked DB ──────────────────────────────────


def _mock_db_gen_no_model_version():
    async def _db() -> AsyncGenerator[Any, None]:
        session = AsyncMock()
        # _resolve_production_model_version sees no rows → no model version.
        session.execute = AsyncMock(return_value=_mock_scalars([]))
        yield session

    return _db


def test_search_similar_returns_no_model_envelope_when_unconfigured() -> None:
    app.dependency_overrides[get_current_user] = lambda: _make_user()
    app.dependency_overrides[get_db] = _mock_db_gen_no_model_version()
    try:
        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/search/similar",
                json={"clip_id": str(uuid.uuid4()), "k": 10},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == []
    assert body["reason"] == "no production embedding model"
    assert body["model_version_id"] is None
    assert body["experimental"] is False


def test_search_by_vector_returns_no_model_envelope_when_unconfigured() -> None:
    app.dependency_overrides[get_current_user] = lambda: _make_user()
    app.dependency_overrides[get_db] = _mock_db_gen_no_model_version()
    try:
        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/search/vector",
                json={"vector": [0.0] * PLAY_EMBEDDING_DIM, "k": 5},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == []
    assert body["reason"] == "no embedding model version available"


def test_search_similar_requires_auth(client) -> None:
    resp = client.post(
        "/api/v1/search/similar",
        json={"clip_id": str(uuid.uuid4()), "k": 10},
    )
    assert resp.status_code == 401


def test_search_text_is_gated_503_when_flag_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENABLE_EMBEDDING_TEXT_SEARCH", raising=False)
    app.dependency_overrides[get_current_user] = lambda: _make_user()
    try:
        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/search/text",
                json={"query": "outside zone with poor backside pursuit", "k": 5},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 503
    assert "ENABLE_EMBEDDING_TEXT_SEARCH" in resp.json()["detail"]


def test_search_text_flag_on_returns_501_until_encoder_wired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag-on without an encoder is the documented "not implemented" path —
    we never want a silent fallback to similar-by-clip from the text route."""
    monkeypatch.setenv("ENABLE_EMBEDDING_TEXT_SEARCH", "1")
    app.dependency_overrides[get_current_user] = lambda: _make_user()
    try:
        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/search/text",
                json={"query": "trips right pass", "k": 5},
            )
    finally:
        app.dependency_overrides.clear()
        os.environ.pop("ENABLE_EMBEDDING_TEXT_SEARCH", None)

    assert resp.status_code == 501
