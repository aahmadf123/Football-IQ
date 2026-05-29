"""Line-of-scrimmage estimator (Issue #132).

Runs immediately after the snap detector and produces the LOS as a field-x
coordinate (NCAA template yards, Issue #127) with a confidence in ``[0, 1]``.
Three methods, tried in order:

* **Method 1 — OL-cluster centroid (primary).** At the snap frame the five
  interior linemen form a tight vertical line: small spread in field-x, large
  spread in field-y. We DBSCAN player field-x values (ε = 2 yd, min_samples =
  5) and pick the densest, tightest cluster, returning its mean x. Confidence
  scales with how tight the cluster is.
* **Method 2 — ball position (fallback).** When no 5-man line is found (e.g.
  occlusion), use the ball's field-x at the snap from the ball tracker.
* **Method 3 — recursive Bayesian propagation.** Between plays the LOS is
  propagated from the previous play's end position plus the gained yards,
  fused with the new measurement by a Kalman-style gain.

Pure NumPy / Python — no model weights, no router stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import structlog

log = structlog.get_logger(__name__)

DBSCAN_EPS_YD: float = 2.0
DBSCAN_MIN_SAMPLES: int = 5
# A line tighter than this (std of field-x, yd) is treated as full confidence.
TIGHT_LINE_STD_YD: float = 1.0


@dataclass(frozen=True)
class LOSEstimate:
    """Estimated line of scrimmage."""

    los_x: float
    confidence: float
    method: str  # "ol_cluster" | "ball" | "bayesian" | "none"
    support: int = 0  # players in the chosen cluster (method 1)


def _dbscan_1d(values: list[float], eps: float, min_samples: int) -> list[list[int]]:
    """Tiny 1-D DBSCAN returning lists of indices for each dense cluster.

    Sorting makes neighbourhood queries O(n log n); we only need the dense
    "core" runs, so a single sorted sweep with an eps-gap split, then a
    min-samples filter, reproduces DBSCAN's clusters on a line without sklearn.
    """
    if len(values) < min_samples:
        return []
    order = sorted(range(len(values)), key=lambda i: values[i])
    clusters: list[list[int]] = []
    current: list[int] = [order[0]]
    for prev, idx in zip(order[:-1], order[1:]):
        if values[idx] - values[prev] <= eps:
            current.append(idx)
        else:
            clusters.append(current)
            current = [idx]
    clusters.append(current)
    return [c for c in clusters if len(c) >= min_samples]


def _positions_at_frame(
    tracklets: list[dict[str, Any]], frame: int
) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for t in tracklets:
        for pt in t.get("track_points", []):
            if pt.get("frame_number") == frame:
                fx, fy = pt.get("field_x"), pt.get("field_y")
                if fx is not None and fy is not None:
                    out.append((float(fx), float(fy)))
                break
    return out


class LOSEstimator:
    """Estimate LOS from tracklets, with ball fallback and play-to-play prior."""

    def __init__(
        self,
        *,
        eps_yd: float = DBSCAN_EPS_YD,
        min_samples: int = DBSCAN_MIN_SAMPLES,
    ) -> None:
        self.eps_yd = eps_yd
        self.min_samples = min_samples

    def estimate(
        self,
        tracklets: list[dict[str, Any]],
        snap_frame: int,
        *,
        ball_field_x: float | None = None,
    ) -> LOSEstimate:
        """Primary OL-cluster estimate; ball fallback; else low-confidence."""
        positions = _positions_at_frame(tracklets, snap_frame)
        xs = [p[0] for p in positions]
        clusters = _dbscan_1d(xs, self.eps_yd, self.min_samples)

        if clusters:
            # Prefer the tightest line (smallest field-x std).
            best = min(clusters, key=lambda c: float(np.std([xs[i] for i in c])))
            cluster_xs = [xs[i] for i in best]
            mean_x = float(np.mean(cluster_xs))
            std_x = float(np.std(cluster_xs))
            confidence = float(np.clip(TIGHT_LINE_STD_YD / (std_x + TIGHT_LINE_STD_YD), 0.0, 1.0))
            log.info(
                "los_estimate",
                method="ol_cluster",
                los_x=round(mean_x, 3),
                support=len(best),
                confidence=round(confidence, 3),
            )
            return LOSEstimate(mean_x, confidence, "ol_cluster", support=len(best))

        if ball_field_x is not None:
            log.info("los_estimate", method="ball", los_x=round(ball_field_x, 3))
            return LOSEstimate(float(ball_field_x), 0.5, "ball")

        log.warning("los_estimate_failed", snap_frame=snap_frame, players=len(positions))
        return LOSEstimate(50.0, 0.0, "none")

    def propagate(
        self,
        prior: LOSEstimate,
        measured: LOSEstimate,
        *,
        gain_yards: float = 0.0,
    ) -> LOSEstimate:
        """Method 3 — recursive Bayesian fuse of a propagated prior + measurement.

        ``gain_yards`` is the net yardage from the previous play (positive =
        offence advanced toward the opponent end zone, i.e. increasing field-x
        in the template). The prior is shifted by the gain, then fused with the
        new measurement using a confidence-weighted (Kalman-style) gain.
        """
        predicted_x = prior.los_x + gain_yards
        # Confidence-weighted blend; the more confident source dominates.
        w_pred = max(prior.confidence, 1e-3)
        w_meas = max(measured.confidence, 1e-3)
        fused_x = (w_pred * predicted_x + w_meas * measured.los_x) / (w_pred + w_meas)
        fused_conf = float(np.clip(1.0 - (1.0 - w_pred) * (1.0 - w_meas), 0.0, 1.0))
        log.info(
            "los_propagate",
            predicted_x=round(predicted_x, 3),
            measured_x=round(measured.los_x, 3),
            fused_x=round(fused_x, 3),
            fused_conf=round(fused_conf, 3),
        )
        return LOSEstimate(fused_x, fused_conf, "bayesian")
