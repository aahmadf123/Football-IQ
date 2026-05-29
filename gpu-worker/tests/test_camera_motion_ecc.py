"""Tests for chained-ECC camera-motion compensation (Issue #138).

The pure-NumPy chaining / zoom / mask math is tested directly. The ECC warp
estimation is tested on a synthetic textured image translated by a known
offset (skipped if OpenCV is unavailable).
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.homography.camera_motion_ecc import (
    ChainedECCCompensator,
    affine_to_homography,
    background_mask,
    estimate_warp,
    exceeds_zoom_rate,
    zoom_magnitude,
)

cv2 = pytest.importorskip("cv2", reason="ECC warp estimation needs OpenCV")


# ── Pure-math: zoom / affine / mask ───────────────────────────────────────────


def test_affine_to_homography_promotes_2x3():
    warp = np.array([[1.0, 0.0, 5.0], [0.0, 1.0, -3.0]])
    H = affine_to_homography(warp)
    assert H.shape == (3, 3)
    assert H[2, 2] == 1.0
    assert H[0, 2] == 5.0 and H[1, 2] == -3.0


def test_zoom_magnitude_identity_is_one():
    assert zoom_magnitude(np.eye(3)) == pytest.approx(1.0)


def test_zoom_magnitude_scaled():
    warp = np.array([[2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 1.0]])
    assert zoom_magnitude(warp) == pytest.approx(2.0)


def test_exceeds_zoom_rate_triggers_above_threshold():
    # 1.2x cumulative over 30 frames at 60 fps ⇒ 1.2**2 = 1.44x/s > 1.15.
    warp = np.array([[1.2, 0.0, 0.0], [0.0, 1.2, 0.0], [0.0, 0.0, 1.0]])
    assert exceeds_zoom_rate(warp, frames_elapsed=30, fps=60.0)


def test_exceeds_zoom_rate_quiet_pan_ok():
    # No zoom (pure translation) never breaches the rate cap.
    warp = np.array([[1.0, 0.0, 25.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    assert not exceeds_zoom_rate(warp, frames_elapsed=15, fps=60.0)


def test_background_mask_zeros_player_boxes():
    grass = np.full((40, 40), 255, dtype=np.uint8)
    mask = background_mask(grass, [(10, 10, 20, 20)])
    assert mask[15, 15] == 0          # inside player box → excluded
    assert mask[0, 0] == 255          # background grass → kept


# ── ECC warp recovery on synthetic frames ─────────────────────────────────────


def _textured_image(h: int = 160, w: int = 200) -> np.ndarray:
    # Smooth, well-conditioned gradient texture: ECC converges reliably on
    # strong low-frequency structure (unlike high-frequency random noise).
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    pattern = (
        128
        + 60 * np.sin(2 * np.pi * xx / 40.0)
        + 50 * np.cos(2 * np.pi * yy / 35.0)
    )
    return np.clip(pattern, 0, 255).astype(np.uint8)


def test_ecc_recovers_translation():
    prev = _textured_image()
    shift = np.array([[1.0, 0.0, 6.0], [0.0, 1.0, 4.0]], dtype=np.float32)
    cur = cv2.warpAffine(
        prev, shift, (prev.shape[1], prev.shape[0]), borderMode=cv2.BORDER_REFLECT101
    )
    warp, ok = estimate_warp(prev, cur, motion_type="affine", max_iters=200)
    assert ok
    # cur = prev shifted by (+6, +4); ECC (template=prev) recovers that shift.
    assert warp[0, 2] == pytest.approx(6.0, abs=1.0)
    assert warp[1, 2] == pytest.approx(4.0, abs=1.0)


def test_ecc_identity_for_identical_frames():
    img = _textured_image()
    warp, ok = estimate_warp(img, img, motion_type="affine")
    assert ok
    assert np.allclose(warp, np.array([[1, 0, 0], [0, 1, 0]]), atol=1e-2)


# ── Chaining + anchoring ──────────────────────────────────────────────────────


def test_fixed_sideline_chain_is_anchor_noop():
    comp = ChainedECCCompensator(regime="fixed_sideline", fps=30.0)
    anchor = np.array([[1.0, 0, 10], [0, 1.0, 5], [0, 0, 1.0]], dtype=np.float64)
    comp.set_anchor(0, anchor, confidence=0.9)
    H, zoom = comp.chain(np.array([[1.0, 0, 99], [0, 1.0, 99]]))
    # Identity collapse: warp ignored, anchor returned unchanged.
    assert np.allclose(H, anchor)
    assert zoom == 1.0


def test_low_confidence_anchor_rejected():
    comp = ChainedECCCompensator(regime="drone_follow")
    ok = comp.set_anchor(0, np.eye(3), confidence=0.5)
    assert ok is False
    assert comp.anchor_H is None


def test_drone_chain_composes_translation():
    comp = ChainedECCCompensator(regime="drone_follow", fps=60.0)
    anchor = np.eye(3, dtype=np.float64)
    comp.set_anchor(0, anchor, confidence=0.8)
    # Two translation warps compose additively in the chain.
    comp.chain(np.array([[1.0, 0, 3.0], [0, 1.0, 0.0]]))
    H, _ = comp.chain(np.array([[1.0, 0, 2.0], [0, 1.0, 0.0]]))
    assert H[0, 2] == pytest.approx(5.0)


def test_needs_reanchor_on_drift():
    comp = ChainedECCCompensator(regime="drone_follow", fps=60.0)
    comp.set_anchor(0, np.eye(3), confidence=0.9)
    comp.chain(np.array([[1.0, 0, 1.0], [0, 1.0, 0.0]]))
    pts = np.array([[0, 0], [100, 0], [100, 60], [0, 60]], dtype=np.float64)
    # A direct fit far from the chained estimate ⇒ re-anchor.
    direct = np.array([[1.0, 0, 50.0], [0, 1.0, 0.0], [0, 0, 1.0]])
    assert comp.needs_reanchor(direct, pts)
    # A direct fit matching the chain ⇒ no re-anchor.
    matching = np.array([[1.0, 0, 1.0], [0, 1.0, 0.0], [0, 0, 1.0]])
    assert not comp.needs_reanchor(matching, pts)
