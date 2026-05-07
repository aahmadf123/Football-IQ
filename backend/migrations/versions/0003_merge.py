"""Merge parallel 0003 branches: pipeline_columns and mlops.

Combines the 0003_pipeline_columns branch (clips, field_calibrations, metrics
columns) and the 0003_mlops branch (training_datasets, active_learning_queue)
into a single linear revision chain so that downstream migrations can chain
from a single head.

Revision ID: 0003_merge
Revises: 0003, 0003_mlops
Create Date: 2026-05-07 00:00:00.000000
"""

from collections.abc import Sequence

revision: str = "0003_merge"
down_revision: tuple[str, str] = ("0003", "0003_mlops")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass  # merge point — no schema changes


def downgrade() -> None:
    pass  # merge point — no schema changes
