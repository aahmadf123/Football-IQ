"""Stage 8 — Football Labels (Phase 2 enhanced).

Produces formation/coverage/route labels for each clip using rule-based
heuristics on the tracking data.

Phase 1 labels:
  - offensive_formation — shotgun / under_center / pistol / trips / empty
  - defensive_front     — 4-3 / 3-4 / 5-2 / nickel / dime / quarters
  - motion_detected     — boolean
  - blitz_candidate     — boolean
  - play_direction      — left / right

Phase 2 additions:
  - shift_detected      — pre-snap shift (distinct from motion)
  - motion_type         — jet / orbit / fly / trade / return
  - personnel_grouping  — 11 / 12 / 21 / 22 / 13 / 10 / 00 (RB count + TE count)
  - formation_strength  — boundary / field / balanced
  - formation_family    — expanded: spread / pro / i_form / singleback / jumbo / ...

All labels are tagged source="model" with a confidence value.
Manual corrections go through the Corrections API and are later exported as Labels.

Output: `labels` rows written to the backend.
"""

from __future__ import annotations

from typing import Any

import structlog

from pipeline import backend

log = structlog.get_logger(__name__)


def run(
    clip_id: str,
    tracklets: list[dict[str, Any]],
    events: list[dict[str, Any]],
    fps: float,
) -> dict[str, Any]:
    """Generate formation and coverage labels for a clip."""
    log.info("stage_labels_start", clip_id=clip_id)

    snap_event = next((e for e in events if e.get("event_type") == "snap"), None)
    snap_frame = snap_event.get("frame_number", 0) if snap_event else 0

    # Build snap-frame centroid list
    snap_positions = _positions_at_frame(tracklets, snap_frame)

    labels: list[dict[str, Any]] = []

    # ── Offensive formation (enhanced) ────────────────────────────────────
    off_formation, off_conf = _classify_offensive_formation(snap_positions)
    labels.append({
        "label_type": "offensive_formation",
        "label_value": {"formation": off_formation, "confidence": off_conf},
    })

    # ── Formation family (Phase 2) ────────────────────────────────────────
    family, family_conf = _classify_formation_family(snap_positions)
    labels.append({
        "label_type": "formation_family",
        "label_value": {"family": family, "confidence": family_conf},
    })

    # ── Formation strength (Phase 2) ──────────────────────────────────────
    strength = _classify_formation_strength(snap_positions)
    labels.append({
        "label_type": "formation_strength",
        "label_value": {"strength": strength},
    })

    # ── Personnel grouping (Phase 2) ──────────────────────────────────────
    personnel, pers_conf = _infer_personnel_grouping(snap_positions, tracklets)
    labels.append({
        "label_type": "personnel_grouping",
        "label_value": {"grouping": personnel, "confidence": pers_conf},
    })

    # ── Defensive front ───────────────────────────────────────────────────
    def_front, def_conf = _classify_defensive_front(snap_positions)
    labels.append({
        "label_type": "defensive_front",
        "label_value": {"front": def_front, "confidence": def_conf},
    })

    # ── Motion detection (enhanced with type) ─────────────────────────────
    motion_events = [e for e in events if e.get("event_type") == "motion_start"]
    motion_type = _classify_motion_type(motion_events, tracklets, snap_frame, fps)
    labels.append({
        "label_type": "motion_detected",
        "label_value": {
            "detected": len(motion_events) > 0,
            "count": len(motion_events),
            "motion_type": motion_type,
        },
    })

    # ── Shift detection (Phase 2) ─────────────────────────────────────────
    shift_detected, shift_conf = _detect_shift(tracklets, events, snap_frame, fps)
    labels.append({
        "label_type": "shift_detected",
        "label_value": {"detected": shift_detected, "confidence": shift_conf},
    })

    # ── Blitz candidate ───────────────────────────────────────────────────
    blitz, blitz_conf = _detect_blitz(snap_positions, tracklets, snap_frame, fps)
    labels.append({
        "label_type": "blitz_candidate",
        "label_value": {"detected": blitz, "confidence": blitz_conf},
    })

    # ── Play direction ────────────────────────────────────────────────────
    direction = _infer_play_direction(tracklets, snap_frame)
    labels.append({
        "label_type": "play_direction",
        "label_value": {"direction": direction},
    })

    # Write labels to backend
    label_ids: list[str] = []
    for lbl in labels:
        try:
            resp = backend.create_label(
                lbl["label_type"],
                lbl["label_value"],
                clip_id=clip_id,
                source="model",
            )
            label_ids.append(resp["id"])
        except Exception as exc:
            log.warning("label_write_failed", label_type=lbl.get("label_type"), error=str(exc))

    log.info("stage_labels_done", clip_id=clip_id, label_count=len(label_ids))
    return {"label_count": len(label_ids), "label_ids": label_ids}


