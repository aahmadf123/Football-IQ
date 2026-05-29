# LICENSES.md

Third-party models, libraries, and tools used in Football-IQ. Updated May 2026.

---

## Meta SAM 3 / SAM 3.1

| Field | Detail |
|---|---|
| **Model** | Segment Anything Model 3 (SAM 3) and SAM 3.1 |
| **Owner** | Meta AI |
| **Code license** | Meta open-source license (GitHub: `facebookresearch/sam3`) |
| **Weight license** | Gated access — Meta SAM Model License (Llama-family variant) |
| **Access** | Request at https://huggingface.co/facebook/sam3 — account approval required |
| **Commercial use** | Non-commercial / research use only per model card; review before any commercial deployment |
| **Integration path** | `pip install -U ultralytics` — SAM 3 is included in Ultralytics >= 8.3.237 |
| **HF token required** | Yes — `HF_TOKEN` env var / GitHub Actions secret |
| **Football-IQ usage** | Phase 2.5 — Issue #74: shipped as `SAM3Detector` in `pipeline/detector_models.py` and `SAM3MaskTracker` in `pipeline/tracker_models.py`. Routed via `model_router` on the nightly path only (`ENABLE_SAM3_NIGHTLY=1`); same-session continues to use YOLOv8n + IoU. Listed in `NIGHTLY_ONLY_VARIANTS` so config overrides cannot route it to a same-session bucket. |
| **Eval** | See `reports/phase2-issue74-sam3-eval.md` and `gpu-worker/eval/eval_sam3_vs_yolo.py` for the comparison harness (synthetic CI path + real-clip path). |
| **Promotion gate** | Frame coverage within 2pp of YOLOv8n, mean track length ≥ YOLO + IoU, fragmentation ≤ 1.1×, and same-session latency fit. Until met SAM 3.1 stays nightly-only; promotion likely awaits a distilled variant. |
| **Notes** | Do not commit model weights (`.pt`, `.pth`, `.safetensors`) to the repository — `.gitignore` enforces this. Weights are downloaded at runtime via `HF_TOKEN`. The adapter logs a warning at construction time when `HF_TOKEN` is unset so the failure mode is obvious. |

---

## NVIDIA TAO Toolkit — PeopleNet, BodyPose3DNet, ReIdentificationNet

| Field | Detail |
|---|---|
| **Toolkit** | NVIDIA TAO Toolkit (Train, Adapt, Optimize) |
| **Code license** | Apache 2.0 (open source as of TAO 5.0) |
| **Pretrained weight license** | NVIDIA Open Model License — free for use, **weights may not be redistributed or resold** |
| **BodyPose3DNet license** | CC BY 4.0 — cleanest IP path |
| **Access** | https://ngc.nvidia.com — NGC account + API key required |
| **NGC API key** | `NGC_API_KEY` env var / GitHub Actions secret |
| **Commercial use** | Models trained using NVIDIA pretrained weights as a starting point are owned by the user and commercially usable; the NVIDIA pretrained weights themselves cannot be resold |
| **Football-IQ usage** | Phase 2.5 / Phase 3 — Issue 76: hardware-accelerated decode (NVDEC), optional TAO ReIdentificationNet adapter for `stagereid.py`, optional BodyPose3DNet adapter for pose |
| **Models in scope** | PeopleNet (person detection), BodyPose3DNet (3D pose, CC BY 4.0), ReIdentificationNet (cross-camera re-ID) |
| **Deferred** | TAO PeopleNet fine-tune, DeepStream SDK (closed-source / enterprise), Triton Inference Server (medium-term), Cosmos World Models (long-term data augmentation) |
| **Notes** | Model weights are downloaded at runtime via `ngc` CLI or Docker from `nvcr.io`. Do not commit NVIDIA model artifacts to the repository. |

---

## NVIDIA Cosmos World Foundation Models

| Field | Detail |
|---|---|
| **Code license** | Apache 2.0 |
| **Weight license** | NVIDIA Open Model License |
| **Access** | https://ngc.nvidia.com |
| **Football-IQ usage** | Long-term / Phase 4 only — synthetic training data generation for rare-situation footage (low light, crowded box). Out-of-band data augmentation, not in the inference pipeline. |
| **Notes** | Deferred — requires 24.5 GB VRAM (7B) or 80 GB (14B). Cloud GPU (A100/H100) required. |

---

## sportsbd

