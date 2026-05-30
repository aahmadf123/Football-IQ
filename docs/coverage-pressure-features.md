# Coverage GNN + pre-snap pressure: shared spatial feature schema

Status: implemented (Issues [#139](https://github.com/aahmadf123/Football-IQ/issues/139)
coverage GNN with uncertainty, [#140](https://github.com/aahmadf123/Football-IQ/issues/140)
pre-snap pressure, [#146](https://github.com/aahmadf123/Football-IQ/issues/146)
calibrated uncertainty). Offline data: [#164](https://github.com/aahmadf123/Football-IQ/issues/164).

This document is the contract for the **shared spatial / graph feature schema**
that the coverage classifier and the pre-snap pressure predictor both build on,
and for how each surfaces **calibrated uncertainty**. The implementation lives in
`gpu-worker/pipeline/spatial/`, `gpu-worker/pipeline/coverage/`,
`gpu-worker/pipeline/pressure/`, and `gpu-worker/pipeline/calibration/`.

## 1. Why one schema

Coverage (#139) keys on **defenders** as graph nodes; pressure (#140) keys on
**OL/DL alignment** at the snap. Both need the same primitives computed the same
way — field-frame position, depth behind the LOS, speed, leverage, nearest
receiver — so they share one module, `pipeline.spatial.feature_schema`. A change
to the field-frame contract or a node feature lands in one place and bumps
`SCHEMA_VERSION`.

## 2. Coordinate-frame contract (no clean-coordinate assumption)

The schema operates **only** on the calibrated field-yard frame produced by the
routed calibration / detection / tracking stages (#127 / #128 / #129). Every
builder routes through `require_field_frame(calibration_confirmed)`:

- Callers pass the calibration stage's analytics-safe flag as
  `calibration_confirmed`.
- When it is `False` the builders raise `FieldFrameError` instead of silently
  treating raw pixel / uncalibrated coordinates as field yards.
- The coverage stage falls back to its legacy depth heuristic and flags the
  result **uncalibrated** when calibration is not confirmed; the pressure stage
  **suppresses** (it never guesses a probability on uncalibrated coordinates).

Big Data Bowl coordinates are *analogous but offline-only* (#164): clean NFL
tracking is not a substitute for confirmed Toledo calibration. A model trained
on BDB stays offline-pretraining/evaluation only until Toledo validation.

## 3. Node features (Issue #139 §5.2)

`NODE_FEATURE_NAMES` — canonical order, indexed by name, never by position:

| Feature | Meaning |
| --- | --- |
| `field_x`, `field_y` | calibrated field-yard position |
| `speed` | per-frame finite-difference speed (or the tracker's `speed`) |
| `depth_behind_los` | signed yards relative to the LOS (direction-aware) |
| `dist_to_nearest_receiver` | yards to the closest eligible receiver |
| `head_yaw_rad` | head-yaw from the pose stage (soft dependency; 0 when absent) |
| `leverage` | signed lateral leverage vs the nearest receiver (− = inside) |

`PlayerNode.has_pose` records whether the head-yaw signal was actually present so
downstream models can down-weight it rather than trust a defaulted 0.

## 4. Graph construction (edge contract)

`build_spatial_graph` connects nodes by **spatial proximity** (within
`EDGE_RADIUS_YARDS`, plus each node's `EDGE_MAX_DEGREE` nearest neighbours so the
graph never fragments) and stamps each edge with `EDGE_FEATURE_NAMES`:
`distance`, `delta_x`, `delta_y`, and `motion_cosine_similarity` (the cosine of
the two velocity vectors — the "motion similarity" half of #139's edges). Edges
are undirected (stored both ways). `SpatialGraph.to_dict()` is JSON-serialisable
for offline artifacts and the training harness.

## 5. Coverage classifier (#139)

`pipeline.coverage.gnn_classifier`:

- **9-class taxonomy** (`COVERAGE_CLASSES`): `cover_0`, `cover_1`, `cover_2_mof`,
  `cover_2_shell`, `cover_3`, `cover_4`, `man_free`, `bracket_match`, `cover_6`.
- `CoverageGNN` — one motion/proximity-weighted message-passing round
  (edge block → node block) + a mean/max graph readout into a learnable softmax
  head (the MLP output). Pure NumPy; `torch_geometric` is **not** a worker
  dependency. A full PyTorch-Geometric 3-layer GNN is the documented offline
  upgrade path — its exported logits/weights load through the same checkpoint
  contract.
- `DeterministicCoverageBaseline` — always-available heuristic over safety depth
  / box count / leverage that returns a valid 9-class distribution. It
  generalises the prior `stage_coverage` shell logic so the stage never
  regresses when no checkpoint is present.
- `coverage_bust_flag` — fires when any defender diverges
  > `BUST_DIVERGENCE_YARDS` (3 yd) from its snap position within
  `BUST_WINDOW_SECONDS` (0.3 s).
- Checkpoints load at runtime from `COVERAGE_GNN_MODEL` (no hard-coded path).
  Missing / malformed → baseline fallback, logged, no crash.

`stage_coverage` now emits, on the `coverage_shell` label:
`coverage_confidence`, `calibration_method`, `is_calibrated`, `experimental`,
the full class `probabilities`, `uncertainty`, the `model` that produced it, and
`coverage_bust_flag`.

## 6. Pre-snap pressure (#140)

`pipeline.pressure`:

- `extract_pressure_features` (snap frame): OL gap widths, DL gap alignment
  (A / B / C / edge), LB depth, blitz indicator (an off-ball LB crept within
  `_BLITZ_DEPTH_YD` of the LOS), rusher-vs-blocker differential, box count, and
  down-and-distance. Feature confidence degrades (never fabricates) when the
  front is not cleanly recovered.
- `PressureClassifier` predicts `P(QB pressured ≤ 2.5 s)`:
  - **Deterministic baseline** — a documented, hand-tuned logistic prior. Always
    flagged uncalibrated / experimental.
  - **Offline-trained model** — a logistic head + Platt calibrator loaded from
    `PRESSURE_MODEL`; reports `calibration_method="platt"` once calibrated.
- `stage_pressure` runs after `stage_oline`, suppresses without confirmed
  calibration, and writes a `pressure_prob` metric that is **always**
  `experimental_flag=True` / `analytics_safe=False` — exactly like the frontier
  metrics, so an unvalidated number is never stored as trusted analytics.

## 7. Calibrated uncertainty (#146)

`pipeline.calibration` provides the `CalibratedOutput` envelope every Phase-CV
classifier returns. It serialises to the #146 contract — `{value, confidence,
calibration_method}` — plus the full class distribution, normalised entropy, an
`is_calibrated` flag, and `experimental` (true whenever not calibrated). The
underlying Platt / isotonic scaling, ECE, Brier, and reliability-curve math is
re-exported from `pipeline.play_prediction.calibration` (one implementation, not
a fork); `TemperatureScaler` adds the multi-class post-hoc calibrator, and
`multiclass_ece` is the top-label ECE for the `ECE < 0.05` production gate.

Honesty rule: an output whose probabilities have **not** been run through a
fitted calibrator reports `calibration_method="uncalibrated"`,
`is_calibrated=False`, and `experimental=True`. The default no-checkpoint paths
for both coverage and pressure are therefore experimental until an
offline-trained, Toledo-validated, calibrated checkpoint is supplied.

## 8. Model-router decision (not routed)

Neither classifier is wired into `pipeline.model_router`, for the same reason as
the pre-snap run/pass predictor (#135/#136) and frontier analytics (#10): in
their default path they load **no heavy weights** and run identical deterministic
math in both priority buckets, consuming the *outputs* of the already-routed
stages. The optional checkpoints (`COVERAGE_GNN_MODEL`, `PRESSURE_MODEL`) are
small CPU-friendly NumPy artifacts that fall back to the deterministic path when
absent — mirroring `PLAY_PREDICTION_FORMATION_MODEL` / `REID_OCR_MODEL`. They
introduce no new `model_router` stage, do not appear in `DEFAULT_ROUTING`, and
do not touch `output_artifacts["model_routing"]`; the routing audit for the
routed stages is preserved untouched. If a future heavy GNN variant needs the
GPU it must be added to `DEFAULT_ROUTING` + `docs/model-routing.md` +
`gpu-worker/tests/test_model_router.py` and benchmarked before any same-session
use — see the "experimental → nightly" rule.

## 9. Offline training (#164)

`pipeline.coverage.train_coverage_gnn` is an **offline-only** harness: it fits
the coverage head on labelled coverage graphs, fits a temperature calibrator on
a held-out split, reports accuracy + ECE, and writes a checkpoint stamped
`offline-pretraining-evaluation-only`. BDB-derived checkpoints carry that marker
and the runtime surfaces it in the prediction `detail.provenance`. No production
BDB inference without Toledo validation; no weights are committed.
