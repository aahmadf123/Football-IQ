"""Tracking + Re-ID upgrade adapters (Issues #129 and #131).

This package holds the heavier, nightly-only tracker adapters and the
Re-ID upgrade layers. All heavy / weight-backed dependencies (torch,
PARSeq, ReID models) are imported lazily inside methods so the package
imports cleanly — and ``pytest`` collects — with only NumPy + OpenCV
present. Selection always flows through ``pipeline.model_router``; nothing
here is wired outside the router or the existing stage entry points.

Single-camera only (Issue #101): the min-cost-flow stitcher links
fragmented tracklets *within one clip*. There is no cross-camera path.
"""

from __future__ import annotations