# ── Heuristic classifiers ─────────────────────────────────────────────────────


def _positions_at_frame(
    tracklets: list[dict[str, Any]], frame: int
) -> list[tuple[float, float]]:
    """Return (field_x, field_y) for every tracklet active at `frame`."""
    positions: list[tuple[float, float]] = []
    for t in tracklets:
        for pt in t.get("track_points", []):
            if pt.get("frame_number") == frame:
                fx = pt.get("field_x")
                fy = pt.get("field_y")
                if fx is not None and fy is not None:
                    positions.append((float(fx), float(fy)))
                break
    return positions


def _classify_offensive_formation(
    positions: list[tuple[float, float]],
) -> tuple[str, float]:
    """Classify offensive formation based on player alignment at snap."""
    if not positions:
        return ("unknown", 0.3)

    xs = sorted(p[0] for p in positions)
    los = xs[len(xs) // 2]

    near_los = sum(1 for x, _ in positions if abs(x - los) < 3)
    backfield = [p for p in positions if p[0] < los - 3]
    wide_left = sum(1 for _, y in positions if y < -10)
    wide_right = sum(1 for _, y in positions if y > 10)

    # Check for trips (3 receivers to one side)
    if wide_left >= 3 or wide_right >= 3:
        return ("trips", 0.65)

    # Check for empty (no backs, all receivers spread)
    if len(backfield) == 0 and (wide_left + wide_right) >= 4:
        return ("empty", 0.65)

    # Check for pistol (QB behind center, RB directly behind QB)
    if len(backfield) == 2:
        back_ys = [abs(b[1]) for b in backfield]
        if all(y < 3.0 for y in back_ys):
            return ("pistol", 0.6)

    # Under center vs shotgun
    if near_los >= 5 and len(backfield) >= 1:
        qb_depth = max(abs(b[0] - los) for b in backfield) if backfield else 0
        if qb_depth < 2.0:
            return ("under_center", 0.6)

    if len(backfield) >= 1:
        return ("shotgun", 0.6)

    return ("shotgun", 0.55)


def _classify_formation_family(
    positions: list[tuple[float, float]],
) -> tuple[str, float]:
    """Classify into broader formation family."""
    if not positions:
        return ("unknown", 0.3)

    xs = sorted(p[0] for p in positions)
    los = xs[len(xs) // 2]
    backfield = [p for p in positions if p[0] < los - 3]
    wide_players = sum(1 for _, y in positions if abs(y) > 10)

    if wide_players >= 4:
        return ("spread", 0.6)
    if len(backfield) >= 2:
        back_ys = sorted(b[1] for b in backfield)
        if len(back_ys) >= 2 and abs(back_ys[0] - back_ys[-1]) < 3:
            return ("i_form", 0.55)
    if wide_players >= 2 and len(backfield) >= 1:
        return ("pro", 0.55)
    if wide_players <= 1 and len(backfield) >= 2:
        return ("jumbo", 0.5)

    return ("singleback", 0.5)


def _classify_formation_strength(
    positions: list[tuple[float, float]],
) -> str:
    """Classify formation strength (boundary/field/balanced)."""
    if not positions:
        return "unknown"
    left_count = sum(1 for _, y in positions if y < -3)
    right_count = sum(1 for _, y in positions if y > 3)
    if abs(left_count - right_count) <= 1:
        return "balanced"
    if left_count > right_count:
        return "left"
    return "right"


def _infer_personnel_grouping(
    positions: list[tuple[float, float]],
    tracklets: list[dict[str, Any]],
) -> tuple[str, float]:
    """Infer personnel grouping (e.g. 11, 12, 21, 22)."""
    if not positions or len(positions) < 5:
        return ("unknown", 0.3)

    xs = sorted(p[0] for p in positions)
    los = xs[len(xs) // 2]

    # Count players in different zones
    backfield = sum(1 for x, _ in positions if x < los - 3)
    tight_end_zone = sum(1 for x, y in positions if abs(x - los) < 3 and abs(y) > 5)

    # Heuristic: RBs = backfield count minus QB (1)
    rb_count = max(0, backfield - 1)
    te_count = tight_end_zone

    # Sanity check: total skill should be <= 5
    rb_count = min(rb_count, 3)
    te_count = min(te_count, 3)

    grouping = f"{rb_count}{te_count}"
    return (grouping, 0.5)


def _classify_motion_type(
    motion_events: list[dict[str, Any]],
    tracklets: list[dict[str, Any]],
    snap_frame: int,
    fps: float,
) -> str | None:
    """Classify motion type: jet, orbit, fly, trade, return."""
    if not motion_events:
        return None

    for event in motion_events:
        frame = event.get("frame_number", 0)
        # Find the tracklet with the most lateral movement around motion frame
        max_lateral = 0.0
        max_speed = 0.0
        for t in tracklets:
            pts = t.get("track_points", [])
            motion_pts = [p for p in pts if abs(p.get("frame_number", 0) - frame) < fps * 0.5]
            if len(motion_pts) < 2:
                continue
            y_start = motion_pts[0].get("field_y", 0)
            y_end = motion_pts[-1].get("field_y", 0)
            lateral = abs(float(y_end or 0) - float(y_start or 0))
            dt = (motion_pts[-1].get("frame_number", 0) - motion_pts[0].get("frame_number", 0))
            speed = lateral / max(dt / max(fps, 1), 0.01)
            if lateral > max_lateral:
                max_lateral = lateral
                max_speed = speed

        # Classify based on speed and distance
        if max_speed > 6.0 and max_lateral > 10.0:
            return "jet"
        if max_lateral > 15.0:
            return "orbit"
        if max_speed > 4.0:
            return "fly"
        if max_lateral > 5.0:
            return "trade"

    return "motion"


def _detect_shift(
    tracklets: list[dict[str, Any]],
    events: list[dict[str, Any]],
    snap_frame: int,
    fps: float,
) -> tuple[bool, float]:
    """Detect pre-snap shift (multiple players moving simultaneously before snap)."""
    # Look at the window 1-3 seconds before snap
    window_start = max(0, snap_frame - int(fps * 3))
    window_end = snap_frame - int(fps * 0.5)

    if window_end <= window_start:
        return (False, 0.3)

    movers = 0
    for t in tracklets:
        pts = t.get("track_points", [])
        window_pts = [
            p for p in pts
            if window_start <= p.get("frame_number", 0) <= window_end
        ]
        if len(window_pts) < 2:
            continue
        start_y = window_pts[0].get("field_y", 0)
        end_y = window_pts[-1].get("field_y", 0)
        if abs(float(end_y or 0) - float(start_y or 0)) > 3.0:
            movers += 1

    # Shift = 2+ players moving simultaneously (motion = just 1)
    if movers >= 2:
        return (True, min(0.8, 0.4 + movers * 0.1))

    return (False, 0.4)


def _classify_defensive_front(
    positions: list[tuple[float, float]],
) -> tuple[str, float]:
    """Heuristic: count defenders near LOS vs. in secondary."""
    if len(positions) < 6:
        return ("unknown", 0.3)
    xs = sorted(p[0] for p in positions)
    los = xs[len(xs) // 2]
    # Defenders should be on the far side of LOS
    near_los = sum(1 for x, _ in positions if 1 < abs(x - los) < 5)
    box_players = sum(1 for x, y in positions if 1 < abs(x - los) < 7 and abs(y) < 12)

    if near_los >= 5:
        return ("5-2", 0.55)
    if near_los >= 4:
        return ("4-3", 0.6)
    elif near_los == 3:
        return ("3-4", 0.6)
    if box_players >= 6:
        return ("dime", 0.5)
    if box_players >= 5:
        return ("nickel", 0.55)
    return ("quarters", 0.5)


def _detect_blitz(
    snap_positions: list[tuple[float, float]],
    tracklets: list[dict[str, Any]],
    snap_frame: int,
    fps: float,
) -> tuple[bool, float]:
    """Detect blitz: defender(s) crossing LOS within ~0.5 s of snap."""
    if not snap_positions:
        return (False, 0.3)
    xs = sorted(p[0] for p in snap_positions)
    los = xs[len(xs) // 2]
    post_snap_frame = snap_frame + int(fps * 0.5)

    crossings = 0
    for t in tracklets:
        pts = {pt["frame_number"]: pt for pt in t.get("track_points", [])}
        snap_pt = pts.get(snap_frame)
        post_pt = pts.get(post_snap_frame)
        if snap_pt and post_pt:
            sx = snap_pt.get("field_x") or 0
            px = post_pt.get("field_x") or 0
            if abs(sx - los) < 6 and abs(px - los) < 2:
                crossings += 1

    return (crossings >= 2, min(0.9, 0.4 + crossings * 0.15))


def _infer_play_direction(
    tracklets: list[dict[str, Any]], snap_frame: int
) -> str:
    """Infer whether the offensive team is moving left→right or right→left."""
    deltas: list[float] = []
    for t in tracklets:
        pts = sorted(t.get("track_points", []), key=lambda p: p.get("frame_number", 0))
        if len(pts) >= 2:
            x_start = pts[0].get("field_x") or 0
            x_end = pts[-1].get("field_x") or 0
            deltas.append(x_end - x_start)
    if not deltas:
        return "unknown"
    mean_delta = sum(deltas) / len(deltas)
    return "right" if mean_delta > 0 else "left"
