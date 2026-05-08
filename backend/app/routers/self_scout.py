"""Self-scout exposure dashboard — Phase 2.

Provides tendency analysis endpoints for the coaching staff to identify
pre-snap tells and formation/motion/field-zone/personnel tendencies.
"""

import uuid
from collections import Counter, defaultdict
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import Clip, Label, User

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/self-scout", tags=["self-scout"])

TENDENCY_ALERT_THRESHOLD = 0.70


# ── Schemas ───────────────────────────────────────────────────────────────────


class TendencyEntry(BaseModel):
    grouping_key: str
    total_plays: int
    run_count: int
    pass_count: int
    run_rate: float
    pass_rate: float


class MotionTendency(BaseModel):
    total: int
    run_count: int
    pass_count: int
    run_rate: float
    pass_rate: float


class MotionTendencyResponse(BaseModel):
    with_motion: MotionTendency
    without_motion: MotionTendency


class TendencyAlert(BaseModel):
    alert_type: str
    message: str
    severity: str
    grouping_key: str
    run_rate: float
    pass_rate: float


class SelfScoutResponse(BaseModel):
    formation_tendencies: list[TendencyEntry]
    motion_tendencies: MotionTendencyResponse
    field_zone_tendencies: list[TendencyEntry]
    personnel_tendencies: list[TendencyEntry]
    alerts: list[TendencyAlert]
    clip_count: int


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/tendencies", response_model=SelfScoutResponse)
async def get_tendencies(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    video_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
) -> SelfScoutResponse:
    """Compute and return self-scout tendency analysis."""
    q = select(Clip).limit(limit)
    if video_id is not None:
        q = q.where(Clip.video_id == video_id)
    clip_result = await db.execute(q)
    clips = list(clip_result.scalars().all())

    clip_ids = [c.id for c in clips]
    if not clip_ids:
        return SelfScoutResponse(
            formation_tendencies=[],
            motion_tendencies=MotionTendencyResponse(
                with_motion=MotionTendency(
                    total=0, run_count=0, pass_count=0,
                    run_rate=0, pass_rate=0,
                ),
                without_motion=MotionTendency(
                    total=0, run_count=0, pass_count=0,
                    run_rate=0, pass_rate=0,
                ),
            ),
            field_zone_tendencies=[],
            personnel_tendencies=[],
            alerts=[],
            clip_count=0,
        )

    labels_result = await db.execute(
        select(Label).where(Label.clip_id.in_(clip_ids))
    )
    all_labels = list(labels_result.scalars().all())

    labels_by_clip: dict[uuid.UUID, list[Label]] = defaultdict(list)
    for lbl in all_labels:
        labels_by_clip[lbl.clip_id].append(lbl)

    # ── Formation tendencies ──────────────────────────────────────────────
    formation_plays: dict[str, Counter[str]] = defaultdict(Counter)
    motion_plays: Counter[str] = Counter()
    no_motion_plays: Counter[str] = Counter()
    zone_plays: dict[str, Counter[str]] = defaultdict(Counter)
    personnel_plays: dict[str, Counter[str]] = defaultdict(Counter)

    for clip in clips:
        clip_labels = labels_by_clip.get(clip.id, [])
        play_type = _get_play_type(clip_labels)
        formation = _get_formation(clip_labels)
        has_motion = _get_motion_detected(clip_labels)
        field_zone = clip.field_zone or "mid_field"
        personnel = clip.personnel_grouping or "unknown"

        if play_type:
            if formation:
                formation_plays[formation][play_type] += 1
            if has_motion:
                motion_plays[play_type] += 1
            else:
                no_motion_plays[play_type] += 1
            zone_plays[field_zone][play_type] += 1
            personnel_plays[personnel][play_type] += 1

    formation_tendencies = _build_tendencies(formation_plays, min_plays=3)
    field_zone_tendencies = _build_tendencies(zone_plays, min_plays=2)
    personnel_tendencies = _build_tendencies(personnel_plays, min_plays=2)

    motion_total = sum(motion_plays.values())
    no_motion_total = sum(no_motion_plays.values())
    motion_tendencies = MotionTendencyResponse(
        with_motion=MotionTendency(
            total=motion_total,
            run_count=motion_plays.get("run", 0),
            pass_count=motion_plays.get("pass", 0),
            run_rate=round(motion_plays.get("run", 0) / max(motion_total, 1), 3),
            pass_rate=round(motion_plays.get("pass", 0) / max(motion_total, 1), 3),
        ),
        without_motion=MotionTendency(
            total=no_motion_total,
            run_count=no_motion_plays.get("run", 0),
            pass_count=no_motion_plays.get("pass", 0),
            run_rate=round(no_motion_plays.get("run", 0) / max(no_motion_total, 1), 3),
            pass_rate=round(no_motion_plays.get("pass", 0) / max(no_motion_total, 1), 3),
        ),
    )

    alerts = _generate_alerts(
        formation_tendencies, motion_tendencies,
        field_zone_tendencies, personnel_tendencies,
    )

    return SelfScoutResponse(
        formation_tendencies=formation_tendencies,
        motion_tendencies=motion_tendencies,
        field_zone_tendencies=field_zone_tendencies,
        personnel_tendencies=personnel_tendencies,
        alerts=alerts,
        clip_count=len(clips),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_play_type(labels: list[Label]) -> str | None:
    for lbl in labels:
        lt = lbl.label_type
        lv = lbl.label_value or {}
        if lt == "play_concept":
            concept = str(lv.get("concept", "")).lower()
            if any(w in concept for w in ("run", "zone", "power", "counter", "draw", "sweep")):
                return "run"
            if any(w in concept for w in ("pass", "screen", "play_action", "rpo")):
                return "pass"
        if lt == "play_direction":
            return "run"
    return None


def _get_formation(labels: list[Label]) -> str | None:
    for lbl in labels:
        if lbl.label_type == "offensive_formation":
            return (lbl.label_value or {}).get("formation")
    return None


def _get_motion_detected(labels: list[Label]) -> bool:
    for lbl in labels:
        if lbl.label_type == "motion_detected":
            return bool((lbl.label_value or {}).get("detected", False))
    return False


def _build_tendencies(
    plays: dict[str, Counter[str]], min_plays: int = 3
) -> list[TendencyEntry]:
    results: list[TendencyEntry] = []
    for key, counts in plays.items():
        total = sum(counts.values())
        if total < min_plays:
            continue
        results.append(TendencyEntry(
            grouping_key=key,
            total_plays=total,
            run_count=counts.get("run", 0),
            pass_count=counts.get("pass", 0),
            run_rate=round(counts.get("run", 0) / total, 3),
            pass_rate=round(counts.get("pass", 0) / total, 3),
        ))
    return sorted(results, key=lambda r: r.total_plays, reverse=True)


def _generate_alerts(
    formation_tendencies: list[TendencyEntry],
    motion_tendencies: MotionTendencyResponse,
    field_zone_tendencies: list[TendencyEntry],
    personnel_tendencies: list[TendencyEntry],
) -> list[TendencyAlert]:
    alerts: list[TendencyAlert] = []

    for ft in formation_tendencies:
        if ft.total_plays >= 5:
            if ft.run_rate >= TENDENCY_ALERT_THRESHOLD:
                alerts.append(TendencyAlert(
                    alert_type="formation_tendency",
                    message=(
                        f"High run tendency from {ft.grouping_key}: "
                        f"{ft.run_rate:.0%} ({ft.total_plays} plays)"
                    ),
                    severity="high" if ft.run_rate >= 0.85 else "medium",
                    grouping_key=ft.grouping_key,
                    run_rate=ft.run_rate,
                    pass_rate=ft.pass_rate,
                ))
            if ft.pass_rate >= TENDENCY_ALERT_THRESHOLD:
                alerts.append(TendencyAlert(
                    alert_type="formation_tendency",
                    message=(
                        f"High pass tendency from {ft.grouping_key}: "
                        f"{ft.pass_rate:.0%} ({ft.total_plays} plays)"
                    ),
                    severity="high" if ft.pass_rate >= 0.85 else "medium",
                    grouping_key=ft.grouping_key,
                    run_rate=ft.run_rate,
                    pass_rate=ft.pass_rate,
                ))

    mt = motion_tendencies.with_motion
    if mt.total >= 5:
        if mt.run_rate >= TENDENCY_ALERT_THRESHOLD:
            alerts.append(TendencyAlert(
                alert_type="motion_tendency",
                message=f"High run tendency after motion: {mt.run_rate:.0%}",
                severity="medium",
                grouping_key="with_motion",
                run_rate=mt.run_rate,
                pass_rate=mt.pass_rate,
            ))

    for zt in field_zone_tendencies:
        if zt.total_plays >= 5 and zt.run_rate >= TENDENCY_ALERT_THRESHOLD:
            alerts.append(TendencyAlert(
                alert_type="field_zone_tendency",
                message=f"High run tendency in {zt.grouping_key}: {zt.run_rate:.0%}",
                severity="medium",
                grouping_key=zt.grouping_key,
                run_rate=zt.run_rate,
                pass_rate=zt.pass_rate,
            ))

    return alerts
