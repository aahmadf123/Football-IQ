"""Typed Pydantic v2 response models for the CFBD endpoints we consume.

CFBD returns camelCase JSON. Each model accepts the camelCase wire names via
field aliases while exposing snake_case Python attributes, and ignores unknown
fields (``extra="ignore"``) so upstream additions never break parsing. Only the
fields Football-IQ needs for Toledo/MAC analytics are typed; the full raw row is
preserved separately by the ingestion layer where useful.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_CONFIG = ConfigDict(populate_by_name=True, extra="ignore")


class CFBDTeam(BaseModel):
    """A team from ``GET /teams``."""

    model_config = _CONFIG

    id: int
    school: str
    mascot: str | None = None
    abbreviation: str | None = None
    conference: str | None = None
    division: str | None = None
    classification: str | None = None
    color: str | None = None
    alt_color: str | None = Field(default=None, alias="altColor")
    logos: list[str] | None = None


class CFBDGame(BaseModel):
    """A game from ``GET /games``."""

    model_config = _CONFIG

    id: int
    season: int
    week: int | None = None
    season_type: str | None = Field(default=None, alias="seasonType")
    start_date: str | None = Field(default=None, alias="startDate")
    neutral_site: bool | None = Field(default=None, alias="neutralSite")
    conference_game: bool | None = Field(default=None, alias="conferenceGame")
    venue: str | None = None
    venue_id: int | None = Field(default=None, alias="venueId")
    home_id: int | None = Field(default=None, alias="homeId")
    home_team: str | None = Field(default=None, alias="homeTeam")
    home_conference: str | None = Field(default=None, alias="homeConference")
    home_points: int | None = Field(default=None, alias="homePoints")
    away_id: int | None = Field(default=None, alias="awayId")
    away_team: str | None = Field(default=None, alias="awayTeam")
    away_conference: str | None = Field(default=None, alias="awayConference")
    away_points: int | None = Field(default=None, alias="awayPoints")
    completed: bool | None = None


class CFBDDrive(BaseModel):
    """A drive from ``GET /drives``."""

    model_config = _CONFIG

    id: int
    game_id: int = Field(alias="gameId")
    offense: str | None = None
    offense_conference: str | None = Field(default=None, alias="offenseConference")
    defense: str | None = None
    defense_conference: str | None = Field(default=None, alias="defenseConference")
    drive_number: int | None = Field(default=None, alias="driveNumber")
    scoring: bool | None = None
    start_period: int | None = Field(default=None, alias="startPeriod")
    end_period: int | None = Field(default=None, alias="endPeriod")
    plays: int | None = None
    yards: int | None = None
    drive_result: str | None = Field(default=None, alias="driveResult")


class CFBDPlay(BaseModel):
    """A play from ``GET /plays``."""

    model_config = _CONFIG

    id: int
    drive_id: int | None = Field(default=None, alias="driveId")
    game_id: int | None = Field(default=None, alias="gameId")
    offense: str | None = None
    offense_conference: str | None = Field(default=None, alias="offenseConference")
    defense: str | None = None
    defense_conference: str | None = Field(default=None, alias="defenseConference")
    home: str | None = None
    away: str | None = None
    period: int | None = None
    yard_line: int | None = Field(default=None, alias="yardLine")
    down: int | None = None
    distance: int | None = None
    yards_gained: int | None = Field(default=None, alias="yardsGained")
    play_type: str | None = Field(default=None, alias="playType")
    play_text: str | None = Field(default=None, alias="playText")
    ppa: float | None = None
    scoring: bool | None = None


class CFBDStat(BaseModel):
    """A single category/value pair inside a team's game-stats block."""

    model_config = _CONFIG

    category: str
    stat: str | None = None


class CFBDTeamStats(BaseModel):
    """One team's stats within a game from ``GET /games/teams``."""

    model_config = _CONFIG

    team_id: int | None = Field(default=None, alias="teamId")
    school: str | None = Field(default=None, alias="team")
    conference: str | None = None
    home_away: str | None = Field(default=None, alias="homeAway")
    points: int | None = None
    stats: list[CFBDStat] = Field(default_factory=list)


class CFBDGameTeamStats(BaseModel):
    """A game wrapper from ``GET /games/teams`` containing both teams."""

    model_config = _CONFIG

    id: int
    teams: list[CFBDTeamStats] = Field(default_factory=list)


class CFBDWinProbability(BaseModel):
    """A win-probability play row from ``GET /metrics/wp``."""

    model_config = _CONFIG

    game_id: int = Field(alias="gameId")
    play_id: int | None = Field(default=None, alias="playId")
    play_number: int | None = Field(default=None, alias="playNumber")
    home: str | None = None
    away: str | None = None
    home_id: int | None = Field(default=None, alias="homeId")
    away_id: int | None = Field(default=None, alias="awayId")
    spread: float | None = None
    home_ball: bool | None = Field(default=None, alias="homeBall")
    home_score: int | None = Field(default=None, alias="homeScore")
    away_score: int | None = Field(default=None, alias="awayScore")
    time_remaining: int | None = Field(default=None, alias="timeRemaining")
    yard_line: int | None = Field(default=None, alias="yardLine")
    down: int | None = None
    distance: int | None = None
    home_win_prob: float | None = Field(default=None, alias="homeWinProb")
    play_text: str | None = Field(default=None, alias="playText")
