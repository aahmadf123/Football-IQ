"""Tests for the shared spatial / graph feature schema (Issues #139 / #140)."""

from __future__ import annotations

import math
import os
import sys
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.spatial import feature_schema as fs


def _track(
    tid: str,
    points: list[tuple[int, float, float]],
    *,
    side: str | None = None,
    jersey: int | None = None,
    position: str | None = None,
) -> dict[str, Any]:
    return {
        "id": tid,
        "side_of_ball": side,
        "jersey_number": jersey,
        "position": position,
        "track_points": [
            {"frame_number": f, "field_x": x, "field_y": y} for f, x, y in points
        ],
    }


def test_node_feature_vector_order_matches_schema() -> None:
    node = fs.PlayerNode(
        track_id="d1",
        field_x=62.0,
        field_y=4.0,
        speed=1.5,
        depth_behind_los=12.0,
        dist_to_nearest_receiver=6.0,
        head_yaw_rad=0.3,
        leverage=-1.0,
    )
    vec = node.to_vector()
    assert vec.shape == (len(fs.NODE_FEATURE_NAMES),)
    assert list(vec) == [62.0, 4.0, 1.5, 12.0, 6.0, 0.3, -1.0]


def test_field_frame_guard_blocks_uncalibrated() -> None:
    with pytest.raises(fs.FieldFrameError):
        fs.build_player_nodes([], 0, 50.0, calibration_confirmed=False)
    # require_field_frame is the single chokepoint.
    with pytest.raises(fs.FieldFrameError):
        fs.require_field_frame(False)
    fs.require_field_frame(True)  # does not raise


def test_build_player_nodes_computes_depth_leverage_and_speed() -> None:
    # Defender 12 yd downfield of the LOS, moving, with a receiver inside of it.
    defender = _track(
        "d1",
        [(8, 60.0, 6.0), (9, 61.0, 6.0), (10, 62.0, 6.0)],
        side="defense",
    )
    receivers = [(50.0, 10.0)]  # receiver further outside (larger |y|)
    nodes = fs.build_player_nodes(
        [defender],
        frame=10,
        los_x=50.0,
        calibration_confirmed=True,
        offense_direction=1,
        receiver_positions=receivers,
    )
    assert len(nodes) == 1
    node = nodes[0]
    assert node.depth_behind_los == pytest.approx(12.0)
    # nearest receiver distance = hypot(62-50, 6-10) = hypot(12, 4)
    assert node.dist_to_nearest_receiver == pytest.approx(math.hypot(12.0, 4.0))
    # leverage = |defender_y| - |receiver_y| = 6 - 10 = -4 (inside leverage)
    assert node.leverage == pytest.approx(-4.0)
    # finite-difference speed from (61,6)->(62,6) ≈ 1 yd/frame
    assert node.speed == pytest.approx(1.0, abs=1e-6)
    assert node.has_pose is False


def test_side_filter_and_pose_yaw() -> None:
    d = _track("d1", [(10, 62.0, 0.0)], side="defense")
    o = _track("o1", [(10, 45.0, 0.0)], side="offense")
    nodes = fs.build_player_nodes(
        [d, o],
        frame=10,
        los_x=50.0,
        calibration_confirmed=True,
        side_filter="defense",
        head_yaw_by_track={"d1": 1.2},
    )
    assert [n.track_id for n in nodes] == ["d1"]
    assert nodes[0].has_pose is True
    assert nodes[0].head_yaw_rad == pytest.approx(1.2)


def test_build_spatial_graph_is_undirected_and_serialisable() -> None:
    nodes = [
        fs.PlayerNode("a", 60.0, -5.0, 0.0, 10.0, 0.0, 0.0, 0.0, velocity=(1.0, 0.0)),
        fs.PlayerNode("b", 60.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, velocity=(1.0, 0.0)),
        fs.PlayerNode("c", 60.0, 5.0, 0.0, 10.0, 0.0, 0.0, 0.0, velocity=(-1.0, 0.0)),
    ]
    graph = fs.build_spatial_graph(nodes, radius_yards=10.0, max_degree=4)
    assert graph.num_nodes == 3
    # Every undirected edge appears in both directions.
    assert graph.num_edges % 2 == 0
    src = graph.edge_index[0].tolist()
    dst = graph.edge_index[1].tolist()
    for s, d in zip(src, dst, strict=True):
        assert [d, s] in [list(p) for p in zip(src, dst, strict=True)]
    # Motion cosine of a (1,0) and c (-1,0) velocities is -1.
    d = graph.to_dict()
    assert d["schema_version"] == fs.SCHEMA_VERSION
    assert d["node_feature_names"] == list(fs.NODE_FEATURE_NAMES)
    assert d["field_frame"] == fs.FIELD_FRAME


def test_empty_graph_has_well_formed_shapes() -> None:
    graph = fs.build_spatial_graph([])
    assert graph.num_nodes == 0
    assert graph.num_edges == 0
    assert graph.node_features.shape == (0, len(fs.NODE_FEATURE_NAMES))
    assert graph.edge_index.shape == (2, 0)


def test_build_spatial_graph_keeps_knn_edges_for_higher_index_nodes() -> None:
    # "d" picks lower-index "c" for k=1, while "c" picks "b" instead.
    nodes = [
        fs.PlayerNode("a", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, velocity=(0.0, 0.0)),
        fs.PlayerNode("b", 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, velocity=(0.0, 0.0)),
        fs.PlayerNode("c", 100.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, velocity=(0.0, 0.0)),
        fs.PlayerNode("d", 101.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, velocity=(0.0, 0.0)),
    ]
    graph = fs.build_spatial_graph(nodes, radius_yards=0.01, max_degree=1)
    src = graph.edge_index[0].tolist()
    dst = graph.edge_index[1].tolist()
    assert [3, 2] in [list(p) for p in zip(src, dst, strict=True)]
    assert [2, 3] in [list(p) for p in zip(src, dst, strict=True)]


def test_estimate_los_x_is_median() -> None:
    tracks = [
        _track("a", [(10, 48.0, 0.0)]),
        _track("b", [(10, 50.0, 0.0)]),
        _track("c", [(10, 52.0, 0.0)]),
    ]
    assert fs.estimate_los_x(tracks, 10) == pytest.approx(50.0)
    assert fs.estimate_los_x([], 10) == 50.0
