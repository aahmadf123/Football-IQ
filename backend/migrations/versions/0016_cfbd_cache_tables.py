"""CFBD Postgres cache tables (Issues #160/#161/#162).

Creates the backend-only College Football Data cache:
``cfbd_teams``, ``cfbd_games``, ``cfbd_drives``, ``cfbd_plays``,
``cfbd_team_game_stats``, ``cfbd_win_probability``, and the ``cfbd_sync_runs``
audit table. Source CFBD IDs are preserved with unique constraints so the
ingestion layer can upsert idempotently. No vendor key is stored.

UUID primary keys use a ``gen_random_uuid()`` server default (built into
Postgres 13+) so the ingestion layer's Core bulk upserts get a PK without a
Python-side default.

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-28 19:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYNC_STATUS_ENUM = "cfbd_sync_status"
SYNC_STATUS_VALUES = ("running", "succeeded", "failed", "partial")

_UUID_PK = sa.text("gen_random_uuid()")
_NOW = sa.text("now()")


def _id_column() -> sa.Column[object]:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK)


def _timestamp_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
    ]


def upgrade() -> None:
    # gen_random_uuid() is core in PG13+, but pgcrypto provides it on older
    # builds; create it defensively so the default never fails to resolve.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "cfbd_teams",
        _id_column(),
        sa.Column("cfbd_team_id", sa.BigInteger(), nullable=False),
        sa.Column("school", sa.String(length=120), nullable=False),
        sa.Column("mascot", sa.String(length=120), nullable=True),
        sa.Column("abbreviation", sa.String(length=32), nullable=True),
        sa.Column("conference", sa.String(length=120), nullable=True),
        sa.Column("division", sa.String(length=120), nullable=True),
        sa.Column("classification", sa.String(length=64), nullable=True),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("alt_color", sa.String(length=32), nullable=True),
        sa.Column("logos", sa.JSON(), nullable=True),
        *_timestamp_columns(),
        sa.UniqueConstraint("cfbd_team_id", name="uq_cfbd_teams_source_id"),
    )
    op.create_index("ix_cfbd_teams_cfbd_team_id", "cfbd_teams", ["cfbd_team_id"])
    op.create_index("ix_cfbd_teams_school", "cfbd_teams", ["school"])
    op.create_index("ix_cfbd_teams_conference", "cfbd_teams", ["conference"])

    op.create_table(
        "cfbd_games",
        _id_column(),
        sa.Column("cfbd_game_id", sa.BigInteger(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=True),
        sa.Column("season_type", sa.String(length=32), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("neutral_site", sa.Boolean(), nullable=True),
        sa.Column("conference_game", sa.Boolean(), nullable=True),
        sa.Column("venue", sa.String(length=200), nullable=True),
        sa.Column("venue_id", sa.Integer(), nullable=True),
        sa.Column("home_id", sa.BigInteger(), nullable=True),
        sa.Column("home_team", sa.String(length=120), nullable=True),
        sa.Column("home_conference", sa.String(length=120), nullable=True),
        sa.Column("home_points", sa.Integer(), nullable=True),
        sa.Column("away_id", sa.BigInteger(), nullable=True),
        sa.Column("away_team", sa.String(length=120), nullable=True),
        sa.Column("away_conference", sa.String(length=120), nullable=True),
        sa.Column("away_points", sa.Integer(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=True),
        *_timestamp_columns(),
        sa.UniqueConstraint("cfbd_game_id", name="uq_cfbd_games_source_id"),
    )
    op.create_index("ix_cfbd_games_cfbd_game_id", "cfbd_games", ["cfbd_game_id"])
    op.create_index("ix_cfbd_games_season", "cfbd_games", ["season"])
    op.create_index("ix_cfbd_games_week", "cfbd_games", ["week"])
    op.create_index("ix_cfbd_games_season_type", "cfbd_games", ["season_type"])
    op.create_index("ix_cfbd_games_home_team", "cfbd_games", ["home_team"])
    op.create_index("ix_cfbd_games_away_team", "cfbd_games", ["away_team"])

    op.create_table(
        "cfbd_drives",
        _id_column(),
        sa.Column("cfbd_drive_id", sa.BigInteger(), nullable=False),
        sa.Column("cfbd_game_id", sa.BigInteger(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("offense", sa.String(length=120), nullable=True),
        sa.Column("offense_conference", sa.String(length=120), nullable=True),
        sa.Column("defense", sa.String(length=120), nullable=True),
        sa.Column("defense_conference", sa.String(length=120), nullable=True),
        sa.Column("drive_number", sa.Integer(), nullable=True),
        sa.Column("scoring", sa.Boolean(), nullable=True),
        sa.Column("start_period", sa.Integer(), nullable=True),
        sa.Column("end_period", sa.Integer(), nullable=True),
        sa.Column("plays", sa.Integer(), nullable=True),
        sa.Column("yards", sa.Integer(), nullable=True),
        sa.Column("drive_result", sa.String(length=64), nullable=True),
        *_timestamp_columns(),
        sa.UniqueConstraint("cfbd_drive_id", name="uq_cfbd_drives_source_id"),
    )
    op.create_index("ix_cfbd_drives_cfbd_drive_id", "cfbd_drives", ["cfbd_drive_id"])
    op.create_index("ix_cfbd_drives_cfbd_game_id", "cfbd_drives", ["cfbd_game_id"])
    op.create_index("ix_cfbd_drives_season", "cfbd_drives", ["season"])
    op.create_index("ix_cfbd_drives_offense", "cfbd_drives", ["offense"])
    op.create_index("ix_cfbd_drives_defense", "cfbd_drives", ["defense"])

    op.create_table(
        "cfbd_plays",
        _id_column(),
        sa.Column("cfbd_play_id", sa.BigInteger(), nullable=False),
        sa.Column("cfbd_game_id", sa.BigInteger(), nullable=True),
        sa.Column("cfbd_drive_id", sa.BigInteger(), nullable=True),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("week", sa.Integer(), nullable=True),
        sa.Column("season_type", sa.String(length=32), nullable=True),
        sa.Column("offense", sa.String(length=120), nullable=True),
        sa.Column("offense_conference", sa.String(length=120), nullable=True),
        sa.Column("defense", sa.String(length=120), nullable=True),
        sa.Column("defense_conference", sa.String(length=120), nullable=True),
        sa.Column("home", sa.String(length=120), nullable=True),
        sa.Column("away", sa.String(length=120), nullable=True),
        sa.Column("period", sa.Integer(), nullable=True),
        sa.Column("yard_line", sa.Integer(), nullable=True),
        sa.Column("down", sa.Integer(), nullable=True),
        sa.Column("distance", sa.Integer(), nullable=True),
        sa.Column("yards_gained", sa.Integer(), nullable=True),
        sa.Column("play_type", sa.String(length=120), nullable=True),
        sa.Column("play_text", sa.Text(), nullable=True),
        sa.Column("ppa", sa.Float(), nullable=True),
        sa.Column("scoring", sa.Boolean(), nullable=True),
        *_timestamp_columns(),
        sa.UniqueConstraint("cfbd_play_id", name="uq_cfbd_plays_source_id"),
    )
    op.create_index("ix_cfbd_plays_cfbd_play_id", "cfbd_plays", ["cfbd_play_id"])
    op.create_index("ix_cfbd_plays_cfbd_game_id", "cfbd_plays", ["cfbd_game_id"])
    op.create_index("ix_cfbd_plays_cfbd_drive_id", "cfbd_plays", ["cfbd_drive_id"])
    op.create_index("ix_cfbd_plays_season", "cfbd_plays", ["season"])
    op.create_index("ix_cfbd_plays_week", "cfbd_plays", ["week"])
    op.create_index("ix_cfbd_plays_offense", "cfbd_plays", ["offense"])
    op.create_index("ix_cfbd_plays_defense", "cfbd_plays", ["defense"])

    op.create_table(
        "cfbd_team_game_stats",
        _id_column(),
        sa.Column("cfbd_game_id", sa.BigInteger(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("week", sa.Integer(), nullable=True),
        sa.Column("season_type", sa.String(length=32), nullable=True),
        sa.Column("team", sa.String(length=120), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=True),
        sa.Column("conference", sa.String(length=120), nullable=True),
        sa.Column("opponent", sa.String(length=120), nullable=True),
        sa.Column("home_away", sa.String(length=8), nullable=True),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("stats", sa.JSON(), nullable=True),
        *_timestamp_columns(),
        sa.UniqueConstraint("cfbd_game_id", "team", name="uq_cfbd_team_game_stats_game_team"),
    )
    op.create_index(
        "ix_cfbd_team_game_stats_cfbd_game_id", "cfbd_team_game_stats", ["cfbd_game_id"]
    )
    op.create_index("ix_cfbd_team_game_stats_season", "cfbd_team_game_stats", ["season"])
    op.create_index("ix_cfbd_team_game_stats_team", "cfbd_team_game_stats", ["team"])
    op.create_index("ix_cfbd_team_game_stats_conference", "cfbd_team_game_stats", ["conference"])
    op.create_index("ix_cfbd_team_game_stats_opponent", "cfbd_team_game_stats", ["opponent"])

    op.create_table(
        "cfbd_win_probability",
        _id_column(),
        sa.Column("cfbd_game_id", sa.BigInteger(), nullable=False),
        sa.Column("play_id", sa.BigInteger(), nullable=True),
        sa.Column("play_number", sa.Integer(), nullable=False),
        sa.Column("home", sa.String(length=120), nullable=True),
        sa.Column("away", sa.String(length=120), nullable=True),
        sa.Column("home_id", sa.BigInteger(), nullable=True),
        sa.Column("away_id", sa.BigInteger(), nullable=True),
        sa.Column("spread", sa.Float(), nullable=True),
        sa.Column("home_ball", sa.Boolean(), nullable=True),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("time_remaining", sa.Integer(), nullable=True),
        sa.Column("yard_line", sa.Integer(), nullable=True),
        sa.Column("down", sa.Integer(), nullable=True),
        sa.Column("distance", sa.Integer(), nullable=True),
        sa.Column("home_win_prob", sa.Float(), nullable=True),
        sa.Column("play_text", sa.Text(), nullable=True),
        *_timestamp_columns(),
        sa.UniqueConstraint(
            "cfbd_game_id", "play_number", name="uq_cfbd_win_probability_game_play"
        ),
    )
    op.create_index(
        "ix_cfbd_win_probability_cfbd_game_id", "cfbd_win_probability", ["cfbd_game_id"]
    )
    op.create_index("ix_cfbd_win_probability_play_id", "cfbd_win_probability", ["play_id"])

    # Enum created up-front with checkfirst, then referenced with
    # create_type=False so create_table never re-issues CREATE TYPE.
    postgresql.ENUM(*SYNC_STATUS_VALUES, name=SYNC_STATUS_ENUM).create(
        op.get_bind(), checkfirst=True
    )
    sync_status = postgresql.ENUM(*SYNC_STATUS_VALUES, name=SYNC_STATUS_ENUM, create_type=False)
    op.create_table(
        "cfbd_sync_runs",
        _id_column(),
        sa.Column("endpoint", sa.String(length=64), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("season_type", sa.String(length=32), nullable=True),
        sa.Column("status", sync_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
    )
    op.create_index("ix_cfbd_sync_runs_endpoint", "cfbd_sync_runs", ["endpoint"])
    op.create_index("ix_cfbd_sync_runs_season", "cfbd_sync_runs", ["season"])


def downgrade() -> None:
    op.drop_table("cfbd_sync_runs")
    op.execute(f"DROP TYPE IF EXISTS {SYNC_STATUS_ENUM}")
    op.drop_table("cfbd_win_probability")
    op.drop_table("cfbd_team_game_stats")
    op.drop_table("cfbd_plays")
    op.drop_table("cfbd_drives")
    op.drop_table("cfbd_games")
    op.drop_table("cfbd_teams")
