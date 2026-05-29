# Model Routing

Football-IQ's GPU worker chooses model variants per pipeline stage based on
the priority of the processing job. Same-session jobs (period-break clips,
priority `10`) must hit the 5–10 minute feedback window, so they route to
lighter variants. Nightly jobs (priority `0`) can spend more compute for
higher quality.

Routing lives in `gpu-worker/pipeline/model_router.py`. Stages call
`select_model(stage, priority)` and get back a variant identifier.

## Default routing table

| Stage        | Same-session (priority ≥ 10) | Nightly (priority < 10) |
| ------------ | ---------------------------- | ----------------------- |
| `segment`    | `optical-flow-fast`          | `optical-flow-fast`     |
| `calibrate`  | `calib-hough-dlt`            | `calib-hough-dlt-kalman`|
| `detect`     | `yolov8n`                    | `yolov8m`               |
| `ball`       | `yolov8n-ball`               | `yolov8n-ball`          |
| `track`      | `iou-tracker`                | `iou-tracker`           |
| `reid`       | `jersey-ocr`                 | `jersey-ocr`            |
| `pose`       | `rtmpose-t`                  | `rtmpose-m`             |
| `render`     | `ffmpeg-overlay`             | `ffmpeg-overlay`        |
| `embeddings` | `none`                       | `play-embed-clip-vitb32-baseline` |

The pose row is the contract preserved from issue #16: same-session pose
jobs route to RTMPose-tiny (~1000 FPS on a GTX 1660 Ti), nightly pose jobs
route to RTMPose-medium (~430 FPS).

## Which variants are safe for same-session use

A variant is "same-session safe" if a clip-length job completes inside the
period-break window on the production GPU. Today that means:

- Detection: YOLOv8n is the cap. Anything larger goes to nightly.
- Pose: RTMPose-tiny only. Heavier RTMPose / ViTPose variants are nightly.
- Segment / track / reid / render: current defaults are already fast
  enough that the same variant runs for both buckets.
