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
| **Football-IQ usage** | Phase 2.5 — Issue 74: detection and tracking adapter (`stagedetect.py`, `stagetrack.py`), nightly-priority routing only until distilled variant validated |
| **Notes** | Do not commit model weights (`.pt` files) to the repository. Weights are downloaded at runtime via `HF_TOKEN`. Add `.pt` to `.gitignore` if not already present. |

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
| **License** | MIT-style permissive license (NVIDIA Video Codec SDK License Agreement) |
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

## Dependency Gating Policy

- Any new model dependency must be added to this file **before** the implementing PR is merged.
- CI includes a license-allowlist check (see `.github/workflows/ci.yml`) that fails if a new package is missing from `LICENSES.md`.
- Model weights (`.pt`, `.pth`, `.onnx`, `.engine`) must never be committed to the repository. Download at runtime using `HF_TOKEN` (Hugging Face) or `NGC_API_KEY` (NVIDIA NGC).
- For any model with a gated or non-commercial license, Football-IQ's use case (university-internal, non-commercial coaching analytics) must be re-verified before any external or commercial deployment.

---

*Last updated: May 26, 2026*
