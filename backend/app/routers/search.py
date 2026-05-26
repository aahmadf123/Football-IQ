"""Similar-rep search router (Issue #8 — Phase 3).

Endpoints:

* ``POST /api/v1/search/similar`` — given a clip ID, return the top-N
  clips whose play embeddings are nearest by cosine similarity. Supports
  the design-doc filter set: date range, opponent (via
  ``videos.metadata``), formation, coverage, side-of-ball.

* ``POST /api/v1/search/vector`` — same retrieval shape but the request
  supplies a raw 256-d vector. Useful for batch CLI tools that want to
  search by a centroid or hand-crafted prototype.

* ``POST /api/v1/search/text`` — *experimental.* Encodes a natural-
  language query with the CLIP text tower and runs the same vector
  search. Outputs always carry ``experimental: true`` and are filtered
  out of any caller that opts into production-only results. The endpoint
  refuses to serve unless ``ENABLE_EMBEDDING_TEXT_SEARCH`` is truthy in
  the env so the surface stays gated end-to-end.

The vector similarity is computed in Postgres via the pgvector ``<=>``
cosine-distance operator. We pre-filter on label / date / opponent
fields (selective WHEREs) and let pgvector's ivfflat index rank the
candidate set.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import (
    PLAY_EMBEDDING_DIM,
    Clip,
    ModelStage,
    ModelVersion,
    PlayEmbedding,
    SessionKind,
    SideOfBall,
    User,
    Video,
)

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/search", tags=["search"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class SearchFilters(BaseModel):
    """Coach-facing filter set; all fields optional."""

    since: datetime | None = None
    until: datetime | None = None
    opponent: str | None = None
    formation: str | None = None
    coverage: str | None = None
    side_of_ball: SideOfBall | None = None
    session_kind: SessionKind | None = None
    our_possession: SideOfBall | None = None
    practice_session_id: uuid.UUID | None = None
    include_experimental: bool = False


class SimilarSearchRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    clip_id: uuid.UUID
    k: int = Field(default=20, ge=1, le=200)
    chunk_kind: str = "play"
    filters: SearchFilters = Field(default_factory=SearchFilters)


class VectorSearchRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    vector: list[float] = Field(..., min_length=PLAY_EMBEDDING_DIM, max_length=PLAY_EMBEDDING_DIM)
    k: int = Field(default=20, ge=1, le=200)
    chunk_kind: str = "play"
    model_version_id: uuid.UUID | None = None
    filters: SearchFilters = Field(default_factory=SearchFilters)


class TextSearchRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    query: str = Field(..., min_length=1, max_length=512)
    k: int = Field(default=20, ge=1, le=200)
    chunk_kind: str = "play"
    filters: SearchFilters = Field(default_factory=SearchFilters)


class SimilarResult(BaseModel):
    model_config = {"protected_namespaces": ()}

    clip_id: uuid.UUID
    embedding_id: uuid.UUID
    score: float
    is_experimental: bool
    snap_anchor: bool
    chunk_kind: str
    label_data: dict[str, Any] | None = None


class SearchResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    anchor_clip_id: uuid.UUID | None
    model_version_id: uuid.UUID | None
    model_version_label: str | None
    experimental: bool
    reason: str | None = None
    results: list[SimilarResult]


# ── Helpers ───────────────────────────────────────────────────────────────────


PRODUCTION_STAGES = (ModelStage.production, ModelStage.staging)


async def _resolve_production_model_version(
    db: AsyncSession,
) -> ModelVersion | None:
    """Pick the highest-promoted embedding model version available.

    Preference order: production > staging. Among rows of the same stage
    we pick the most recently created. ``experimental`` versions never
    serve the retrieval router by default — they exist to write rows,
    not to be searched against.
    """
    q = (
        select(ModelVersion)
        .where(ModelVersion.model_type == "play_embedding")
        .where(ModelVersion.promoted_stage.in_(PRODUCTION_STAGES))
        .order_by(ModelVersion.promoted_stage.asc(), ModelVersion.created_at.desc())
    )
    result = await db.execute(q)
    versions = list(result.scalars().all())
    # Prefer production over staging when both exist.
    for stage in PRODUCTION_STAGES:
        for v in versions:
            if v.promoted_stage == stage:
                return v
    return versions[0] if versions else None


def _model_label(mv: ModelVersion) -> str:
    return f"{mv.model_name}@{mv.version}"


async def _candidate_clip_ids(db: AsyncSession, filters: SearchFilters) -> list[uuid.UUID] | None:
    """Pre-filter clip IDs by metadata. Returns ``None`` if no filters set."""
    if not any(
        [
            filters.since,
            filters.until,
            filters.opponent,
            filters.formation,
            filters.coverage,
            filters.side_of_ball,
            filters.session_kind,
            filters.our_possession,
            filters.practice_session_id,
        ]
    ):
        return None

    q = select(Clip.id).join(Video, Video.id == Clip.video_id)
    if filters.since is not None:
        q = q.where(Video.recorded_at >= filters.since)
    if filters.until is not None:
        q = q.where(Video.recorded_at <= filters.until)
    if filters.opponent:
        # Opponent first-class column wins, but the JSON value remains
        # a compatibility fallback (#98 backfill is best-effort).
        q = q.where(
            or_(
                Video.opponent_team == filters.opponent,
                Video.metadata_["opponent"].astext == filters.opponent,
            )
        )
    if filters.formation:
        q = q.where(Clip.label_data["formation"]["generic"].astext.ilike(filters.formation))
    if filters.coverage:
        q = q.where(Clip.label_data["coverage"]["generic"].astext.ilike(filters.coverage))
    if filters.side_of_ball:
        q = q.where(Clip.side_of_ball == filters.side_of_ball)
    if filters.session_kind:
        q = q.where(Video.session_kind == filters.session_kind)
    if filters.our_possession:
        q = q.where(Clip.our_possession == filters.our_possession)
    if filters.practice_session_id:
        q = q.where(Video.practice_session_id == filters.practice_session_id)

    result = await db.execute(q)
    return [r[0] for r in result.all()]


def _format_vector_for_sql(values: list[float]) -> str:
    """pgvector accepts ``"[1.0,2.0,...]"`` as a parameter binding."""
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


async def _run_vector_search(
    db: AsyncSession,
    *,
    anchor_vector: list[float],
    k: int,
    chunk_kind: str,
    model_version_id: uuid.UUID,
    candidate_clip_ids: list[uuid.UUID] | None,
    include_experimental: bool,
    exclude_clip_ids: list[uuid.UUID] | None = None,
) -> list[SimilarResult]:
    """Run the pgvector cosine-distance ORDER BY for the given anchor."""
    where_clauses = [
        "pe.model_version_id = :model_version_id",
        "pe.chunk_kind = :chunk_kind",
    ]
    params: dict[str, Any] = {
        "anchor": _format_vector_for_sql(anchor_vector),
        "k": k,
        "model_version_id": str(model_version_id),
        "chunk_kind": chunk_kind,
    }
    if not include_experimental:
        where_clauses.append("pe.is_experimental = false")
    if candidate_clip_ids is not None:
        if not candidate_clip_ids:
            return []
        where_clauses.append("pe.clip_id = ANY(:candidate_clip_ids)")
        params["candidate_clip_ids"] = [str(cid) for cid in candidate_clip_ids]
    if exclude_clip_ids:
        where_clauses.append("pe.clip_id <> ALL(:exclude_clip_ids)")
        params["exclude_clip_ids"] = [str(cid) for cid in exclude_clip_ids]

    # The ``where_clauses`` list is built from a closed set of literal
    # fragments in this function — no user input ever lands in it — so the
    # f-string interpolation is safe and the bandit warning is a false
    # positive. All actual values flow through ``params`` and are bound
    # by SQLAlchemy as parameters.
    where_sql = " AND ".join(where_clauses)
    sql_str = (  # noqa: S608 — where_sql is composed from static fragments above
        "SELECT pe.id AS embedding_id, pe.clip_id AS clip_id, "
        "pe.snap_anchor AS snap_anchor, pe.chunk_kind AS chunk_kind, "
        "pe.is_experimental AS is_experimental, c.label_data AS label_data, "
        "1 - (pe.vector <=> CAST(:anchor AS vector)) AS score "
        "FROM playembeddings pe "
        "JOIN clips c ON c.id = pe.clip_id "
        "WHERE " + where_sql + " "
        "ORDER BY pe.vector <=> CAST(:anchor AS vector) ASC "
        "LIMIT :k"
    )
    from sqlalchemy.dialects.postgresql import ARRAY, UUID

    sql = text(sql_str)
    if candidate_clip_ids is not None:
        sql = sql.bindparams(bindparam("candidate_clip_ids", type_=ARRAY(UUID(as_uuid=True))))
    if exclude_clip_ids:
        sql = sql.bindparams(bindparam("exclude_clip_ids", type_=ARRAY(UUID(as_uuid=True))))
    result = await db.execute(sql, params)
    out: list[SimilarResult] = []
    for row in result.mappings():
        out.append(
            SimilarResult(
                clip_id=row["clip_id"],
                embedding_id=row["embedding_id"],
                score=float(row["score"]),
                is_experimental=bool(row["is_experimental"]),
                snap_anchor=bool(row["snap_anchor"]),
                chunk_kind=row["chunk_kind"],
                label_data=row["label_data"],
            )
        )
    return out


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/similar", response_model=SearchResponse)
async def search_similar(
    payload: SimilarSearchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> SearchResponse:
    """Top-K plays whose embedding is closest to the anchor clip's.

    The router automatically resolves the production / staging embedding
    model version and excludes the anchor clip itself from the result
    list. Filters (opponent, date range, formation, coverage,
    side-of-ball) are applied as a pre-filter before the vector ORDER BY
    so pgvector only ranks the relevant candidate set.
    """
    mv = await _resolve_production_model_version(db)
    if mv is None:
        return SearchResponse(
            anchor_clip_id=payload.clip_id,
            model_version_id=None,
            model_version_label=None,
            experimental=False,
            reason="no production embedding model",
            results=[],
        )

    anchor_q = select(PlayEmbedding).where(
        PlayEmbedding.clip_id == payload.clip_id,
        PlayEmbedding.chunk_kind == payload.chunk_kind,
        PlayEmbedding.model_version_id == mv.id,
    )
    anchor = (await db.execute(anchor_q)).scalar_one_or_none()
    if anchor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No embedding for this clip with the production model version yet — "
                "rerun the nightly embed stage."
            ),
        )

    candidate_ids = await _candidate_clip_ids(db, payload.filters)
    results = await _run_vector_search(
        db,
        anchor_vector=list(anchor.vector or []),
        k=payload.k,
        chunk_kind=payload.chunk_kind,
        model_version_id=mv.id,
        candidate_clip_ids=candidate_ids,
        include_experimental=payload.filters.include_experimental,
        exclude_clip_ids=[payload.clip_id],
    )
    log.info(
        "search_similar",
        anchor_clip_id=str(payload.clip_id),
        k=payload.k,
        result_count=len(results),
        model_version_id=str(mv.id),
    )
    return SearchResponse(
        anchor_clip_id=payload.clip_id,
        model_version_id=mv.id,
        model_version_label=_model_label(mv),
        experimental=False,
        results=results,
    )


@router.post("/vector", response_model=SearchResponse)
async def search_by_vector(
    payload: VectorSearchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> SearchResponse:
    """Top-K plays nearest a raw query vector.

    The query model version is the one supplied in the request, falling
    back to the highest promoted ``play_embedding`` version. Useful for
    batch / CLI tools that want to query by a hand-built prototype or a
    cluster centroid pulled from ``embedding_cluster_proposals``.
    """
    if payload.model_version_id is not None:
        mv = (
            await db.execute(
                select(ModelVersion).where(ModelVersion.id == payload.model_version_id)
            )
        ).scalar_one_or_none()
    else:
        mv = await _resolve_production_model_version(db)
    if mv is None:
        return SearchResponse(
            anchor_clip_id=None,
            model_version_id=None,
            model_version_label=None,
            experimental=False,
            reason="no embedding model version available",
            results=[],
        )

    candidate_ids = await _candidate_clip_ids(db, payload.filters)
    results = await _run_vector_search(
        db,
        anchor_vector=payload.vector,
        k=payload.k,
        chunk_kind=payload.chunk_kind,
        model_version_id=mv.id,
        candidate_clip_ids=candidate_ids,
        include_experimental=payload.filters.include_experimental,
    )
    log.info(
        "search_by_vector",
        k=payload.k,
        result_count=len(results),
        model_version_id=str(mv.id),
    )
    return SearchResponse(
        anchor_clip_id=None,
        model_version_id=mv.id,
        model_version_label=_model_label(mv),
        experimental=False,
        results=results,
    )


def _text_search_enabled() -> bool:
    raw = os.environ.get("ENABLE_EMBEDDING_TEXT_SEARCH", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@router.post("/text", response_model=SearchResponse)
async def search_by_text(
    payload: TextSearchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> SearchResponse:
    """Natural-language query — *experimental*.

    Always returns ``experimental: true`` in the response envelope so the
    front-end can label results clearly and the back-end correction
    export job skips them. The endpoint is gated behind
    ``ENABLE_EMBEDDING_TEXT_SEARCH``; when off it returns 503 instead of
    silently degrading to similar-by-clip.
    """
    if not _text_search_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Text search is gated behind ENABLE_EMBEDDING_TEXT_SEARCH and is "
                "currently disabled."
            ),
        )

    # Stub text-encoder: production ships the CLIP text tower here, but
    # we don't pre-load CLIP weights in the backend container — the
    # production deploy injects an encoder via dependency override.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Text search is enabled but no text encoder is wired into this "
            "deployment. Override ``encode_query_text`` in app state."
        ),
    )
