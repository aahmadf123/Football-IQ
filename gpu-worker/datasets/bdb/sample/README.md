# SYNTHETIC BDB sample — NOT real data

Every file in this directory is **hand-fabricated synthetic data** that only
mimics the NFL Big Data Bowl (BDB) **column schema**. It contains:

- **No real NFL Big Data Bowl / Kaggle data.** Teams (`AAA`, `BBB`), player
  names, `nflId`s, and all coordinates are made up.
- **No Toledo film and no Toledo labels.**

It exists solely so the adapter, the offline benchmark, and the unit tests can
run deterministically in CI **without downloading anything from Kaggle**. Real
BDB data is never committed to this repository — see
[`../README.md`](../README.md) for the documented download flow and the gitignored
cache/artifact paths real runs use.

Run the self-contained demo (writes to a gitignored dir of your choosing):

```bash
cd gpu-worker
python -m datasets.bdb demo --output-dir .cache/bdb/demo
```
