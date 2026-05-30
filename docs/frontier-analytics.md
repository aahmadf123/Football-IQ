# Frontier analytics — xSep / xYards / xPressure (Issue #10)

Status: **experimental scaffold.** These advanced metrics are implemented
end-to-end (producer → store → read surface → UI) but are **not validated
Toledo results**. They are surfaced only to coaching staff, always badged
EXPERIMENTAL, and never stored as trusted (`analytics_safe=False`) until a coach
reviews them. This document is the coach-readable definition + interpretation
guide the issue's acceptance criteria require.

## Where the math lives

| Layer | File | Role |
| ----- | ---- | ---- |
| Producer | `gpu-worker/pipeline/frontier_analytics.py` | Deterministic geometry over calibrated tracking → metric payloads |
| Ingest guard | `backend/app/routers/clips.py` (`create_metric`) | Forces these metric names experimental + never `analytics_safe` |
| Store | `metrics` table (`Metric` model) | `experimental_flag`, `analytics_safe`, `confidence`, `is_suppressed` |
| Read surface | `GET /api/v1/analytics/frontier` (`backend/app/routers/frontier_analytics.py`) | Sliceable, staff-only, players never see experimental |
| UI | `frontend/src/app/analytics/page.tsx` | Renders value + EXPERIMENTAL badge + source + sample-size caveat |

Nothing here is routed through the model router (see
[`docs/model-routing.md`](model-routing.md) → *Not routed*). It consumes the
outputs of the routed `detect` / `track` / `calibrate` stages.

## Dependencies (hard)

All three metrics require **calibrated, single-camera tracking** from Issues
**#127** (field calibration), **#128** (detection), and **#129** (tracking).
When field calibration is not analytics-safe, or there are too few tracked
frames, the producer **suppresses** the metric (`is_suppressed=True`) rather
than guessing. SAM masks (#74) and play embeddings (#8) are **enrichment only**:
they nudge confidence up when present, but every metric still computes without
them. No new vector DB, multi-camera, or SAM path is introduced.

## Metrics

### xSep — Expected Separation

* **What:** yards of separation between a receiver and the nearest defender at
  the throw / target-decision frame (field-frame Euclidean distance).
* **Inputs:** receiver tracklet, nearest-defender tracklet, throw frame,
  calibration `analytics_safe` flag. (Enrichment: SAM mask, play embedding.)
* **Why it matters:** quantifies whether a route actually created room, beyond
  "was it complete".
* **Interpretation:** higher is better for the offense. One clip is an estimate;
  trust trends only after ~30+ clean reps.
* **Concept family:** spacing/route concepts (offense).

### xPressure — Expected Pressure

* **What:** expected pressure on the QB given rusher proximity at the throw and
  time-to-throw. A rusher inside ~2 yd before the throw counts as pressure;
  quick throws (< 2.5 s) discount realized pressure.
* **Inputs:** QB tracklet, rusher tracklets, snap frame, throw frame, fps,
  calibration `analytics_safe` flag.
* **Why it matters:** separates protection/structure quality from box-score
  sacks (a clean pocket vs. a hurried throw).
* **Interpretation:** higher = more duress. Defensive structure metric.
* **Defensive structure:** pass-rush / protection.

### xYards — Expected Yards After Catch *(scaffold only)*

* **Status:** deliberately a **low-confidence placeholder** (`confidence=0.1`,
  `model="placeholder_observed_only"`). A trustworthy xYards needs spacing +
  leverage + pursuit modeling the tracking layer does not yet expose. Rather
  than fabricate a number, it reports only the observed downfield distance after
  the catch, clearly flagged. **Do not use as a trusted xYards.**

## Stability & noise

| Metric | Min inputs | Trust threshold |
| ------ | ---------- | --------------- |
| xSep | ≥ 3 tracked points per track, calibration analytics-safe, a point at the throw | ~30+ clean reps before a trend is meaningful |
| xPressure | ≥ 3 QB points, ≥ 1 rusher with a point at the throw, valid snap→throw window | ~30+ reps; sensitive to snap/throw event accuracy |
| xYards | ≥ 2 post-catch points + catch frame | Not a trusted metric yet (scaffold) |

Each emitted metric carries `sample_size` and a `stability_note` so a coach can
judge how far to trust a single value. Suppressed metrics carry a
`suppression_reason` (e.g. `calibration_not_analytics_safe`).

## Governance

* **Never trusted by default:** `app.routers.clips.create_metric` forces
  `experimental_flag=True` and `analytics_safe=False` for `xsep` / `xyards` /
  `xpressure` regardless of the producer payload.
* **Never player-facing:** the read endpoint blocks `player` / `viewer` roles,
  and the metrics list already strips experimental metrics from player views.
* **Coach review:** an experimental metric only becomes `analytics_safe` after a
  position coach approves it via the existing metric-review flow.
