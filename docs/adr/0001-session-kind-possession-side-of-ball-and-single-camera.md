# ADR 0001: Session kind, possession, side-of-ball, and single-camera product decision

- **Status:** Accepted
- **Date:** 2026-05-26
- **Issue:** [#110](https://github.com/aahmadf123/Football-IQ/issues/110)

## Context

Football-IQ ingests film captured under three operating modes — `practice`, `scrimmage`, and `game` — and analyzes it to surface formations, coverages, biomechanics, tracking, and tendencies. The terminology used across the backend models, the API filters, and the frontend filter UI has drifted as features have been added piecemeal:

- Sessions are currently implicit: a "session" today is whatever `Video` row a coach uploaded. There is no `Session` table and no `session_kind` enum.
- `our_possession` (which side of the ball Toledo is on for a given session or clip) is not stored as a typed field. It is implied by `Clip.label_data["side_of_ball"]` strings.
- `side_of_ball` exists as `Tracklet.side_of_ball` (a string on each tracked entity) and as a `Clip.label_data["side_of_ball"]` JSON field. The semantic relationship between these two layers has never been written down.
- Opponent metadata for game clips currently lives inside `Video.metadata_["opponent"]` (a JSON blob) and is queried via `Video.metadata_["opponent"].astext.ilike(...)` in `backend/app/routers/search.py`.
- The frontend filter widget in `frontend/src/components/football-shell.tsx` exposes a "Session Type" pill with values `practice | scrimmage | game | all` and a "Side of Ball" pill with values `offense | defense | special | all`. These literals are defined in `frontend/src/lib/app-state.tsx` and do not yet line up with backend names (`special` vs. `special_teams`).
- Earlier discussion has occasionally referenced multi-camera affordances (Endzone view, Sideline view) borrowed from Hudl-style products. Football-IQ is deployed today against a single overhead camera per session.

Several P0/P1 issues — #97 (Session model), #98 (opponent column), #99 (clip metadata migration), #100 (tracklet refactor), #101 (real upload/R2), #102 (clip-model API rewrite) — depend on a shared vocabulary. We need a single document that fixes the terms and the single-camera product rule before those issues land.

## Decision

### 1. `session_kind`

A required enum on the session envelope:

```
session_kind = practice | scrimmage | game
```

- `practice`: routine team practice. Possession does not flip mid-session; one side of the ball is being repped.
- `scrimmage`: live scripted scrimmage. Possession may flip across periods; usually still focused on one side at a time.
- `game`: real opponent. Possession alternates throughout.

In the current schema this field lives on `Video`. Promotion to a dedicated `Session` table is deferred to **#97**.

### 2. `our_possession`

A session-level enum representing which side of the ball Toledo is on for the session as a whole:

```
our_possession = offense | defense | special_teams
```

- **Required** for `session_kind = practice`. A practice session is dedicated to one side of the ball; this field captures which.
- **Optional** for `session_kind = scrimmage | game`. Possession alternates, so a session-wide value is not meaningful. When set on a game/scrimmage session, it means "the side we are primarily analyzing in this session"; when unset, all possession context must be read from clip-level fields.

### 3. Clip-level `side_of_ball`

Per-clip enum:

```
clip.side_of_ball = offense | defense | special_teams
```

- **Optional** for clips whose parent session has a defined `our_possession` (typical for practice). When unset, resolves to the parent session's `our_possession`.
- **Required** for clips whose parent session has no `our_possession` (typical for game/scrimmage). The clip itself must declare the side because possession flips.

This is the same vocabulary as `our_possession`, but scoped to a single play.

### 4. Tracklet-level `side_of_ball`

Already exists at `backend/app/models.py:Tracklet.side_of_ball`. We canonicalize its meaning here:

```
tracklet.side_of_ball = offense | defense | special_teams
```

- Describes the side of the ball a single tracked entity is on **within a clip**, independent of `our_possession`.
- This is how we distinguish "our players" from "opponent players" when both appear in a game clip: the tracklets on `clip.side_of_ball` are our team; the tracklets on the opposite side are the opponent.
- This field is set by the tracker / labeler, not derived from session metadata.

### 5. Opponent context for game clips

For `session_kind = game`, the opposing team must be identifiable. The canonical storage for now is:

```
Video.metadata_["opponent"]   # JSON, free-form string
```

This is what `backend/app/routers/search.py:SearchFilters.opponent` already filters against. Promotion to a first-class column (`Video.opponent_id` foreign-keyed to an `Opponent`/`Team` table) is deferred to **#98** and is out of scope for this ADR.

Practice and scrimmage clips do not carry opponent context.

### 6. Single-camera product decision

**Football-IQ is single-camera.** All analysis runs against one overhead capture per session. There is no Endzone view, no Sideline view, no multi-angle player UI, and no plans to add any of the above.

#### Allowed render-layer toggles

The player UI may overlay or hide the following layers on top of the single camera feed:

```
raw | tracks | labels | events | metrics | wireframe
```

- `raw`: untouched video.
- `tracks`: bounding boxes / track IDs.
- `labels`: formation, coverage, personnel, route tags.
- `events`: snap, handoff, tackle, etc.
- `metrics`: per-player or per-play scalar overlays (speed, separation, confidence).
- `wireframe`: pose / skeleton overlay.

These are **render layers on a single video stream**. They are not camera angles.

#### Disallowed in the UI

- "Endzone view" / "Sideline view" toggles or buttons.
- Multi-camera grid views.
- Any affordance that implies switching between cameras.

If a future product change requires multi-camera analysis, it must come back through a new ADR.

## Consequences

### Impacted backend

- `backend/app/models.py`:
  - `Video` (or future `Session`) gains `session_kind` and optional `our_possession` (deferred to #97).
  - `Clip` gains `side_of_ball` as a first-class column (deferred to #99 / #102).
  - `Tracklet.side_of_ball` already exists; semantics are now pinned by this ADR.
  - `ProcessingJob` is unaffected directly but must surface `session_kind` through its job context for routing decisions.
- `backend/app/routers/search.py`:
  - `SearchFilters` already accepts `side_of_ball`. Add `session_kind` and `our_possession` filter parameters when the corresponding columns exist (#97, #99).
- Migrations: new revisions under `backend/migrations/versions/` will introduce the columns above. None of them are written in this branch.

### Impacted frontend

- `frontend/src/lib/types.ts`: introduce typed enums `SessionKind`, `SideOfBall`, `OurPossession` aligned with the backend. (Not done in this branch.)
- `frontend/src/lib/app-state.tsx`: the existing `SessionType` and `SideOfBall` literals are close but not aligned:
  - `SessionType` includes an `all` filter sentinel that has no backend equivalent — acceptable as a UI-only value.
  - `SideOfBall = "all" | "offense" | "defense" | "special"` should become `"all" | "offense" | "defense" | "special_teams"` to match the backend. The rename is **flagged but deliberately deferred** to avoid bleeding into #96; it should land with #99/#100.
- The player UI must not introduce camera-angle controls. Render-layer toggles (per the allowed list above) are fine.

### Impacted API filters

`SearchFilters` in `backend/app/routers/search.py` should grow `session_kind` and `our_possession` query params alongside the existing `side_of_ball` and `opponent` filters once the underlying columns exist.

### Impacted migrations

Future revisions (driven by #97–#102) must:

1. Add `session_kind` to the session envelope.
2. Add `our_possession` to the session envelope.
3. Add `side_of_ball` to `Clip` as a first-class column (the value currently lives in `Clip.label_data`).
4. Backfill the new columns from existing `Clip.label_data` / video-naming conventions where possible.

## Alternatives Considered

- **Multi-camera (Hudl pattern):** Rejected. Football-IQ is deployed against a single overhead camera. Multi-camera would force re-architecting capture, storage, calibration, and the player UI for no current product win.
- **Store `our_possession` only on clips, not sessions:** Rejected. Practice clips inherit naturally from the session; forcing per-clip annotation doubles the labeling burden for the most common case.
- **Treat `side_of_ball` as a boolean `is_offense`:** Rejected. Special teams is irreducible to a binary, and special-teams-specific metrics (return lanes, coverage tendencies) need a first-class label.
- **Keep `side_of_ball` in `Clip.label_data` JSON forever:** Rejected. JSON filtering is workable today (`backend/app/routers/search.py` already does it) but a first-class column unlocks indexed queries and typed APIs. Migration deferred to #99.
- **Drop `scrimmage` and fold it into `practice`:** Rejected. Scrimmages have game-like possession flips that practice does not; conflating them would muddy session-level `our_possession` semantics.

## References

- [#96](https://github.com/aahmadf123/Football-IQ/issues/96) — Stop mock data from masquerading as live Football-IQ data
- [#97](https://github.com/aahmadf123/Football-IQ/issues/97) — Session model + `session_kind` migration
- [#98](https://github.com/aahmadf123/Football-IQ/issues/98) — Opponent first-class column
- [#99](https://github.com/aahmadf123/Football-IQ/issues/99) — Clip metadata migration (`side_of_ball` to first-class column)
- [#100](https://github.com/aahmadf123/Football-IQ/issues/100) — Tracklet refactor aligned with this ADR
- [#101](https://github.com/aahmadf123/Football-IQ/issues/101) — Real upload / R2 path
- [#102](https://github.com/aahmadf123/Football-IQ/issues/102) — Clip-model API rewrite
- [#110](https://github.com/aahmadf123/Football-IQ/issues/110) — This ADR
- `docs/label-taxonomy-v1.md` — Toledo ↔ generic label mapping
- `docs/capture-protocol-v1.md` — Drone capture standards (single-camera baseline)
- `backend/app/models.py` — current `Tracklet.side_of_ball`
- `backend/app/routers/search.py` — current `side_of_ball` and `opponent` filters
