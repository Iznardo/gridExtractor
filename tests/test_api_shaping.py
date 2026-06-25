"""Tests for the API's pure shaping functions (no DB or network).

Cover the transformation logic that does not depend on Postgres: parameter
parsing, pick-relation derivation and composition from soloq stats.
"""

from __future__ import annotations

from src.api.routers.draft_stats import _parse_game_types
from src.api.routers.games import _comp_from_stats, _team_obj
from src.api.routers.matchups import _pick_relation


def test_parse_game_types_csv():
    assert _parse_game_types("OFFICIAL,SCRIM") == ["OFFICIAL", "SCRIM"]


def test_parse_game_types_trims_and_drops_empty():
    assert _parse_game_types(" OFFICIAL , , SCRIM ") == ["OFFICIAL", "SCRIM"]


def test_parse_game_types_none_and_empty():
    assert _parse_game_types(None) is None
    assert _parse_game_types("") is None
    assert _parse_game_types("  ,  ") is None


def test_pick_relation_blind_counter_and_unknown():
    assert _pick_relation(1, 4) == "blind"      # picks earlier -> blind
    assert _pick_relation(4, 1) == "counter"    # picks later -> counter
    assert _pick_relation(None, 4) is None
    assert _pick_relation(4, None) is None


def test_team_obj_none():
    assert _team_obj(None, "x", "y") is None
    assert _team_obj(1, "Team", "TG") == {"id": 1, "name": "Team", "tag": "TG"}


def test_comp_from_stats_soloq_participants():
    stats = {
        "participants": [
            {"team_side": "BLUE", "champion_id": 1},
            {"team_side": "RED", "champion_id": 2},
            {"team_side": "BLUE", "champion_id": 3},
            {"team_side": "RED", "champion_id": None},   # ignored
            {"team_side": "PURPLE", "champion_id": 9},    # invalid side ignored
        ]
    }
    comp = _comp_from_stats(stats)
    assert comp == {"BLUE": [1, 3], "RED": [2]}


def test_comp_from_stats_no_participants():
    assert _comp_from_stats({}) is None
    assert _comp_from_stats(None) is None
    assert _comp_from_stats({"participants": []}) is None
