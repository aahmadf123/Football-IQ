# NFL Big Data Bowl (BDB) — local data, NOT committed (Issue #164)

This directory is a **pointer only**. No NFL Big Data Bowl / Kaggle data is
committed to the repository, and none should ever be.

- **Raw downloads** live in a gitignored local/cache path, default
  `BDB_DATA_DIR` (`$HOME/.cache/football-iq/bdb`). See the documented Kaggle
  auth/download flow in
  [`gpu-worker/datasets/bdb/README.md`](../../gpu-worker/datasets/bdb/README.md).
- **Normalized artifacts** (`*.jsonl` + `manifest.json`) are written to
  `BDB_ARTIFACT_DIR` (default `gpu-worker/.cache/bdb`), also gitignored.
- The adapter is **offline pretraining / evaluation only** — not production
  runtime, not in the model router, and BDB is **not Toledo film**.

The only BDB-shaped files committed anywhere are the clearly-labeled **synthetic**
fixtures under
[`gpu-worker/datasets/bdb/sample/`](../../gpu-worker/datasets/bdb/sample/), which
exist solely so the adapter and its tests run in CI without downloading anything.
