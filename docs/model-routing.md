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
| `detect`     | `yolov8n`                    | `yolov8m`               |
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
