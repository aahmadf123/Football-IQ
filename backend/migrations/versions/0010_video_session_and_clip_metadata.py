"""Video session metadata + practice/game clip model (Issues #97, #98).

Adds, per ADR 0001:

  - ``session_kind`` Postgres enum (``practice|scrimmage|game``)
  - ``source_type`` Postgres enum (``drone|uploaded_clip``)
  - ``side_of_ball`` Postgres enum (``offense|defense|special_teams``)
  - ``videos.session_kind``, ``videos.source_type``,
    ``videos.opponent_team``, ``videos.practice_session_id``,
    ``videos.our_possession`` columns (all nullable)
  - Index on ``videos.recorded_at`` (Hudl-style date sort)
  - ``clips.session_kind``, ``clips.our_possession``,
    ``clips.side_of_ball`` columns (all nullable)
  - Backfill ``clips.side_of_ball`` from ``clips.label_data->>'side_of_ball'``
    where the JSON value is a recognized enum literal. The JSON is left in
    place — this branch does not destroy any existing label_data.
  - Backfill ``clips.our_possession`` from the freshly-set ``side_of_ball``
    so practice clips inherit a sensible default; coaches can correct later.
  - Backfill ``videos.opponent_team`` from ``videos.metadata->>'opponent'``
    where present.

``Tracklet.side_of_ball`` is intentionally left as ``String(10)`` — ADR
0001 §4 pins the vocabulary there but defers the column-type migration.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-26 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Enums ────────────────────────────────────────────────────────────
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE session_kind AS ENUM ('practice','scrimmage','game'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE source_type AS ENUM ('drone','uploaded_clip'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE side_of_ball AS ENUM ('offense','defense','special_teams'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )

    # ── videos ───────────────────────────────────────────────────────────
    op.add_column(
        "videos",
        sa.Column(
            "session_kind",
            sa.Enum("practice", "scrimmage", "game", name="session_kind", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "videos",
        sa.Column(
            "source_type",
            sa.Enum("drone", "uploaded_clip", name="source_type", create_type=False),
            nullable=True,
        ),
    )
    op.add_column("videos", sa.Column("opponent_team", sa.String(120), nullable=True))
    op.add_column(
        "videos",
        sa.Column(
            "practice_session_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "videos",
        sa.Column(
            "our_possession",
            sa.Enum("offense", "defense", "special_teams", name="side_of_ball", create_type=False),
            nullable=True,
        ),
    )
    op.create_index("ix_videos_session_kind", "videos", ["session_kind"])
    op.create_index("ix_videos_opponent_team", "videos", ["opponent_team"])
    op.create_index("ix_videos_practice_session_id", "videos", ["practice_session_id"])
    op.create_index("ix_videos_recorded_at", "videos", ["recorded_at"])

    # ── clips ────────────────────────────────────────────────────────────
    op.add_column(
        "clips",
        sa.Column(
            "session_kind",
            sa.Enum("practice", "scrimmage", "game", name="session_kind", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "clips",
        sa.Column(
            "our_possession",
            sa.Enum("offense", "defense", "special_teams", name="side_of_ball", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "clips",
        sa.Column(
            "side_of_ball",
            sa.Enum("offense", "defense", "special_teams", name="side_of_ball", create_type=False),
            nullable=True,
        ),
    )
    op.create_index("ix_clips_session_kind", "clips", ["session_kind"])
    op.create_index("ix_clips_side_of_ball", "clips", ["side_of_ball"])

    # ── Backfills (non-destructive) ──────────────────────────────────────
    # 1. Clip.side_of_ball from label_data["side_of_ball"] where recognized.
    op.execute(
        """
        UPDATE clips
        SET side_of_ball = (label_data->>'side_of_ball')::side_of_ball
        WHERE label_data IS NOT NULL
          AND label_data->>'side_of_ball' IN ('offense', 'defense', 'special_teams')
          AND side_of_ball IS NULL
        """
    )
    # 2. Clip.our_possession seeded from side_of_ball (same vocabulary;
    #    coaches can correct via PATCH /api/v1/clips/{id}).
    op.execute(
        """
        UPDATE clips
        SET our_possession = side_of_ball
        WHERE our_possession IS NULL
          AND side_of_ball IS NOT NULL
        """
    )
    # 3. Video.opponent_team from metadata->>'opponent' (JSON value
    #    preserved in place — search.py keeps reading it as a fallback).
    op.execute(
        """
        UPDATE videos
        SET opponent_team = metadata->>'opponent'
        WHERE opponent_team IS NULL
          AND metadata IS NOT NULL
          AND metadata ? 'opponent'
          AND length(metadata->>'opponent') > 0
        """
    )


def downgrade() -> None:
    # Drop indexes first, then columns, then enums (only after all columns
    # that reference the enum are gone).
    op.drop_index("ix_clips_side_of_ball", table_name="clips")
    op.drop_index("ix_clips_session_kind", table_name="clips")
    op.drop_column("clips", "side_of_ball")
    op.drop_column("clips", "our_possession")
    op.drop_column("clips", "session_kind")

    op.drop_index("ix_videos_recorded_at", table_name="videos")
    op.drop_index("ix_videos_practice_session_id", table_name="videos")
    op.drop_index("ix_videos_opponent_team", table_name="videos")
    op.drop_index("ix_videos_session_kind", table_name="videos")
    op.drop_column("videos", "our_possession")
    op.drop_column("videos", "practice_session_id")
    op.drop_column("videos", "opponent_team")
    op.drop_column("videos", "source_type")
    op.drop_column("videos", "session_kind")

    op.execute("DROP TYPE IF EXISTS side_of_ball")
    op.execute("DROP TYPE IF EXISTS source_type")
    op.execute("DROP TYPE IF EXISTS session_kind")
