"""Normalized DLT + RANSAC homography estimation (Issue #127 §7.1).

Pure-NumPy implementation so it is testable without OpenCV: the math core
is shared by both capture regimes (FIXED_SIDELINE and DRONE_FOLLOW). The
pipeline solves ``A h = 0`` via SVD on normalized point coordinates, then
wraps that in a RANSAC loop with a re-projection threshold (default 3 px).

The normalization (Hartley) is what makes the linear solution numerically
stable: translate each point set so its centroid is at the origin and scale
so the RMS distance to the origin is √2.
"""

from __future__ import annotations

import numpy as np

EPS = 1e-12


def normalize_points(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Hartley-normalize 2D points.

    Returns ``(normalized_pts, T)`` where ``T`` is the 3×3 similarity that
    maps the input points into the normalized frame (centroid at origin,
    RMS distance √2). ``normalized = (T @ homog(pts).T).T``.
    """
    pts = np.asarray(pts, dtype=np.float64)
    centroid = pts.mean(axis=0)
    shifted = pts - centroid
    mean_dist = float(np.sqrt((shifted**2).sum(axis=1)).mean())
    scale = np.sqrt(2.0) / mean_dist if mean_dist > EPS else 1.0
    T = np.array(
        [
            [scale, 0.0, -scale * centroid[0]],
            [0.0, scale, -scale * centroid[1]],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    homog = np.hstack([pts, np.ones((len(pts), 1))])
    normalized = (T @ homog.T).T[:, :2]
    return normalized, T


def dlt_homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray | None:
    """Estimate H mapping ``src`` → ``dst`` via normalized DLT.

    Requires at least 4 point correspondences. Returns a 3×3 homography
    normalized so ``H[2, 2] == 1``, or ``None`` if the system is degenerate.
    """
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    if len(src) < 4 or len(src) != len(dst):
        return None

    src_n, T_src = normalize_points(src)
    dst_n, T_dst = normalize_points(dst)

    rows: list[list[float]] = []
    for (x, y), (u, v) in zip(src_n, dst_n):
        rows.append([-x, -y, -1.0, 0.0, 0.0, 0.0, u * x, u * y, u])
        rows.append([0.0, 0.0, 0.0, -x, -y, -1.0, v * x, v * y, v])
    A = np.asarray(rows, dtype=np.float64)

    try:
        _, _, vh = np.linalg.svd(A)
    except np.linalg.LinAlgError:
        return None
    h = vh[-1].reshape(3, 3)

    # Denormalize: H = T_dst^-1 · H_n · T_src
    try:
        H = np.linalg.inv(T_dst) @ h @ T_src
    except np.linalg.LinAlgError:
        return None
    if abs(H[2, 2]) < EPS:
        return None
    return H / H[2, 2]


def reprojection_error(H: np.ndarray, src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Per-point Euclidean re-projection error ``||H·src - dst||`` (pixels/yards)."""
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    homog = np.hstack([src, np.ones((len(src), 1))])
    proj = (H @ homog.T).T
    w = proj[:, 2:3]
    w = np.where(np.abs(w) < EPS, EPS, w)
    proj_2d = proj[:, :2] / w
    return np.sqrt(((proj_2d - dst) ** 2).sum(axis=1))


def ransac_homography(
    src: np.ndarray,
    dst: np.ndarray,
    *,
    threshold: float = 3.0,
    max_iters: int = 500,
    seed: int | None = 0,
) -> tuple[np.ndarray | None, np.ndarray]:
    """Robustly estimate H with RANSAC over 4-point minimal samples.

    Args:
        src: ``(N, 2)`` source points (pixels).
        dst: ``(N, 2)`` destination points (field yards).
        threshold: inlier re-projection threshold (in ``dst`` units).
        max_iters: RANSAC iteration cap.
        seed: RNG seed for deterministic tests; ``None`` for nondeterministic.

    Returns ``(H, inlier_mask)``. ``H`` is refit on all inliers; ``None`` when
    fewer than 4 correspondences are supplied or no model is found.
    """
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    n = len(src)
    if n < 4 or n != len(dst):
        return None, np.zeros(n, dtype=bool)
    if n == 4:
        H = dlt_homography(src, dst)
        if H is None:
            return None, np.zeros(n, dtype=bool)
        err = reprojection_error(H, src, dst)
        return H, err <= threshold

    rng = np.random.default_rng(seed)
    best_inliers = np.zeros(n, dtype=bool)
    best_count = 0
    indices = np.arange(n)

    for _ in range(max_iters):
        sample = rng.choice(indices, size=4, replace=False)
        H = dlt_homography(src[sample], dst[sample])
        if H is None:
            continue
        err = reprojection_error(H, src, dst)
        inliers = err <= threshold
        count = int(inliers.sum())
        if count > best_count:
            best_count = count
            best_inliers = inliers
            if count == n:
                break

    if best_count < 4:
        return None, best_inliers
    # Refit on the consensus set.
    H = dlt_homography(src[best_inliers], dst[best_inliers])
    if H is None:
        return None, best_inliers
    return H, best_inliers
