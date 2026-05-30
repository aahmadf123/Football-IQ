# Spike / schema report — NFL Big Data Bowl offline adapter (Issue #164)

**Status: implemented as an OFFLINE adapter.** Offline pretraining / evaluation
only — not production runtime, not wired into the model router, and **not Toledo
film**. Part of epic [#160](https://github.com/aahmadf123/Football-IQ/issues/160);
governed by [#166](https://github.com/aahmadf123/Football-IQ/issues/166).

Code: [`gpu-worker/datasets/bdb/`](../gpu-worker/datasets/bdb/) ·
README (auth/download/schema): [`gpu-worker/datasets/bdb/README.md`](../gpu-worker/datasets/bdb/README.md).

## 1. External-resource rubric (#166)

| Field | Answer |
|---|---|
| **Sport coverage** | NFL / American football ✅ (player tracking). Not soccer. |
| **Toledo / MAC relevance** | Broad American football. **Not** Toledo film/labels — offline analogue only. |
| **Runtime category** | Offline training / benchmark only. Normalized locally; never in same-session/nightly. |
| **License / access terms** | Per-competition Kaggle rules; account + rules acceptance required. Non-commercial research typical; redistribution generally not permitted. |
| **Secret / key requirement** | `KAGGLE_USERNAME` + `KAGGLE_API_TOKEN` (**not** `KAGGLE_KEY`). Used only at manual download; never exposed to frontend/bundles/Workers/logs/PR/issue/R2/DB. Not read by backend. |
| **Data privacy risk** | Public NFL competition data; no Toledo PII/medical/recruiting data. BDB labels must not be shown as Toledo labels. |
| **Model-router / registry path** | N/A — data normalizer, no model code. Any future model trained on these artifacts routes via `select_model(stage, priority)`, nightly-only until benchmarked. |
| **Overlap with closed decisions** | None. Single-camera (#101), pgvector (#8/#77), SAM (#74), CFBD (#160–#163) all untouched. |
| **Calibrated-tracking dependency** | BDB ships clean ground-truth field yards; Football-IQ derives coordinates via #127/#128/#129. Offline-only until Toledo transfer is validated. |

## 2. Kaggle auth & download flow (no secrets committed)

The adapter **never** downloads from Kaggle. A human/CI downloads to a local,
gitignored path; credentials stay in the shell/secret store:

```bash
export KAGGLE_USERNAME="$KAGGLE_USERNAME"
export KAGGLE_KEY="$KAGGLE_API_TOKEN"   # bridge our secret name -> CLI's var
pip install kaggle
DEST="${BDB_DATA_DIR:-$HOME/.cache/football-iq/bdb}/nfl-big-data-bowl-2025"
mkdir -p "$DEST"
kaggle competitions download -c nfl-big-data-bowl-2025 -p "$DEST"   # accept rules first
unzip -o "$DEST"/*.zip -d "$DEST"
```

`~/.kaggle/kaggle.json` (mode `600`) is the equivalent path. Either way, nothing
is committed and the token is never printed/logged.

## 3. Normalized schema & BDB → Football-IQ field map

`python -m datasets.bdb normalize ...` writes JSONL tables + `manifest.json`
(provenance) to a gitignored artifact dir.

| Football-IQ concept | BDB source | Normalized table | Key fields |
|---|---|---|---|
| Session / game metadata | `games.csv` | `games` | `game_id, season, week, game_date, home_team, away_team` |
| Play | `plays.csv` | `plays` | `down, yards_to_go, possession_team, defensive_team, offense_formation, receiver_alignment, los_absolute_yard, play_direction` |
| Player / roster identity | `players.csv` | `players` | `nfl_id, display_name, position, height, weight, college` |
| Route / label (analogue) | `player_play.csv` | `player_plays` | `route_ran, was_running_route, motion_since_lineset, in_motion_at_snap` |
| Tracklet frame sample | `tracking_week_*.csv` | `tracking` | `frame_id, x, y, s, a, dis, o, dir, event, side` |

`tracking.side` (`offense`/`defense`/`ball`) is derived by joining the track
row's club to the play's possession/defensive team. Coordinates are recorded as
`coordinate_frame: bdb_field_yards` (x 0–120, y 0–53.3) — **not pixels and not a
calibrated Football-IQ homography output**.

**Header aliasing.** One code path handles BDB 2025 camelCase (`gameId`, `nflId`,
`frameId`) and BDB 2026 snake_case (`game_id`, `nfl_id`, `frame_id`). Missing
tables are skipped so partial downloads degrade gracefully.

## 4. Offline benchmark (reproducible on the synthetic sample)

`python -m datasets.bdb demo --output-dir .cache/bdb/demo` runs the full
normalize→benchmark path on the committed **synthetic** sample (no Kaggle data),
demonstrating the features each downstream consumes:

| Downstream | Feature |
|---|---|
| #139 coverage GNN | offense-formation distribution; nearest-defender separation |
| #140 pre-snap pressure | pre-snap spacing (width / depth / on-LOS); motion flags |
| #141 counterfactual sim | route distribution; per-frame kinematics |
| #150 self-distillation | coverage separation; normalized tracking |

Sample output (synthetic — values are fabricated):

```
Offense formation distribution: SHOTGUN=1, SINGLEBACK=1
Route distribution: HITCH, GO, FLAT, SLANT, OUT, CROSS (1 each)
Pre-snap spacing: mean_width=40.0 yd, mean_depth=7.0 yd, mean_on_LOS=3.0
Coverage separation: 10 matchups, mean nearest defender 5.96 yd, min 2.69 yd
Kinematics: max_speed=2.4 yd/s, mean_speed=0.25 yd/s, max_accel=1.5 yd/s^2
```

## 5. License / terms caveats

- Governed by each Kaggle competition's rules; verify before any use beyond
  offline research. **Redistribution generally not permitted** → raw data and
  normalized artifacts are gitignored, never committed.
- **BDB labels ≠ Toledo labels** and **BDB coordinates ≠ calibrated Football-IQ
  coordinates.** Both caveats are stamped into every artifact `manifest.json`
  (`label_note`, `coordinate_note`) and the `offline-pretraining-evaluation-only`
  usage marker.

## 6. Suggested follow-ups (only if a downstream needs them)

- **BDB 2026 prediction targets.** The 2026 competition has an input/output
  tracking split for player-movement prediction. Tracking columns already
  normalize; add explicit target extraction when #140/#141 consume it.
- **Train/val/test split manifest.** When a model (#139/#140/#141/#150) starts
  training, add a deterministic split manifest alongside the artifacts (mirror
  the `data/ball_annotations` split convention).
- **Transfer-validation gate.** Before any BDB-pretrained model becomes
  coach-facing, validate on Toledo footage and record the result — BDB stays
  offline-only until then.