- Experimental models (e.g. anything queued for issues #74–#76) must
  default to nightly until benchmarked.

When in doubt, route experimental models to `nightly` and let them prove
out before promoting them to `same_session`.

The router maintains `NIGHTLY_ONLY_VARIANTS` (currently `{"sam3.1",
"sam3-mask-tracker", "play-embed-clip-vitb32-baseline"}`). Any routing
config — env override or otherwise — that tries to place one of these
in the same-session bucket is rejected at load time and the bucket
falls back to the bundled default. This is the hard guardrail behind
the "experimental models default to nightly" rule above.

## Detection: players, ball, officials (Issues #128 / #133 / #148)

Detection is **regime-aware**: it branches on the `capture_regime` detected at
ingest (Issue #126), exactly like `calibrate`. The model router still owns the
*model* choice; the *slicing strategy* is chosen at the stage call site from
the regime, so `select_model` stays purely priority-keyed.

| Stage | What the router picks | `drone_follow` strategy | `fixed_sideline` / `unknown` |
| ----- | --------------------- | ----------------------- | ---------------------------- |
| `detect` (player) | `yolov8n` / `yolov8m` | dual-resolution + SAHI 400 px tiles (0.2 overlap) — recovers 30–80 px players | base detector, full frame |
| `ball` | `yolov8n-ball` (dedicated nano model) | SAHI 128 px tiles (0.2 overlap) — recovers the 6–18 px ball | base detector, full frame (~3× faster) |

- **Why player detect stays `yolov8n`/`yolov8m`.** SAHI and dual-resolution
  are *inference strategies* wrapped around the router-resolved base detector
  (`pipeline.detection.sahi_wrapper`, `pipeline.detection.dual_res_merger`),
  not new variants. The same-session VRAM ceiling keeps YOLOv8n as the
  same-session cap; YOLO11m / RF-DETR-L (Issue #128) are future variants that
  must clear a benchmark before promotion, per the "experimental → nightly"
  rule above. Wrapping a router-resolved adapter (never a raw YOLO handle)
  preserves same-session safety.
- **Ball is a separate model, not a player class** (Issue #133): the
  player/ball class imbalance is too severe for a shared head. `ball` runs the
  same nano model in both priority buckets; SAHI is gated by regime, not
  priority, and stays under the 1.5 GB same-session add-on budget. The ball
  variant is **not** on `NIGHTLY_ONLY_VARIANTS`.
- **Official suppression** (Issue #148): striped officials are relabeled
  `class = "official"` (and off-field figures `"sideline"` when a field
  polygon is supplied) by `pipeline.detection.official_suppressor`. It
  relabels — never deletes — so a false positive costs a relabel, not a lost
  player. `stage_labels` filters `official` / `sideline` before formation,
  personnel, and team analysis.

The per-job audit records the model choices in
`output_artifacts["model_routing"]` (`{"detect": ..., "ball": ...}`) and the
regime/slicing detail in `output_artifacts["detection_strategy"]`.

## Calibration variants (Issue #127)

The `calibrate` stage is regime-aware (it branches on the `capture_regime`
detected at ingest, Issue #126) and pixel-only — both variants are pure
OpenCV/NumPy paths, so neither is on the `NIGHTLY_ONLY_VARIANTS` guardrail:

- `calib-hough-dlt` (same-session): white-paint detection → Hough →
  angle clustering → labeled yard-line correspondences → normalized
  DLT + RANSAC, with a 5-component confidence score. Fast enough for the
  period-break window.
- `calib-hough-dlt-kalman` (nightly): the same detection core plus a
  9-DoF Kalman smoother over the per-window homography series for
  `drone_follow` clips, and chained-ECC drift (Issue #138) as the
  temporal-stability signal.

For `fixed_sideline` (game) film the camera is effectively bolted down, so a
single homography is fit once on the cleanest frame and flagged
`is_game_anchor`; same-session jobs can reuse that cached anchor instead of
recomputing. The deep-keypoint upgrade (PnLCalib / No-Bells-Just-Whistles)
referenced in Issue #127 is a future nightly-only variant and is **not** yet
bundled. See [`docs/calibration-contract.md`](calibration-contract.md) for the
full calibration contract.

## Nightly-only: play embeddings (Issue #8)

`embeddings` is a nightly-only stage. Same-session jobs return the
sentinel `"none"` so the embed stage is a no-op inside the period-break
window — the "find me reps like this" coach flow operates on
previously-ingested clips, so there is no value in spending
period-break GPU budget on a new clip the coach hasn't watched yet.

The nightly variant is `play-embed-clip-vitb32-baseline`. It fits in
~1.5 GB VRAM (CLIP ViT-B/32 + a small structured projector) so it
cohabitates the 16 GB nightly bucket comfortably with YOLOv8m +
RTMPose-m. SAM 3.1 (when `ENABLE_SAM3_NIGHTLY=1`) and `stage_embed`
must not share a job slot — schedule them in separate slots to stay
under the ceiling. See `docs/embeddings-architecture.md` §11 for the
full rationale.

## Experimental nightly: SAM 3.1 (Issue #74)

Set `ENABLE_SAM3_NIGHTLY=1` in the worker env to upgrade the nightly
buckets for `detect` and `track`:

| Stage | Same-session | Nightly (flag off) | Nightly (flag on) |
| ----- | ------------ | ------------------ | ----------------- |
| `detect` | `yolov8n` | `yolov8m` | `sam3.1` |
| `track`  | `iou-tracker` | `iou-tracker` | `sam3-mask-tracker` |

The flag only affects the nightly bucket; same-session always uses
YOLOv8n + IoU regardless of its value. SAM 3.1 weights are gated on
Hugging Face — the worker reads `HF_TOKEN` at runtime to download them
and logs a warning if the token is absent. See
`reports/phase2-issue74-sam3-eval.md` for the eval harness and
promotion criteria.

## Overriding routing

Set `MODEL_ROUTING_CONFIG` to the path of a JSON file shaped like
`gpu-worker/pipeline/model_routing.json`. Partial overrides are merged on
top of `DEFAULT_ROUTING`, so a config only has to name the stages it
changes.

```json
{
  "detect": {"same_session": "yolov8s", "nightly": "yolov8m"}
}
```

If the file is missing or malformed the worker logs a warning and falls
back to the defaults — it does not crash.

## Audit trail

Every completed job records the routing decision in
`processing_jobs.output_artifacts["model_routing"]` as a `{stage:
variant}` dict. Inspect it to confirm which variant served a clip:

```sql
SELECT id, job_type, priority, output_artifacts->'model_routing'
FROM processing_jobs
WHERE id = '...';
```

This is additive — existing artifact keys are untouched.

## Unknown stages

`select_model("not-a-stage", priority)` returns the module-level
`UNKNOWN_STAGE_FALLBACK` string (`"default"`) and logs a
`model_router_unknown_stage` warning. It does not raise, so a typo in a
job message never fails a pipeline outright.
