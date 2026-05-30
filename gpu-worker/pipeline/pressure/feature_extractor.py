"""Pre-snap pressure feature extraction (Issue #140).

Extracts, at the snap frame, the features Issue #140 §5.3 calls for:

1. **OL gap widths** between adjacent linemen.
2. **DL alignment** relative to OL gaps (A-gap / B-gap / C-gap / edge).
3. **LB depth** and distance from the LOS.
4. **Blitz indicator** — a LB within 2 yd of the LOS.
5. **Down-and-distance**.

All geometry is in the calibrated field-yard frame and routes through the shared
field-frame guard (``pipeline.spatial.feature_schema.require_field_frame``), so
the extractor refuses to operate on uncalibrated coordinates — the "no
clean-coordinate assumption" guardrail. Missing inputs degrade a feature's
confidence rather than fabricating a value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from pipeline.spatial import feature_schema as fs

# Canonical feature order consumed by the classifier (index by name, not pos).
PRESSURE_FEATURE_NAMES: tuple[str, ...] = (
    "mean_gap_width",
    "max_gap_width",
    "dl_count",
    "box_count",
    "rusher_blocker_diff",
    "lb_count",
    "mean_lb_depth",
    "min_lb_depth",
    "blitzers",
    "dl_in_a_gap",
    "dl_in_b_gap",
    "dl_in_c_gap",
    "dl_on_edge",
    "down",
    "distance_yards",
)

# Alignment / box thresholds (yards), mirroring stage_oline conventions.
_OL_LOS_RANGE_YD = 2.0
_DL_DEPTH_MAX_YD = 1.5  # hand-in-dirt down-lineman is within this of the LOS
_LB_DEPTH_MIN_YD = 1.5  # off-ball box defender starts just behind the DL …
_LB_DEPTH_MAX_YD = 7.0  # … and ends in front of the deep shell
_BLITZ_DEPTH_YD = 2.0  # an off-ball LB crept within this of the LOS = blitz look
_BOX_DEPTH_YD = 5.0
_BOX_WIDTH_YD = 9.0


@dataclass(slots=True)
class PressureFeatures:
    """Snap-frame pressure features for one pass play (Issue #140)."""

    ol_gap_widths: list[float]
    mean_gap_width: float
    max_gap_width: float
    dl_count: int
    box_count: int
    ol_count: int
    rusher_blocker_diff: float
    lb_count: int
    mean_lb_depth: float
    min_lb_depth: float
    blitzers: int
    blitz_indicator: bool
    dl_gap_counts: dict[str, int]
    down: int | None
    distance_yards: float | None
    feature_confidence: float
    schema_version: int = fs.SCHEMA_VERSION

    def to_vector(self) -> np.ndarray:
        """Numeric features in :data:`PRESSURE_FEATURE_NAMES` order."""
        return np.array(
            [
                self.mean_gap_width,
                self.max_gap_width,
                float(self.dl_count),
                float(self.box_count),
                self.rusher_blocker_diff,
                float(self.lb_count),
                self.mean_lb_depth,
                self.min_lb_depth,
                float(self.blitzers),
                float(self.dl_gap_counts.get("a", 0)),
                float(self.dl_gap_counts.get("b", 0)),
                float(self.dl_gap_counts.get("c", 0)),
                float(self.dl_gap_counts.get("edge", 0)),
                float(self.down or 0),
                float(self.distance_yards if self.distance_yards is not None else 0.0),
            ],
            dtype=np.float64,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ol_gap_widths": [round(w, 2) for w in self.ol_gap_widths],
            "mean_gap_width": round(self.mean_gap_width, 2),
            "max_gap_width": round(self.max_gap_width, 2),
            "dl_count": self.dl_count,
            "box_count": self.box_count,
            "ol_count": self.ol_count,
            "rusher_blocker_diff": round(self.rusher_blocker_diff, 2),
            "lb_count": self.lb_count,
            "mean_lb_depth": round(self.mean_lb_depth, 2),
            "min_lb_depth": round(self.min_lb_depth, 2),
            "blitzers": self.blitzers,
            "blitz_indicator": self.blitz_indicator,
            "dl_gap_counts": dict(self.dl_gap_counts),
            "down": self.down,
            "distance_yards": self.distance_yards,
            "feature_confidence": round(self.feature_confidence, 3),
        }


def _side_split(
    tracklets: list[dict[str, Any]],
    snap_frame: int,
    los_x: float,
    offense_direction: int,
) -> tuple[list[tuple[str, tuple[float, float]]], list[tuple[str, tuple[float, float]]]]:
    """Split tracklets into (offense, defense) snap-frame positions."""
    offense: list[tuple[str, tuple[float, float]]] = []
    defense: list[tuple[str, tuple[float, float]]] = []
    for t in tracklets:
        pos = fs.position_at_frame(t, snap_frame)
        if pos is None:
            continue
        tid = str(t.get("id", "unknown"))
        side = t.get("side_of_ball")
        if side == "offense":
            offense.append((tid, pos))
        elif side == "defense":
            defense.append((tid, pos))
        else:
            # depth relative to the offense's direction of travel: offense is
            # behind the LOS (depth <= 0), defense is ahead of it.
            depth = offense_direction * (pos[0] - los_x)
            (offense if depth <= 0 else defense).append((tid, pos))
    return offense, defense


def _identify_ol(
    offense: list[tuple[str, tuple[float, float]]], los_x: float
) -> list[tuple[float, float]]:
    """The 5 offensive players closest to the LOS and the ball laterally."""
    near = [
        pos
        for _, pos in offense
        if abs(pos[0] - los_x) <= _OL_LOS_RANGE_YD and abs(pos[1]) < 10.0
    ]
    near.sort(key=lambda p: abs(p[1]))
    ol = near[:5]
    ol.sort(key=lambda p: p[1])  # left → right for gap geometry
    return ol


def _classify_dl_gaps(
    defense: list[tuple[str, tuple[float, float]]],
    ol: list[tuple[float, float]],
    los_x: float,
    offense_direction: int,
) -> tuple[dict[str, int], int]:
    """Count down-linemen by the gap they align in. Returns (counts, dl_count)."""
    counts = {"a": 0, "b": 0, "c": 0, "edge": 0}
    if not ol:
        return counts, 0
    ol_ys = sorted(p[1] for p in ol)
    center_y = ol_ys[len(ol_ys) // 2]
    outer_left, outer_right = ol_ys[0], ol_ys[-1]
    # Gap midpoints between adjacent OL, tagged by distance from center.
    gaps = [(0.5 * (ol_ys[i] + ol_ys[i + 1])) for i in range(len(ol_ys) - 1)]

    dl_count = 0
    for _, pos in defense:
        depth = offense_direction * (pos[0] - los_x)
        if depth > _DL_DEPTH_MAX_YD or depth < -1.0:
            continue  # not a down-lineman
        dl_count += 1
        y = pos[1]
        if y < outer_left - 0.5 or y > outer_right + 0.5:
            counts["edge"] += 1
            continue
        # Nearest interior gap → A (touching center) / B (next) by rank.
        nearest_gap = min(range(len(gaps)), key=lambda g: abs(gaps[g] - y)) if gaps else None
        if nearest_gap is None:
            counts["edge"] += 1
            continue
        gap_rank = abs(gaps[nearest_gap] - center_y)
        if gap_rank <= 2.0:
            counts["a"] += 1
        elif gap_rank <= 5.0:
            counts["b"] += 1
        else:
            counts["c"] += 1
    return counts, dl_count


def extract_pressure_features(
    tracklets: list[dict[str, Any]],
    snap_frame: int,
    los_x: float,
    *,
    calibration_confirmed: bool,
    offense_direction: int = 1,
    down: int | None = None,
    distance_yards: float | None = None,
) -> PressureFeatures:
    """Build the snap-frame pressure feature set (Issue #140)."""
    fs.require_field_frame(calibration_confirmed)

    offense, defense = _side_split(tracklets, snap_frame, los_x, offense_direction)
    ol = _identify_ol(offense, los_x)

    # OL gap widths (lateral spacing between adjacent linemen).
    gap_widths = [abs(ol[i + 1][1] - ol[i][1]) for i in range(len(ol) - 1)]
    mean_gap = float(np.mean(gap_widths)) if gap_widths else 0.0
    max_gap = float(np.max(gap_widths)) if gap_widths else 0.0

    dl_gap_counts, dl_count = _classify_dl_gaps(defense, ol, los_x, offense_direction)

    # Linebackers: defenders behind the DL but in front of the deep shell.
    lb_depths: list[float] = []
    box_count = 0
    for _, pos in defense:
        depth = offense_direction * (pos[0] - los_x)
        if 0.0 <= depth <= _BOX_DEPTH_YD and abs(pos[1]) <= _BOX_WIDTH_YD:
            box_count += 1
        if _LB_DEPTH_MIN_YD <= depth <= _LB_DEPTH_MAX_YD and abs(pos[1]) <= _BOX_WIDTH_YD:
            lb_depths.append(depth)

    # Blitz indicator: a linebacker that has crept inside the blitz depth.
    blitzers = sum(1 for d in lb_depths if d <= _BLITZ_DEPTH_YD)
    lb_count = len(lb_depths)
    mean_lb_depth = float(np.mean(lb_depths)) if lb_depths else 0.0
    min_lb_depth = float(np.min(lb_depths)) if lb_depths else 0.0

    # Pressure differential: potential rushers (DL + creeping LBs) vs blockers.
    rushers = dl_count + blitzers
    rusher_blocker_diff = float(rushers - len(ol))

    # Confidence degrades when the OL/DL fronts are not cleanly recovered.
    feature_confidence = 0.6
    if len(ol) < 5:
        feature_confidence -= 0.15
    if dl_count == 0:
        feature_confidence -= 0.2
    if down is None or distance_yards is None:
        feature_confidence -= 0.1
    feature_confidence = max(feature_confidence, 0.1)

    return PressureFeatures(
        ol_gap_widths=gap_widths,
        mean_gap_width=mean_gap,
        max_gap_width=max_gap,
        dl_count=dl_count,
        box_count=box_count,
        ol_count=len(ol),
        rusher_blocker_diff=rusher_blocker_diff,
        lb_count=lb_count,
        mean_lb_depth=mean_lb_depth,
        min_lb_depth=min_lb_depth,
        blitzers=blitzers,
        blitz_indicator=blitzers > 0,
        dl_gap_counts=dl_gap_counts,
        down=down,
        distance_yards=distance_yards,
        feature_confidence=feature_confidence,
    )
