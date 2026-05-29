# Pre-snap run/pass prediction (Issues #135 + #136)

Phase-2 of the pre-snap predictor: extract six pre-snap signals from
already-calibrated, tracked, team-classified, snap-anchored play state and
combine them into a **calibrated** run/pass probability with an explicit
**uncertainty**. Feature extraction (#135) and the calibrated Bayesian ensemble
(#136) ship together so the signal schema, model calibration, and uncertainty
semantics stay aligned.

## Where it lives

| Concern | Module |
|---|---|
| 6-signal extractor (orchestrator) | `gpu-worker/pipeline/play_prediction/signal_extractor.py` |
| Personnel (jersey ranges + roster) | `gpu-worker/pipeline/play_prediction/personnel.py` |
| Formation classifier (MLP + geometric fallback) | `gpu-worker/pipeline/play_prediction/formation_mlp.py` |
| Motion-type classifier (LSTM + rule fallback) | `gpu-worker/pipeline/play_prediction/motion_lstm.py` |
| Naive-Bayes log-odds + Platt + MoE | `gpu-worker/pipeline/play_prediction/bayesian_ensemble.py` |
| Platt / isotonic + diagnostics | `gpu-worker/pipeline/play_prediction/calibration.py` |
| Per-opponent Dirichlet priors | `gpu-worker/pipeline/play_prediction/per_opponent_prior.py` |
| Stage wiring + persistence | `gpu-worker/pipeline/stage_presnap_prediction.py` |
| Backend tables / API | `play_predictions`, `opponent_priors`, `app/routers/play_prediction.py` |

## Not a routed model stage

Like the Bayesian snap detector (see [snap-los-ball-events.md](snap-los-ball-events.md)),
the predictor consumes the **outputs** of the routed stages (`calibrate`,
`detect`, `track`, `reid`, `pose`, the snap event) and runs a small classifier
+ deterministic math. In its default path it loads no heavy weights and runs
identically in both priority buckets, so it intentionally registers **no**
`model_router` stage and does not appear in `DEFAULT_ROUTING`. The optional
formation MLP / motion LSTM checkpoints (`PLAY_PREDICTION_FORMATION_MODEL`,
`PLAY_PREDICTION_MOTION_MODEL`) load at runtime and fall back to the
deterministic path when absent — the same fallback convention as PARSeq re-ID.

## The 6 pre-snap signals (Issue #135)

Each signal exposes a categorical `value` **and** a `confidence` in `[0, 1]`.
The whole vector serializes to `play_predictions.signal_vector` (JSON) with a
`schema_version` for forward compatibility.

| # | Signal (`key`) | Values | Confidence source |
|---|---|---|---|
| 1 | `personnel` | `"{n_RB}{n_TE}"` e.g. `11`, `12`, `21` | fraction of the 11 with a resolved position (roster preferred, NCAA jersey range fallback) |
| 2 | `formation` | 12 classes (`i_form`, `shotgun_empty`, `trips`, …) | MLP softmax, or capped geometric-fallback confidence |
| 3 | `backfield` | `under_center` / `pistol` / `shotgun` | Gaussian responsibility of QB depth behind the LOS |
| 4 | `split` | `wide` (>6 yd) / `normal` (3–6) / `tight` (<3) | fixed when receivers present, low when absent |
| 5 | `motion` | `none` / `jet` / `orbit` / `return` / `shift` / `across` | LSTM softmax, or capped rule-based confidence |
| 6 | `down_distance_zone` | `"{down}_{short\|medium\|long}_{zone}"` | 0.95 from the event log, lower when auto-inferred |

Field zones use the NCAA field frame (X `0→100`, see
[calibration-contract.md](calibration-contract.md)): `backed_up` (≤ own 10),
`own_territory`, `opp_territory`, `red_zone` (≥ opp 20).

**Graceful degradation.** Any missing input yields a low-confidence /
`"unknown"` signal rather than an exception, so a partially-analysed play still
produces an appropriately-uncertain prediction — never a fabricated one.

### Example `signal_vector`

```json
{
  "schema_version": 1,
  "personnel": {"value": "11", "confidence": 1.0, "n_rb": 1, "n_te": 1, "n_wr": 3, "source": "roster"},
  "formation": {"value": "shotgun_empty", "confidence": 0.5, "method": "geometric"},
  "backfield": {"value": "shotgun", "confidence": 0.78, "qb_depth_yd": 6.0},
  "split": {"value": "wide", "confidence": 0.7, "min_sideline_distance_yd": 6.7},
  "motion": {"value": "jet", "confidence": 0.5, "method": "rule"},
  "down_distance_zone": {"value": "3_long_red_zone", "confidence": 0.95,
                          "down": 3, "distance_bucket": "long", "field_zone": "red_zone"}
}
```

## Bayesian ensemble (Issue #136)

Naive-Bayes log-odds combination:

```
logit P(pass | s_1..s_6) = logit P0 + Σ_i  conf_i · log Λ_i
Λ_i = P(s_i | pass) / P(s_i | run)          (Laplace-smoothed, |log Λ| capped)
P(pass) = sigmoid( logit P0 + Σ_i conf_i · log Λ_i )
```

* **`logit P0`** is the situational base log-odds. It comes from the
  per-opponent Dirichlet store when a **data-backed** cell exists; otherwise it
  defaults to the documented D1 CFB neutral base rate (~55 % pass) — never a
  fabricated opponent tendency.
* **Confidence weighting** (`conf_i`) downweights low-confidence / fallback
  signals so they cannot corrupt the combination (the #135 degradation
  contract).
* **Platt scaling** (`calibration.PlattScaler`) maps the raw combined
  probability to a calibrated one. An unfitted scaler is the identity and the
  result is flagged `is_calibrated=false` — a raw probability is never presented
  as calibrated.
* **Mixture of Experts** optionally refines the binary call into the 4-class
  taxonomy (`run_inside` / `run_outside` / `play_action` / `screen`). It only
  emits a distribution when a fitted MoE is supplied; otherwise `multiclass` is
  `null` (no mock multi-class output).

### Calibrated uncertainty (Issue #146)

Every prediction carries `uncertainty` = the binary (Shannon) entropy of the
calibrated probability, in bits: `1.0` at `p=0.5` (maximally uncertain), `→0` as
the prediction sharpens. `confidence = max(p, 1−p)`. Calibration quality is
reported with Brier score, ECE (10 equal-width bins), and a reliability curve,
all available from `GET /api/v1/play-predictions/calibration` for the MLOps
reliability diagram.

## Per-opponent Dirichlet priors (Issue #136)

One Beta posterior per `(opponent, down, distance-bucket, field-zone)`:

```
P(pass | opp, down, dist, zone) = (alpha_pass + n_pass)
                                  / (alpha_pass + alpha_run + n_pass + n_run)
```

The default `Beta(2, 2)` is uninformative (0.5). **There are no hard-coded
opponent-specific priors** — a cell only diverges from 0.5 once coach-confirmed
outcomes accumulate (`n_pass` / `n_run`), and a cell is only trusted to override
the neutral base rate after ≥ 8 real observations (`is_data_backed`). Every
non-default prior is therefore data-backed and auditable via `observation_count`.

### Coach-correction flywheel

`PATCH /api/v1/play-predictions/{id}` with `{"true_class": "run"|"pass"}` records
the confirmed outcome and folds it into the matching `opponent_priors` cell
(derived from the prediction's stored `down_distance_zone` signal). The
overnight refit then re-fits the per-signal likelihood ratios and Platt scaler.

## Persistence & API

Migration `0018` adds:

* **`play_predictions`** — one calibrated prediction per snap: `signal_vector`
  (JSON), `logit_score`, `predicted_class`, `true_class`, `confidence`,
  `calibrated_prob`, `uncertainty`, `is_calibrated`, `model_version_id`
  (→ `model_versions`), `opponent_team`, optional `play_id`.
* **`opponent_priors`** — the Dirichlet cells, unique per situation.

Opponents are keyed by `opponent_team` (VARCHAR) to match the existing derived
opponent model (`videos.opponent_team`); there is no opponents table to FK
against. JSON (not JSONB) matches the column type used throughout the schema.

Endpoints (all governance-gated via `app.governance.POLICY`, resource
`play_prediction`):

| Method | Path | Policy | Notes |
|---|---|---|---|
| POST | `/api/v1/play-predictions/batch` | `play_prediction:write` + workload gate | worker posts computed predictions; heavy → 503 `workload_gated` under saturation |
| GET | `/api/v1/clips/{clip_id}/play-predictions` | `play_prediction:read` | coaching-staff read |
| GET | `/api/v1/play-predictions/calibration` | `play_prediction:read` | reliability + ECE + Brier |
| GET | `/api/v1/play-predictions/opponent-priors` | `play_prediction:read` | situational priors (worker base log-odds) |
| PATCH | `/api/v1/play-predictions/{id}` | `play_prediction:write` | coach-correction flywheel |

`play_prediction:read` is coaching-staff only (admin/analyst/coach/sports-perf)
— never exposed to `player`/`viewer`. No vendor key is involved at any point.

## External resources

No external dataset, model, API, or third-party library is introduced. The
classifiers are pure-NumPy (no `scipy`/`scikit-learn`, matching the rest of the
pipeline); the optional formation/motion checkpoints are produced offline and
are never committed. The HAW-Hamburg thesis, NFL Big Data Bowl, and Frontiers
paper referenced in the issues are **methodology references only** — no data or
weights from them are bundled — so the Issue #166 external-resource governance
gate and a LICENSES.md row do not apply.

## Acceptance-criteria notes

The model-accuracy gates in #135/#136 (formation MLP ≥ 80 %, motion LSTM ≥ 75 %,
ensemble accuracy ≥ 62 %, ECE < 0.05) are **data-dependent** and are validated
offline once ≥ 500 labelled plays per class are available from the Toledo play
log + coach corrections. This change ships the schema, the calibrated ensemble,
the calibration diagnostics, the data-backed/safely-defaulted priors, and the
deterministic fallbacks, all unit-tested; the trained checkpoints load via the
documented env vars without further code change.
