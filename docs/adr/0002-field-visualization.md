# ADR 0002 — Field & route visualization: frontend-native SVG over sportypy / R

Status: **Accepted** (Issue #169)
Date: 2026-05-28
Deciders: Football-IQ analytics/UX
Related: #163 (CFBD analytics surfaces), #166 (external-resource governance),
#127/#128/#129 (calibrated tracking), #96 (no mock data as real)

## Context

Issue #169 asked whether existing sports-visualization packages can reduce the
custom chart / field-drawing work for Football-IQ reports and dashboards:

- **sportypy** — Python, draws regulation fields (incl. NCAA football). Source:
  https://sportypy.sportsdataverse.org
- **sportyR** — R, the original of the same family. Source:
  https://github.com/sportsdataverse/sportyR
- **cfbplotR** — R, college-football team logos/colors + ggplot helpers. Source:
  https://github.com/sportsdataverse/cfbplotR

Football-IQ's two visualization needs are different:

1. **Interactive coach-facing overlays** in the Next.js app (clip review,
   dashboards, the new College Data surface). These need to be interactive,
   themeable, and shipped in the browser bundle.
2. **Static report artifacts** (PDF/PNG) generated server-side for coach exports.

## Decision

1. **Interactive overlays → frontend-native SVG/Canvas.** We render fields and
   route/spacing overlays directly in React with SVG. The first sample lives in
   `frontend/src/components/field-diagram.tsx` and is used on the College Data
   page. No new runtime dependency.

2. **Do NOT add an R runtime dependency.** `cfbplotR` and `sportyR` are R
   packages. Adding an R runtime to the FastAPI backend or the GPU worker for
   chart drawing is disproportionate to the need and adds operational surface,
   image size, and a second language toolchain. Per #169's own out-of-scope
   note, R is rejected for production unless separately justified — it is not
   justified here. cfbplotR's logo/color helpers are convenient but its value
   (team branding) is achievable with our existing brand assets + CSS.

3. **`sportypy` is DEFERRED, not adopted.** It is pure Python (MIT) and would
   fit *offline* report generation if/when we need print-quality static field
   plots. It is **not** added as a dependency now: the report pipeline does not
   yet emit field plots, and adding it preemptively would be unused weight.
   Revisit when a concrete report needs a static field image. Tracked as a
   follow-up (see below).

## Rationale

- The interactive surface must run in the browser; a Python/R field renderer
  cannot, so SVG is the only native fit for #163's dashboards anyway.
- A single rendering approach (SVG now, optionally sportypy later for static
  Python reports) avoids maintaining duplicate field geometry across languages.
- Coordinates for *real* route/spacing overlays depend on calibrated tracking
  (#127/#128/#129). Until that lands, `FieldDiagram` renders a generic field
  schematic only and never presents positions as real data (#96). `markers` is
  wired so calibrated coordinates can be overlaid later without a rewrite.

## External-resource rubric (per #166 / docs/external-resource-rubric.md)

| Field | sportypy | sportyR | cfbplotR |
|---|---|---|---|
| Sport coverage | American football (+others) ✅ | American football (+others) ✅ | College football ✅ |
| Toledo/MAC relevance | Broad (field geometry) | Broad | Direct (CFB logos/colors) |
| Runtime category | offline report (deferred) | n/a (rejected) | n/a (rejected) |
| License / access | MIT (no key) | MIT (no key) | MIT (no key) |
| Secret/key requirement | None | None | None |
| Data privacy risk | None | None | None |
| Model-router/registry path | N/A (rendering only) | N/A | N/A |
| Overlap with closed decisions | None | None | None |
| Calibrated-tracking dependency | Yes, for real overlays (#127/#128/#129) | same | same |

## Consequences

- ✅ No new production dependency; smaller, single-language frontend path.
- ✅ Interactive, theme-aware, test-covered field component shipped today.
- ➖ If we later need print-quality static field plots in Python reports, we
  must add `sportypy` (MIT, no key) at that point.

## Follow-up

- Open an implementation issue only if/when a report needs static field plots,
  to add `sportypy` behind the report pipeline (offline, with a `LICENSES.md`
  row). Until then, no action.
