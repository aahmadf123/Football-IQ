"""9-DoF Kalman smoother on the flattened homography (Issue #127).

The homography ``H_t`` is tracked as a 9-vector ``vec(H_t) ∈ ℝ⁹`` under a
constant-position (random-walk) model. Process noise is tuned per capture
regime — a bolted-down sideline camera drifts far less than an operator-flown
drone:

  σ_q = 0.001  for FIXED_SIDELINE
  σ_q = 0.02   for DRONE_FOLLOW

Measurement noise is scaled by per-frame calibration confidence so that
low-confidence anchors are trusted less. Pure NumPy — no filterpy/scipy
dependency — so it runs in any container with numpy.
"""

from __future__ import annotations

import numpy as np

# Per-regime process-noise standard deviation (see module docstring).
SIGMA_Q_FIXED_SIDELINE: float = 0.001
SIGMA_Q_DRONE_FOLLOW: float = 0.02

_STATE_DIM = 9


def process_noise_for_regime(regime: str) -> float:
    """Return σ_q for a capture regime, defaulting to the drone (looser) value."""
    if regime == "fixed_sideline":
        return SIGMA_Q_FIXED_SIDELINE
    return SIGMA_Q_DRONE_FOLLOW


class HomographyKalman:
    """Constant-position Kalman filter over ``vec(H)`` (row-major, 9-vector).

    Each homography is normalized to ``H[8] == 1`` before being folded in so
    the filter operates on a consistent scale.
    """

    def __init__(
        self,
        *,
        sigma_q: float = SIGMA_Q_DRONE_FOLLOW,
        sigma_r: float = 0.05,
    ) -> None:
        self.sigma_q = float(sigma_q)
        self.sigma_r = float(sigma_r)
        self.x: np.ndarray | None = None  # state estimate (9,)
        self.P = np.eye(_STATE_DIM) * 1.0  # covariance
        self._q = (self.sigma_q**2) * np.eye(_STATE_DIM)

    @staticmethod
    def _normalize(H: np.ndarray) -> np.ndarray:
        flat = np.asarray(H, dtype=np.float64).reshape(_STATE_DIM)
        if abs(flat[8]) > 1e-12:
            flat = flat / flat[8]
        return flat

    def update(self, H: np.ndarray, confidence: float = 1.0) -> np.ndarray:
        """Fold a measured homography in and return the smoothed 3×3 matrix.

        ``confidence`` in ``(0, 1]`` inflates the measurement noise for weak
        anchors: ``R = (sigma_r / max(confidence, 0.05))² I``.
        """
        z = self._normalize(H)
        conf = max(float(confidence), 0.05)
        R = ((self.sigma_r / conf) ** 2) * np.eye(_STATE_DIM)

        if self.x is None:
            # First measurement seeds the state directly.
            self.x = z.copy()
            self.P = R.copy()
            return self.x.reshape(3, 3)

        # Predict (F = I for a random walk).
        x_pred = self.x
        P_pred = self.P + self._q

        # Update (H_obs = I).
        S = P_pred + R
        K = P_pred @ np.linalg.inv(S)
        self.x = x_pred + K @ (z - x_pred)
        self.P = (np.eye(_STATE_DIM) - K) @ P_pred

        out = self.x.copy()
        if abs(out[8]) > 1e-12:
            out = out / out[8]
        self.x = out
        return out.reshape(3, 3)

    def state_vector(self) -> list[float] | None:
        """Current 9-vector state as a JSON-serializable list (or ``None``)."""
        if self.x is None:
            return None
        return [float(v) for v in self.x]


def smooth_series(
    homographies: list[np.ndarray],
    *,
    regime: str = "drone_follow",
    confidences: list[float] | None = None,
) -> list[np.ndarray]:
    """Kalman-smooth a sequence of per-window homographies.

    Returns a list of smoothed 3×3 matrices the same length as the input.
    ``None`` entries (failed windows) are skipped but preserve the running
    estimate, so the output reuses the last smoothed matrix for those slots.
    """
    sigma_q = process_noise_for_regime(regime)
    kf = HomographyKalman(sigma_q=sigma_q)
    out: list[np.ndarray] = []
    last: np.ndarray | None = None
    for i, H in enumerate(homographies):
        if H is None:
            out.append(last if last is not None else np.eye(3))
            continue
        conf = 1.0 if confidences is None else float(confidences[i])
        last = kf.update(H, conf)
        out.append(last)
    return out
