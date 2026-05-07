# Phase 0 Detection Calibration Report

## Goal
Check whether initial player detection quality is sufficient for formation and spacing review on the Phase 0 evaluation set.

## Dataset
- Source: `data/eval-clips/manifest.csv`
- Clips reviewed: 50
- Situations covered: run, pass, motion, red zone, bad lighting, crowded box

## Field Marking Visibility
- Clips with usable field markings: **46 / 50 (92%)**
- Pass threshold: **>= 90%** (met)
- Challenging clips: `TOL_P0_040`, `TOL_P0_041`, `TOL_P0_046`, `TOL_P0_050`

## Baseline Detector Findings
- Detector used: phase0 baseline person detector (default confidence 0.35)
- Qualitative result:
  - Good separation and track continuity on most open-field and red-zone reps
  - Acceptable in crowded box plays for spacing context, but occasional merge errors
  - Bad-lighting reps show confidence drops but still provide usable formation snapshots

## Summary Metrics (manual QA sample)
- Formation-level usability: **44 / 50 clips (88%)**
- Spacing-level usability: **42 / 50 clips (84%)**
- “Good enough for MVP overlay prototyping” threshold: met for majority of clips

## Calibration Recommendations
1. Keep baseline detector for MVP Phase 1 prototype.
2. Add clip-level quality flags for bad lighting and crowd density.
3. Revisit confidence threshold by lighting condition in next sprint.
