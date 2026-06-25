"""Offline tests for the Riot layer, against the real fixtures in tests/fixtures/.

No network or DB. Expected values are hand-verified against the fixture
KR_8232000299 (melendi#F1RE, Garen TOP, loss 4/10/3).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.extraction.soloq import pick_stats_from_player
from src.riot.extract import (
    build_path,
    extract_match,
    game_duration_s,
    is_remake,
    normalize_version,
    skill_order,
)
from src.riot.routing import platform_to_region, region_from_match_id

FIXTURES = Path(__file__).resolve().parent / "fixtures"

PUUID_MELENDI = ("3bzchn636WhKwvEAlaFgBWlg2fZYGQGGfMuqvIRhqPcT8aCrLq5uwUuGKDYg4"
                 "MQ2HlC5Mjl8pi4GOA")
PUUID_XINZHAO = ("fEUcjCdf9oj8iLec8orgAY59x58OLFNHIP_XjnjKEd67CftJSaORTnHJJuYZ"
                 "_CL0TRhqGrbIRJr8Nw")


@pytest.fixture(scope="module")
def match():
    return json.loads((FIXTURES / "match_KR_8232000299.json").read_text())


@pytest.fixture(scope="module")
def timeline():
    return json.loads((FIXTURES / "match_timeline").read_text())


# ----------------------------------------------------------------- routing

def test_platform_to_region():
    assert platform_to_region("kr") == "asia"
    assert platform_to_region("EUW1") == "europe"
    assert platform_to_region("na1") == "americas"
    assert platform_to_region("oc1") == "sea"
    with pytest.raises(ValueError):
        platform_to_region("xx9")


def test_region_from_match_id():
    assert region_from_match_id("KR_8232000299") == "asia"
    assert region_from_match_id("EUW1_7000000001") == "europe"


# ------------------------------------------------------------ normalizers

def test_normalize_version():
    assert normalize_version("16.10.776.5552") == "16.10"
    assert normalize_version(None) == "Unknown"
    assert normalize_version("16") == "Unknown"


def test_game_duration_modern_vs_legacy():
    assert game_duration_s({"gameDuration": 1680, "gameEndTimestamp": 1}) == 1680
    # Old matches without gameEndTimestamp: gameDuration in ms.
    assert game_duration_s({"gameDuration": 1680000}) == 1680
    assert game_duration_s({}) is None


# ----------------------------------------------------------- extract_match

def test_extract_match_general(match, timeline):
    r = extract_match(match, timeline, {PUUID_MELENDI})
    assert r["match_id"] == "KR_8232000299"
    assert r["platform"] == "KR"
    assert r["queue_id"] == 420
    assert r["game_version"] == "16.10"
    assert r["game_duration_s"] == 1680
    assert r["winner"] == "RED"
    assert len(r["players"]) == 1


def test_extract_match_player(match, timeline):
    p = extract_match(match, timeline, {PUUID_MELENDI})["players"][0]
    assert p["riot_id"] == "melendi#F1RE"
    assert p["champion_id"] == 86 and p["champion_name"] == "Garen"
    assert p["team_side"] == "BLUE" and p["team_position"] == "TOP"
    assert p["win"] is False
    assert (p["kills"], p["deaths"], p["assists"]) == (4, 10, 3)
    assert p["cs"] == 193  # 189 minions + 4 neutrals
    assert p["gold"] == 10111
    assert p["champ_level"] == 15
    assert p["vision_score"] == 29
    assert p["summoner_spells"] == [14, 4]
    assert p["final_items"] == [1018, 6631, 3142, 3006, 1042, 3123, 3340]
    assert p["runes"] == {
        "primary_style": 8000,
        "primary": [8010, 9111, 9105, 8299],
        "sub_style": 8200,
        "sub": [8224, 8234],
        "stat_perks": [5008, 5008, 5011],
    }


def test_extract_match_multi_player(match, timeline):
    r = extract_match(match, timeline, {PUUID_MELENDI, PUUID_XINZHAO})
    assert len(r["players"]) == 2
    champs = {p["champion_name"] for p in r["players"]}
    assert champs == {"Garen", "XinZhao"}


def test_extract_match_no_tracked(match, timeline):
    assert extract_match(match, timeline, {"foreign-puuid"}) is None


def test_extract_match_without_timeline(match):
    p = extract_match(match, None, {PUUID_MELENDI})["players"][0]
    assert p["build_path"] is None
    assert p["skill_order"] is None


# --------------------------------------------- composition, bans and remakes

def test_extract_match_bans(match, timeline):
    r = extract_match(match, timeline, {PUUID_MELENDI})
    assert r["bans"] == {
        "blue": [238, 64, 901, 89, 17],
        "red": [64, 950, 117, 43, 67],
    }


def test_bans_skipped_normalized_to_none():
    from src.riot.extract import _bans
    info = {"teams": [
        {"teamId": 100, "bans": [
            {"championId": 246, "pickTurn": 1},
            {"championId": -1, "pickTurn": 2},   # turn with no ban
            {"championId": 51, "pickTurn": 3},
        ]},
        {"teamId": 200, "bans": [
            {"championId": -1, "pickTurn": 4},   # turn with no ban
            {"championId": 64, "pickTurn": 5},
        ]},
    ]}
    assert _bans(info) == {"blue": [246, None, 51], "red": [None, 64]}


def test_final_items_filters_empty_slots():
    # item5 empty (0) is filtered; the rest is kept in order.
    participant = {
        "puuid": "x", "championId": 1, "teamId": 100,
        **{f"item{i}": v for i, v in
           enumerate([1056, 3040, 6657, 3170, 1011, 0, 3363])},
    }
    out = extract_match(
        {"info": {"participants": [participant], "teams": []}}, None, {"x"}
    )["players"][0]
    assert out["final_items"] == [1056, 3040, 6657, 3170, 1011, 3363]


def test_extract_match_composition(match, timeline):
    parts = extract_match(match, timeline, {PUUID_MELENDI})["participants"]
    # The fixture carries 2 of the 10 participants (truncation note in the JSON).
    assert [p["puuid"] for p in parts] == [PUUID_MELENDI, PUUID_XINZHAO]
    assert parts[0] == {
        "puuid": PUUID_MELENDI,
        "champion_id": 86,
        "team_side": "BLUE",
        "team_position": "TOP",
    }
    for p in parts:
        assert set(p) == {"puuid", "champion_id", "team_side", "team_position"}


def test_is_remake(match):
    assert is_remake(match) is False
    early = {"info": {"participants": [{"gameEndedInEarlySurrender": True}],
                      "gameDuration": 1500, "gameEndTimestamp": 1}}
    assert is_remake(early) is True
    short = {"info": {"participants": [], "gameDuration": 240,
                      "gameEndTimestamp": 1}}
    assert is_remake(short) is True


def test_pick_stats_contract(match, timeline):
    player = extract_match(match, timeline, {PUUID_MELENDI})["players"][0]
    stats = pick_stats_from_player(player)
    assert set(stats) == {
        "kills", "deaths", "assists", "gold", "cs",
        "champ_level", "vision_score", "team_position",
        "summoner_spells", "final_items", "runes",
        "build_path", "skill_order",
    }
    # Identities excluded: neither riot_id nor puuid go inside picks.stats.
    assert "riot_id" not in stats and "puuid" not in stats
    assert stats["kills"] == 4 and stats["skill_order"] == "QEWEEREQEQRQQWW"


# ------------------------------------------------------------- build path

def test_build_path_fixture(match, timeline):
    p = extract_match(match, timeline, {PUUID_MELENDI})["players"][0]
    path = p["build_path"]
    # 21 buys - 1 buy undo = 20 BUY; 3 sells - 2 sell undos = 1 SELL.
    assert sum(1 for e in path if e["action"] == "BUY") == 20
    assert sum(1 for e in path if e["action"] == "SELL") == 1
    assert path[0] == {"ts_s": 2, "action": "BUY", "item_id": 1054}
    assert {"ts_s": 1547, "action": "SELL", "item_id": 1054} in path
    # Chronological order.
    assert [e["ts_s"] for e in path] == sorted(e["ts_s"] for e in path)
    # The Phage (3044) bought at 233s was undone; only the later rebuy at 817s
    # remains.
    assert [e["ts_s"] for e in path if e["item_id"] == 3044] == [817]


def test_build_path_undo_of_sell_synthetic():
    timeline = {"info": {"frames": [{"events": [
        {"type": "ITEM_PURCHASED", "timestamp": 1000, "participantId": 1, "itemId": 1054},
        {"type": "ITEM_SOLD", "timestamp": 2000, "participantId": 1, "itemId": 1054},
        {"type": "ITEM_UNDO", "timestamp": 3000, "participantId": 1,
         "beforeId": 0, "afterId": 1054},
        {"type": "ITEM_PURCHASED", "timestamp": 4000, "participantId": 2, "itemId": 9999},
    ]}]}}
    # The undo cancels the sale; another participant's purchase does not leak in.
    assert build_path(timeline, 1) == [
        {"ts_s": 1, "action": "BUY", "item_id": 1054},
    ]


# ------------------------------------------------------------ skill order

def test_skill_order_fixture(match, timeline):
    p = extract_match(match, timeline, {PUUID_MELENDI})["players"][0]
    assert p["skill_order"] == "QEWEEREQEQRQQWW"
    assert len(p["skill_order"]) == 15  # == champ_level
    assert set(p["skill_order"]) <= set("QWER")


def test_skill_order_excludes_evolve():
    timeline = {"info": {"frames": [{"events": [
        {"type": "SKILL_LEVEL_UP", "timestamp": 1, "participantId": 1,
         "skillSlot": 1, "levelUpType": "NORMAL"},
        {"type": "SKILL_LEVEL_UP", "timestamp": 2, "participantId": 1,
         "skillSlot": 2, "levelUpType": "EVOLVE"},
        {"type": "SKILL_LEVEL_UP", "timestamp": 3, "participantId": 1,
         "skillSlot": 4, "levelUpType": "NORMAL"},
    ]}]}}
    assert skill_order(timeline, 1) == "QR"
