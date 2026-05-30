"""Offline NFL Big Data Bowl → Football-IQ normalizer (Issue #164).

Reads raw BDB Kaggle CSVs (already downloaded locally — this module never calls
Kaggle and never downloads anything) and emits the stable normalized schema from
``schema.py`` plus a provenance manifest. Pure stdlib (``csv``/``json``) so it
runs in CI without pandas/torch and without GPU.

Scope guardrails (Issue #164 / Epic #160):
  * Offline pretraining / evaluation only — no production runtime, no router.
  * Never downloads or commits Kaggle data; callers point ``--input-dir`` at a
    local copy and ``--output-dir`` at a gitignored cache/artifact path.
  * Records provenance + an explicit ``offline-pretraining-evaluation-only``
    usage marker so artifacts can never be mistaken for Toledo film.
"""

from __future__ import annotations

import csv
import glob
import os
from collections.abc import Iterable, Iterator, Mapping

from datasets.bdb.schema import (
    _GAME_ALIASES,
    _PLAY_ALIASES,
    _PLAYER_ALIASES,
    _PLAYER_PLAY_ALIASES,
    _TRACK_ALIASES,
    NormalizedDataset,
    NormalizedGame,
    NormalizedPlay,
    NormalizedPlayer,
    NormalizedPlayerPlay,
    NormalizedTrackPoint,
)

# BDB encodes missing values as empty string or the literal "NA"/"nan".
_NULLISH = {"", "na", "n/a", "nan", "null", "none"}
# BDB boolean-ish columns arrive as "true"/"false"/"1"/"0"/"yes"/"no".
_TRUTHY = {"true", "t", "1", "yes", "y"}
_FALSY = {"false", "f", "0", "no", "n"}


# ── value coercion ───────────────────────────────────────────────────────────


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped.lower() in _NULLISH:
        return None
    return stripped


def _to_int(value: str | None) -> int | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    try:
        # tolerate "12.0" style ints in float-typed exports
        return int(float(cleaned))
    except ValueError:
        return None


def _to_float(value: str | None) -> float | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _to_bool(value: str | None) -> bool | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    low = cleaned.lower()
    if low in _TRUTHY:
        return True
    if low in _FALSY:
        return False
    return None


def _to_str(value: str | None) -> str | None:
    return _clean(value)


# ── header aliasing ──────────────────────────────────────────────────────────


def _build_resolver(
    fieldnames: Iterable[str], aliases: Mapping[str, set[str]]
) -> dict[str, str]:
    """Map each canonical field to the actual header present in this file.

    Returns ``{canonical: actual_header}`` for the canonical fields that exist.
    Lookups are case-insensitive and whitespace-tolerant so 2025 (camelCase) and
    2026 (snake_case) headers resolve through one path.
    """
    lowered = {name.strip().lower(): name for name in fieldnames if name is not None}
    resolver: dict[str, str] = {}
    for canonical, accepted in aliases.items():
        for spelling in accepted:
            if spelling in lowered:
                resolver[canonical] = lowered[spelling]
                break
    return resolver


def _get(row: Mapping[str, str], resolver: Mapping[str, str], canonical: str) -> str | None:
    header = resolver.get(canonical)
    if header is None:
        return None
    return row.get(header)


