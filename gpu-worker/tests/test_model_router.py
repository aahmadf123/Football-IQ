"""Tests for gpu-worker/pipeline/model_router.py (Issue #16).

Covers:
  - select_model returns RTMPOSE_FAST for SAME_SESSION_PRIORITY (10)
  - select_model returns RTMPOSE_MEDIUM for NIGHTLY_PRIORITY (0)
  - select_model returns RTMPOSE_FAST for any priority >= SAME_SESSION_PRIORITY
  - select_model returns RTMPOSE_MEDIUM for any priority < SAME_SESSION_PRIORITY
  - is_same_session / is_nightly helper predicates
  - Constants align with queue module priority values
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.model_router import (
    RTMPOSE_FAST,
    RTMPOSE_MEDIUM,
    is_nightly,
    is_same_session,
    select_model,
)
from queue.same_session_queue import NIGHTLY_PRIORITY, SAME_SESSION_PRIORITY


# ── select_model ──────────────────────────────────────────────────────────────


def test_select_model_same_session_priority_returns_fast() -> None:
    assert select_model(SAME_SESSION_PRIORITY) == RTMPOSE_FAST


def test_select_model_nightly_priority_returns_medium() -> None:
    assert select_model(NIGHTLY_PRIORITY) == RTMPOSE_MEDIUM


def test_select_model_high_priority_returns_fast() -> None:
    assert select_model(SAME_SESSION_PRIORITY + 5) == RTMPOSE_FAST


def test_select_model_priority_just_below_same_session_returns_medium() -> None:
    assert select_model(SAME_SESSION_PRIORITY - 1) == RTMPOSE_MEDIUM


def test_select_model_zero_priority_returns_medium() -> None:
    assert select_model(0) == RTMPOSE_MEDIUM


def test_select_model_negative_priority_returns_medium() -> None:
    assert select_model(-5) == RTMPOSE_MEDIUM


# ── is_same_session / is_nightly ──────────────────────────────────────────────


def test_is_same_session_true_for_high_priority() -> None:
    assert is_same_session(SAME_SESSION_PRIORITY) is True
    assert is_same_session(SAME_SESSION_PRIORITY + 1) is True


def test_is_same_session_false_for_low_priority() -> None:
    assert is_same_session(SAME_SESSION_PRIORITY - 1) is False
    assert is_same_session(NIGHTLY_PRIORITY) is False


def test_is_nightly_true_for_zero_priority() -> None:
    assert is_nightly(NIGHTLY_PRIORITY) is True
    assert is_nightly(0) is True


def test_is_nightly_false_for_high_priority() -> None:
    assert is_nightly(SAME_SESSION_PRIORITY) is False


# ── Model name constants ──────────────────────────────────────────────────────


def test_rtmpose_fast_is_tiny_variant() -> None:
    assert "t" in RTMPOSE_FAST.lower()


def test_rtmpose_medium_is_m_variant() -> None:
    assert "m" in RTMPOSE_MEDIUM.lower()


def test_fast_and_medium_are_different() -> None:
    assert RTMPOSE_FAST != RTMPOSE_MEDIUM


# ── Alignment with queue module ───────────────────────────────────────────────


def test_same_session_priority_value_is_10() -> None:
    assert SAME_SESSION_PRIORITY == 10


def test_nightly_priority_value_is_0() -> None:
    assert NIGHTLY_PRIORITY == 0


def test_model_selection_covers_all_integer_priorities() -> None:
    """Every integer priority maps to one of the two model variants."""
    for p in range(-5, 20):
        model = select_model(p)
        assert model in (RTMPOSE_FAST, RTMPOSE_MEDIUM), (
            f"select_model({p}) returned unexpected value: {model!r}"
        )
