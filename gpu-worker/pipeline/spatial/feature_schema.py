"""Shared spatial / graph feature schema (Issues #139 + #140).

This module is the authoritative definition of the spatial features that feed
both the coverage GNN (#139) and the pre-snap pressure predictor (#140). It
turns the routed pipeline's per-frame tracking output into:

* :class:`PlayerNode` — one node per tracked player at a frame, carrying the
  seven node features named in Issue #139:
  ``field_x``, ``field_y``, ``speed``, ``depth_behind_los``,
  ``dist_to_nearest_receiver``, ``head_yaw_rad`` (from pose), ``leverage``.
* :class:`SpatialGraph` — nodes plus edges built from *spatial proximity* and
  *motion similarity* (the edge contract from Issue #139), serialisable to a
  plain dict so an offline trainer or an in-pipeline classifier can consume it
  without pulling in torch / torch-geometric.

Coordinate-frame contract (the "no clean-coordinate assumption" guardrail):
the schema operates on the **calibrated field-yard frame** (#127/#128/#129).
Callers must pass ``calibration_confirmed=True`` (the analytics-safe flag the
calibration stage emits). When calibration is not confirmed the builders raise
:class:`FieldFrameError` rather than silently treating raw pixel/uncalibrated
coordinates as field yards — a coverage/pressure number computed on
uncalibrated coordinates would be meaningless, and BDB clean coordinates are
offline-only (#164), never a substitute for confirmed calibration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# Bump when the node/edge feature layout changes. Written into every graph dict
# and checked by consumers so a stale checkpoint can be detected.
SCHEMA_VERSION = 1

# The calibrated field-yard frame produced by #127/#128/#129. The shared schema
# only operates in this frame; BDB's ``bdb_field_yards`` frame is *analogous*
# but offline-only (#164) and must be tagged as such by the caller.
FIELD_FRAME = "calibrated_field_yards"

# Canonical node-feature order (Issue #139, §5.2). Consumers index by this list,
# never by position, so a reorder here is a SCHEMA_VERSION bump.
NODE_FEATURE_NAMES: tuple[str, ...] = (
    "field_x",
    "field_y",
    "speed",
    "depth_behind_los",
    "dist_to_nearest_receiver",
    "head_yaw_rad",
    "leverage",
)

# Edge features: spatial proximity (distance + components) and motion similarity
# (cosine of the two velocity vectors). Issue #139 edge contract.
EDGE_FEATURE_NAMES: tuple[str, ...] = (
    "distance",
    "delta_x",
    "delta_y",
    "motion_cosine_similarity",
)

# Default graph-construction knobs. A defender is connected to every other
# defender within ``EDGE_RADIUS_YARDS`` *and* to its ``EDGE_MAX_DEGREE`` nearest
# neighbours, so the graph stays connected even when the front is spread out.
EDGE_RADIUS_YARDS = 10.0
EDGE_MAX_DEGREE = 4


class FieldFrameError(ValueError):
    """Raised when a spatial feature is requested without confirmed calibration."""


def require_field_frame(calibration_confirmed: bool) -> None:
    """Guard: refuse to build field-frame features on uncalibrated input.

    The coverage/pressure features are only meaningful in the calibrated
    field-yard frame (#127). This is the single chokepoint that enforces the
    "no clean-coordinate assumption unless calibration is confirmed" rule.
    """
    if not calibration_confirmed:
        raise FieldFrameError(
            "spatial features require confirmed field-frame calibration "
            "(#127/#128/#129); refusing to treat uncalibrated coordinates as "
            "field yards"
        )


# ── Player node ───────────────────────────────────────────────────────────────


@dataclass(slots=True)
class PlayerNode:
    """One player at the analysis frame, in the calibrated field-yard frame."""

    track_id: str
    field_x: float
    field_y: float
    speed: float
    depth_behind_los: float
    dist_to_nearest_receiver: float
    head_yaw_rad: float
    leverage: float
    # Provenance / routing-friendly metadata (not part of the feature vector).
    side: str | None = None  # "offense" | "defense" | None
    jersey_number: int | None = None
    position: str | None = None
    has_pose: bool = False
    velocity: tuple[float, float] = (0.0, 0.0)

    def to_vector(self) -> np.ndarray:
        """Return the node features in :data:`NODE_FEATURE_NAMES` order."""
        return np.array(
            [
                self.field_x,
                self.field_y,
                self.speed,
                self.depth_behind_los,
                self.dist_to_nearest_receiver,
                self.head_yaw_rad,
                self.leverage,
            ],
            dtype=np.float64,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "field_x": round(self.field_x, 3),
            "field_y": round(self.field_y, 3),
            "speed": round(self.speed, 3),
            "depth_behind_los": round(self.depth_behind_los, 3),
            "dist_to_nearest_receiver": round(self.dist_to_nearest_receiver, 3),
            "head_yaw_rad": round(self.head_yaw_rad, 4),
            "leverage": round(self.leverage, 4),
            "side": self.side,
            "jersey_number": self.jersey_number,
            "position": self.position,
            "has_pose": self.has_pose,
        }


# ── Spatial graph ─────────────────────────────────────────────────────────────


@dataclass(slots=True)
class SpatialGraph:
    """A player graph: node features + proximity/motion edges (Issue #139)."""

    node_ids: list[str]
    node_features: np.ndarray  # (N, len(NODE_FEATURE_NAMES))
    edge_index: np.ndarray  # (2, E) int — directed pairs (undirected → both ways)
    edge_features: np.ndarray  # (E, len(EDGE_FEATURE_NAMES))
    schema_version: int = SCHEMA_VERSION
    node_meta: list[dict[str, Any]] = field(default_factory=list)

    @property
    def num_nodes(self) -> int:
        return int(self.node_features.shape[0])

    @property
    def num_edges(self) -> int:
        return int(self.edge_index.shape[1])

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for offline artifacts / debugging."""
        return {
            "schema_version": self.schema_version,
            "field_frame": FIELD_FRAME,
            "node_feature_names": list(NODE_FEATURE_NAMES),
            "edge_feature_names": list(EDGE_FEATURE_NAMES),
            "node_ids": list(self.node_ids),
            "node_features": self.node_features.round(4).tolist(),
            "edge_index": self.edge_index.tolist(),
            "edge_features": self.edge_features.round(4).tolist(),
            "node_meta": self.node_meta,
        }


# ── Geometry helpers (shared with the existing stages' conventions) ───────────


def position_at_frame(
    tracklet: dict[str, Any], frame: int
) -> tuple[float, float] | None:
    """Field-frame ``(x, y)`` of a tracklet at ``frame`` (None if absent)."""
    for pt in tracklet.get("track_points", []):
        if pt.get("frame_number") == frame:
            fx = pt.get("field_x")
            fy = pt.get("field_y")
            if fx is not None and fy is not None:
                return (float(fx), float(fy))
    return None


def _velocity_at_frame(
    tracklet: dict[str, Any], frame: int, lookback: int
) -> tuple[float, float]:
    """Finite-difference velocity (yd/frame) over ``lookback`` frames.

    Direction is what motion-similarity edges care about; magnitude doubles as a
    cheap speed proxy when the tracklet carries no explicit ``speed`` field.
    """
    cur = position_at_frame(tracklet, frame)
    if cur is None:
        return (0.0, 0.0)
    prev: tuple[float, float] | None = None
    for back in range(1, lookback + 1):
        prev = position_at_frame(tracklet, frame - back)
        if prev is not None:
            denom = float(back)
            return ((cur[0] - prev[0]) / denom, (cur[1] - prev[1]) / denom)
    return (0.0, 0.0)


def _explicit_speed(tracklet: dict[str, Any], frame: int) -> float | None:
    """Read a per-frame ``speed`` field if the tracker supplied one (e.g. BDB)."""
    for pt in tracklet.get("track_points", []):
        if pt.get("frame_number") == frame:
            spd = pt.get("speed")
            return float(spd) if spd is not None else None
    return None


def _leverage(
    defender: tuple[float, float], receiver: tuple[float, float] | None
) -> float:
    """Signed lateral leverage vs the nearest receiver, in yards.

    Negative ⇒ inside leverage (defender nearer the middle of the field than the
    receiver), positive ⇒ outside leverage. 0 when there is no receiver to key.
    Matches the sign convention of ``stage_coverage._classify_leverage``.
    """
    if receiver is None:
        return 0.0
    return abs(defender[1]) - abs(receiver[1])


# ── Node construction ─────────────────────────────────────────────────────────


def build_player_nodes(
    tracklets: list[dict[str, Any]],
    frame: int,
    los_x: float,
    *,
    calibration_confirmed: bool,
    offense_direction: int = 1,
    receiver_positions: list[tuple[float, float]] | None = None,
    head_yaw_by_track: dict[str, float] | None = None,
    velocity_lookback: int = 3,
    side_filter: str | None = None,
) -> list[PlayerNode]:
    """Build :class:`PlayerNode` rows for every tracklet present at ``frame``.

    Args:
        tracklets: pipeline tracklets (each with ``track_points`` carrying
            ``field_x``/``field_y`` in the calibrated frame).
        frame: the analysis frame (typically the snap frame).
        los_x: line-of-scrimmage x in the field frame.
        calibration_confirmed: the calibration stage's analytics-safe flag. When
            ``False`` this raises :class:`FieldFrameError` (guardrail).
        offense_direction: +1 if the offense advances toward increasing x, else
            -1. Used so ``depth_behind_los`` has a consistent sign.
        receiver_positions: eligible-receiver field positions used for the
            ``dist_to_nearest_receiver`` and ``leverage`` features. When omitted
            both degrade to 0 with ``has_pose`` unaffected.
        head_yaw_by_track: optional ``{track_id: yaw_radians}`` from the pose
            stage (signal 5 of #139, a soft dependency).
        velocity_lookback: frames to look back for the finite-difference
            velocity used by the speed proxy and motion-similarity edges.
        side_filter: when set (``"offense"``/``"defense"``) only that side's
            tracklets become nodes — the coverage GNN keys on defenders.
    """
    require_field_frame(calibration_confirmed)
    head_yaw_by_track = head_yaw_by_track or {}

    nodes: list[PlayerNode] = []
    for t in tracklets:
        side = t.get("side_of_ball")
        if side_filter is not None and side != side_filter:
            continue
        pos = position_at_frame(t, frame)
        if pos is None:
            continue

        track_id = str(t.get("id", "unknown"))
        vx, vy = _velocity_at_frame(t, frame, velocity_lookback)
        speed = _explicit_speed(t, frame)
        if speed is None:
            speed = math.hypot(vx, vy)

        depth = offense_direction * (pos[0] - los_x)

        nearest_receiver = _nearest_point(pos, receiver_positions)
        if nearest_receiver is None:
            dist_to_rx = 0.0
            leverage = 0.0
        else:
            dist_to_rx = math.dist(pos, nearest_receiver)
            leverage = _leverage(pos, nearest_receiver)

        yaw = head_yaw_by_track.get(track_id)
        nodes.append(
            PlayerNode(
                track_id=track_id,
                field_x=pos[0],
                field_y=pos[1],
                speed=float(speed),
                depth_behind_los=float(depth),
                dist_to_nearest_receiver=float(dist_to_rx),
                head_yaw_rad=float(yaw) if yaw is not None else 0.0,
                leverage=float(leverage),
                side=side,
                jersey_number=_as_int(t.get("jersey_number")),
                position=t.get("position"),
                has_pose=yaw is not None,
                velocity=(vx, vy),
            )
        )
    return nodes


def _nearest_point(
    pos: tuple[float, float], candidates: list[tuple[float, float]] | None
) -> tuple[float, float] | None:
    if not candidates:
        return None
    return min(candidates, key=lambda c: math.dist(pos, c))


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ── Graph construction ────────────────────────────────────────────────────────


def build_spatial_graph(
    nodes: list[PlayerNode],
    *,
    radius_yards: float = EDGE_RADIUS_YARDS,
    max_degree: int = EDGE_MAX_DEGREE,
) -> SpatialGraph:
    """Connect nodes by spatial proximity + motion similarity (Issue #139).

    An undirected edge connects two nodes when they are within ``radius_yards``;
    additionally each node keeps its ``max_degree`` nearest neighbours so the
    graph never fragments into isolated nodes on a spread-out front. Edge
    features carry the distance, its components, and the cosine similarity of the
    two velocity vectors (the "motion similarity" half of the edge contract).
    """
    n = len(nodes)
    feat = (
        np.stack([node.to_vector() for node in nodes])
        if n
        else np.zeros((0, len(NODE_FEATURE_NAMES)), dtype=np.float64)
    )
    node_ids = [node.track_id for node in nodes]
    node_meta = [node.to_dict() for node in nodes]

    edges_src: list[int] = []
    edges_dst: list[int] = []
    edge_feats: list[list[float]] = []

    undirected_edges: set[tuple[int, int]] = set()
    for i in range(n):
        # Rank neighbours by distance for the k-NN fallback.
        dists = sorted(
            (
                (math.dist((nodes[i].field_x, nodes[i].field_y), (nodes[j].field_x, nodes[j].field_y)), j)
                for j in range(n)
                if j != i
            ),
            key=lambda d: d[0],
        )
        for rank, (dist, j) in enumerate(dists):
            within_radius = dist <= radius_yards
            within_knn = rank < max_degree
            if not (within_radius or within_knn):
                continue
            undirected_edges.add((min(i, j), max(i, j)))

    for i, j in sorted(undirected_edges):
        dist = math.dist((nodes[i].field_x, nodes[i].field_y), (nodes[j].field_x, nodes[j].field_y))
        dx = nodes[j].field_x - nodes[i].field_x
        dy = nodes[j].field_y - nodes[i].field_y
        cos = _motion_cosine(nodes[i].velocity, nodes[j].velocity)
        ef = [float(dist), float(dx), float(dy), float(cos)]
        edges_src += [i, j]
        edges_dst += [j, i]
        edge_feats += [ef, [ef[0], -ef[1], -ef[2], ef[3]]]

    edge_index = (
        np.array([edges_src, edges_dst], dtype=np.int64)
        if edges_src
        else np.zeros((2, 0), dtype=np.int64)
    )
    edge_features = (
        np.array(edge_feats, dtype=np.float64)
        if edge_feats
        else np.zeros((0, len(EDGE_FEATURE_NAMES)), dtype=np.float64)
    )
    return SpatialGraph(
        node_ids=node_ids,
        node_features=feat,
        edge_index=edge_index,
        edge_features=edge_features,
        node_meta=node_meta,
    )


def _motion_cosine(a: tuple[float, float], b: tuple[float, float]) -> float:
    na = math.hypot(*a)
    nb = math.hypot(*b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return (a[0] * b[0] + a[1] * b[1]) / (na * nb)


def estimate_los_x(tracklets: list[dict[str, Any]], frame: int) -> float:
    """Median field-frame x of all tracklets at ``frame`` (LOS proxy).

    Mirrors ``stage_coverage._estimate_los`` / ``stage_oline._estimate_los`` so
    every spatial consumer estimates the LOS the same way.
    """
    xs: list[float] = []
    for t in tracklets:
        pos = position_at_frame(t, frame)
        if pos is not None:
            xs.append(pos[0])
    if not xs:
        return 50.0
    xs.sort()
    return xs[len(xs) // 2]
