"""Ball-detection support package (Issue #133).

Holds the annotation-manifest schema for the regime-split ball dataset. The
runtime detector lives in :mod:`pipeline.detection.ball_detector`; this package
defines the *shape* of the labeling data (no real annotations are committed —
the manifest is populated by the active-learning labeling loop and stored out
of tree, see ``data/ball_annotations/``).
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

# Capture regimes a ball frame can be annotated under (Issue #126).
BALL_REGIMES = ("fixed_sideline", "drone_follow")
# Dataset split labels (Issue #133: 70 / 15 / 15).
BALL_SPLITS = ("train", "val", "test")

# Manifest schema version — bump on any breaking field change.
MANIFEST_VERSION = 1


class BallAnnotation(TypedDict, total=False):
    """A single ball bounding box on one frame.

    ``bbox`` is pixel-space ``[x1, y1, x2, y2]``. ``visible`` is False for
    occluded/blurred balls that are labeled but should not count against
    recall. ``regime`` and ``split`` mirror the manifest-level fields and are
    duplicated per row so the file can be sharded.
    """

    video_id: str
    frame_number: int
    bbox: list[float]
    visible: bool
    regime: Literal["fixed_sideline", "drone_follow"]
    split: Literal["train", "val", "test"]


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Validate a ball-annotation manifest dict against the schema.

    Returns a list of human-readable problems; an empty list means valid.
    Pure-Python so it runs anywhere and is unit-testable without the dataset.
    """
    errors: list[str] = []
    if manifest.get("version") != MANIFEST_VERSION:
        errors.append(
            f"version must be {MANIFEST_VERSION}, got {manifest.get('version')!r}"
        )
    annotations = manifest.get("annotations")
    if not isinstance(annotations, list):
        errors.append("'annotations' must be a list")
        return errors
    for i, ann in enumerate(annotations):
        if not isinstance(ann, dict):
            errors.append(f"annotation[{i}] is not an object")
            continue
        bbox = ann.get("bbox")
        if not (isinstance(bbox, list) and len(bbox) == 4):
            errors.append(f"annotation[{i}].bbox must be [x1,y1,x2,y2]")
        if ann.get("regime") not in BALL_REGIMES:
            errors.append(f"annotation[{i}].regime invalid: {ann.get('regime')!r}")
        if ann.get("split") not in BALL_SPLITS:
            errors.append(f"annotation[{i}].split invalid: {ann.get('split')!r}")
        if not isinstance(ann.get("frame_number"), int):
            errors.append(f"annotation[{i}].frame_number must be an int")
    return errors
