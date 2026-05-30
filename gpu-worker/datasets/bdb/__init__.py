"""Offline NFL Big Data Bowl (BDB) → Football-IQ adapter (Issue #164).

OFFLINE PRETRAINING / EVALUATION ONLY. This package:

  * never downloads from Kaggle (callers point it at a local copy),
  * never commits Kaggle data,
  * never runs in the same-session or nightly production pipeline,
  * is not wired into the model router (`pipeline.model_router`),
  * makes no claim that BDB labels/coordinates equal Toledo labels/coordinates.

See ``datasets/bdb/README.md`` for the Kaggle auth/download flow, schema mapping,
and license caveats.
"""

from datasets.bdb.adapter import (
    NormalizedDataset,
    normalize_directory,
    normalize_games,
    normalize_player_plays,
    normalize_players,
    normalize_plays,
    normalize_tracking,
)
from datasets.bdb.features import build_report, render_markdown
from datasets.bdb.provenance import build_provenance, write_artifacts
from datasets.bdb.schema import SCHEMA_VERSION, USAGE_MARKER

__all__ = [
    "SCHEMA_VERSION",
    "USAGE_MARKER",
    "NormalizedDataset",
    "normalize_directory",
    "normalize_games",
    "normalize_plays",
    "normalize_players",
    "normalize_player_plays",
    "normalize_tracking",
    "build_provenance",
    "write_artifacts",
    "build_report",
    "render_markdown",
]
