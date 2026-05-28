# Toledo Drone Capture Protocol v1

## Purpose
Standardize drone film collection so clips are usable for field mapping, player detection, and early tactical overlays.

## Capture Standards
- **Camera height:** 90–120 ft AGL (target 105 ft)
- **Framing:** Entire offensive formation pre-snap plus 5 yards outside each sideline when possible
- **Frame rate:** **60 FPS preferred**, **30 FPS minimum**
- **Resolution:** **4K preferred** (3840x2160), 1080p minimum if signal stability requires fallback
- **Exposure:** Manual exposure preferred; avoid auto-exposure pumping during snap-to-whistle
- **Shutter/ISO guidance:** Keep shutter fast enough to limit motion blur; lock white balance per session block
- **Stabilization:** Gimbal horizon level before each series

## Recording Procedure
1. Start recording by huddle break or pre-snap motion.
2. Keep both tackle boxes and near hash marks visible at snap.
3. Follow play through whistle, then hold 1–2 seconds before cutting.
4. Re-center immediately for next rep.

## Naming Convention
Use:

`TOL_{YYYYMMDD}_{period}_{series}_{play}_{scenario}_DRONEA.mp4`

Example:

`TOL_20260503_P2_S07_PL04_REDZONE_DRONEA.mp4`

Where:
- `period`: P1, P2, OTK, RZ
- `scenario`: RUN, PASS, MOTION, REDZONE, BADLIGHT, CROWDEDBOX, MIXED
- Source is fixed to `DRONEA` for the single-camera capture pipeline.

## Upload Process
1. Offload all files immediately after session to encrypted field laptop.
2. Run checksum verification (SHA-256) before upload.
3. Upload to secured shared storage path under:
   - `phase0/raw/{date}/`
   - `phase0/processed/{date}/`
4. Upload corresponding clip manifest entry to `data/eval-clips/manifest.csv`.
5. Analyst performs spot-check of 10% random files for corruption, naming, and framing quality.

## Validation Gate (Phase 0)
Capture batch passes if:
- At least 90% clips show usable field markings for mapping
- Video quality supports player detection and spacing review
- Required scenarios are represented in the evaluation set

## Capture-Regime Detection (Issue #126)
Every Phase-CV stage (homography, detection, tracking, events) branches on
the source regime. Toledo film arrives without SRT/GPS/IMU, so the regime
is inferred from pixels exactly once, at ingest.

Supported regimes:
- `drone_follow` — operator-flown drone with pans/zooms/tilts (practice film)
- `fixed_sideline` — static elevated wide game camera
- `unknown` — safe fallback when fusion confidence is below
  `REGIME_MIN_CONFIDENCE` (default `0.55`) or feature extraction fails

Where it runs:
- `gpu-worker/pipeline/homography/regime_detector.py` (the detector
  module, exposes `CaptureRegimeDetector` and the abstract
  `RegimeDetectorAdapter`).
- Invoked from `gpu-worker/pipeline/stage_ingest.py` immediately after the
  ffprobe step. The result is persisted via
  `PATCH /api/v1/videos/{id}/status` and denormalized onto every `clips`
  row created later by `backend/app/routers/clips.py:create_clip`.

`regime_confidence` is the fusion classifier's distance from the 0.5
decision boundary, rescaled to `[0, 1]` — `1.0` means the four pixel
features all agree strongly on a single regime, `0.0` means the detector
is on the fence and the row is tagged `unknown`.

Coaches can override the predicted regime via
`PATCH /api/v1/clips/{id}` (manual overrides are recorded with
`regime_confidence=1.0`). A separate frontend issue tracks surfacing this
override as a clip-review UI control.

