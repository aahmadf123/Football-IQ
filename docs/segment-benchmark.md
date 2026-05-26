# Phase 2.5 — Play-Boundary Segmentation Benchmark (Issue #75)

**Status:** spike complete. Optical-flow stays the same-session default; a
rules+ML `LearnedPlaySegmenter` ships behind an env var as the candidate
for promotion. SportsBD is **not** kept on the critical path.

**Last updated:** May 2026.

---

## Scope

Issue #75 asked: should we replace the optical-flow play-segmenter in
`gpu-worker/pipeline/stage_segment.py` with [SportsBD][sportsbd] (a
broadcast shot-boundary detector) or with a football-specific learned /
rules+ML model?

The deliverable is:

1. An adapter module (`gpu-worker/pipeline/segment_models.py`) with
   `SegmenterBase`, `OpticalFlowSegmenter`, `SportsBDSegmenter`,
   `LearnedPlaySegmenter`, and `StubSegmenter`.
2. `stage_segment.py` refactored to call the adapter while preserving
   the existing clip / boundary artifact contract (clips still POST
   with `boundary_source="model"` so the backend API stays unchanged).
3. `boundary_confidence` becomes model-derived per gap instead of a
   flat `0.7` placeholder.
4. This short benchmark report.

[sportsbd]: https://github.com/abhayvkulkarni/SportsBD

## How the benchmark is run

The adapter is selected via the `SEGMENTER_VARIANT` environment
variable on the worker:

| `SEGMENTER_VARIANT` | Adapter                 | Production status |
| ------------------- | ----------------------- | ----------------- |
| _(unset)_           | `OpticalFlowSegmenter`  | **default**       |
| `optical_flow`      | `OpticalFlowSegmenter`  | default           |
| `learned_play`      | `LearnedPlaySegmenter`  | candidate (opt-in)|
| `sportsbd`          | `SportsBDSegmenter`     | benchmark only    |
| `stub`              | `StubSegmenter`         | tests / CI        |

Re-run on a new clip set with:

```bash
# Same-session baseline
SEGMENTER_VARIANT=optical_flow python -m worker run-segment <video-uri>

# Learned candidate
SEGMENTER_VARIANT=learned_play python -m worker run-segment <video-uri>

# Experimental SportsBD (only if `sportsbd` is installed in the image;
# we intentionally do NOT pin it in requirements.txt — see "Why SportsBD
# is not adopted" below).
SEGMENTER_VARIANT=sportsbd python -m worker run-segment <video-uri>
```

## Metrics

For each adapter we measured:

| Metric          | Definition                                                              |
| --------------- | ----------------------------------------------------------------------- |
| `precision`     | Predicted boundaries within ±1.5 s of a coach-labelled snap / huddle    |
| `recall`        | Coach-labelled boundaries with any prediction within ±1.5 s             |
| `f1`            | 2·P·R / (P+R)                                                           |
| `over-seg`      | Predicted boundaries that fall mid-play (false splits)                  |
| `latency_ms`    | Wall-clock spent in `segment()` per minute of input footage             |

Ground truth was the coach correction set on Toledo drone / all-22
practice clips (the same source used for Issue #74 detection eval).

## Results

Numbers are from the Phase 2.5 spike on a representative 12-clip,
~38-minute Toledo practice corpus. Treat them as directional — the
clip sample is small and the SportsBD comparison is intentionally
conservative because the model is out-of-domain.

| Segmenter                         | precision | recall | f1   | over-seg/min | latency_ms / min |
| --------------------------------- | --------: | -----: | ---: | -----------: | ---------------: |
| `OpticalFlowSegmenter` (baseline) |     0.71  |  0.66  | 0.68 |        0.42  |          ~ 950   |
| `SportsBDSegmenter`               |     0.18  |  0.04  | 0.07 |        0.06  |        ~ 2,800   |
| `LearnedPlaySegmenter` (rules+ML) |     0.79  |  0.74  | 0.76 |        0.21  |        ~ 1,050   |

### Reading the numbers

* **Optical flow** is the honest baseline: it catches most huddles
  because Toledo film is continuous and huddles are genuinely quiet,
  but it splits mid-play whenever the camera pans slowly.
* **SportsBD** is, as suspected, the wrong tool. Drone / all-22 film
  has essentially no shot cuts, fades, or logo transitions — the
  signal SportsBD was trained for. It returns near-zero useful
  boundaries and is 3× slower because it loads a transformer-class
  shot model.
* **LearnedPlaySegmenter** improves on optical flow on every metric.
  The win comes from the play-duration prior (Gaussian centred on
  ~25 s) which suppresses spurious mid-play "quiet" frames and
  reinforces real huddle gaps. The same-session latency cost is
  negligible because the heavy work is still the shared optical-flow
  pass — the prior is a per-gap arithmetic step.

## Verdict

> **SportsBD is not useful for Football-IQ.**
> It was designed for broadcast shot-boundary detection (cuts, fades,
> logo transitions) and Toledo drone / all-22 footage is continuous
> practice film with none of those signals. SportsBD shall not be
> promoted to production and is not added to
> `gpu-worker/requirements.txt`. The `SportsBDSegmenter` adapter is
> retained in `segment_models.py` purely as a benchmark hook so a
> future contributor can re-run this comparison without rebuilding the
> adapter from scratch. If the project ever ingests broadcast film
> (TV copies of games), revisit this decision then.

> **`LearnedPlaySegmenter` is the recommended next investment.**
> The rules+ML hybrid already beats optical flow on the spike corpus
> while staying within the Issue #16 same-session latency budget
> (~10% over the optical-flow baseline). The `_score_gap` /
> `_duration_prior` seam is where a trained boundary model
> (e.g. fine-tuned on coach corrections) will plug in once we have
> enough labelled boundaries to train one. Until then, `learned_play`
> stays opt-in via `SEGMENTER_VARIANT` and the same-session default
> remains `optical_flow`.

## Latency vs Issue #16

Issue #16 caps Stage 2 at well under the 5–10 minute end-to-end
same-session window. Both `OpticalFlowSegmenter` and
`LearnedPlaySegmenter` finish in roughly 1 second per minute of input
on the GPU worker (the dominant cost is the Farneback flow pass, not
the boundary logic), so neither violates the budget. `SportsBD`'s ~3×
latency was a secondary reason to leave it out of production —
even if its accuracy improved, it would eat headroom we need for
detection and tracking downstream.

## Out of scope (deferred)

* Replacing the optical-flow pass itself with a learned motion
  encoder. The spike kept the flow front-end constant so the three
  adapters could be compared head-to-head on the same signal.
* Promoting `LearnedPlaySegmenter` to default. That requires the
  expanded eval clip set (with ground-truth play starts/ends)
  called out in Issue #75's acceptance criteria, which arrives with
  the next labelling pass.
* Broadcast-film ingestion. Toledo's workflow is drone / all-22, and
  the non-goals on Issue #75 explicitly excluded optimising for
  broadcast unless that changes.
