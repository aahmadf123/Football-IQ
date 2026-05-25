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
| `embeddings` | `none`                       | `none`                  |

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
