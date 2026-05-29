"""Yard-line keypoint detection (Issue #127 — light Hough+DLT path).

Pixel-only field-marking detection that feeds the DLT solver:

1. **White-paint mask** — HSV threshold (high V, low S) gated to the grass
   region, then morphological close to bridge dashed hashes.
2. **Hough lines** — ``cv2.HoughLines`` on Canny edges of the paint mask.
3. **Angle clustering** — group lines by orientation (yard lines vs
   sidelines/hashes) with a simple 5° angular tolerance (no sklearn).
4. **Correspondences** — match detected near-vertical lines (left→right) to
   evenly-spaced template yard lines, intersect with the dominant
   near-horizontal lines (sidelines/hashes), and label each crossing with its
   field-frame ``(x_yd, y_yd)`` coordinate.

OpenCV is imported lazily so the module stays importable (and partially
testable) in containers without cv2 — the clustering and correspondence math
are pure NumPy and unit-tested directly. The deep-keypoint upgrade
(PnLCalib / No-Bells-Just-Whistles) referenced in Issue #127 is a future
nightly-only variant and is intentionally **not** bundled here; this path is
the light Hough+DLT detector that is safe for the same-session window.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from pipeline.homography.field_template import FieldTemplate, default_template

# Orientation tolerance for "this line is a yard line" vs "this is a
# sideline/hash" (radians). ~5° matches the DBSCAN ε in Issue #127.
ANGLE_TOL_RAD = math.radians(5.0)
VERTICAL_BAND_RAD = math.radians(35.0)  # near-vertical yard-line acceptance


@dataclass
class KeypointResult:
    """Detected correspondences + diagnostic features for confidence scoring."""

    src_pts: np.ndarray  # (N, 2) pixel coordinates
    dst_pts: np.ndarray  # (N, 2) field-yard coordinates
    line_count: int
    field_coverage: float
    yardline_angles: list[float] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)

    def has_enough(self) -> bool:
        return len(self.src_pts) >= 4


# ── White-paint + grass masks (cv2) ───────────────────────────────────────────


def grass_mask(frame: np.ndarray) -> tuple[np.ndarray, float]:
    """Return ``(mask, coverage)`` of the green playing surface via HSV."""
    import cv2

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower = np.array([35, 40, 40])
    upper = np.array([90, 255, 255])
    mask = cv2.inRange(hsv, lower, upper)
    coverage = float(np.count_nonzero(mask)) / float(mask.size)
    return mask, coverage


def white_paint_mask(frame: np.ndarray, grass: np.ndarray) -> np.ndarray:
    """White paint = high value, low saturation, dilated near the grass region."""
    import cv2

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower = np.array([0, 0, 170])
    upper = np.array([180, 60, 255])
    paint = cv2.inRange(hsv, lower, upper)
    # Only keep paint adjacent to grass (dilate grass to form a gate).
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    grass_gate = cv2.dilate(grass, kernel, iterations=1)
    paint = cv2.bitwise_and(paint, grass_gate)
    # Close to bridge dashed hash marks into continuous lines.
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    return cv2.morphologyEx(paint, cv2.MORPH_CLOSE, close_kernel)


def detect_hough_lines(paint: np.ndarray) -> list[tuple[float, float]]:
    """Return Hough lines as ``(rho, theta)`` from the paint mask edges."""
    import cv2

    edges = cv2.Canny(paint, 50, 150)
    raw = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)
    if raw is None:
        return []
    return [(float(r), float(t)) for r, t in raw[:, 0, :]]


# ── Pure-NumPy clustering + correspondence math (unit-tested directly) ─────────


def cluster_lines_by_angle(
    lines: list[tuple[float, float]], tol_rad: float = ANGLE_TOL_RAD
) -> list[list[tuple[float, float]]]:
    """Greedy 1-D clustering of ``(rho, theta)`` lines by orientation.

    Angles are taken modulo π (a line and its 180° flip are the same
    orientation). Returns clusters sorted by descending size.
    """
    if not lines:
        return []
    items = sorted(lines, key=lambda lt: lt[1] % math.pi)
    clusters: list[list[tuple[float, float]]] = []
    for rho, theta in items:
        t = theta % math.pi
        placed = False
        for cluster in clusters:
            ref = cluster[0][1] % math.pi
            diff = abs(t - ref)
            diff = min(diff, math.pi - diff)
            if diff <= tol_rad:
                cluster.append((rho, theta))
                placed = True
                break
        if not placed:
            clusters.append([(rho, theta)])
    clusters.sort(key=len, reverse=True)
    return clusters


def _line_x_at_y(rho: float, theta: float, y: float) -> float | None:
    """x-intercept of a (rho, theta) line at a given image row ``y``."""
    c, s = math.cos(theta), math.sin(theta)
    if abs(c) < 1e-9:
        return None
    return (rho - y * s) / c


def _intersect(
    l1: tuple[float, float], l2: tuple[float, float]
) -> tuple[float, float] | None:
    """Intersection point of two ``(rho, theta)`` lines, or ``None`` if parallel."""
    r1, t1 = l1
    r2, t2 = l2
    a = np.array([[math.cos(t1), math.sin(t1)], [math.cos(t2), math.sin(t2)]])
    b = np.array([r1, r2])
    det = float(np.linalg.det(a))
    if abs(det) < 1e-6:
        return None
    x, y = np.linalg.solve(a, b)
    return float(x), float(y)


def build_correspondences(
    lines: list[tuple[float, float]],
    frame_shape: tuple[int, int],
    template: FieldTemplate | None = None,
) -> KeypointResult:
    """Match detected lines to the field template and emit pixel↔yard pairs.

    Strategy (regime-agnostic geometric core):
    - Split lines into near-vertical (yard lines) and near-horizontal
      (sidelines / hash lines) by orientation.
    - Order yard lines left→right by their x-intercept at mid-image and map
      them onto consecutive template yard lines.
    - Order horizontal lines top→bottom and map them onto the field rows
      (north sideline, north hash, south hash, south sideline) that are
      present, using as many as were detected.
    - Every (yard-line × row) intersection inside the frame becomes a labeled
      correspondence.
    """
    tmpl = template or default_template()
    h, w = frame_shape[:2]
    reason_codes: list[str] = []

    vertical: list[tuple[float, float]] = []
    horizontal: list[tuple[float, float]] = []
    for rho, theta in lines:
        t = theta % math.pi
        # theta near 0 / π ⇒ vertical line in image space; near π/2 ⇒ horizontal.
        if min(t, math.pi - t) <= VERTICAL_BAND_RAD:
            vertical.append((rho, theta))
        elif abs(t - math.pi / 2) <= VERTICAL_BAND_RAD:
            horizontal.append((rho, theta))

    if len(vertical) < 2 or len(horizontal) < 1:
        reason_codes.append("insufficient_structured_lines")
        return KeypointResult(
            src_pts=np.empty((0, 2)),
            dst_pts=np.empty((0, 2)),
            line_count=len(lines),
            field_coverage=0.0,
            reason_codes=reason_codes,
        )

    mid_y = h / 2.0
    # De-duplicate near-coincident vertical lines and order left→right.
    verticals_x: list[tuple[float, tuple[float, float]]] = []
    for line in vertical:
        x = _line_x_at_y(line[0], line[1], mid_y)
        if x is None:
            continue
        verticals_x.append((x, line))
    verticals_x.sort(key=lambda p: p[0])
    deduped: list[tuple[float, tuple[float, float]]] = []
    for x, line in verticals_x:
        if deduped and abs(x - deduped[-1][0]) < max(8.0, w * 0.01):
            continue
        deduped.append((x, line))
    if len(deduped) < 2:
        reason_codes.append("insufficient_yard_lines")
        return KeypointResult(
            src_pts=np.empty((0, 2)),
            dst_pts=np.empty((0, 2)),
            line_count=len(lines),
            field_coverage=0.0,
            reason_codes=reason_codes,
        )

    # Map detected yard lines onto consecutive template yard lines. Without
    # numeral OCR we anchor to a centered span of the template — enough for a
    # well-conditioned DLT; absolute yard offset is refined downstream.
    n_v = len(deduped)
    yard_xs = list(tmpl.yard_lines_x)
    start = max(0, (len(yard_xs) - n_v) // 2)
    chosen_yard_x = yard_xs[start : start + n_v]
    if len(chosen_yard_x) < n_v:  # fewer template lines than detected
        chosen_yard_x = yard_xs[:n_v]

    # Order horizontal lines top→bottom (smallest y first) and map to rows.
    rows_order = [
        ("north", tmpl.sideline_y_north),
        ("hash_n", tmpl.hash_y_north),
        ("hash_s", tmpl.hash_y_south),
        ("south", tmpl.sideline_y_south),
    ]
    horiz_y: list[tuple[float, tuple[float, float]]] = []
    for line in horizontal:
        c = math.cos(line[1])
        s = math.sin(line[1])
        if abs(s) < 1e-9:
            continue
        y_at_mid = (line[0] - (w / 2.0) * c) / s
        horiz_y.append((y_at_mid, line))
    horiz_y.sort(key=lambda p: p[0])
    deduped_h: list[tuple[float, tuple[float, float]]] = []
    for y, line in horiz_y:
        if deduped_h and abs(y - deduped_h[-1][0]) < max(8.0, h * 0.01):
            continue
        deduped_h.append((y, line))
    n_h = min(len(deduped_h), len(rows_order))
    chosen_rows = rows_order[:n_h]

    src: list[list[float]] = []
    dst: list[list[float]] = []
    yardline_angles: list[float] = []
    for (_, v_line), x_yd in zip(deduped, chosen_yard_x):
        yardline_angles.append(v_line[1] % math.pi)
        for (_, h_line), (_, y_yd) in zip(deduped_h[:n_h], chosen_rows):
            pt = _intersect(v_line, h_line)
            if pt is None:
                continue
            px, py = pt
            if -0.1 * w <= px <= 1.1 * w and -0.1 * h <= py <= 1.1 * h:
                src.append([px, py])
                dst.append([float(x_yd), float(y_yd)])

    if len(src) < 4:
        reason_codes.append("insufficient_intersections")

    return KeypointResult(
        src_pts=np.asarray(src, dtype=np.float64) if src else np.empty((0, 2)),
        dst_pts=np.asarray(dst, dtype=np.float64) if dst else np.empty((0, 2)),
        line_count=len(lines),
        field_coverage=0.0,
        yardline_angles=yardline_angles,
        reason_codes=reason_codes,
    )


def detect_keypoints(
    frame: np.ndarray, template: FieldTemplate | None = None
) -> KeypointResult:
    """Full single-frame detection: masks → Hough → cluster → correspondences.

    Requires OpenCV. Failures degrade to an empty :class:`KeypointResult`
    with a reason code rather than raising, so the calibrate stage can record
    ``analytics_safe=False`` instead of crashing the pipeline.
    """
    try:
        import cv2  # noqa: F401
    except Exception:
        return KeypointResult(
            src_pts=np.empty((0, 2)),
            dst_pts=np.empty((0, 2)),
            line_count=0,
            field_coverage=0.0,
            reason_codes=["cv2_unavailable"],
        )

    grass, coverage = grass_mask(frame)
    reason_codes: list[str] = []
    if coverage < 0.25:
        reason_codes.append("low_field_coverage")
    paint = white_paint_mask(frame, grass)
    lines = detect_hough_lines(paint)
    if len(lines) < 4:
        return KeypointResult(
            src_pts=np.empty((0, 2)),
            dst_pts=np.empty((0, 2)),
            line_count=len(lines),
            field_coverage=coverage,
            reason_codes=reason_codes + ["insufficient_lines"],
        )

    result = build_correspondences(lines, frame.shape[:2], template)
    result.field_coverage = coverage
    result.reason_codes = reason_codes + result.reason_codes
    return result


def diagnostics(result: KeypointResult) -> dict[str, Any]:
    """Serializable summary of a detection for logging / debugging."""
    return {
        "n_correspondences": int(len(result.src_pts)),
        "line_count": int(result.line_count),
        "field_coverage": float(result.field_coverage),
        "reason_codes": list(result.reason_codes),
    }
