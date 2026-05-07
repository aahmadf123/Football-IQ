"""Stage 8 — Football Labels.

Produces formation/coverage/route labels for each clip using rule-based
heuristics on the tracking data.

Labels written:
  - offensive_formation — shotgun / under_center / pistol / trips / empty
  - defensive_front     — 4-3 / 3-4 / 5-2 / nickel / dime / quarters
  - defensive_shell     — cover0 / cover1 / cover2 / cover3 / cover4 / man
  - motion_detected     — boolean
  - blitz_candidate     — boolean
  - play_direction      — left / right (normalized for downstream vector math)

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

    # ── Offensive formation ───────────────────────────────────────────────
    off_formation, off_conf = _classify_offensive_formation(snap_positions)
    labels.append({
        "label_type": "offensive_formation",
        "label_value": {"formation": off_formation, "confidence": off_conf},
    })

    # ── Defensive front ───────────────────────────────────────────────────
    def_front, def_conf = _classify_defensive_front(snap_positions)
    labels.append({
        "label_type": "defensive_front",
        "label_value": {"front": def_front, "confidence": def_conf},
    })

    # ── Motion detection ──────────────────────────────────────────────────
    motion_events = [e for e in events if e.get("event_type") == "motion_start"]
    labels.append({
        "label_type": "motion_detected",
        "label_value": {"detected": len(motion_events) > 0, "count": len(motion_events)},
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
    """Very simple heuristic: count players near the line of scrimmage."""
    if not positions:
        return ("unknown", 0.3)
    # Assume LOS is somewhere near median x
    xs = sorted(p[0] for p in positions)
    los = xs[len(xs) // 2]
    near_los = sum(1 for x, _ in positions if abs(x - los) < 3)
    if near_los >= 5:
        return ("under_center", 0.6)
    elif near_los <= 2:
        return ("empty", 0.65)
    return ("shotgun", 0.6)


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
    if near_los >= 4:
        return ("4-3", 0.6)
    elif near_los == 3:
        return ("3-4", 0.6)
    return ("nickel", 0.55)


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
