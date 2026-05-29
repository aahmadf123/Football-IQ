"""Trajectory-prior re-ID (Issue #131).

When jersey OCR fails (small crop, occlusion, motion blur) we can still
recover identity from *physics + roster priors* on a single camera:

  * **Constant-velocity prediction** — extrapolate where each already-known
    player should be now from their last confirmed tracklet
    (``position + velocity · dt``).
  * **Roster position prior** — a WR is rarely in the OL gap; an OL is rarely
    30 yd downfield. Incompatible position groups are penalised.
  * **Team-membership constraint** — offense/defense from the k=3 team
    classifier (Issue #130) is a hard gate: an offense tracklet never matches
    a defense player.

These combine into a cost matrix solved with the Hungarian algorithm
(implemented here in pure NumPy — ``scipy`` is not a worker dependency). The
output is purely ``{track_index: player_id}`` assignments that the caller
turns into existing ``player_id`` PATCHes; **no new tracklet schema** and no
cross-camera reasoning (single-camera, Issue #101).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import structlog

log = structlog.get_logger(__name__)

# Cost added when two position groups are incompatible (e.g. WR vs OL). Soft —
# it discourages but does not forbid, since group estimates are noisy.
POSITION_GROUP_PENALTY = 0.75
# Cost that effectively forbids an assignment (team mismatch / over-gate).
FORBIDDEN_COST = 1.0e6
# Tracklets farther than this (normalised) from a predicted player position are
# left unassigned rather than forced onto the nearest leftover player.
MAX_ASSIGN_COST = 0.6

# Coarse offense/defense grouping used only to score position-group affinity.
_OFFENSE_GROUPS = {"QB", "RB", "WR", "TE", "OL"}
_DEFENSE_GROUPS = {"DL", "LB", "DB", "CB", "S"}


@dataclass
class KnownPlayer:
    """A previously-identified player with a predictable trajectory.

    ``last_frame`` anchors the constant-velocity prediction so the per-pair
    time delta to an unknown track is computed from absolute frame numbers.
    """

    player_id: str
    position: tuple[float, float]
    velocity: tuple[float, float] = (0.0, 0.0)
    last_frame: int = 0
    team: str | None = None
    position_group: str | None = None

    def predict(self, dt: float) -> tuple[float, float]:
        return (
            self.position[0] + self.velocity[0] * dt,
            self.position[1] + self.velocity[1] * dt,
        )


@dataclass
class UnknownTrack:
    """A tracklet that OCR could not identify."""

    index: int
    position: tuple[float, float]
    frame: int = 0
    team: str | None = None
    position_group: str | None = None


def _group_penalty(a: str | None, b: str | None) -> float:
    if a is None or b is None or a == b:
        return 0.0
    same_side = (a in _OFFENSE_GROUPS and b in _OFFENSE_GROUPS) or (
        a in _DEFENSE_GROUPS and b in _DEFENSE_GROUPS
    )
    return 0.0 if same_side else POSITION_GROUP_PENALTY


def hungarian(cost: np.ndarray) -> list[tuple[int, int]]:
    """Minimum-cost assignment for a rectangular cost matrix (pure NumPy).

    Implements the O(n³) Kuhn–Munkres algorithm on a square-padded copy and
    returns ``(row, col)`` pairs that fall within the original shape.
    """
    cost = np.asarray(cost, dtype=np.float64)
    if cost.size == 0:
        return []
    n_rows, n_cols = cost.shape
    n = max(n_rows, n_cols)
    pad = np.full((n, n), 0.0, dtype=np.float64)
    fill = float(cost.max()) + 1.0 if cost.size else 0.0
    pad[:] = fill
    pad[:n_rows, :n_cols] = cost

    u = np.zeros(n + 1)
    v = np.zeros(n + 1)
    p = np.zeros(n + 1, dtype=int)
    way = np.zeros(n + 1, dtype=int)
    INF = float("inf")
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = np.full(n + 1, INF)
        used = np.zeros(n + 1, dtype=bool)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = -1
            for j in range(1, n + 1):
                if not used[j]:
                    cur = pad[i0 - 1, j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break

    pairs: list[tuple[int, int]] = []
    for j in range(1, n + 1):
        i = p[j]
        if 1 <= i <= n_rows and 1 <= j <= n_cols:
            pairs.append((i - 1, j - 1))
    return pairs


class TrajectoryPriorReID:
    """Assign OCR-missing tracklets to known players via physics + priors.

    Args:
        position_scale: divides Euclidean distance (in the same units as the
            supplied positions — image px or field yards) so the motion term
            lands in roughly ``[0, 1]`` for plausible matches.
        max_assign_cost: gate above which a tracklet is left unassigned.
    """

    def __init__(
        self,
        position_scale: float = 300.0,
        max_assign_cost: float = MAX_ASSIGN_COST,
    ) -> None:
        self.position_scale = max(1e-6, position_scale)
        self.max_assign_cost = max_assign_cost

    def _cost(self, track: UnknownTrack, player: KnownPlayer) -> float:
        if track.team is not None and player.team is not None and track.team != player.team:
            return FORBIDDEN_COST
        dt = max(0.0, float(track.frame - player.last_frame))
        px, py = player.predict(dt)
        dist = float(np.hypot(track.position[0] - px, track.position[1] - py))
        motion = dist / self.position_scale
        return motion + _group_penalty(track.position_group, player.position_group)

    def assign(
        self,
        tracks: list[UnknownTrack],
        players: list[KnownPlayer],
    ) -> dict[int, str]:
        """Return ``{track.index: player_id}`` for confident matches only."""
        if not tracks or not players:
            return {}
        cost = np.array(
            [[self._cost(t, p) for p in players] for t in tracks],
            dtype=np.float64,
        )
        assignments: dict[int, str] = {}
        for r, c in hungarian(cost):
            if cost[r, c] <= self.max_assign_cost:
                assignments[tracks[r].index] = players[c].player_id
        log.info(
            "trajectory_prior_assigned",
            tracks=len(tracks),
            players=len(players),
            matched=len(assignments),
        )
        return assignments
