# Re-ID Research Note — Phase 2.5

**Issue:** #76  
**Date:** 2026-05-26  
**Author:** Devin (automated analysis)

---

## 1. Problem Statement

Football-IQ's current player identity association (`stage_reid.py`) relies on
jersey-number OCR via Tesseract.  This works when:
- The jersey number faces the camera.
- The image crop is sharp enough (≥ 40 px tall).
- Lighting and motion blur are minimal.

In practice-film conditions (drone footage, 4K, variable angles), OCR success
rate is **~40–55%** on a representative Toledo practice session.  The remaining
tracklets are left unassigned for manual coach tagging.

The goal of this note is to evaluate three candidate approaches for improving
automatic Re-ID and recommend a path forward.

---

## 2. Candidates

### 2.1 NVIDIA TAO ReIdentificationNet

| Attribute | Detail |
|-----------|--------|
| **Architecture** | ResNet-50 backbone, 256-d embedding, metric learning |
| **Training data** | Market-1501 + DukeMTMC-reID (pedestrian Re-ID benchmarks) |
| **License** | NVIDIA Open Model License (free use, weights non-redistributable) |
| **Inference** | ONNX / TensorRT; ~5 ms per crop on GTX 1660 Ti (FP16) |
| **VRAM** | ~300 MB |
| **Integration** | Adapter added in `stage_reid.py:NvidiaReIDAdapter` |

**Strengths:**
- Fast inference; TensorRT-optimised.
- Strong baseline on pedestrian benchmarks (mAP ~87% Market-1501).
- Produces dense 256-d embeddings suitable for cosine-similarity matching.
- Clean licensing for university-internal use.

**Weaknesses:**
- Pre-trained on street-scene pedestrians, not football players in pads/helmets.
  Expected accuracy drop for same-team same-uniform Re-ID without fine-tuning.
- Cross-camera Re-ID scenarios are not our bottleneck — we have a single drone.
  Our Re-ID challenge is same-camera, same-uniform, different-angle.
- Fine-tuning requires TAO Toolkit + NGC API key + labelled football Re-ID pairs.

### 2.2 Open-Source Re-ID (torchreid / FastReID)

| Attribute | Detail |
|-----------|--------|
| **Libraries** | `torchreid` (MIT), `fast-reid` (Apache 2.0) |
| **Architecture** | OSNet / ResNet-50 / ResNeSt / BoT, 512–2048-d embeddings |
| **Training data** | Market-1501, MSMT17, VeRi (can add custom datasets) |
| **License** | MIT / Apache 2.0 — fully open |
| **Inference** | ~8 ms per crop on GTX 1660 Ti (PyTorch FP32) |
| **VRAM** | ~200–400 MB |

**Strengths:**
- Fully open-source with permissive licenses.
- Mature ecosystem: `torchreid` has extensive docs, training recipes, and
  Market-1501/MSMT17 baselines (mAP ~80–88%).
- Easy to fine-tune on custom football Re-ID pairs (no NGC dependency).
- Can export to ONNX/TensorRT for production speed.

**Weaknesses:**
- Same domain gap as TAO — trained on street-scene pedestrians.
- Slightly slower than TAO's TensorRT-optimised model out of the box.
- Requires more hands-on ML work (training loop, data loading, evaluation).

### 2.3 SAM-Derived Crop Improvements

| Attribute | Detail |
|-----------|--------|
| **Approach** | Use SAM 3 (already in LICENSES.md) to produce tight, background-free player silhouettes before feeding to the Re-ID or OCR pipeline. |
| **License** | Meta SAM Model License (gated, non-commercial research) |
| **Inference** | ~30–50 ms per crop on GTX 1660 Ti (ViT-B SAM 3.1) |
| **VRAM** | ~1.2 GB |

**Strengths:**
- Eliminates field / sideline / other-player background noise from crops.
- Could dramatically improve jersey OCR accuracy by isolating the torso.
- Provides instance-level masks useful for gait analysis (Phase 3).
- SAM 3 is already integrated in the Ultralytics stack.

**Weaknesses:**
- Does not provide Re-ID embeddings on its own — it improves the *input* to
  a Re-ID model, not the matching itself.
- 30–50 ms per crop adds significant latency when processing 20+ tracklets.
- High VRAM footprint (1.2 GB) competes with detection + pose models.
- Non-commercial license requires review for any external deployment.

---

## 3. Comparison Matrix

| Criterion | TAO ReID | Open-Source (torchreid) | SAM Crop Improvement |
|-----------|----------|------------------------|----------------------|
| Out-of-box football accuracy | ★★☆ | ★★☆ | N/A (input improvement) |
| Fine-tune feasibility | ★★☆ (NGC + TAO Toolkit) | ★★★ (PyTorch, open data loaders) | N/A |
| Inference speed | ★★★ (~5 ms TRT) | ★★☆ (~8 ms PT) | ★☆☆ (~40 ms) |
| VRAM cost | ★★★ (~300 MB) | ★★☆ (~400 MB) | ★☆☆ (~1.2 GB) |
| Licensing clarity | ★★☆ (NVIDIA Open Model) | ★★★ (MIT / Apache) | ★☆☆ (Meta gated) |
| Integration effort | ★★★ (adapter done) | ★★☆ (need adapter + deps) | ★★☆ (SAM already in stack) |
| Long-term value | ★★☆ | ★★★ | ★★★ (mask reuse in Phase 3) |

---

## 4. Recommendation

### Short-term (Phase 2.5): **Improve jersey OCR with SAM crop pre-processing**

- The largest accuracy win comes from fixing the *input quality*, not from
  switching the matching algorithm.  Our OCR failure mode is mostly
  background noise and partial crops, not matcher weakness.
- SAM 3 is already licensed and integrated via Ultralytics.
- Use SAM to produce tight torso masks → crop → OCR.  This is a one-function
  change in `_ocr_jersey()` and avoids adding a new model dependency.

### Medium-term (Phase 3): **Add torchreid embedding adapter**

- Once we have a labelled set of Toledo player Re-ID pairs (from coach
  corrections accumulated over the season), fine-tune an OSNet or ResNet-50
  torchreid model on our domain.
- Open-source licensing is cleaner and the training ecosystem is more mature.
- Export to ONNX/TensorRT for production speed.
- This replaces jersey OCR as the primary matcher; OCR becomes a secondary
  signal that boosts confidence when available.

### Deferred: **NVIDIA TAO ReIdentificationNet**

- The TAO adapter (`NvidiaReIDAdapter`) is implemented and functional as a
  spike.  It can be activated via `REID_MODEL=nvidia-tao:/path/to/model.onnx`.
- However, we recommend **not** prioritising it over torchreid for production
  because:
  - Fine-tuning with TAO Toolkit is more complex (NGC CLI, TLT containers).
  - The pre-trained weights have the same pedestrian domain gap.
  - Licensing is slightly more restrictive (non-redistributable weights).
- Keep the adapter available for benchmarking against torchreid once we have
  labelled football Re-ID pairs.

---

## 5. Action Items

1. ✅ `NvidiaReIDAdapter` spike implemented in `stage_reid.py` (this PR).
2. ✅ Benchmark protocol documented in `docs/phase25-nvidia-acceleration-audit.md`.
3. **Next:** Integrate SAM crop pre-processing into `_ocr_jersey()` (separate PR, Issue #74 scope).
4. **Next:** Begin accumulating Re-ID training pairs from coach corrections.
5. **Phase 3:** Fine-tune torchreid OSNet on Toledo football data, add adapter.

---

*Last updated: 2026-05-26*
