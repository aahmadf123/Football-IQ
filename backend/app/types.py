"""Custom SQLAlchemy column types.

Currently exposes ``Vector(dim)`` — a thin adapter for the ``vector`` type
provided by the pgvector extension. The ORM never imports the optional
``pgvector`` Python package; the adapter just converts between
``list[float]`` and the textual ``"[1.0,2.0,...]"`` form that pgvector
accepts as input. SELECTs return the textual form and we parse back to
``list[float]`` in the result processor.

This keeps Football-IQ's ORM dependency surface small (we already lean on
raw SQL for the actual ``vector <=> vector`` similarity queries inside
``backend/app/routers/search.py``) while still letting Alembic emit
``vector(N)`` DDL.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.types import UserDefinedType


def _format_vector(value: list[float]) -> str:
    """Render a Python float list as pgvector's textual input format."""
    return "[" + ",".join(repr(float(x)) for x in value) + "]"


def _parse_vector(value: Any) -> list[float] | None:
    """Parse pgvector's textual output (``"[1,2,3]"``) into a Python list."""
    if value is None:
        return None
    if isinstance(value, list):
        return [float(x) for x in value]
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    if not text:
        return []
    return [float(x) for x in text.split(",")]


class Vector(UserDefinedType[list[float]]):
    """Postgres pgvector column type.

    ``Vector(256)`` declares a ``vector(256)`` column at the SQL level and
    round-trips Python ``list[float]`` values.

    Notes:
    - DDL fidelity depends on the pgvector extension being installed; the
      Alembic migration ``0008_play_embeddings.py`` runs
      ``CREATE EXTENSION IF NOT EXISTS vector`` before declaring the
      column.
    - The bind processor only formats lists of floats; ``None`` is passed
      through to allow nullable columns.
    """

    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = int(dim)

    def get_col_spec(self, **_: Any) -> str:
        return f"vector({self.dim})"

    def bind_processor(self, dialect: Any) -> Any:  # noqa: ANN401 — dialect is opaque
        def process(value: Any) -> Any:  # noqa: ANN401
            if value is None:
                return None
            return _format_vector(list(value))

        return process

    def result_processor(self, dialect: Any, coltype: Any) -> Any:  # noqa: ANN401
        def process(value: Any) -> Any:  # noqa: ANN401
            return _parse_vector(value)

        return process
