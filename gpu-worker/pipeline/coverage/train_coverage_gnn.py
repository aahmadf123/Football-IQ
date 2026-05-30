"""Offline training harness for the coverage classifier (Issue #139).

**OFFLINE PRETRAINING / EVALUATION ONLY.** This script never runs inside the
same-session or nightly production pipeline and is not wired into the model
router. It fits the :class:`~pipeline.coverage.gnn_classifier.CoverageGNN`
softmax head on labelled coverage graphs, fits a temperature calibrator on a
held-out split (Issue #146), reports accuracy + ECE, and writes a checkpoint the
runtime classifier can load via ``COVERAGE_GNN_MODEL``.

Data contract — each input record is one play's serialised
:class:`~pipeline.spatial.feature_schema.SpatialGraph` (``SpatialGraph.to_dict``)
plus a ``"label"`` field naming one of
:data:`~pipeline.coverage.gnn_classifier.COVERAGE_CLASSES`:

    {"schema_version": 1, "node_features": [[...], ...],
     "edge_index": [[...], [...]], "edge_features": [[...], ...],
     "label": "cover_3"}

Big Data Bowl provenance (#164): BDB ships clean NFL coordinates, so any
checkpoint pretrained on BDB graphs is tagged ``offline-pretraining-evaluation-
only`` and must clear Toledo validation before it is trusted — the checkpoint
carries that marker and the runtime surfaces it in ``detail.provenance``.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import structlog

from pipeline.calibration.calibrated_output import multiclass_ece
from pipeline.coverage.gnn_classifier import (
    COVERAGE_CLASSES,
    CoverageGNN,
    graph_embedding,
)
from pipeline.spatial import feature_schema as fs

log = structlog.get_logger(__name__)

USAGE_MARKER = "offline-pretraining-evaluation-only"

_LABEL_INDEX = {label: i for i, label in enumerate(COVERAGE_CLASSES)}


@dataclass
class TrainingReport:
    n_train: int
    n_holdout: int
    train_accuracy: float
    holdout_accuracy: float
    holdout_ece: float
    classes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_train": self.n_train,
            "n_holdout": self.n_holdout,
            "train_accuracy": round(self.train_accuracy, 4),
            "holdout_accuracy": round(self.holdout_accuracy, 4),
            "holdout_ece": round(self.holdout_ece, 4),
            "classes": list(self.classes),
        }


def graph_from_dict(d: dict[str, Any]) -> fs.SpatialGraph:
    """Reconstruct a :class:`SpatialGraph` from its serialised dict."""
    return fs.SpatialGraph(
        node_ids=list(d.get("node_ids", [])),
        node_features=np.asarray(d.get("node_features", []), dtype=np.float64).reshape(
            -1, len(fs.NODE_FEATURE_NAMES)
        ),
        edge_index=np.asarray(d.get("edge_index", [[], []]), dtype=np.int64).reshape(2, -1),
        edge_features=np.asarray(d.get("edge_features", []), dtype=np.float64).reshape(
            -1, len(fs.EDGE_FEATURE_NAMES)
        ),
        schema_version=int(d.get("schema_version", fs.SCHEMA_VERSION)),
        node_meta=list(d.get("node_meta", [])),
    )


def load_examples(path: Path) -> tuple[list[fs.SpatialGraph], list[int]]:
    """Read a JSONL file of serialised graphs + labels."""
    graphs: list[fs.SpatialGraph] = []
    labels: list[int] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        label = rec.get("label")
        if label not in _LABEL_INDEX:
            log.warning("coverage_train_unknown_label_skipped", label=label)
            continue
        graphs.append(graph_from_dict(rec))
        labels.append(_LABEL_INDEX[label])
    return graphs, labels


def graphs_to_embeddings(graphs: list[fs.SpatialGraph]) -> np.ndarray:
    if not graphs:
        return np.zeros((0, 4 * len(fs.NODE_FEATURE_NAMES)), dtype=np.float64)
    return np.stack([graph_embedding(g) for g in graphs])


def train(
    graphs: list[fs.SpatialGraph],
    labels: list[int],
    *,
    holdout_frac: float = 0.25,
    seed: int = 0,
) -> tuple[CoverageGNN, TrainingReport]:
    """Fit the head + temperature calibrator and report accuracy/ECE."""
    if len(graphs) != len(labels) or not graphs:
        raise ValueError("graphs and labels must be non-empty and equal length")

    emb = graphs_to_embeddings(graphs)
    y = np.asarray(labels, dtype=np.int64)
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(y))
    n_holdout = max(1, int(round(len(y) * holdout_frac))) if len(y) > 1 else 0
    holdout_idx = order[:n_holdout]
    train_idx = order[n_holdout:] if n_holdout else order

    gnn = CoverageGNN(provenance={"usage": USAGE_MARKER})
    gnn.fit(emb[train_idx], y[train_idx], seed=seed)

    train_acc = _accuracy(gnn, emb[train_idx], y[train_idx])
    if n_holdout:
        gnn.calibrate(emb[holdout_idx], y[holdout_idx])
        holdout_acc = _accuracy(gnn, emb[holdout_idx], y[holdout_idx])
        holdout_ece = _ece(gnn, emb[holdout_idx], y[holdout_idx])
    else:
        holdout_acc = float("nan")
        holdout_ece = float("nan")

    report = TrainingReport(
        n_train=int(len(train_idx)),
        n_holdout=int(n_holdout),
        train_accuracy=train_acc,
        holdout_accuracy=holdout_acc,
        holdout_ece=holdout_ece,
        classes=COVERAGE_CLASSES,
    )
    return gnn, report


def _probs_matrix(gnn: CoverageGNN, emb: np.ndarray) -> np.ndarray:
    xs = gnn._standardize(emb)
    assert gnn.weight is not None and gnn.bias is not None
    logits = xs @ gnn.weight.T + gnn.bias
    if gnn.temperature is not None and gnn.temperature.is_fitted:
        return gnn.temperature.transform_logits(logits)
    logits = logits - logits.max(axis=1, keepdims=True)
    e = np.exp(logits)
    return e / e.sum(axis=1, keepdims=True)


def _accuracy(gnn: CoverageGNN, emb: np.ndarray, y: np.ndarray) -> float:
    if emb.shape[0] == 0:
        return float("nan")
    preds = np.argmax(_probs_matrix(gnn, emb), axis=1)
    return float(np.mean(preds == y))


def _ece(gnn: CoverageGNN, emb: np.ndarray, y: np.ndarray) -> float:
    if emb.shape[0] == 0:
        return float("nan")
    return multiclass_ece(_probs_matrix(gnn, emb), y)


def save_checkpoint(
    gnn: CoverageGNN, path: Path, *, report: TrainingReport, source: str
) -> None:
    """Write the checkpoint JSON, stamping offline-only provenance."""
    checkpoint = gnn.to_checkpoint()
    checkpoint["provenance"] = {
        "usage": USAGE_MARKER,
        "source": source,
        "training_report": report.to_dict(),
        "note": (
            "Offline-trained coverage head. NOT validated on Toledo film unless "
            "the source says so. Load via COVERAGE_GNN_MODEL only after Toledo "
            "validation (#139/#164)."
        ),
    }
    path.write_text(json.dumps(checkpoint, indent=2))
    log.info("coverage_checkpoint_written", path=str(path), **report.to_dict())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="JSONL of graphs+labels")
    parser.add_argument("--output", required=True, type=Path, help="checkpoint path")
    parser.add_argument("--source", default="unspecified", help="dataset provenance tag")
    parser.add_argument("--holdout-frac", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    print(f"[coverage-train] {USAGE_MARKER}: offline only, not production inference.")
    graphs, labels = load_examples(args.input)
    if not graphs:
        print("[coverage-train] no labelled examples found; nothing to train.")
        return 1
    gnn, report = train(graphs, labels, holdout_frac=args.holdout_frac, seed=args.seed)
    save_checkpoint(gnn, args.output, report=report, source=args.source)
    print(f"[coverage-train] {json.dumps(report.to_dict())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
