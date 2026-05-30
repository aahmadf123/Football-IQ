"""Offline CLI for the NFL Big Data Bowl adapter (Issue #164).

Run from ``gpu-worker/``:

    # 1. Normalize a LOCAL copy of a downloaded BDB competition into artifacts.
    #    (Download flow is documented in datasets/bdb/README.md — this command
    #     never touches Kaggle and never downloads anything.)
    python -m datasets.bdb normalize \
        --input-dir /path/to/nfl-big-data-bowl-2025 \
        --output-dir .cache/bdb/2025 \
        --competition nfl-big-data-bowl-2025 --season 2025

    # 2. Emit the offline benchmark/schema report from those artifacts.
    python -m datasets.bdb report --artifact-dir .cache/bdb/2025

    # 3. Self-contained demo on the bundled SYNTHETIC sample (no Kaggle data).
    python -m datasets.bdb demo --output-dir .cache/bdb/demo

OFFLINE PRETRAINING / EVALUATION ONLY. Never wire this into the production
pipeline or the model router.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from datasets.bdb.adapter import normalize_directory
from datasets.bdb.features import build_report, render_markdown
from datasets.bdb.provenance import build_provenance, write_artifacts

_SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "sample")


def _cmd_normalize(args: argparse.Namespace) -> int:
    dataset = normalize_directory(args.input_dir)
    provenance = build_provenance(
        competition=args.competition,
        season=args.season,
        input_dir=args.input_dir,
        dataset=dataset,
    )
    written = write_artifacts(dataset, provenance, args.output_dir)
    print(json.dumps({"record_counts": dataset.record_counts(), "artifacts": written}, indent=2))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    manifest_path = os.path.join(args.artifact_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        print(f"No manifest.json in {args.artifact_dir}; run `normalize` first.", file=sys.stderr)
        return 2
    # Re-derive the dataset from the source dir recorded alongside artifacts is
    # not needed: rebuild straight from the JSONL the artifacts already hold.
    dataset = _load_dataset(args.artifact_dir)
    with open(manifest_path, encoding="utf-8") as handle:
        provenance_dict = json.load(handle)
    report = build_report(dataset, provenance_dict)
    if args.markdown:
        print(render_markdown(report))
    else:
        print(json.dumps(report, indent=2))
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    dataset = normalize_directory(_SAMPLE_DIR)
    provenance = build_provenance(
        competition="synthetic-bdb-sample",
        season=2025,
        input_dir=_SAMPLE_DIR,
        dataset=dataset,
    )
    write_artifacts(dataset, provenance, args.output_dir)
    report = build_report(dataset, provenance.to_dict())
    print(render_markdown(report))
    return 0


def _load_dataset(artifact_dir: str):
    """Rebuild a NormalizedDataset from previously-written JSONL artifacts."""
    from datasets.bdb.schema import (
        NormalizedDataset,
        NormalizedGame,
        NormalizedPlay,
        NormalizedPlayer,
        NormalizedPlayerPlay,
        NormalizedTrackPoint,
    )

    def _read(name: str, ctor):
        path = os.path.join(artifact_dir, f"{name}.jsonl")
        rows = []
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line:
                        rows.append(ctor(**json.loads(line)))
        return rows

    return NormalizedDataset(
        games=_read("games", NormalizedGame),
        plays=_read("plays", NormalizedPlay),
        players=_read("players", NormalizedPlayer),
        player_plays=_read("player_plays", NormalizedPlayerPlay),
        tracking=_read("tracking", NormalizedTrackPoint),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m datasets.bdb", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_norm = sub.add_parser("normalize", help="Normalize a local BDB competition dir.")
    p_norm.add_argument("--input-dir", required=True, help="Local dir of downloaded BDB CSVs.")
    p_norm.add_argument("--output-dir", required=True, help="Gitignored artifact/cache dir.")
    p_norm.add_argument("--competition", required=True, help="e.g. nfl-big-data-bowl-2025")
    p_norm.add_argument("--season", type=int, default=None, help="Season year, e.g. 2025")
    p_norm.set_defaults(func=_cmd_normalize)

    p_report = sub.add_parser("report", help="Emit the offline benchmark/schema report.")
    p_report.add_argument("--artifact-dir", required=True, help="Dir written by `normalize`.")
    p_report.add_argument("--markdown", action="store_true", help="Render Markdown instead of JSON.")
    p_report.set_defaults(func=_cmd_report)

    p_demo = sub.add_parser("demo", help="Run on the bundled SYNTHETIC sample (no Kaggle data).")
    p_demo.add_argument("--output-dir", required=True, help="Where to write demo artifacts.")
    p_demo.set_defaults(func=_cmd_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