def _iter_rows(path: str) -> Iterator[tuple[list[str], dict[str, str]]]:
    """Yield (fieldnames, row) for each data row in a CSV. Empty file → nothing."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        for row in reader:
            yield fieldnames, row


# ── per-table normalizers ────────────────────────────────────────────────────


def normalize_games(path: str) -> list[NormalizedGame]:
    out: list[NormalizedGame] = []
    resolver: dict[str, str] = {}
    for fieldnames, row in _iter_rows(path):
        if not resolver:
            resolver = _build_resolver(fieldnames, _GAME_ALIASES)
        game_id = _to_str(_get(row, resolver, "game_id"))
        if game_id is None:
            continue
        out.append(
            NormalizedGame(
                game_id=game_id,
                season=_to_int(_get(row, resolver, "season")),
                week=_to_int(_get(row, resolver, "week")),
                game_date=_to_str(_get(row, resolver, "game_date")),
                home_team=_to_str(_get(row, resolver, "home_team")),
                away_team=_to_str(_get(row, resolver, "away_team")),
            )
        )
    return out


def normalize_plays(path: str) -> list[NormalizedPlay]:
    out: list[NormalizedPlay] = []
    resolver: dict[str, str] = {}
    for fieldnames, row in _iter_rows(path):
        if not resolver:
            resolver = _build_resolver(fieldnames, _PLAY_ALIASES)
        game_id = _to_str(_get(row, resolver, "game_id"))
        play_id = _to_str(_get(row, resolver, "play_id"))
        if game_id is None or play_id is None:
            continue
        out.append(
            NormalizedPlay(
                game_id=game_id,
                play_id=play_id,
                quarter=_to_int(_get(row, resolver, "quarter")),
                down=_to_int(_get(row, resolver, "down")),
                yards_to_go=_to_int(_get(row, resolver, "yards_to_go")),
                possession_team=_to_str(_get(row, resolver, "possession_team")),
                defensive_team=_to_str(_get(row, resolver, "defensive_team")),
                offense_formation=_to_str(_get(row, resolver, "offense_formation")),
                receiver_alignment=_to_str(_get(row, resolver, "receiver_alignment")),
                yardline_side=_to_str(_get(row, resolver, "yardline_side")),
                yardline_number=_to_int(_get(row, resolver, "yardline_number")),
                los_absolute_yard=_to_float(_get(row, resolver, "los_absolute_yard")),
                pass_result=_to_str(_get(row, resolver, "pass_result")),
                play_direction=_to_str(_get(row, resolver, "play_direction")),
            )
        )
    return out


def normalize_players(path: str) -> list[NormalizedPlayer]:
    out: list[NormalizedPlayer] = []
    resolver: dict[str, str] = {}
    for fieldnames, row in _iter_rows(path):
        if not resolver:
            resolver = _build_resolver(fieldnames, _PLAYER_ALIASES)
        nfl_id = _to_str(_get(row, resolver, "nfl_id"))
        if nfl_id is None:
            continue
        out.append(
            NormalizedPlayer(
                nfl_id=nfl_id,
                display_name=_to_str(_get(row, resolver, "display_name")),
                position=_to_str(_get(row, resolver, "position")),
                height=_to_str(_get(row, resolver, "height")),
                weight=_to_int(_get(row, resolver, "weight")),
                college=_to_str(_get(row, resolver, "college")),
            )
        )
    return out


def normalize_player_plays(path: str) -> list[NormalizedPlayerPlay]:
    out: list[NormalizedPlayerPlay] = []
    resolver: dict[str, str] = {}
    for fieldnames, row in _iter_rows(path):
        if not resolver:
            resolver = _build_resolver(fieldnames, _PLAYER_PLAY_ALIASES)
        game_id = _to_str(_get(row, resolver, "game_id"))
        play_id = _to_str(_get(row, resolver, "play_id"))
        nfl_id = _to_str(_get(row, resolver, "nfl_id"))
        if game_id is None or play_id is None or nfl_id is None:
            continue
        out.append(
            NormalizedPlayerPlay(
                game_id=game_id,
                play_id=play_id,
                nfl_id=nfl_id,
                team=_to_str(_get(row, resolver, "team")),
                route_ran=_to_str(_get(row, resolver, "route_ran")),
                was_running_route=_to_bool(_get(row, resolver, "was_running_route")),
                motion_since_lineset=_to_bool(_get(row, resolver, "motion_since_lineset")),
                in_motion_at_snap=_to_bool(_get(row, resolver, "in_motion_at_snap")),
            )
        )
    return out


def normalize_tracking(path: str) -> list[NormalizedTrackPoint]:
    out: list[NormalizedTrackPoint] = []
    resolver: dict[str, str] = {}
    for fieldnames, row in _iter_rows(path):
        if not resolver:
            resolver = _build_resolver(fieldnames, _TRACK_ALIASES)
        game_id = _to_str(_get(row, resolver, "game_id"))
        play_id = _to_str(_get(row, resolver, "play_id"))
        if game_id is None or play_id is None:
            continue
        out.append(
            NormalizedTrackPoint(
                game_id=game_id,
                play_id=play_id,
                nfl_id=_to_str(_get(row, resolver, "nfl_id")),
                frame_id=_to_int(_get(row, resolver, "frame_id")),
                time=_to_str(_get(row, resolver, "time")),
                jersey_number=_to_int(_get(row, resolver, "jersey_number")),
                club=_to_str(_get(row, resolver, "club")),
                side=None,  # filled by assign_sides() once plays are known
                play_direction=_to_str(_get(row, resolver, "play_direction")),
                x=_to_float(_get(row, resolver, "x")),
                y=_to_float(_get(row, resolver, "y")),
                s=_to_float(_get(row, resolver, "s")),
                a=_to_float(_get(row, resolver, "a")),
                dis=_to_float(_get(row, resolver, "dis")),
                o=_to_float(_get(row, resolver, "o")),
                dir=_to_float(_get(row, resolver, "dir")),
                event=_to_str(_get(row, resolver, "event")),
            )
        )
    return out


# ── side assignment (offense / defense / ball) ───────────────────────────────


def assign_sides(
    tracking: list[NormalizedTrackPoint], plays: list[NormalizedPlay]
) -> list[NormalizedTrackPoint]:
    """Fill ``side`` per track point using each play's possession team.

    ``club == "football"`` → ``"ball"``. Otherwise the row is ``offense`` when
    its club matches the play's possession team, ``defense`` when it matches the
    defensive team, else ``None`` (e.g. clubs that pre-date the join).
    """
    poss = {(p.game_id, p.play_id): p.possession_team for p in plays}
    deff = {(p.game_id, p.play_id): p.defensive_team for p in plays}
    out: list[NormalizedTrackPoint] = []
    for pt in tracking:
        if pt.is_ball:
            side: str | None = "ball"
        else:
            key = (pt.game_id, pt.play_id)
            if pt.club is not None and pt.club == poss.get(key):
                side = "offense"
            elif pt.club is not None and pt.club == deff.get(key):
                side = "defense"
            else:
                side = None
        out.append(
            NormalizedTrackPoint(
                game_id=pt.game_id,
                play_id=pt.play_id,
                nfl_id=pt.nfl_id,
                frame_id=pt.frame_id,
                time=pt.time,
                jersey_number=pt.jersey_number,
                club=pt.club,
                side=side,
                play_direction=pt.play_direction,
                x=pt.x,
                y=pt.y,
                s=pt.s,
                a=pt.a,
                dis=pt.dis,
                o=pt.o,
                dir=pt.dir,
                event=pt.event,
            )
        )
    return out


# ── directory-level normalization ────────────────────────────────────────────

# Canonical file names BDB ships. Matching is case-insensitive and tolerant of a
# directory prefix; tracking files are globbed (one per week).
_GAMES_NAMES = ("games.csv",)
_PLAYS_NAMES = ("plays.csv",)
_PLAYERS_NAMES = ("players.csv",)
_PLAYER_PLAY_NAMES = ("player_play.csv", "player_plays.csv")
_TRACKING_GLOB = "tracking_week_*.csv"


def _first_existing(input_dir: str, names: tuple[str, ...]) -> str | None:
    existing = {name.lower(): name for name in os.listdir(input_dir)}
    for candidate in names:
        actual = existing.get(candidate.lower())
        if actual is not None:
            return os.path.join(input_dir, actual)
    return None


def normalize_directory(input_dir: str, *, tracking_glob: str = _TRACKING_GLOB) -> NormalizedDataset:
    """Normalize every BDB table present in ``input_dir`` into one dataset.

    Missing tables are skipped (BDB competitions ship different file sets across
    years), so the adapter degrades gracefully rather than crashing on a partial
    download. Tracking files are read in sorted order for determinism.
    """
    if not os.path.isdir(input_dir):
        raise NotADirectoryError(f"BDB input dir not found: {input_dir}")

    dataset = NormalizedDataset()

    games_path = _first_existing(input_dir, _GAMES_NAMES)
    if games_path:
        dataset.games = normalize_games(games_path)

    plays_path = _first_existing(input_dir, _PLAYS_NAMES)
    if plays_path:
        dataset.plays = normalize_plays(plays_path)

    players_path = _first_existing(input_dir, _PLAYERS_NAMES)
    if players_path:
        dataset.players = normalize_players(players_path)

    pp_path = _first_existing(input_dir, _PLAYER_PLAY_NAMES)
    if pp_path:
        dataset.player_plays = normalize_player_plays(pp_path)

    tracking: list[NormalizedTrackPoint] = []
    for track_path in sorted(glob.glob(os.path.join(input_dir, tracking_glob))):
        tracking.extend(normalize_tracking(track_path))
    if tracking and dataset.plays:
        tracking = assign_sides(tracking, dataset.plays)
    dataset.tracking = tracking

    return dataset
