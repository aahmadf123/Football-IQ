"""Self-scout exposure dashboard — Phase 2.

Provides tendency analysis endpoints for the coaching staff to identify
pre-snap tells and formation/motion/field-zone/personnel tendencies.
"""

import uuid
from collections import Counter, defaultdict
from typing import Annotated, Any

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
PRE_SNAP_TELL_THRESHOLD = 0.80
PRE_SNAP_TELL_HIGH_SEVERITY_THRESHOLD = 0.90
LOW_SAMPLE_THRESHOLD = 10
EVIDENCE_CLIP_LIMIT = 10
DISTANCE_BUCKET_ORDER = {"short": 0, "medium": 1, "long": 2}
MOTION_STATE_LABELS = {
    "with_motion": "with motion",
    "without_motion": "without motion",
}


# ── Schemas ───────────────────────────────────────────────────────────────────


class TendencyEntry(BaseModel):
    grouping_key: str
    total_plays: int
    run_count: int
    pass_count: int
    run_rate: float
    pass_rate: float
    evidence_clip_ids: list[str]
    low_sample: bool


class MotionTendency(BaseModel):
    total: int
    run_count: int
    pass_count: int
    run_rate: float
    pass_rate: float


class MotionTendencyResponse(BaseModel):
    with_motion: MotionTendency
    without_motion: MotionTendency


class DownDistanceTendency(BaseModel):
    down: int
    distance_bucket: str
    total_plays: int
    run_count: int
    pass_count: int
    run_rate: float
    pass_rate: float
    evidence_clip_ids: list[str]
    low_sample: bool


class ConceptFamilyEntry(BaseModel):
    formation: str
    concept_family: str
    total_plays: int
    rate: float
    evidence_clip_ids: list[str]
    low_sample: bool


class TendencyAlert(BaseModel):
    alert_type: str
    message: str
    severity: str
    grouping_key: str
    run_rate: float
    pass_rate: float


class ExposureAlert(BaseModel):
    grouping_key: str
    formation: str
    motion_state: str
    total_plays: int
    lean: str
    severity: str
    run_rate: float
    pass_rate: float
    evidence_clip_ids: list[str]
    low_sample: bool
    message: str


class SelfScoutResponse(BaseModel):
    formation_tendencies: list[TendencyEntry]
    motion_tendencies: MotionTendencyResponse
    field_zone_tendencies: list[TendencyEntry]
    personnel_tendencies: list[TendencyEntry]
    down_distance_tendencies: list[DownDistanceTendency]
    formation_concept_families: dict[str, list[ConceptFamilyEntry]]
    pre_snap_tells: list[ExposureAlert]
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
    log.info(
        "self_scout_tendencies_requested",
        video_id=str(video_id) if video_id is not None else None,
        limit=limit,
    )
    return await _run_tendency_engine(
        db=db,
        video_id=video_id,
        limit=limit,
    )


