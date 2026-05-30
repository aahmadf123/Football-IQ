"""Offline benchmark feature extraction over normalized BDB data (Issue #164).

Demonstrates that the normalized schema feeds the downstream offline targets:

  * Formation clustering (#139 coverage GNN input)  — offense_formation dist.
  * Pre-snap spacing / pressure (#140)              — width / depth / on-LOS.
  * Route identification (#141 counterfactual)       — route_ran distribution.
  * Coverage separation (#139 / xSep, #150)          — nearest-defender sep.
  * Kinematics sanity                                — speed / accel ranges.

Everything is deterministic, pure-Python, and computed from the field-yard
coordinate frame. These are OFFLINE benchmark features, not coach-facing metrics,
and they do not run through the model router.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from datasets.bdb.schema import NormalizedDataset, NormalizedTrackPoint

# Event names BDB uses for the snap across competition years.
_SNAP_EVENTS = {"ball_snap", "snap", "autoevent_ballsnap"}
# A player is "on the line of scrimmage" within this many yards of the LOS x.
_ON_LOS_YARDS = 1.0


def _snap_points_by_play(
    tracking: list[NormalizedTrackPoint],
) -> dict[tuple[str, str], list[NormalizedTrackPoint]]:
    """Group the at-snap frame's track points per (game_id, play_id).

    Picks the frame whose event marks the snap; falls back to the earliest
    frame_id when no snap event is present so spacing is still computable.
    """
    by_play: dict[tuple[str, str], list[NormalizedTrackPoint]] = defaultdict(list)
    for pt in tracking:
        by_play[(pt.game_id, pt.play_id)].append(pt)

    out: dict[tuple[str, str], list[NormalizedTrackPoint]] = {}
    for key, pts in by_play.items():
        snap_frames = {
            pt.frame_id
            for pt in pts
            if pt.event is not None and pt.event.lower() in _SNAP_EVENTS and pt.frame_id is not None
        }
        if snap_frames:
            target = min(snap_frames)
        else:
            frame_ids = [pt.frame_id for pt in pts if pt.frame_id is not None]
            if not frame_ids:
                continue
            target = min(frame_ids)
        out[key] = [pt for pt in pts if pt.frame_id == target]
    return out


def _los_x(snap_pts: list[NormalizedTrackPoint], fallback: float | None) -> float | None:
    for pt in snap_pts:
        if pt.is_ball and pt.x is not None:
            return pt.x
    return fallback


def formation_distribution(dataset: NormalizedDataset) -> dict[str, int]:
    counts = Counter(
        p.offense_formation for p in dataset.plays if p.offense_formation is not None
    )
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def route_distribution(dataset: NormalizedDataset) -> dict[str, int]:
    counts = Counter(
        pp.route_ran for pp in dataset.player_plays if pp.route_ran is not None
    )
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def spacing_features(dataset: NormalizedDataset) -> dict[str, Any]:
    """Per-play offensive spacing at the snap, aggregated to means.

    width  = lateral (y) spread of offensive players
    depth  = downfield (x) spread of offensive players
    on_los = offensive players within ``_ON_LOS_YARDS`` of the LOS x
    """
    los_by_play = {(p.game_id, p.play_id): p.los_absolute_yard for p in dataset.plays}
    snap_pts = _snap_points_by_play(dataset.tracking)

    widths: list[float] = []
    depths: list[float] = []
    on_los_counts: list[int] = []
    plays_measured = 0

    for key, pts in snap_pts.items():
        offense = [pt for pt in pts if pt.side == "offense" and pt.x is not None and pt.y is not None]
        if len(offense) < 2:
            continue
        plays_measured += 1
        ys = [pt.y for pt in offense if pt.y is not None]
        xs = [pt.x for pt in offense if pt.x is not None]
        widths.append(max(ys) - min(ys))
        depths.append(max(xs) - min(xs))
        los = _los_x(pts, los_by_play.get(key))
        if los is not None:
            on_los_counts.append(
                sum(1 for pt in offense if pt.x is not None and abs(pt.x - los) <= _ON_LOS_YARDS)
            )

    return {
        "plays_measured": plays_measured,
        "mean_width_yards": round(_mean(widths), 3),
        "mean_depth_yards": round(_mean(depths), 3),
        "mean_offensive_players_on_los": round(_mean([float(c) for c in on_los_counts]), 3),
    }


def coverage_separation(dataset: NormalizedDataset) -> dict[str, Any]:
    """Nearest-defender separation per offensive player at snap (xSep analogue).

    A coverage / separation primitive for #139 and #150: for each offensive
    player at the snap, the distance to the closest defender. Aggregated to a
    mean and a min across the dataset.
    """
    snap_pts = _snap_points_by_play(dataset.tracking)
    separations: list[float] = []

    for pts in snap_pts.values():
        offense = [
            pt for pt in pts if pt.side == "offense" and pt.x is not None and pt.y is not None
        ]
        defense = [
            pt for pt in pts if pt.side == "defense" and pt.x is not None and pt.y is not None
        ]
        if not offense or not defense:
            continue
        for off in offense:
            nearest = min(
                math.dist((off.x, off.y), (d.x, d.y))  # type: ignore[arg-type]
                for d in defense
            )
            separations.append(nearest)

    return {
        "matchups_measured": len(separations),
        "mean_nearest_defender_yards": round(_mean(separations), 3),
        "min_nearest_defender_yards": round(min(separations), 3) if separations else 0.0,
    }


def kinematics_summary(dataset: NormalizedDataset) -> dict[str, Any]:
    speeds = [pt.s for pt in dataset.tracking if pt.s is not None]
    accels = [pt.a for pt in dataset.tracking if pt.a is not None]
    return {
        "frames": len(dataset.tracking),
        "max_speed_yps": round(max(speeds), 3) if speeds else 0.0,
        "mean_speed_yps": round(_mean(speeds), 3),
        "max_accel_ypss": round(max(accels), 3) if accels else 0.0,
    }


def build_report(dataset: NormalizedDataset, provenance_dict: dict[str, Any]) -> dict[str, Any]:
    """Assemble the full offline benchmark report (JSON-serializable)."""
    return {
        "usage": provenance_dict.get("usage"),
        "competition": provenance_dict.get("competition"),
        "season": provenance_dict.get("season"),
        "schema_version": provenance_dict.get("schema_version"),
        "record_counts": dataset.record_counts(),
        "formation_distribution": formation_distribution(dataset),
        "route_distribution": route_distribution(dataset),
        "spacing": spacing_features(dataset),
        "coverage_separation": coverage_separation(dataset),
        "kinematics": kinematics_summary(dataset),
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render the benchmark report as a small Markdown document."""
    lines: list[str] = []
    lines.append("# NFL Big Data Bowl — offline benchmark report")
    lines.append("")
    lines.append(f"> **Usage:** `{report.get('usage')}` — NOT production, NOT Toledo film.")
    lines.append("")
    lines.append(f"- Competition: `{report.get('competition')}`")
    lines.append(f"- Season: `{report.get('season')}`")
    lines.append(f"- Schema version: `{report.get('schema_version')}`")
    lines.append("")
    lines.append("## Record counts")
    lines.append("")
    for name, count in report["record_counts"].items():
        lines.append(f"- `{name}`: {count}")
    lines.append("")
    lines.append("## Offense formation distribution (#139 input)")
    lines.append("")
    fd = report["formation_distribution"]
    if fd:
        for formation, count in fd.items():
            lines.append(f"- `{formation}`: {count}")
    else:
        lines.append("- (no formation labels present)")
    lines.append("")
    lines.append("## Route distribution (#141 input)")
    lines.append("")
    rd = report["route_distribution"]
    if rd:
        for route, count in rd.items():
            lines.append(f"- `{route}`: {count}")
    else:
        lines.append("- (no route labels present)")
    lines.append("")
    lines.append("## Pre-snap spacing (#140 input)")
    lines.append("")
    for key, value in report["spacing"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Coverage separation — xSep analogue (#139 / #150 input)")
    lines.append("")
    for key, value in report["coverage_separation"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Kinematics sanity")
    lines.append("")
    for key, value in report["kinematics"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    return "\n".join(lines)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
