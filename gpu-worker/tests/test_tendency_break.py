"""Unit tests for the tendency-break engine + stage wiring (Issue #137).

All tests run without GPU hardware, real footage, or a running backend.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline import stage_self_scout
from pipeline.play_prediction import tendency_break_engine as tbe


def _clip(clip_id, *, formation="Trips", personnel="11", field_zone="red_zone", down=3, distance=8.0):
    return {
        "id": clip_id,
        "personnel_grouping": personnel,
        "field_zone": field_zone,
        "down": down,
        "distance": distance,
        "_formation": formation,
    }


def _labels_for(clips, play_types):
    out = {}
    for clip, pt in zip(clips, play_types):
        concept = "inside zone" if pt == "run" else "quick pass"
        out[clip["id"]] = [
            {"label_type": "offensive_formation", "label_value": {"formation": clip["_formation"]}},
            {"label_type": "play_concept", "label_value": {"concept": concept}},
        ]
    return out


# ── build_plays ──────────────────────────────────────────────────────────────


def test_build_plays_reduces_dimensions():
    clips = [_clip("c0")]
    plays = tbe.build_plays(clips, _labels_for(clips, ["pass"]))
    assert len(plays) == 1
    assert plays[0].bucket_key() == ("Trips", "11", "red_zone", "3-long")
    assert plays[0].play_type == "pass"


def test_build_plays_skips_unlabeled():
    clips = [_clip("c0")]
    labels = {"c0": [{"label_type": "offensive_formation", "label_value": {"formation": "I"}}]}
    assert tbe.build_plays(clips, labels) == []


# ── season tendencies ──────────────────────────────────────────────────────────


def test_season_tendency_alert_fires():
    clips = [_clip(f"c{i}") for i in range(10)]
    plays = tbe.build_plays(clips, _labels_for(clips, ["pass"] * 9 + ["run"]))
    alerts = tbe.season_tendency_alerts(plays)
    assert len(alerts) == 1
    a = alerts[0]
    assert a.tendency_kind == "season_tendency"
    assert a.lean == "pass"
    assert a.pass_rate == 0.9
    assert a.severity == "high"
    assert len(a.evidence_clip_ids) == 3


def test_season_tendency_respects_sample_floor():
    clips = [_clip(f"c{i}") for i in range(8)]  # exactly 8, not > 8
    plays = tbe.build_plays(clips, _labels_for(clips, ["pass"] * 8))
    assert tbe.season_tendency_alerts(plays) == []


def test_season_tendency_ignores_balanced():
    clips = [_clip(f"c{i}") for i in range(10)]
    plays = tbe.build_plays(clips, _labels_for(clips, ["pass"] * 5 + ["run"] * 5))
    assert tbe.season_tendency_alerts(plays) == []


# ── pattern breaks ───────────────────────────────────────────────────────────────


def test_pattern_break_fires():
    bucket = ("Trips", "11", "red_zone", "3-long")
    clips = [_clip(f"g{i}") for i in range(6)]
    plays = tbe.build_plays(clips, _labels_for(clips, ["pass"] * 6))
    alerts = tbe.pattern_break_alerts(plays, {bucket: 0.5})
    assert len(alerts) == 1
    assert alerts[0].tendency_kind == "pattern_break"
    assert alerts[0].divergence_pp == 0.5


def test_pattern_break_needs_min_plays():
    bucket = ("Trips", "11", "red_zone", "3-long")
    clips = [_clip(f"g{i}") for i in range(4)]
    plays = tbe.build_plays(clips, _labels_for(clips, ["pass"] * 4))
    assert tbe.pattern_break_alerts(plays, {bucket: 0.5}) == []


# ── payload shaping ──────────────────────────────────────────────────────────────


def test_to_alert_payload_shape():
    clips = [_clip(f"c{i}") for i in range(10)]
    plays = tbe.build_plays(clips, _labels_for(clips, ["pass"] * 9 + ["run"]))
    alert = tbe.season_tendency_alerts(plays)[0]
    payload = tbe.to_alert_payload(alert, session_id="season")
    assert payload["alert_type"] == "formation_tendency"
    assert payload["position_group"] == "OFFENSE"
    assert payload["severity"] == "high"
    assert 0.0 <= payload["confidence"] <= 1.0
    assert payload["metric_value"]["tendency_kind"] == "season_tendency"
    assert payload["session_id"] == "season"
    assert payload["clip_id"] in {f"c{i}" for i in range(10)}


def test_generate_alert_payloads_season_and_pattern_break():
    # Bucket A ("Trips"): 10 plays, 90% pass → a season_tendency alert.
    trips = [_clip(f"t{i}", formation="Trips") for i in range(10)]
    trips_types = ["pass"] * 9 + ["run"]
    # Bucket B ("I"): 12 plays, balanced 50% pass (baseline 0.5). The 6 pass
    # clips are this game → game pass-rate 1.0, diverging +0.5 → pattern_break.
    iform = [_clip(f"i{j}", formation="I") for j in range(12)]
    iform_types = ["pass"] * 6 + ["run"] * 6

    clips = trips + iform
    labels = {**_labels_for(trips, trips_types), **_labels_for(iform, iform_types)}
    game_ids = {f"i{j}" for j in range(6)}  # the 6 balanced-bucket pass clips

    payloads = tbe.generate_alert_payloads(
        clips, labels, game_clip_ids=game_ids, game_session_id="game-1"
    )
    kinds = {p["metric_value"]["tendency_kind"] for p in payloads}
    assert "season_tendency" in kinds
    assert "pattern_break" in kinds


# ── stage wiring ────────────────────────────────────────────────────────────────


def test_run_includes_tendency_break_alerts():
    clips = [_clip(f"c{i}") for i in range(10)]
    labels = _labels_for(clips, ["pass"] * 9 + ["run"])
    result = stage_self_scout.run(clips, labels, {})
    assert "tendency_break_alerts" in result
    assert len(result["tendency_break_alerts"]) == 1
    assert result["tendency_break_alerts"][0]["alert_type"] == "formation_tendency"


def test_persist_tendency_break_alerts_posts(monkeypatch):
    posted = []

    def _fake_create_alert(payload):
        posted.append(payload)
        return {"id": "abc"}

    monkeypatch.setattr(stage_self_scout.backend, "create_alert", _fake_create_alert)
    payloads = [{"alert_type": "formation_tendency", "metric_name": "x"}]
    count = stage_self_scout.persist_tendency_break_alerts(payloads)
    assert count == 1
    assert posted == payloads


def test_persist_tendency_break_alerts_noop_when_empty(monkeypatch):
    monkeypatch.setattr(
        stage_self_scout.backend, "create_alert", lambda p: (_ for _ in ()).throw(AssertionError)
    )
    assert stage_self_scout.persist_tendency_break_alerts([]) == 0