@router.get("/opponent-tendencies", response_model=SelfScoutResponse)
async def get_opponent_tendencies(
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_user)],
    opponent_video_id: uuid.UUID = Query(...),
    limit: int = Query(default=500, ge=1, le=2000),
) -> SelfScoutResponse:
    """Compute and return opponent tendency analysis for a single video."""
    log.info(
        "opponent_tendencies_requested",
        opponent_video_id=str(opponent_video_id),
        limit=limit,
    )
    return await _run_tendency_engine(db=db, video_id=opponent_video_id, limit=limit)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _run_tendency_engine(
    db: AsyncSession,
    video_id: uuid.UUID | None,
    limit: int,
) -> SelfScoutResponse:
    q = select(Clip).order_by(Clip.start_time, Clip.id).limit(limit)
    if video_id is not None:
        q = q.where(Clip.video_id == video_id)
    clip_result = await db.execute(q)
    clips = list(clip_result.scalars().all())

    clip_ids = [c.id for c in clips]
    if not clip_ids:
        return _empty_self_scout_response()

    labels_result = await db.execute(select(Label).where(Label.clip_id.in_(clip_ids)))
    all_labels = list(labels_result.scalars().all())

    labels_by_clip: dict[uuid.UUID, list[Label]] = defaultdict(list)
    for lbl in all_labels:
        if lbl.clip_id is not None:
            labels_by_clip[lbl.clip_id].append(lbl)

    formation_plays: dict[str, Counter[str]] = defaultdict(Counter)
    formation_evidence: dict[str, list[str]] = defaultdict(list)
    motion_plays: Counter[str] = Counter()
    no_motion_plays: Counter[str] = Counter()
    field_zone_plays: dict[str, Counter[str]] = defaultdict(Counter)
    field_zone_evidence: dict[str, list[str]] = defaultdict(list)
    personnel_plays: dict[str, Counter[str]] = defaultdict(Counter)
    personnel_evidence: dict[str, list[str]] = defaultdict(list)
    down_distance_plays: dict[tuple[int, str], Counter[str]] = defaultdict(Counter)
    down_distance_evidence: dict[tuple[int, str], list[str]] = defaultdict(list)
    concept_family_plays: dict[str, Counter[str]] = defaultdict(Counter)
    concept_family_evidence: dict[tuple[str, str], list[str]] = defaultdict(list)
    exposure_plays: dict[str, Counter[str]] = defaultdict(Counter)
    exposure_evidence: dict[str, list[str]] = defaultdict(list)
    exposure_meta: dict[str, tuple[str, str]] = {}

    for clip in clips:
        clip_labels = labels_by_clip.get(clip.id, [])
        play_type = _get_play_type(clip_labels)
        if play_type is None:
            continue

        clip_id = str(clip.id)
        formation = _get_formation(clip_labels)
        has_motion = _get_motion_detected(clip_labels)
        field_zone = clip.field_zone or "mid_field"
        personnel = clip.personnel_grouping or "unknown"
        down_distance_key = _get_down_distance_key(clip)
        concept_family = _get_concept_family(clip_labels)

        if formation:
            formation_plays[formation][play_type] += 1
            formation_evidence[formation].append(clip_id)

            motion_state = "with_motion" if has_motion else "without_motion"
            exposure_key = f"{formation}|{motion_state}"
            exposure_meta[exposure_key] = (formation, motion_state)
            exposure_plays[exposure_key][play_type] += 1
            exposure_evidence[exposure_key].append(clip_id)

            if concept_family is not None:
                concept_family_plays[formation][concept_family] += 1
                concept_family_evidence[(formation, concept_family)].append(clip_id)

        if has_motion:
            motion_plays[play_type] += 1
        else:
            no_motion_plays[play_type] += 1

        field_zone_plays[field_zone][play_type] += 1
        field_zone_evidence[field_zone].append(clip_id)

        personnel_plays[personnel][play_type] += 1
        personnel_evidence[personnel].append(clip_id)

        if down_distance_key is not None:
            down_distance_plays[down_distance_key][play_type] += 1
            down_distance_evidence[down_distance_key].append(clip_id)

    formation_tendencies = _build_tendencies(formation_plays, formation_evidence, min_plays=3)
    field_zone_tendencies = _build_tendencies(field_zone_plays, field_zone_evidence, min_plays=2)
    personnel_tendencies = _build_tendencies(personnel_plays, personnel_evidence, min_plays=2)
    down_distance_tendencies = _build_down_distance_tendencies(
        down_distance_plays,
        down_distance_evidence,
        min_plays=2,
    )
    formation_concept_families = _build_concept_family_distribution(
        concept_family_plays,
        concept_family_evidence,
    )
    motion_tendencies = _build_motion_tendencies(motion_plays, no_motion_plays)
    pre_snap_tells = _build_pre_snap_tells(exposure_plays, exposure_meta, exposure_evidence)
    alerts = _generate_alerts(
        formation_tendencies,
        motion_tendencies,
        field_zone_tendencies,
        personnel_tendencies,
    )

    return SelfScoutResponse(
        formation_tendencies=formation_tendencies,
        motion_tendencies=motion_tendencies,
        field_zone_tendencies=field_zone_tendencies,
        personnel_tendencies=personnel_tendencies,
        down_distance_tendencies=down_distance_tendencies,
        formation_concept_families=formation_concept_families,
        pre_snap_tells=pre_snap_tells,
        alerts=alerts,
        clip_count=len(clips),
    )


