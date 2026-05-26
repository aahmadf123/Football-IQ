# Phase 2.5 — Issue #74 Eval Notes: SAM 3.1 vs YOLO + IoU

**Status:** experimental nightly path landed; same-session path unchanged.
**Last updated:** May 2026.

---

## Scope

Issue #74 introduces Meta SAM 3.1 (loaded via Ultralytics >= 8.3.237) as
an *experimental nightly* detector + mask-aware tracker alongside the
existing YOLOv8 + IoU same-session path. The deliverable is:

1. Adapter modules (`detector_models.py`, `tracker_models.py`) mirroring
   the `pose_estimator.py` pattern.
2. Detection/tracklet schema extended with an **optional** `mask` field
   so downstream stages remain backward compatible.
3. `model_router` keeps SAM 3.1 strictly on the nightly bucket — even a
   misconfigured `MODEL_ROUTING_CONFIG` cannot leak it into same-session.
4. Eval harness comparing both stacks on the same input.

## How the eval is run

`gpu-worker/eval/eval_sam3_vs_yolo.py` runs both stacks on the same set
of clips and emits a JSON report.

```bash
# Real footage — requires HF_TOKEN with access to facebook/sam3.
python -m eval.eval_sam3_vs_yolo \
    --clip-dir data/eval-clips/sample/ \
    --frame-step 3 \
    --out reports/phase2-issue74-sam3-eval.json

# Synthetic CI path (no weights / no GPU).
python -m eval.eval_sam3_vs_yolo --synthetic --out /tmp/eval.json
```

### Detection metrics

| Metric | Definition |
| --- | --- |
| `frame_coverage` | Fraction of sampled frames with at least one detection. |
| `mean_detections_per_frame` | Throughput proxy — too high suggests noise. |
| `mean_confidence` | Confidence score across all detections. |
| `mask_coverage` | Fraction of detections carrying the optional `mask` field. |

### Tracking-stability metrics

| Metric | Definition |
| --- | --- |
| `track_count` | Total tracks emitted across the clip. |
| `mean_track_length` | Frames per track — higher = fewer fragments. |
| `max_track_length` | Longest contiguous track. |
| `fragmentation_index` | `track_count / unique_player_estimate` — closer to 1 is better. |
| `short_track_fraction` | Tracks shorter than 5 frames; ID-switch proxy. |

## Synthetic CI run (no weights)

The synthetic path is built on `StubDetector` so CI can exercise the
schema and routing plumbing without the gated SAM weights. The numbers
below confirm the pipeline runs end-to-end and that masks propagate
through tracklets when present.

| Variant | Tracker | Tracks | Mean len | Mask coverage |
| --- | --- | --- | --- | --- |
| `yolov8n` | `iou-tracker` | 11 | 40.0 | 0.0% |
| `sam3.1`  | `iou-tracker` | 11 | 40.0 | 100.0% |
| `sam3.1`  | `sam3-mask-tracker` | 11 | 40.0 | 100.0% |

> Synthetic mode is for plumbing verification only — it does not reflect
> real model quality. Real-clip numbers are filled in by the nightly
> eval workflow once `HF_TOKEN` is provisioned.

## Real-clip results

> **TODO:** populate from the first nightly eval against
> `data/eval-clips/manifest.csv` once Hugging Face access for
> `facebook/sam3` is granted to the CI service account.

Reserved table to be filled by the nightly job:

| Variant | Tracker | Mean conf | Frame coverage | Mean track len | Fragmentation |
| --- | --- | --- | --- | --- | --- |
| `yolov8n` | `iou-tracker` | TBD | TBD | TBD | TBD |
| `sam3.1`  | `iou-tracker` | TBD | TBD | TBD | TBD |
| `sam3.1`  | `sam3-mask-tracker` | TBD | TBD | TBD | TBD |

## Promotion criteria (gate to same-session)

SAM 3.1 stays in the nightly bucket until **all** of the following hold
on the eval clips:

- Frame coverage parity with YOLOv8n (within 2 percentage points).
- Mean track length at least matches YOLO + IoU.
- Fragmentation index ≤ 1.1× YOLO + IoU.
- 95th-percentile latency fits inside the period-break budget on the
  production GPU. Until SAM 3.1-distilled lands this is unlikely;
  promotion is therefore expected to come via a future distilled variant
  rather than the base SAM 3.1 weights.

`model_router.NIGHTLY_ONLY_VARIANTS` enforces the policy in code: a
config override that puts `sam3.1` or `sam3-mask-tracker` in the
same-session bucket is rejected at load time. Promotion will require
removing the entry from that set and re-running this eval.

## License + weight policy

- Weights live in `facebook/sam3` on Hugging Face under Meta's
  research/non-commercial license — see `LICENSES.md`.
- `HF_TOKEN` is provided as a GitHub Actions secret; weights download
  at runtime and are never committed.
- `.pt` / `.pth` files are in `.gitignore`; the CI license-allowlist
  check fails on any new model dep not added to `LICENSES.md`.
