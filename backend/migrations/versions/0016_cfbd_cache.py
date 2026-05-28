"""CFBD cache tables (Issues #161/#162/#163).

Creates the CollegeFootballData.com cache tables so Toledo/MAC analytics can be
served from Postgres without a live vendor call on every request:

    cfbd_sync_runs        — one row per ingestion attempt (drives cache_meta)
    cfbd_teams            — Toledo, MAC peers, scheduled opponents
    cfbd_games            — schedule / game results
    cfbd_drives           — per-game drive summaries
    cfbd_plays            — per-game play-by-play
    cfbd_team_game_stats  — per-team box-score stats per game
    cfbd_win_probability  — per-play win-probability timeline

American football (college) only. No vendor API key is stored in these tables.

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-28 20:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_missing(conn: sa.engine.Connection, name: str) -> bool:
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=:name"
        ),
        {"name": name},
    ).scalar()
    return not exists


def upgrade() -> None:
    conn = op.get_bind()

    cfbd_sync_status = postgresql.ENUM("running", "ok", "partial", "error", name="cfbd_sync_status")
    cfbd_sync_status.create(conn, checkfirst=True)

    if _table_missing(conn, "cfbd_sync_runs"):
        op.create_table(
            "cfbd_sync_runs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("source_endpoint", sa.String(64), nullable=False, index=True),
            sa.Column("parameters", sa.JSON, nullable=True),
            sa.Column(
                "status",
                postgresql.ENUM(name="cfbd_sync_status", create_type=False),
                nullable=False,
                index=True,
            ),
            sa.Column("row_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("error_summary", sa.Text, nullable=True),
            sa.Column(
                "started_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )

    if _table_missing(conn, "cfbd_teams"):
        op.create_table(
            "cfbd_teams",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("cfbd_team_id", sa.Integer, nullable=True, unique=True, index=True),
            sa.Column("school", sa.String(128), nullable=False, index=True),
            sa.Column("mascot", sa.String(128), nullable=True),
            sa.Column("abbreviation", sa.String(16), nullable=True),
            sa.Column("conference", sa.String(64), nullable=True, index=True),
            sa.Column("division", sa.String(64), nullable=True),
            sa.Column("color", sa.String(16), nullable=True),
            sa.Column("alt_color", sa.String(16), nullable=True),
            sa.Column("logos", sa.JSON, nullable=True),
            sa.Column("raw", sa.JSON, nullable=True),
            sa.Column(
                "synced_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    if _table_missing(conn, "cfbd_games"):
        op.create_table(
            "cfbd_games",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("cfbd_game_id", sa.Integer, nullable=False, unique=True, index=True),
            sa.Column("season", sa.Integer, nullable=False, index=True),
            sa.Column("week", sa.Integer, nullable=True),
            sa.Column("season_type", sa.String(32), nullable=True),
            sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("home_team", sa.String(128), nullable=True, index=True),
            sa.Column("away_team", sa.String(128), nullable=True, index=True),
            sa.Column("home_conference", sa.String(64), nullable=True),
            sa.Column("away_conference", sa.String(64), nullable=True),
            sa.Column("home_points", sa.Integer, nullable=True),
            sa.Column("away_points", sa.Integer, nullable=True),
            sa.Column("venue", sa.String(160), nullable=True),
            sa.Column("completed", sa.Boolean, nullable=True),
            sa.Column("raw", sa.JSON, nullable=True),
            sa.Column(
                "synced_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    if _table_missing(conn, "cfbd_drives"):
        op.create_table(
            "cfbd_drives",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("cfbd_drive_id", sa.Integer, nullable=False, unique=True, index=True),
            sa.Column("cfbd_game_id", sa.Integer, nullable=False, index=True),
            sa.Column("offense", sa.String(128), nullable=True),
            sa.Column("defense", sa.String(128), nullable=True),
            sa.Column("drive_number", sa.Integer, nullable=True),
            sa.Column("scoring", sa.Boolean, nullable=True),
            sa.Column("start_period", sa.Integer, nullable=True),
            sa.Column("end_period", sa.Integer, nullable=True),
            sa.Column("plays", sa.Integer, nullable=True),
            sa.Column("yards", sa.Integer, nullable=True),
            sa.Column("drive_result", sa.String(64), nullable=True),
            sa.Column("raw", sa.JSON, nullable=True),
            sa.Column(
                "synced_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    if _table_missing(conn, "cfbd_plays"):
        op.create_table(
            "cfbd_plays",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("cfbd_play_id", sa.Integer, nullable=False, unique=True, index=True),
            sa.Column("cfbd_game_id", sa.Integer, nullable=False, index=True),
            sa.Column("cfbd_drive_id", sa.Integer, nullable=True, index=True),
            sa.Column("offense", sa.String(128), nullable=True),
            sa.Column("defense", sa.String(128), nullable=True),
            sa.Column("period", sa.Integer, nullable=True),
            sa.Column("clock", sa.String(16), nullable=True),
            sa.Column("down", sa.Integer, nullable=True),
            sa.Column("distance", sa.Integer, nullable=True),
            sa.Column("yard_line", sa.Integer, nullable=True),
            sa.Column("yards_gained", sa.Integer, nullable=True),
            sa.Column("play_type", sa.String(64), nullable=True),
            sa.Column("play_text", sa.Text, nullable=True),
            sa.Column("ppa", sa.Float, nullable=True),
            sa.Column("raw", sa.JSON, nullable=True),
            sa.Column(
                "synced_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    if _table_missing(conn, "cfbd_team_game_stats"):
        op.create_table(
            "cfbd_team_game_stats",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("cfbd_game_id", sa.Integer, nullable=False, index=True),
            sa.Column("season", sa.Integer, nullable=False, index=True),
            sa.Column("team", sa.String(128), nullable=False, index=True),
            sa.Column("conference", sa.String(64), nullable=True, index=True),
            sa.Column("opponent", sa.String(128), nullable=True),
            sa.Column("home_away", sa.String(8), nullable=True),
            sa.Column("points", sa.Integer, nullable=True),
            sa.Column("stats", sa.JSON, nullable=True),
            sa.Column("raw", sa.JSON, nullable=True),
            sa.Column(
                "synced_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("cfbd_game_id", "team", name="uq_cfbd_team_game_stats_game_team"),
        )

    if _table_missing(conn, "cfbd_win_probability"):
        op.create_table(
            "cfbd_win_probability",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("cfbd_game_id", sa.Integer, nullable=False, index=True),
            sa.Column("play_number", sa.Integer, nullable=True),
            sa.Column("cfbd_play_id", sa.Integer, nullable=True),
            sa.Column("home_team", sa.String(128), nullable=True),
            sa.Column("away_team", sa.String(128), nullable=True),
            sa.Column("home_win_prob", sa.Float, nullable=True),
            sa.Column("period", sa.Integer, nullable=True),
            sa.Column("clock", sa.String(16), nullable=True),
            sa.Column("play_text", sa.Text, nullable=True),
            sa.Column("raw", sa.JSON, nullable=True),
            sa.Column(
                "synced_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "cfbd_game_id", "play_number", name="uq_cfbd_win_probability_game_play"
            ),
        )


def downgrade() -> None:
    op.drop_table("cfbd_win_probability")
    op.drop_table("cfbd_team_game_stats")
    op.drop_table("cfbd_plays")
    op.drop_table("cfbd_drives")
    op.drop_table("cfbd_games")
    op.drop_table("cfbd_teams")
    op.drop_table("cfbd_sync_runs")
    postgresql.ENUM(name="cfbd_sync_status").drop(op.get_bind(), checkfirst=True)