def _empty_self_scout_response() -> SelfScoutResponse:
    return SelfScoutResponse(
        formation_tendencies=[],
        motion_tendencies=MotionTendencyResponse(
            with_motion=MotionTendency(
                total=0,
                run_count=0,
                pass_count=0,
                run_rate=0,
                pass_rate=0,
            ),
            without_motion=MotionTendency(
                total=0,
                run_count=0,
                pass_count=0,
                run_rate=0,
                pass_rate=0,
            ),
        ),
        field_zone_tendencies=[],
        personnel_tendencies=[],
        down_distance_tendencies=[],
        formation_concept_families={},
        pre_snap_tells=[],
        alerts=[],
        clip_count=0,
    )


def _get_play_type(labels: list[Label]) -> str | None:
    for lbl in labels:
        lt = lbl.label_type
        lv = lbl.label_value or {}
        if lt == "play_concept":
            concept = _get_label_text(lv)
            if _contains_any_phrase(concept, ("run", "zone", "power", "counter", "draw", "sweep")):
                return "run"
            if _contains_any_phrase(concept, ("pass", "screen", "play_action", "rpo")):
                return "pass"
        if lt == "play_direction":
            return "run"
    return None


def _get_formation(labels: list[Label]) -> str | None:
    for lbl in labels:
        if lbl.label_type == "offensive_formation":
            formation = (lbl.label_value or {}).get("formation")
            if isinstance(formation, str):
                return formation
    return None


def _get_motion_detected(labels: list[Label]) -> bool:
    for lbl in labels:
        if lbl.label_type == "motion_detected":
            return bool((lbl.label_value or {}).get("detected", False))
    return False


def _get_concept_family(labels: list[Label]) -> str | None:
    for lbl in labels:
        if lbl.label_type != "play_concept":
            continue
        concept = _get_label_text(lbl.label_value or {})
        if _contains_any_phrase(concept, ("pass", "screen", "mesh", "smash", "stick", "rpo")):
            return "pass_concept"
        if _contains_any_phrase(concept, ("inside_zone", "inside zone", "duo", "split zone")):
            return "inside_zone"
        if _contains_any_phrase(
            concept,
            ("outside_zone", "outside zone", "wide zone", "stretch", "toss"),
        ):
            return "outside_zone"
        if _contains_any_phrase(concept, ("gap", "power", "counter", "trap", "wham", "dart")):
            return "gap"
    return None