| Field | Detail |
|---|---|
| **Library** | `sportsbd` by mehdih7 |
| **License** | MIT |
| **Access** | `pip install sportsbd` — no account required |
| **Football-IQ usage** | Issue 75 spike only — benchmark against current optical-flow play segmenter. Not promoted to production without benchmark evidence. |
| **Notes** | 2-star single-author library (as of May 2026). Designed for broadcast shot-boundary detection; applicability to continuous drone footage must be validated before any production use. Benchmark against PySceneDetect as an alternative. |

---

## Ultralytics (YOLOv8 / YOLOv11)

| Field | Detail |
|---|---|
| **License** | AGPL-3.0 (open source) |
| **Commercial use** | Requires Ultralytics Enterprise License for commercial deployment |
| **Access** | `pip install ultralytics` |
| **Football-IQ usage** | Current production detector (`stagedetect.py`) — YOLOv8n, classes 0-32. SAM 3 also loaded via Ultralytics. |

---

## PyTorch

| Field | Detail |
|---|---|
| **License** | BSD-3-Clause |
| **Access** | `pip install torch` — base Docker image `pytorch/pytorch:2.5.1-cuda12.4-cudnn9` |

---

## NVIDIA Video Codec SDK (NVDEC / NVENC)

| Field | Detail |
|---|---|
| **Component** | NVIDIA Video Codec SDK — hardware-accelerated video decode (NVDEC) and encode (NVENC) |
| **License** | [NVIDIA Video Codec SDK License Agreement](https://developer.nvidia.com/nvidia-video-codec-sdk-license-terms) |
| **Access** | Bundled with NVIDIA GPU drivers (≥ 470.x); no separate download required for runtime use. SDK headers available at https://developer.nvidia.com/video-codec-sdk |
| **Commercial use** | Yes — freely usable in commercial products |
| **Football-IQ usage** | Phase 2.5 — Issue #76: `pipeline/hwaccel.py` provides NVDEC-accelerated `cv2.VideoCapture` and NVENC-accelerated ffmpeg encode for `renderer/hls_encoder.py`. Transparent CPU fallback when GPU is unavailable. |
| **Notes** | NVDEC/NVENC capabilities are accessed through OpenCV's FFmpeg backend and the `ffmpeg` CLI (`h264_nvenc`). No NVIDIA SDK headers are compiled into Football-IQ. The driver-level codec libraries (`libnvcuvid.so`, `libnvidia-encode.so`) are part of the standard NVIDIA driver installation. |

---

## ONNX Runtime (GPU)

| Field | Detail |
|---|---|
| **Library** | `onnxruntime-gpu` by Microsoft |
| **License** | MIT |
| **Access** | `pip install onnxruntime-gpu` — no account required |
| **Football-IQ usage** | Phase 2.5 — Issue #76: optional runtime for NVIDIA TAO BodyPose3DNet and ReIdentificationNet ONNX models in `pipeline/pose_estimator.py` and `pipeline/stage_reid.py`. Only loaded when the corresponding model is configured. |

---

## College Football Data (CFBD)

| Field | Detail |
|---|---|
| **Resource** | College Football Data (CFBD) API |
| **Sport coverage** | College football ✅ (American football — Toledo Rockets / MAC). Not soccer. |
| **Toledo / MAC relevance** | Direct — Toledo + MAC schedules, games, drives, plays, team game stats, win probability. |
| **Source URL** | https://collegefootballdata.com — API https://api.collegefootballdata.com (org: https://github.com/CFBD; ecosystem: https://cfbfastr.sportsdataverse.org) |
| **License / access terms** | Free tier / API-key access; review CFBD terms and rate limits before any external or commercial deployment. Attribution to CollegeFootballData.com is surfaced in the UI. |
| **Runtime category** | Production API (backend-only) → cached ingestion into Postgres → read-only backend API. No live vendor call in the request path. |
| **Secret / key requirement** | `CFBD_API_KEY` (+ `CFBD_BASE_URL`) — backend env / Fly.io / GitHub Actions secret. Never exposed to frontend, browser bundles, Workers, logs, or coach-visible errors, and never stored in the database. |
| **Data privacy risk** | None expected — public team/game statistics. No PII, medical, or recruiting data ingested in v1. |
| **Model-router / registry path** | N/A — data integration, not an inference model. |
| **Overlap with closed decisions** | None. Single-camera (#101), pgvector (#8/#77), SAM (#74) decisions are untouched. |
| **Calibrated-tracking dependency** | None. |
| **Football-IQ usage** | Issues #160/#161/#162/#163 — backend `app/cfbd/` client + `cfbd_*` Postgres cache tables (migration 0016), plus read-only `/api/cfbd/*` and College Data frontend surfaces. Synced via `python -m app.cfbd --season <year>`. |
| **Notes** | No vendor key is committed, logged, returned to clients, or written to the database. Cached rows remain available when CFBD is unavailable. |

---

## Sportradar NCAAFB API v7 — evaluated, not adopted (Issue #165)

| Field | Detail |
|---|---|
| **Resource** | Sportradar NCAAFB (NCAA Football) API v7 |
| **Sport coverage** | American / college football ✅ (NCAA FB). Not soccer. |
| **Toledo / MAC relevance** | Broad college football incl. MAC; no Toledo-specific advantage over CFBD established. |
| **Source URL** | https://developer.sportradar.com/football/docs/ncaafb-ig-api-basics |
| **License / access terms** | Commercial B2B contract. Trial: 30 days / 1,000 calls / 1 QPS. Production QPS per signed package. Not redistributable; respect documented TTLs (2 s live PBP, 120 s seasonal stats). |
| **Runtime category** | Documentation only — **evaluated, not adopted** (spike #165). Would be backend-only production API if adopted. |
| **Secret / key requirement** | If adopted: proposed `SPORTRADAR_API_KEY` (+ `SPORTRADAR_BASE_URL`, `SPORTRADAR_ACCESS_LEVEL`, `SPORTRADAR_NCAAFB_VERSION`). Backend-only; `x-api-key` header; never exposed to frontend, browser bundles, Workers, logs, PR/issue text, R2 artifacts, coach-visible errors, or the database. **No value committed.** |
| **Data privacy risk** | Public team/game statistics and game-day player availability statuses. No medical/wellness data; treat statuses as not-for-logging. |
| **Model-router / registry path** | N/A — data integration, not an inference model. |
| **Overlap with closed decisions** | None. CFBD (#160–#163) remains the authoritative college-data source; this spike does **not** replace it. Single-camera (#101), pgvector (#8/#77), SAM (#74) untouched. |
| **Calibrated-tracking dependency** | None (#127/#128/#129 not implicated). |
| **Decision** | **Not adopted now — defer** behind a scoped live in-game feature. CFBD stays authoritative. See [`reports/spike-issue165-sportradar-ncaafb-v7.md`](reports/spike-issue165-sportradar-ncaafb-v7.md). |

---

## Field visualization evaluation — sportypy / sportyR / cfbplotR (Issue #169)

| Field | Detail |
|---|---|
| **Resources evaluated** | `sportypy` (Python, MIT, https://sportypy.sportsdataverse.org); `sportyR` (R, MIT, https://github.com/sportsdataverse/sportyR); `cfbplotR` (R, MIT, https://github.com/sportsdataverse/cfbplotR) |
| **Sport coverage** | American / college football ✅ |
| **Decision** | **Not adopted as runtime dependencies.** Interactive overlays use frontend-native SVG (`frontend/src/components/field-diagram.tsx`). `sportypy` is **deferred** for possible future *offline* Python report plots; R packages (`sportyR`, `cfbplotR`) are **rejected** as a production dependency (no R runtime). See [`docs/adr/0002-field-visualization.md`](docs/adr/0002-field-visualization.md). |
| **Secret / key requirement** | None for any of them. |
| **License impact** | All MIT; none are currently installed/redistributed. A `LICENSES.md` row + dependency add is required *if* `sportypy` is later adopted. |

---

## Dependency Gating Policy

- Any new model dependency must be added to this file **before** the implementing PR is merged.
- New external resources (datasets, models, APIs, libraries) must clear the rubric, soccer/association-football denylist, and license gate in [`docs/external-resource-rubric.md`](docs/external-resource-rubric.md). Football-IQ is an American football platform — soccer resources are rejected.
- CI includes a license-allowlist check (see `.github/workflows/ci.yml`) that fails if a new package is missing from `LICENSES.md`.
- Model weights (`.pt`, `.pth`, `.onnx`, `.engine`) must never be committed to the repository. Download at runtime using `HF_TOKEN` (Hugging Face) or `NGC_API_KEY` (NVIDIA NGC).
- For any model with a gated or non-commercial license, Football-IQ's use case (university-internal, non-commercial coaching analytics) must be re-verified before any external or commercial deployment.

---

*Last updated: May 26, 2026*
