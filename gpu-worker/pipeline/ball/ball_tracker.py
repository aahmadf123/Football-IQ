"""Kalman ball tracker (Issue #134).

The dedicated ball detector (``pipeline.detection.ball_detector``) is high-
precision but drops detections during occlusion, motion blur, and the small-
ball drone-follow regime. A constant-velocity Kalman filter over the 4-state
``[x, y, ẋ, ẏ]`` interpolates across these gaps so the trajectory fitter and
state machine see a continuous path.

The filter is unit-agnostic: feed it image pixels for the parabola fit, or
field-plane yards (after homography projection) for the field-distance and
state-machine logic. Pure NumPy — no weights, no GPU, no router stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import structlog

log = structlog.get_logger(__name__)

# Max consecutive missed frames the filter will coast through before it stops
# emitting (gap longer than this → ball considered lost, no interpolation).
DEFAULT_MAX_GAP: int = 15


@dataclass(frozen=True)
class BallTrackPoint:
    """One smoothed ball state."""

    frame: int
    x: float
    y: float
    vx: float
    vy: float
    observed: bool  # True if a real detection updated this frame

    @property
    def speed(self) -> float:
        return float(np.hypot(self.vx, self.vy))


class BallKalman2D:
    """Constant-velocity Kalman filter for a 2-D point with velocity."""

    def __init__(
        self,
        *,
        process_var: float = 1.0,
        measurement_var: float = 4.0,
    ) -> None:
        self._x = np.zeros((4, 1), dtype=np.float64)
        self._P = np.eye(4, dtype=np.float64) * 1000.0
        self._q = float(process_var)
        self._H = np.array(
            [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float64
        )
        self._R = np.eye(2, dtype=np.float64) * float(measurement_var)
        self._initialised = False

    def _F(self, dt: float) -> np.ndarray:
        return np.array(
            [
                [1.0, 0.0, dt, 0.0],
                [0.0, 1.0, 0.0, dt],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )

    def _Q(self, dt: float) -> np.ndarray:
        # White-noise-acceleration discretisation.
        dt2, dt3, dt4 = dt * dt, dt**3, dt**4
        return self._q * np.array(
            [
                [dt4 / 4, 0.0, dt3 / 2, 0.0],
                [0.0, dt4 / 4, 0.0, dt3 / 2],
                [dt3 / 2, 0.0, dt2, 0.0],
                [0.0, dt3 / 2, 0.0, dt2],
            ],
            dtype=np.float64,
        )

    def init(self, x: float, y: float) -> None:
        self._x = np.array([[x], [y], [0.0], [0.0]], dtype=np.float64)
        self._P = np.eye(4, dtype=np.float64) * 10.0
        self._initialised = True

    def predict(self, dt: float = 1.0) -> tuple[float, float, float, float]:
        F = self._F(dt)
        self._x = F @ self._x
        self._P = F @ self._P @ F.T + self._Q(dt)
        return self.state

    def update(self, x: float, y: float) -> None:
        z = np.array([[x], [y]], dtype=np.float64)
        y_res = z - self._H @ self._x
        S = self._H @ self._P @ self._H.T + self._R
        K = self._P @ self._H.T @ np.linalg.inv(S)
        self._x = self._x + K @ y_res
        self._P = (np.eye(4) - K @ self._H) @ self._P

    @property
    def state(self) -> tuple[float, float, float, float]:
        return (
            float(self._x[0, 0]),
            float(self._x[1, 0]),
            float(self._x[2, 0]),
            float(self._x[3, 0]),
        )

    @property
    def initialised(self) -> bool:
        return self._initialised


def track_ball(
    observations: dict[int, tuple[float, float]],
    fps: float = 30.0,
    *,
    max_gap: int = DEFAULT_MAX_GAP,
    process_var: float = 1.0,
    measurement_var: float = 4.0,
) -> list[BallTrackPoint]:
    """Smooth + gap-fill ball observations into a per-frame track.

    Args:
        observations: ``frame_number → (x, y)`` ball detections (sparse).
        fps: Frame rate, used only to scale the constant-velocity ``dt``.
        max_gap: Coast at most this many frames without a detection; a longer
            gap ends the track (no fabricated positions across long dropouts).

    Returns:
        One :class:`BallTrackPoint` per frame from the first to the last
        observation, with ``observed`` marking real-detection frames.
    """
    if not observations:
        return []
    frames = sorted(observations)
    kf = BallKalman2D(process_var=process_var, measurement_var=measurement_var)
    kf.init(*observations[frames[0]])

    out: list[BallTrackPoint] = []
    start, end = frames[0], frames[-1]
    last_obs_frame = start
    prev_frame = start
    out.append(BallTrackPoint(start, *observations[start], 0.0, 0.0, observed=True))

    for f in range(start + 1, end + 1):
        if f - last_obs_frame > max_gap:
            # Gap too long: stop interpolating until the next detection.
            if f in observations:
                kf.init(*observations[f])
                last_obs_frame = f
                prev_frame = f
                out.append(
                    BallTrackPoint(f, *observations[f], 0.0, 0.0, observed=True)
                )
            continue
        # Step in frame units so the Kalman velocity is px/frame; convert to
        # px/s (or yd/s) on output by multiplying by fps.
        dt_frames = float(f - prev_frame) or 1.0
        kf.predict(dt_frames)
        prev_frame = f
        if f in observations:
            kf.update(*observations[f])
            last_obs_frame = f
        px, py, vx, vy = kf.state
        out.append(
            BallTrackPoint(f, px, py, vx * fps, vy * fps, observed=f in observations)
        )

    log.info(
        "ball_track",
        frames=len(out),
        observed=sum(1 for p in out if p.observed),
        interpolated=sum(1 for p in out if not p.observed),
    )
    return out


def observations_from_detections(
    ball_detections: dict[str, list[dict[str, Any]]],
) -> dict[int, tuple[float, float]]:
    """Reduce per-frame ball detections to one centroid per frame.

    Picks the highest-confidence ball per frame (the detector emits at most a
    few candidates). Returns ``frame_number → (cx, cy)`` in the detector's
    pixel space.
    """
    out: dict[int, tuple[float, float]] = {}
    for frame_str, dets in ball_detections.items():
        balls = [d for d in dets if d.get("class") == "ball" and d.get("bbox")]
        if not balls:
            continue
        best = max(balls, key=lambda d: float(d.get("confidence", 0.0)))
        x1, y1, x2, y2 = best["bbox"]
        out[int(frame_str)] = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    return out