def _get_label_text(label_value: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in label_value.values():
        if isinstance(value, str | int | float | bool):
            parts.append(str(value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str | int | float | bool):
                    parts.append(str(item))
    return " ".join(parts).lower().replace("_", " ")


def _contains_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    tokens = set(text.split())
    for phrase in phrases:
        normalized_phrase = phrase.lower().replace("_", " ")
        if " " in normalized_phrase:
            if normalized_phrase in text:
                return True
        elif normalized_phrase in tokens:
            return True
    return False


def _get_distance_bucket(distance: float | None) -> str | None:
    """Bucket yards-to-go into short (1-3), medium (4-6), and long (7+) bands."""
    if distance is None:
        return None
    if distance <= 3:
        return "short"
    if distance <= 6:
        return "medium"
    return "long"


def _get_down_distance_key(clip: Clip) -> tuple[int, str] | None:
    if clip.down is None or clip.down < 1 or clip.down > 4:
        return None
    distance_bucket = _get_distance_bucket(clip.distance)
    if distance_bucket is None:
        return None
    return (clip.down, distance_bucket)


def _build_tendencies(
    plays: dict[str, Counter[str]],
    evidence: dict[str, list[str]] | None = None,
    min_plays: int = 3,
) -> list[TendencyEntry]:
    results: list[TendencyEntry] = []
    for key, counts in plays.items():
        total = sum(counts.values())
        if total < min_plays:
            continue
        results.append(
            TendencyEntry(
                grouping_key=key,
                total_plays=total,
                run_count=counts.get("run", 0),
                pass_count=counts.get("pass", 0),
                run_rate=round(counts.get("run", 0) / total, 3),
                pass_rate=round(counts.get("pass", 0) / total, 3),
                evidence_clip_ids=_limit_evidence((evidence or {}).get(key, [])),
                low_sample=total < LOW_SAMPLE_THRESHOLD,
            )
        )
    return sorted(results, key=lambda r: r.total_plays, reverse=True)


def _build_motion_tendencies(
    motion_plays: Counter[str],
    no_motion_plays: Counter[str],
) -> MotionTendencyResponse:
    motion_total = sum(motion_plays.values())
    no_motion_total = sum(no_motion_plays.values())
    return MotionTendencyResponse(
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


def _build_down_distance_tendencies(
    plays: dict[tuple[int, str], Counter[str]],
    evidence: dict[tuple[int, str], list[str]],
    min_plays: int = 2,
) -> list[DownDistanceTendency]:
    results: list[DownDistanceTendency] = []
    for (down, distance_bucket), counts in plays.items():
        total = sum(counts.values())
        if total < min_plays:
            continue
        results.append(
            DownDistanceTendency(
                down=down,
                distance_bucket=distance_bucket,
                total_plays=total,
                run_count=counts.get("run", 0),
                pass_count=counts.get("pass", 0),
                run_rate=round(counts.get("run", 0) / total, 3),
                pass_rate=round(counts.get("pass", 0) / total, 3),
                evidence_clip_ids=_limit_evidence(evidence.get((down, distance_bucket), [])),
                low_sample=total < LOW_SAMPLE_THRESHOLD,
            )
        )
    return sorted(
        results,
        key=lambda r: (r.down, DISTANCE_BUCKET_ORDER.get(r.distance_bucket, 99)),
    )


def _build_concept_family_distribution(
    plays: dict[str, Counter[str]],
    evidence: dict[tuple[str, str], list[str]],
) -> dict[str, list[ConceptFamilyEntry]]:
    formation_totals = {formation: sum(counts.values()) for formation, counts in plays.items()}
    results: dict[str, list[ConceptFamilyEntry]] = {}
    for formation, _total in sorted(
        formation_totals.items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        counts = plays[formation]
        entries: list[ConceptFamilyEntry] = []
        total = sum(counts.values())
        if total == 0:
            continue
        for concept_family, count in counts.items():
            entries.append(
                ConceptFamilyEntry(
                    formation=formation,
                    concept_family=concept_family,
                    total_plays=count,
                    rate=round(count / total, 3),
                    evidence_clip_ids=_limit_evidence(
                        evidence.get((formation, concept_family), [])
                    ),
                    low_sample=count < LOW_SAMPLE_THRESHOLD,
                )
            )
        results[formation] = sorted(entries, key=lambda entry: entry.total_plays, reverse=True)
    return results


def _build_pre_snap_tells(
    plays: dict[str, Counter[str]],
    exposure_meta: dict[str, tuple[str, str]],
    evidence: dict[str, list[str]],
) -> list[ExposureAlert]:
    results: list[ExposureAlert] = []
    for key, counts in plays.items():
        total = sum(counts.values())
        if total == 0:
            continue
        run_rate = round(counts.get("run", 0) / total, 3)
        pass_rate = round(counts.get("pass", 0) / total, 3)
        if run_rate < PRE_SNAP_TELL_THRESHOLD and pass_rate < PRE_SNAP_TELL_THRESHOLD:
            continue
        formation, motion_state = exposure_meta[key]
        lean = "run" if run_rate >= PRE_SNAP_TELL_THRESHOLD else "pass"
        lean_rate = run_rate if lean == "run" else pass_rate
        results.append(
            ExposureAlert(
                grouping_key=key,
                formation=formation,
                motion_state=motion_state,
                total_plays=total,
                lean=lean,
                severity=(
                    "high" if lean_rate >= PRE_SNAP_TELL_HIGH_SEVERITY_THRESHOLD else "medium"
                ),
                run_rate=run_rate,
                pass_rate=pass_rate,
                evidence_clip_ids=_limit_evidence(evidence.get(key, [])),
                low_sample=total < LOW_SAMPLE_THRESHOLD,
                message=(
                    f"Pre-snap tell from {formation} "
                    f"{MOTION_STATE_LABELS.get(motion_state, motion_state.replace('_', ' '))}: "
                    f"{lean_rate:.0%} {lean} ({total} plays)"
                ),
            )
        )
    return sorted(results, key=lambda r: r.total_plays, reverse=True)


def _limit_evidence(clip_ids: list[str]) -> list[str]:
    return clip_ids[:EVIDENCE_CLIP_LIMIT]


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
                alerts.append(
                    TendencyAlert(
                        alert_type="formation_tendency",
                        message=(
                            f"High run tendency from {ft.grouping_key}: "
                            f"{ft.run_rate:.0%} ({ft.total_plays} plays)"
                        ),
                        severity="high" if ft.run_rate >= 0.85 else "medium",
                        grouping_key=ft.grouping_key,
                        run_rate=ft.run_rate,
                        pass_rate=ft.pass_rate,
                    )
                )
            if ft.pass_rate >= TENDENCY_ALERT_THRESHOLD:
                alerts.append(
                    TendencyAlert(
                        alert_type="formation_tendency",
                        message=(
                            f"High pass tendency from {ft.grouping_key}: "
                            f"{ft.pass_rate:.0%} ({ft.total_plays} plays)"
                        ),
                        severity="high" if ft.pass_rate >= 0.85 else "medium",
                        grouping_key=ft.grouping_key,
                        run_rate=ft.run_rate,
                        pass_rate=ft.pass_rate,
                    )
                )

    mt = motion_tendencies.with_motion
    if mt.total >= 5:
        if mt.run_rate >= TENDENCY_ALERT_THRESHOLD:
            alerts.append(
                TendencyAlert(
                    alert_type="motion_tendency",
                    message=f"High run tendency after motion: {mt.run_rate:.0%}",
                    severity="medium",
                    grouping_key="with_motion",
                    run_rate=mt.run_rate,
                    pass_rate=mt.pass_rate,
                )
            )
        if mt.pass_rate >= TENDENCY_ALERT_THRESHOLD:
            alerts.append(
                TendencyAlert(
                    alert_type="motion_tendency",
                    message=f"High pass tendency after motion: {mt.pass_rate:.0%}",
                    severity="medium",
                    grouping_key="with_motion",
                    run_rate=mt.run_rate,
                    pass_rate=mt.pass_rate,
                )
            )

    for zt in field_zone_tendencies:
        if zt.total_plays >= 5:
            if zt.run_rate >= TENDENCY_ALERT_THRESHOLD:
                alerts.append(
                    TendencyAlert(
                        alert_type="field_zone_tendency",
                        message=f"High run tendency in {zt.grouping_key}: {zt.run_rate:.0%}",
                        severity="medium",
                        grouping_key=zt.grouping_key,
                        run_rate=zt.run_rate,
                        pass_rate=zt.pass_rate,
                    )
                )
            if zt.pass_rate >= TENDENCY_ALERT_THRESHOLD:
                alerts.append(
                    TendencyAlert(
                        alert_type="field_zone_tendency",
                        message=f"High pass tendency in {zt.grouping_key}: {zt.pass_rate:.0%}",
                        severity="medium",
                        grouping_key=zt.grouping_key,
                        run_rate=zt.run_rate,
                        pass_rate=zt.pass_rate,
                    )
                )

    for pt in personnel_tendencies:
        if pt.total_plays >= 5:
            if pt.run_rate >= TENDENCY_ALERT_THRESHOLD:
                alerts.append(
                    TendencyAlert(
                        alert_type="personnel_tendency",
                        message=f"High run tendency from {pt.grouping_key}: {pt.run_rate:.0%}",
                        severity="medium",
                        grouping_key=pt.grouping_key,
                        run_rate=pt.run_rate,
                        pass_rate=pt.pass_rate,
                    )
                )
            if pt.pass_rate >= TENDENCY_ALERT_THRESHOLD:
                alerts.append(
                    TendencyAlert(
                        alert_type="personnel_tendency",
                        message=f"High pass tendency from {pt.grouping_key}: {pt.pass_rate:.0%}",
                        severity="medium",
                        grouping_key=pt.grouping_key,
                        run_rate=pt.run_rate,
                        pass_rate=pt.pass_rate,
                    )
                )

    return alerts
