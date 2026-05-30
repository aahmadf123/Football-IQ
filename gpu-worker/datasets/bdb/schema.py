"""Normalized schema + BDB→Football-IQ field mapping (Issue #164).

This module defines the *stable local artifact schema* the NFL Big Data Bowl
(BDB) adapter normalizes raw Kaggle CSVs into. The schema is intentionally
small, flat, and JSON-serializable so downstream offline work (#139 coverage
GNN, #140 pre-snap pressure, #141 counterfactual simulator, #150 cross-regime
self-distillation) can read it without pulling in pandas/torch.

IMPORTANT — these records are **offline pretraining / evaluation only**. BDB
ships clean, hand-corrected NFL tracking coordinates in field yards. Football-IQ
derives field coordinates from single-camera video through the calibration /
detection / tracking chain (#127 / #128 / #129). The two are *analogous* but not
interchangeable: a BDB label is **not** a Toledo label, and a BDB coordinate is
**not** a calibrated Football-IQ coordinate. The schema records the source so a
consumer can never silently confuse the two.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Bump when the normalized record shape changes. Written into every manifest.
SCHEMA_VERSION = 1

# Field-of-play geometry the BDB coordinate frame uses, recorded so downstream
# code never assumes pixels. x runs end zone → end zone (0..120 incl. both end
# zones), y runs sideline → sideline (0..53.3). This is NOT a calibrated
# Football-IQ homography output — see module docstring.
BDB_FIELD_LENGTH_YARDS = 120.0
BDB_FIELD_WIDTH_YARDS = 53.3
COORDINATE_FRAME = "bdb_field_yards"

# Marker stamped onto every artifact manifest so no consumer mistakes these for
# production / Toledo data.
USAGE_MARKER = "offline-pretraining-evaluation-only"

# Sentinel club value BDB uses for the ball row in tracking files.
FOOTBALL_CLUB = "football"


# ─────────────────────────────────────────────────────────────────────────────
# Column aliasing
#
# BDB 2025 uses camelCase headers (gameId, nflId, frameId, ...). BDB 2026 and
# some derived exports use snake_case (game_id, nfl_id, frame_id, ...). The
# adapter normalizes every incoming header to lower-case and looks the canonical
# field up through these alias sets, so one code path handles both seasons.
# ─────────────────────────────────────────────────────────────────────────────

# canonical -> set of accepted (already-lowercased) source header spellings.
_GAME_ALIASES: dict[str, set[str]] = {
    "game_id": {"gameid", "game_id"},
    "season": {"season", "year"},
    "week": {"week"},
    "game_date": {"gamedate", "game_date"},
    "home_team": {"hometeamabbr", "home_team_abbr", "home_team", "hometeam"},
    "away_team": {
        "visitorteamabbr",
        "visitor_team_abbr",
        "awayteamabbr",
        "away_team_abbr",
        "away_team",
        "visitorteam",
    },
}

_PLAY_ALIASES: dict[str, set[str]] = {
    "game_id": {"gameid", "game_id"},
    "play_id": {"playid", "play_id"},
    "quarter": {"quarter", "period"},
    "down": {"down"},
    "yards_to_go": {"yardstogo", "yards_to_go"},
    "possession_team": {"possessionteam", "possession_team"},
    "defensive_team": {"defensiveteam", "defensive_team"},
    "offense_formation": {"offenseformation", "offense_formation"},
    "receiver_alignment": {"receiveralignment", "receiver_alignment"},
    "yardline_side": {"yardlineside", "yardline_side"},
    "yardline_number": {"yardlinenumber", "yardline_number"},
    "los_absolute_yard": {"absoluteyardlinenumber", "absolute_yardline_number"},
    "pass_result": {"passresult", "pass_result"},
    "play_direction": {"playdirection", "play_direction"},
}

_PLAYER_ALIASES: dict[str, set[str]] = {
    "nfl_id": {"nflid", "nfl_id"},
    "display_name": {"displayname", "display_name", "player_name"},
    "position": {"position", "player_position"},
    "height": {"height"},
    "weight": {"weight"},
    "college": {"collegename", "college_name", "college"},
}

_PLAYER_PLAY_ALIASES: dict[str, set[str]] = {
    "game_id": {"gameid", "game_id"},
    "play_id": {"playid", "play_id"},
    "nfl_id": {"nflid", "nfl_id"},
    "team": {"teamabbr", "team_abbr", "club", "team"},
    "route_ran": {"routeran", "route_ran", "route"},
    "was_running_route": {"wasrunningroute", "was_running_route"},
    "motion_since_lineset": {"motionsincelineset", "motion_since_lineset"},
    "in_motion_at_snap": {"inmotionatballsnap", "in_motion_at_ball_snap", "in_motion_at_snap"},
}

_TRACK_ALIASES: dict[str, set[str]] = {
    "game_id": {"gameid", "game_id"},
    "play_id": {"playid", "play_id"},
    "nfl_id": {"nflid", "nfl_id"},
    "frame_id": {"frameid", "frame_id", "frame"},
    "time": {"time"},
    "jersey_number": {"jerseynumber", "jersey_number"},
    "club": {"club", "team", "teamabbr"},
    "play_direction": {"playdirection", "play_direction"},
    "x": {"x"},
    "y": {"y"},
    "s": {"s", "speed"},
    "a": {"a", "acceleration", "accel"},
    "dis": {"dis", "distance"},
    "o": {"o", "orientation"},
    "dir": {"dir", "direction"},
    "event": {"event"},
}


@dataclass(frozen=True)
class NormalizedGame:
    """A BDB game → Football-IQ session-level metadata (offline analogue)."""

    game_id: str
    season: int | None
    week: int | None
    game_date: str | None
    home_team: str | None
    away_team: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedPlay:
    """A BDB play → Football-IQ play concept (offline analogue)."""

    game_id: str
    play_id: str
    quarter: int | None
    down: int | None
    yards_to_go: int | None
    possession_team: str | None
    defensive_team: str | None
    offense_formation: str | None
    receiver_alignment: str | None
    yardline_side: str | None
    yardline_number: int | None
    los_absolute_yard: float | None
    pass_result: str | None
    play_direction: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedPlayer:
    """A BDB roster player → Football-IQ player concept (offline analogue)."""

    nfl_id: str
    display_name: str | None
    position: str | None
    height: str | None
    weight: int | None
    college: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedPlayerPlay:
    """Per-player-per-play BDB row carrying route / motion labels.

    Routes and motion flags are the closest BDB analogue to Football-IQ route /
    label taxonomy. They feed offline route-ID (#141) and pressure (#140) work —
    they are NOT asserted to equal Toledo labels.
    """

    game_id: str
    play_id: str
    nfl_id: str
    team: str | None
    route_ran: str | None
    was_running_route: bool | None
    motion_since_lineset: bool | None
    in_motion_at_snap: bool | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedTrackPoint:
    """One player (or the ball) at one frame.

    Mirrors Football-IQ tracklet samples (x/y plus kinematics) but in the BDB
    field-yard coordinate frame, NOT a calibrated single-camera output.
    """

    game_id: str
    play_id: str
    nfl_id: str | None
    frame_id: int | None
    time: str | None
    jersey_number: int | None
    club: str | None
    side: str | None  # "offense" | "defense" | "ball" | None (filled on join)
    play_direction: str | None
    x: float | None
    y: float | None
    s: float | None  # speed (yd/s)  ~ Football-IQ speed
    a: float | None  # acceleration (yd/s^2)
    dis: float | None  # distance since last frame (yd)
    o: float | None  # orientation (deg) ~ body facing
    dir: float | None  # direction of motion (deg)
    event: str | None  # e.g. ball_snap, pass_forward, tackle

    @property
    def is_ball(self) -> bool:
        return self.club == FOOTBALL_CLUB or self.nfl_id in (None, "")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NormalizedDataset:
    """In-memory bundle of all normalized tables for one BDB competition/season."""

    games: list[NormalizedGame] = field(default_factory=list)
    plays: list[NormalizedPlay] = field(default_factory=list)
    players: list[NormalizedPlayer] = field(default_factory=list)
    player_plays: list[NormalizedPlayerPlay] = field(default_factory=list)
    tracking: list[NormalizedTrackPoint] = field(default_factory=list)

    def record_counts(self) -> dict[str, int]:
        return {
            "games": len(self.games),
            "plays": len(self.plays),
            "players": len(self.players),
            "player_plays": len(self.player_plays),
            "tracking": len(self.tracking),
        }


# Human-readable mapping table, surfaced in the schema report and README so the
# BDB→Football-IQ correspondence is documented, not implicit.
FIELD_MAPPING: list[dict[str, str]] = [
    {
        "football_iq_concept": "Session / game metadata",
        "bdb_source": "games.csv",
        "normalized_table": "games",
        "notes": "season/week/teams; offline analogue of an upload session, NOT Toledo film.",
    },
    {
        "football_iq_concept": "Play",
        "bdb_source": "plays.csv",
        "normalized_table": "plays",
        "notes": "down/distance, possession/defense, offense_formation, LOS. Maps to the play concept.",
    },
    {
        "football_iq_concept": "Player / roster identity",
        "bdb_source": "players.csv",
        "normalized_table": "players",
        "notes": "nfl_id ~ a stable player key; position drives roster priors.",
    },
    {
        "football_iq_concept": "Route / label",
        "bdb_source": "player_play.csv",
        "normalized_table": "player_plays",
        "notes": "route_ran + motion flags. Offline label analogue ONLY — not Toledo labels.",
    },
    {
        "football_iq_concept": "Tracklet frame sample",
        "bdb_source": "tracking_week_*.csv",
        "normalized_table": "tracking",
        "notes": (
            "x/y in BDB field yards + s (speed), a (accel), o (orientation), dir, event. "
            "Analogue of calibrated tracking output but NOT a #127/#128/#129 result."
        ),
    },
]
