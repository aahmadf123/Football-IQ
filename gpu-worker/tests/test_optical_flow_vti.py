"""Tests for the VTI optical-flow snap signal (Issue #132)."""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.events.optical_flow_vti import (
    VTIConfig,
    active_cell_counts,
    burst_strength,
)


def _static_frame() -> np.ndarray:
    return np.zeros((96, 96), dtype=np.float32)


def _frame_with_block(x: int) -> np.ndarray:
    f = np.zeros((96, 96), dtype=np.float32)
    f[40:56, x : x + 16] = 255.0
    return f


def test_static_sequence_has_no_burst() -> None:
    frames = [_static_frame() for _ in range(8)]
    counts = active_cell_counts(frames, config=VTIConfig(cell_size=16))
    assert counts[0] == 0
    assert all(c == 0 for c in counts)


def test_motion_burst_spikes_active_cells() -> None:
    # Static for a while, then a block jumps across frames → motion burst.
    frames = [_static_frame() for _ in range(6)]
    frames += [_frame_with_block(10), _frame_with_block(40), _frame_with_block(70)]
    counts = active_cell_counts(frames, config=VTIConfig(cell_size=16))
    strengths = burst_strength(counts)
    # The strongest burst must land on one of the moving frames (index >= 6).
    peak = max(range(len(strengths)), key=lambda i: strengths[i])
    assert peak >= 6
    assert max(strengths) > 0.0


def test_los_band_restricts_counting() -> None:
    # Motion only on the far right; a LOS band on the left should see nothing.
    frames = [_static_frame() for _ in range(4)]
    frames += [_frame_with_block(70), _frame_with_block(74)]
    counts_band = active_cell_counts(
        frames, config=VTIConfig(cell_size=16), los_band_px=(0, 30)
    )
    assert all(c == 0 for c in counts_band)


def test_short_sequence_is_safe() -> None:
    assert active_cell_counts([], config=VTIConfig()) == []
    assert active_cell_counts([_static_frame()]) == [0]
