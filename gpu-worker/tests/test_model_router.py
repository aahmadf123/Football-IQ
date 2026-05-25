"""Tests for gpu-worker/pipeline/model_router.py (Issue #73).

Covers the stage-aware routing API that replaced Issue #16's
priority-only ``select_model(priority)``. Pose mapping must remain
identical so issue #16's downstream behaviour is preserved.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline import model_router
from pipeline.model_router import (
    DEFAULT_ROUTING,
    RTMPOSE_FAST,
    RTMPOSE_MEDIUM,
    UNKNOWN_STAGE_FALLBACK,
    build_routing_artifact,
    is_nightly,
    is_same_session,
    select_model,
)
from queue.same_session_queue import NIGHTLY_PRIORITY, SAME_SESSION_PRIORITY


@pytest.fixture(autouse=True)
def _reset_routing(monkeypatch: pytest.MonkeyPatch):
    """Each test starts with the default routing table and no env override."""
    monkeypatch.delenv("MODEL_ROUTING_CONFIG", raising=False)
    model_router.reload_routing()
    yield
    monkeypatch.delenv("MODEL_ROUTING_CONFIG", raising=False)
    model_router.reload_routing()


# ── Pose preservation (Issue #16 contract) ────────────────────────────────────


def test_select_model_pose_same_session_returns_rtmpose_fast() -> None:
    assert select_model("pose", SAME_SESSION_PRIORITY) == RTMPOSE_FAST


def test_select_model_pose_nightly_returns_rtmpose_medium() -> None:
    assert select_model("pose", NIGHTLY_PRIORITY) == RTMPOSE_MEDIUM


def test_select_model_pose_high_priority_returns_fast() -> None:
    assert select_model("pose", SAME_SESSION_PRIORITY + 5) == RTMPOSE_FAST


def test_select_model_pose_just_below_threshold_returns_medium() -> None:
    assert select_model("pose", SAME_SESSION_PRIORITY - 1) == RTMPOSE_MEDIUM


def test_select_model_pose_negative_priority_returns_medium() -> None:
    assert select_model("pose", -5) == RTMPOSE_MEDIUM


# ── Other stages ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "stage",
    ["segment", "detect", "track", "reid", "pose", "render", "embeddings"],
)
def test_select_model_returns_non_empty_string_for_known_stages(stage: str) -> None:
    fast = select_model(stage, SAME_SESSION_PRIORITY)
    nightly = select_model(stage, NIGHTLY_PRIORITY)
    assert isinstance(fast, str) and fast
    assert isinstance(nightly, str) and nightly


def test_detect_same_session_and_nightly_variants_differ() -> None:
    # The default detect routing uses a lighter YOLO for same-session.
    fast = select_model("detect", SAME_SESSION_PRIORITY)
    nightly = select_model("detect", NIGHTLY_PRIORITY)
    assert fast != nightly
    assert fast == DEFAULT_ROUTING["detect"]["same_session"]
    assert nightly == DEFAULT_ROUTING["detect"]["nightly"]


def test_select_model_returns_match_from_default_routing_table() -> None:
    for stage, variants in DEFAULT_ROUTING.items():
        assert select_model(stage, SAME_SESSION_PRIORITY) == variants["same_session"]
        assert select_model(stage, NIGHTLY_PRIORITY) == variants["nightly"]


# ── Unknown-stage fallback ────────────────────────────────────────────────────


def test_select_model_unknown_stage_returns_fallback_without_raising() -> None:
    assert select_model("does-not-exist", SAME_SESSION_PRIORITY) == UNKNOWN_STAGE_FALLBACK
    assert select_model("also-bogus", NIGHTLY_PRIORITY) == UNKNOWN_STAGE_FALLBACK


# ── build_routing_artifact ────────────────────────────────────────────────────


def test_build_routing_artifact_shape_for_pose() -> None:
    assert build_routing_artifact("pose", SAME_SESSION_PRIORITY) == {"pose": RTMPOSE_FAST}
    assert build_routing_artifact("pose", NIGHTLY_PRIORITY) == {"pose": RTMPOSE_MEDIUM}


def test_build_routing_artifact_for_unknown_stage() -> None:
    assert build_routing_artifact("ghost-stage", 0) == {"ghost-stage": UNKNOWN_STAGE_FALLBACK}


# ── Predicates ────────────────────────────────────────────────────────────────


def test_is_same_session_true_for_high_priority() -> None:
    assert is_same_session(SAME_SESSION_PRIORITY) is True
    assert is_same_session(SAME_SESSION_PRIORITY + 1) is True


def test_is_same_session_false_for_low_priority() -> None:
    assert is_same_session(SAME_SESSION_PRIORITY - 1) is False
    assert is_same_session(NIGHTLY_PRIORITY) is False


def test_is_nightly_true_for_zero_priority() -> None:
    assert is_nightly(NIGHTLY_PRIORITY) is True


def test_is_nightly_false_for_high_priority() -> None:
    assert is_nightly(SAME_SESSION_PRIORITY) is False


# ── Env-driven override via MODEL_ROUTING_CONFIG ──────────────────────────────


def test_routing_config_override_replaces_named_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "routing.json"
    cfg.write_text(
        json.dumps(
            {
                "detect": {"same_session": "custom-fast", "nightly": "custom-heavy"},
            }
        )
    )
    monkeypatch.setenv("MODEL_ROUTING_CONFIG", str(cfg))
    model_router.reload_routing()

    assert select_model("detect", SAME_SESSION_PRIORITY) == "custom-fast"
    assert select_model("detect", NIGHTLY_PRIORITY) == "custom-heavy"
    # Stages not mentioned in the override keep their defaults — pose unchanged.
    assert select_model("pose", SAME_SESSION_PRIORITY) == RTMPOSE_FAST
    assert select_model("pose", NIGHTLY_PRIORITY) == RTMPOSE_MEDIUM


def test_routing_config_partial_override_keeps_unmentioned_bucket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Only override the same_session bucket for detect — nightly should still
    # be the default.
    cfg = tmp_path / "routing.json"
    cfg.write_text(json.dumps({"detect": {"same_session": "yolov8s"}}))
    monkeypatch.setenv("MODEL_ROUTING_CONFIG", str(cfg))
    model_router.reload_routing()

    assert select_model("detect", SAME_SESSION_PRIORITY) == "yolov8s"
    assert select_model("detect", NIGHTLY_PRIORITY) == DEFAULT_ROUTING["detect"]["nightly"]


def test_routing_config_missing_file_falls_back_to_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_ROUTING_CONFIG", str(tmp_path / "nope.json"))
    model_router.reload_routing()

    assert select_model("pose", SAME_SESSION_PRIORITY) == RTMPOSE_FAST


def test_routing_config_malformed_json_falls_back_to_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "routing.json"
    cfg.write_text("{not valid json")
    monkeypatch.setenv("MODEL_ROUTING_CONFIG", str(cfg))
    model_router.reload_routing()

    assert select_model("pose", NIGHTLY_PRIORITY) == RTMPOSE_MEDIUM


def test_bundled_routing_json_matches_default_routing() -> None:
    """The in-tree JSON should mirror DEFAULT_ROUTING so the doc and the
    Python defaults never drift apart."""
    bundled = Path(__file__).resolve().parent.parent / "pipeline" / "model_routing.json"
    payload = json.loads(bundled.read_text())
    assert payload == DEFAULT_ROUTING


# ── Coverage sanity ───────────────────────────────────────────────────────────


def test_model_selection_covers_all_integer_priorities_for_pose() -> None:
    for p in range(-5, 20):
        model = select_model("pose", p)
        assert model in (RTMPOSE_FAST, RTMPOSE_MEDIUM), (
            f"select_model('pose', {p}) returned unexpected value: {model!r}"
        )


def test_reload_routing_returns_current_table() -> None:
    table = model_router.reload_routing()
    assert table is model_router.ROUTING
    assert "pose" in table
