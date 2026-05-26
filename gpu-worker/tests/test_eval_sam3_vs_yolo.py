"""Smoke tests for eval/eval_sam3_vs_yolo.py (Issue #74).

The eval script is intended to be runnable in CI on the synthetic path
(no weights, no GPU, no opencv).  These tests lock that contract in
place so the script never silently breaks when adapter signatures or
metric shapes change.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval.eval_sam3_vs_yolo import (
    DetectionMetrics,
    TrackingMetrics,
    _to_jsonable,
    main,
    run_eval,
)


def test_run_eval_synthetic_returns_both_detectors_and_three_tracker_runs() -> None:
    result = run_eval(synthetic=True, frame_step=3)
    variants = {m.variant for m in result.detection}
    assert variants == {"yolov8n", "sam3.1"}
    # YOLO + IoU, SAM + IoU, SAM + mask-tracker
    assert len(result.tracking) == 3
    pairs = {(m.variant, m.tracker) for m in result.tracking}
    assert pairs == {
        ("yolov8n", "iou-tracker"),
        ("sam3.1", "iou-tracker"),
        ("sam3.1", "sam3-mask-tracker"),
    }


def test_run_eval_synthetic_yolo_has_no_masks_sam3_does() -> None:
    result = run_eval(synthetic=True)
    by_variant = {m.variant: m for m in result.detection}
    assert by_variant["yolov8n"].mask_coverage == 0.0
    assert by_variant["sam3.1"].mask_coverage == pytest.approx(1.0)


def test_run_eval_synthetic_records_provenance_note() -> None:
    result = run_eval(synthetic=True)
    assert any("synthetic" in note.lower() for note in result.notes)


def test_run_eval_raises_when_no_clips_and_not_synthetic() -> None:
    with pytest.raises(ValueError):
        run_eval(clip_paths=None, synthetic=False)


def test_detection_metrics_summary_includes_variant_name() -> None:
    m = DetectionMetrics(
        variant="sam3.1",
        frame_count=10,
        detection_count=20,
        detected_frames=8,
        mean_detections_per_frame=2.0,
        frame_coverage=0.8,
        mean_confidence=0.9,
        mask_coverage=1.0,
    )
    assert "sam3.1" in m.summary


def test_tracking_metrics_summary_includes_tracker_name() -> None:
    m = TrackingMetrics(
        variant="sam3.1",
        tracker="sam3-mask-tracker",
        track_count=4,
        mean_track_length=12.0,
        max_track_length=30,
        fragmentation_index=0.18,
        short_track_fraction=0.0,
    )
    assert "sam3-mask-tracker" in m.summary


def test_to_jsonable_is_serialisable() -> None:
    result = run_eval(synthetic=True)
    payload = _to_jsonable(result)
    text = json.dumps(payload)
    parsed = json.loads(text)
    assert "detection" in parsed
    assert "tracking" in parsed
    assert "notes" in parsed


def test_main_synthetic_writes_output_file(tmp_path: Path, capsys) -> None:
    out = tmp_path / "eval.json"
    rc = main(["--synthetic", "--out", str(out)])
    assert rc == 0
    assert out.exists()
    payload = json.loads(out.read_text())
    assert len(payload["detection"]) == 2
    assert len(payload["tracking"]) == 3


def test_main_errors_without_clip_dir_when_not_synthetic() -> None:
    with pytest.raises(SystemExit):
        main([])  # neither --synthetic nor --clip-dir


def test_run_eval_tracking_metrics_non_negative() -> None:
    result = run_eval(synthetic=True)
    for m in result.tracking:
        assert m.track_count >= 0
        assert m.mean_track_length >= 0
        assert m.max_track_length >= 0
        assert m.short_track_fraction >= 0
        assert m.fragmentation_index >= 0
