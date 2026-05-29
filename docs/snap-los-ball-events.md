# Snap / LOS detection + ball state machine (Issues #132, #134)

This document describes the Phase-CV event layer added in the GPU worker: the
multi-signal Bayesian snap detector, the line-of-scrimmage (LOS) estimator, the
Kalman ball tracker, the ball trajectory fitter, the ball state machine, and
throw/catch attribution. They are implemented together so event *timing* (the
snap frame) and ball *semantics* (throw → in-air → catch) stay consistent for
downstream pre-snap and analytics work.

## Where it lives

| Concern | Module |
|---|---|
| VTI optical-flow snap-burst signal | `gpu-worker/pipeline/events/optical_flow_vti.py` |
| Multi-signal Bayesian snap detector | `gpu-worker/pipeline/events/snap_detector.py` |
| LOS estimator | `gpu-worker/pipeline/events/los_estimator.py` |
| Kalman ball tracker | `gpu-worker/pipeline/ball/ball_tracker.py` |
| Trajectory fit + field projection | `gpu-worker/pipeline/ball/trajectory_fitter.py` |
| Ball state machine | `gpu-worker/pipeline/ball/ball_state_machine.py` |
| Throw / catch attribution | `gpu-worker/pipeline/ball/attribution.py` |
| Stage wiring + persistence | `gpu-worker/pipeline/stage_events.py` |

## Not a routed model stage

These are deterministic OpenCV / NumPy / pure-Python algorithms that consume the
**outputs** of the routed stages (`detect`, `ball`, `track`, `calibrate`,
`pose`). They run no neural inference and load no weights, so they intentionally
do **not** register a new `model_router` stage and do not appear in
`DEFAULT_ROUTING`. The dedicated ball *detector* (the `ball` stage) is already
routed; trajectory fitting and state classification sit downstream of it.

## Snap detection (Issue #132)

Naive-Bayes fusion of up to five independent signals into a calibrated per-frame
probability:

```
logit P(snap) = logit P0 + Σ_i  w_i · strength_i(frame)
```

with base rate `P0 = 0.02`. Each signal yields a continuous strength in
`[0, 1]`; a missing signal (no pose, no ball, no frames) simply contributes
nothing, so the detector degrades gracefully rather than failing.

| # | Signal | Source | Notes |
|---|---|---|---|
| 1 | VTI optical-flow burst | dense Farneback flow in the LOS band | Variable-Threshold-Image active-cell spike (Oregon State IAAI-2013) |
| 2 | OL stance break | pose torso-angle change > 30° over ≤ 3 frames across ≥ 4 OL | needs `stage_pose` output |
| 3 | QB hand-under-centre | pose wrist velocity down/back | shotgun snaps lack this; other signals carry |
| 4 | Centre-ball separation | ball leaves the centre at > 10 yd/s | needs ball detector |
| 5 | Formation-stability prior | players static ≥ 0.5 s then burst | median over players → robust to a lone motion man |

Weights are tuned so **no single signal alone crosses `P = 0.5`** (corroboration
required → low false-positive rate). The per-signal strengths at the chosen snap
frame are stored for explainability. When no frame crosses threshold the stage
does **not** assert a snap unless the best probability clears a low floor
(0.2), in which case it is emitted with `low_confidence = true` — we never
present an undefended detection as a confident one.

### LOS estimator

1. **OL-cluster centroid (primary).** 1-D DBSCAN (ε = 2 yd, min_samples = 5) on
   player field-x at the snap; pick the tightest line, return its mean x.
2. **Ball position (fallback).** Ball field-x at the snap.
3. **Recursive Bayesian propagation.** Shift the previous play's LOS by the net
   gain and fuse with the new measurement by a confidence-weighted gain.

## Ball trajectory + state machine (Issue #134)

* **Kalman tracker** — constant-velocity `[x, y, ẋ, ẏ]`; interpolates across
  detection gaps (default ≤ 15 frames) and reports per-second velocity.
* **Trajectory fit** — image-y parabola `y(t) = y0 + v_y·t − ½·α·t²`; field-plane
  throw distance via the calibration homography; ECC affine compensation for the
  `drone_follow` regime; a physics regulariser rejects fits outside the 18–32
  ft/s, 30–45° throw envelope.
* **State machine**

  ```
  PRE_SNAP → SNAP → (CARRIED | THROWN)
      THROWN:  IN_AIR → (CAUGHT | INCOMPLETE | INT | FUMBLE)
      CARRIED: RUNNING → (TACKLE | OOB | TD | FUMBLE)
  ```

  `SNAP → THROWN` fires when the ball exceeds the running-speed threshold **and**
  leaves the QB region; `IN_AIR → CAUGHT` when the ball settles near a player
  (a defender there ⇒ `INT`, nobody ⇒ `INCOMPLETE`). `validate()` checks the
  emitted sequence against the legal-transition table.

* **Attribution** — throw → nearest player to the ball at the first airborne
  (release) frame within 3 yd; catch → player whose velocity-predicted position
  best intersects the landing point, falling back to nearest at the catch frame.

## Persistence — existing schema, no migration

Events are written through the existing `POST /api/v1/events` endpoint and the
`events` table. The rich payload is stored in the existing **`attributes` JSON
column**, so this work needs **no Alembic migration** and no backend code
change:

| Event | Key attributes |
|---|---|
| `snap` | `p_snap`, `low_confidence`, `signals_present`, `signal_strengths`, `los_x`, `los_confidence`, `los_method`, `los_support` |
| `throw` | `qb_id`, `throw_distance_yd`, `hang_time_s`, `apex_y_image`, `ball_state` |
| `catch` / `interception` | `receiver_id`, `throw_distance_yd`, `hang_time_s`, `ball_state` |
| `tackle` / `out_of_bounds` / `touchdown` / `fumble` / `incomplete` | `ball_state` |

> **Migration alternative.** Issues #132/#134 sketch dedicated columns
> (`los_x`, `los_confidence`, `throw_distance_yd`, `hang_time_s`, `apex_y_field`,
> `qb_id`, `receiver_id`). We deliberately use the `attributes` JSON instead to
> ship the algorithms with zero schema risk and full reversibility. Promoting
> the hottest fields to typed/indexed columns is a clean follow-up (a forward +
> backward Alembic migration that backfills from `attributes`) if query
> patterns demand it. `apex_y_image` is named honestly: a single uncalibrated
> camera cannot recover true field-frame apex *height*, so we expose the image-y
> apex, not a fabricated `apex_y_field`.

Every auto-detected event carries `attributes.source = "model"`; coaches can
PATCH any event via the API. No synthetic/mock event is ever presented as a
confirmed result.

## Downstream consumption

`stage_events.run()` returns the event dicts under the `events` key (plus a
`snap_frame` / `los_x` summary), which the dispatcher forwards as
`input_artifacts["events"]` to `stage_labels`, `stage_metrics`, `stage_oline`,
and `stage_routes`. Those stages already key off `event_type == "snap"` and the
snap `frame_number`, so pre-snap formation/motion analysis can consume the new,
more accurate snap timing and the `los_x` field without further changes.

## Inputs the stage accepts

`stage_events.run()` stays backward compatible: with only `detections` it runs
the legacy bbox-displacement heuristic. The multi-signal path activates when
`tracklets` (with field coordinates) are supplied, and uses whatever of
`ball_detections`, `pose_by_frame`, `ol_track_ids`, `qb_track_id`,
`center_track_id`, `defender_ids`, `homography`, `los_band_px`, `los_prior`,
`end_of_play_frame`, and `goal_line_x` are present.
