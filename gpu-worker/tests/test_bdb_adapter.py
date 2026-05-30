"""Tests for the offline NFL Big Data Bowl adapter (Issue #164).

Covers: camelCase (2025) + snake_case (2026) header aliasing, value coercion,
side assignment, provenance/usage marking, artifact round-trip, and the offline
benchmark features. All run against the bundled SYNTHETIC sample — no Kaggle
data, no network, no GPU.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datasets.bdb import (
    SCHEMA_VERSION,
    USAGE_MARKER,
    build_provenance,
    build_report,
    normalize_directory,
    render_markdown,
    write_artifacts,
)
from datasets.bdb.adapter import (
    _to_bool,
    _to_float,
    _to_int,
    assign_sides,
    normalize_tracking,
)
from datasets.bdb.features import coverage_separation, formation_distribution, spacing_features
from datasets.bdb.schema import NormalizedPlay

_SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "datasets", "bdb", "sample")


# ── coercion helpers ─────────────────────────────────────────────────────────


def test_value_coercion_handles_nullish_and_floats():
    assert _to_int("12.0") == 12
    assert _to_int("NA") is None
    assert _to_int("") is None
    assert _to_float("3.14") == 3.14
    assert _to_float("nan") is None
    assert _to_bool("true") is True
    assert _to_bool("0") is False
    assert _to_bool("maybe") is None


# ── directory normalization on the synthetic sample ──────────────────────────


def test_normalize_sample_directory_counts():
    ds = normalize_directory(_SAMPLE_DIR)
    counts = ds.record_counts()
    assert counts == {
        "games": 1,
        "plays": 2,
        "players": 9,
        "player_plays": 8,
        "tracking": 40,
    }


def test_sides_assigned_from_possession_team():
    ds = normalize_directory(_SAMPLE_DIR)
    sides = {pt.side for pt in ds.tracking}
    assert sides == {"offense", "defense", "ball"}
    # The football row must be flagged as the ball, never a player.
    ball_rows = [pt for pt in ds.tracking if pt.is_ball]
    assert ball_rows and all(pt.side == "ball" for pt in ball_rows)


# ── header aliasing: 2026 snake_case must normalize identically ──────────────


def test_snake_case_tracking_headers_alias(tmp_path):
    csv_text = (
        "game_id,play_id,nfl_id,frame_id,club,x,y,speed,acceleration,orientation,direction,event\n"
        "5,9,77,3,ZZZ,10.5,20.0,4.1,1.2,180.0,90.0,ball_snap\n"
    )
    path = tmp_path / "tracking_week_1.csv"
    path.write_text(csv_text, encoding="utf-8")
    pts = normalize_tracking(str(path))
    assert len(pts) == 1
    pt = pts[0]
    assert pt.game_id == "5" and pt.play_id == "9" and pt.nfl_id == "77"
    assert pt.frame_id == 3
    assert pt.s == 4.1 and pt.a == 1.2 and pt.o == 180.0 and pt.dir == 90.0
    assert pt.event == "ball_snap"


def test_assign_sides_marks_unknown_club_none():
    pts = normalize_tracking(os.path.join(_SAMPLE_DIR, "tracking_week_1.csv"))
    plays = [
        NormalizedPlay(
            game_id="9000001",
            play_id="101",
            quarter=None,
            down=None,
            yards_to_go=None,
            possession_team="AAA",
            defensive_team="BBB",
            offense_formation=None,
            receiver_alignment=None,
            yardline_side=None,
            yardline_number=None,
            los_absolute_yard=None,
            pass_result=None,
            play_direction=None,
        )
    ]
    assigned = assign_sides(pts, plays)
    # play 102 has no matching play row → its non-ball clubs resolve to None.
    p102 = [pt for pt in assigned if pt.play_id == "102" and not pt.is_ball]
    assert p102 and all(pt.side is None for pt in p102)


# ── provenance + artifact round-trip ─────────────────────────────────────────


def test_provenance_marks_offline_and_records_sources():
    ds = normalize_directory(_SAMPLE_DIR)
    prov = build_provenance(
        competition="synthetic-bdb-sample",
        season=2025,
        input_dir=_SAMPLE_DIR,
        dataset=ds,
    )
    d = prov.to_dict()
    assert d["usage"] == USAGE_MARKER == "offline-pretraining-evaluation-only"
    assert d["schema_version"] == SCHEMA_VERSION
    assert d["coordinate_frame"] == "bdb_field_yards"
    # Provenance must caveat Toledo + calibration, and checksum the sources.
    assert "Toledo" in d["label_note"]
    assert "#127/#128/#129" in d["coordinate_note"]
    names = {sf["name"] for sf in d["source_files"]}
    assert "tracking_week_1.csv" in names
    assert all(len(sf["sha256"]) == 64 for sf in d["source_files"])


def test_artifact_roundtrip_writes_jsonl_and_manifest(tmp_path):
    ds = normalize_directory(_SAMPLE_DIR)
    prov = build_provenance(
        competition="synthetic-bdb-sample", season=2025, input_dir=_SAMPLE_DIR, dataset=ds
    )
    written = write_artifacts(ds, prov, str(tmp_path))
    for name in ("games", "plays", "players", "player_plays", "tracking", "manifest"):
        assert os.path.isfile(written[name])
    with open(written["manifest"], encoding="utf-8") as handle:
        manifest = json.load(handle)
    assert manifest["record_counts"]["tracking"] == 40
    # tracking.jsonl is newline-delimited JSON, one record per line.
    with open(written["tracking"], encoding="utf-8") as handle:
        lines = [line for line in handle if line.strip()]
    assert len(lines) == 40
    json.loads(lines[0])  # parses


# ── offline benchmark features ───────────────────────────────────────────────


def test_formation_distribution():
    ds = normalize_directory(_SAMPLE_DIR)
    fd = formation_distribution(ds)
    assert fd == {"SHOTGUN": 1, "SINGLEBACK": 1}


def test_spacing_features_reasonable():
    ds = normalize_directory(_SAMPLE_DIR)
    sp = spacing_features(ds)
    assert sp["plays_measured"] == 2
    # 5 offensive players span the field laterally; 3 sit on the LOS.
    assert sp["mean_width_yards"] > 30.0
    assert sp["mean_offensive_players_on_los"] == 3.0


def test_coverage_separation_positive():
    ds = normalize_directory(_SAMPLE_DIR)
    cov = coverage_separation(ds)
    assert cov["matchups_measured"] == 10  # 5 offense x 2 plays
    assert cov["min_nearest_defender_yards"] > 0.0
    assert cov["mean_nearest_defender_yards"] >= cov["min_nearest_defender_yards"]


def test_report_render_marks_offline():
    ds = normalize_directory(_SAMPLE_DIR)
    prov = build_provenance(
        competition="synthetic-bdb-sample", season=2025, input_dir=_SAMPLE_DIR, dataset=ds
    )
    report = build_report(ds, prov.to_dict())
    assert report["usage"] == USAGE_MARKER
    md = render_markdown(report)
    assert "NOT production, NOT Toledo film" in md
    assert "Offense formation distribution" in md
