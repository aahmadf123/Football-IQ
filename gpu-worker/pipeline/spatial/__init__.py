"""Shared spatial / graph feature primitives for Phase-CV analytics.

This package holds the *single* spatial feature schema used by both the coverage
classifier GNN (Issue #139) and the pre-snap pressure predictor (Issue #140).
Keeping one schema means a node feature (e.g. ``depth_behind_los`` or
``leverage``) is computed the same way for every downstream model, and a change
to the field-frame contract lands in one place.

Everything here is deterministic, pure-Python + NumPy, and operates on the
**calibrated field-yard coordinate frame** produced by the routed
calibration/tracking stages (#127/#128/#129). It loads no model weights and is
not wired into the model router — it is geometry over the outputs of the routed
stages, exactly like ``pipeline.frontier_analytics`` and the pre-snap predictor.
"""
