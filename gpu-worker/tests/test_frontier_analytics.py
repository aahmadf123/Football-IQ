"""Unit tests for frontier analytics scaffolds (Issue #10): xSep / xYards / xPressure.

All metrics must be experimental + never analytics_safe, must suppress (not
guess) when inputs are missing, and must compute without SAM/embeddings.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline import frontier_analytics as fa


def _track(coords, start_frame=0):
    """coords: list of (x, y) → track points with incrementing frame numbers."""
    return [{"frame_number": start_frame + i, "x": x, "y": y} for i, (x, y) in enumerate(coords)]


# ── xSep ─────────────────────────────────────────────────────────────────────


def test_xsep_computes_separation():
    receiver = _track([(50.0, 10.0), (52.0, 10.0), (54.0, 10.0)])
    defender = _track([(50.0, 13.0), (52.0, 13.0), (54.0, 13.0)])
    m = fa.compute_xsep(receiver, defender, throw_frame=2)
    assert not m.suppressed
    assert m.metric_name == "xsep"
    assert m.metric_value["yards"] == 3.0  # 3 yards apart in y
    assert m.unit == "yd"
    assert m.experimental is True
    assert m.analytics_safe is False
    assert m.metric_value["source"] == "tracking"
    assert m.metric_value["sample_size"] == 3


def test_xsep_suppressed_when_calibration_unsafe():
    receiver = _track([(50.0, 10.0)] * 3)
    defender = _track([(50.0, 13.0)] * 3)
    m = fa.compute_xsep(receiver, defender, throw_frame=1, calibration_analytics_safe=False)
    assert m.suppressed
    assert m.suppression_reason == "calibration_not_analytics_safe"


def test_xsep_suppressed_when_too_few_points():
    receiver = _track([(50.0, 10.0)])
    defender = _track([(50.0, 13.0)])
    m = fa.compute_xsep(receiver, defender, throw_frame=0)
    assert m.suppressed
    assert m.suppression_reason == "insufficient_track_points"


def test_xsep_enrichment_raises_confidence():
    receiver = _track([(50.0, 10.0)] * 5)
    defender = _track([(50.0, 12.0)] * 5)
    base = fa.compute_xsep(receiver, defender, throw_frame=2)
    enriched = fa.compute_xsep(
        receiver, defender, throw_frame=2, used_sam=True, used_embeddings=True
    )
    assert enriched.confidence > base.confidence
    assert enriched.metric_value["used_sam"] is True


# ── xPressure ──────────────────────────────────────────────────────────────────


def test_xpressure_computes_rate():
    qb = _track([(40.0, 0.0)] * 10)
    # One rusher closes to within 1 yd, one stays far away.
    rusher_close = _track([(41.0, 0.0)] * 10)
    rusher_far = _track([(60.0, 20.0)] * 10)
    m = fa.compute_xpressure(
        qb, [rusher_close, rusher_far], snap_frame=0, throw_frame=9, fps=30.0
    )
    assert not m.suppressed
    assert m.metric_name == "xpressure"
    assert m.metric_value["rushers_closed"] == 1
    assert m.metric_value["rushers_counted"] == 2
    assert 0.0 <= m.metric_value["xpressure"] <= 1.0
    assert m.experimental is True and m.analytics_safe is False


def test_xpressure_suppressed_without_rushers():
    qb = _track([(40.0, 0.0)] * 5)
    m = fa.compute_xpressure(qb, [], snap_frame=0, throw_frame=4)
    assert m.suppressed
    assert m.suppression_reason == "insufficient_tracks"


def test_xpressure_suppressed_on_degenerate_window():
    qb = _track([(40.0, 0.0)] * 5)
    rusher = _track([(41.0, 0.0)] * 5)
    m = fa.compute_xpressure(qb, [rusher], snap_frame=5, throw_frame=3)
    assert m.suppressed
    assert m.suppression_reason == "degenerate_snap_throw_window"


# ── xYards (stub) ───────────────────────────────────────────────────────────────


def test_xyards_is_low_confidence_placeholder():
    receiver = _track([(50.0, 10.0), (54.0, 10.0), (60.0, 10.0)])
    m = fa.compute_xyards(receiver, catch_frame=0)
    assert not m.suppressed
    assert m.metric_name == "xyards"
    assert m.confidence == 0.1  # deliberately low — scaffold only
    assert m.metric_value["model"] == "placeholder_observed_only"
    assert m.metric_value["observed_yac_yd"] == 10.0


def test_xyards_suppressed_without_catch_frame():
    receiver = _track([(50.0, 10.0)] * 3)
    m = fa.compute_xyards(receiver, catch_frame=None)
    assert m.suppressed


# ── payload shaping ──────────────────────────────────────────────────────────────


def test_to_metric_payload_is_always_experimental():
    receiver = _track([(50.0, 10.0)] * 3)
    defender = _track([(50.0, 12.0)] * 3)
    m = fa.compute_xsep(receiver, defender, throw_frame=1, receiver_tracklet_id="t1")
    payload = m.to_metric_payload("clip-1", job_id="job-1")
    assert payload["clip_id"] == "clip-1"
    assert payload["metric_name"] == "xsep"
    assert payload["experimental_flag"] is True
    assert payload["analytics_safe"] is False
    assert payload["tracklet_id"] == "t1"
    assert payload["job_id"] == "job-1"


def test_suppressed_metric_payload_marks_suppressed():
    m = fa.compute_xsep([], [], throw_frame=0)
    payload = m.to_metric_payload("clip-1")
    assert payload["is_suppressed"] is True
    assert payload["experimental_flag"] is True
