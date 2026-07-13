"""Offline tests for the pure helpers in extraction/_persistence.py (no DB).

The DB-bound flow (run_series / process_one_game) is not covered here; these
target the correctness-critical mapping logic it depends on: global draft pick
order, the duration heuristic, blue/red assignment and run aggregation.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from src.common.roles import normalize_team_position
from src.extraction._persistence import (
    FP_PICK_ORDER,
    SMITE_ID,
    SP_PICK_ORDER,
    RunStats,
    SeriesResult,
    _assign_blue_red,
    _extract_duration_s,
    draft_champ_ids,
    draft_missing_reason_for,
    parse_date,
    pick_order_for,
    played_champ_ids,
    resolve_champ,
    smite_suspect_sides,
)


# --------------------------------------------------------------- pick_order_for

# fp team "100" picks champions 1..5; sp team "200" picks 6..10, each in the
# team's chronological order.
_DRAFT = {
    "fp": {"team_id": "100", "picks": [{"id": i} for i in (1, 2, 3, 4, 5)]},
    "sp": {"team_id": "200", "picks": [{"id": i} for i in (6, 7, 8, 9, 10)]},
}
_LOOKUP = {f"C{i}": i for i in range(1, 11)}


def test_pick_order_first_pick_team_maps_to_global_order():
    # FP team's i-th pick maps through FP_PICK_ORDER (1,4,5,8,9).
    expected = [FP_PICK_ORDER[i] for i in range(5)]
    got = [pick_order_for(f"C{i}", _DRAFT, 100, _LOOKUP) for i in (1, 2, 3, 4, 5)]
    assert got == expected == [1, 4, 5, 8, 9]


def test_pick_order_second_pick_team_maps_to_global_order():
    expected = [SP_PICK_ORDER[i] for i in range(5)]
    got = [pick_order_for(f"C{i}", _DRAFT, 200, _LOOKUP) for i in (6, 7, 8, 9, 10)]
    assert got == expected == [2, 3, 6, 7, 10]


def test_pick_order_team_id_compared_as_string():
    # grid_team_id may arrive as int or str; comparison is string-based.
    assert pick_order_for("C1", _DRAFT, "100", _LOOKUP) == 1


def test_pick_order_none_inputs():
    assert pick_order_for(None, _DRAFT, 100, _LOOKUP) is None
    assert pick_order_for("C1", _DRAFT, None, _LOOKUP) is None
    assert pick_order_for("Unknown", _DRAFT, 100, _LOOKUP) is None  # not in lookup


def test_pick_order_champion_not_in_picks():
    # C9 belongs to the SP team; querying it as the FP team finds no match.
    assert pick_order_for("C9", _DRAFT, 100, _LOOKUP) is None


def test_pick_order_unknown_fp_team_returns_none_for_everyone():
    # fp.team_id is None (blind pick / orphaned draft): no participant should
    # be attributed a pick_order, not even the champions listed under "sp"
    # (decision 2026-07-13 — see F15 in full_audit_2026-07-13.md).
    draft = {
        "fp": {"team_id": None, "picks": [{"id": i} for i in (1, 2, 3, 4, 5)]},
        "sp": {"team_id": "200", "picks": [{"id": i} for i in (6, 7, 8, 9, 10)]},
    }
    for i in range(1, 11):
        assert pick_order_for(f"C{i}", draft, 200, _LOOKUP) is None


# --------------------------------------------------------------- resolve_champ

def test_resolve_champ():
    assert resolve_champ("C1", _LOOKUP) == 1
    assert resolve_champ(None, _LOOKUP) is None
    assert resolve_champ("Unknown", _LOOKUP) is None


# ----------------------------------------------------------------- parse_date

def test_parse_date_handles_zulu_and_offset():
    assert parse_date("2026-06-21T10:00:00Z") == date(2026, 6, 21)
    assert parse_date("2026-06-21T23:30:00+02:00") == date(2026, 6, 21)


# ------------------------------------------------------------ _extract_duration_s

class _FakeMidgame:
    """Stand-in for MidGameStatsObserver, exposing only _max_game_time."""
    def __init__(self, max_game_time: int = -1):
        self._max_game_time = max_game_time


def test_duration_prefers_riot_summary_seconds():
    assert _extract_duration_s({"gameDuration": 1800}, None, _FakeMidgame()) == 1800.0


def test_duration_riot_summary_milliseconds_heuristic():
    # > 7200 (impossible in seconds) is treated as milliseconds.
    assert _extract_duration_s({"gameDuration": 1800000}, None, _FakeMidgame()) == 1800.0


def test_duration_falls_back_to_midgame_proxy():
    # No Riot/Tencent: midgame max time (ms) is the last resort.
    assert _extract_duration_s(None, None, _FakeMidgame(1500000)) == 1500.0


def test_duration_none_when_no_source():
    assert _extract_duration_s(None, None, _FakeMidgame()) is None


# --------------------------------------------------------------- _assign_blue_red

def _participant(grid_team_id, side):
    return SimpleNamespace(grid_team_id=grid_team_id, team_side=side)


def test_assign_blue_red():
    parts = [_participant(100, "BLUE"), _participant(200, "RED")]
    mapping = {100: 1, 200: 2}
    assert _assign_blue_red(parts, mapping) == (1, 2)


def test_assign_blue_red_missing_side():
    parts = [_participant(100, "BLUE")]
    assert _assign_blue_red(parts, {100: 1}) == (1, None)


# ------------------------------------------------------- smite_suspect_sides

def _side_participants(side: str):
    """5 participants of one side in riot_id order (BLUE=1..5, RED=6..10)."""
    base = 0 if side == "BLUE" else 5
    return [SimpleNamespace(riot_id=base + i, team_side=side)
            for i in range(1, 6)]


def _spells(spells_by_riot_id: dict[int, list[int]]) -> dict:
    return {rid: {"summoner_spells": sp}
            for rid, sp in spells_by_riot_id.items()}


def test_smite_on_derived_jungler_is_clean():
    parts = _side_participants("BLUE")
    stats = _spells({1: [4, 12], 2: [SMITE_ID, 4], 3: [4, 14], 4: [7, 4], 5: [14, 4]})
    assert smite_suspect_sides(parts, stats) == set()


def test_smite_elsewhere_flags_side():
    # Derived jungler (riot_id 2) has no Smite but the "TOP" does -> shuffled.
    parts = _side_participants("BLUE")
    stats = _spells({1: [SMITE_ID, 4], 2: [4, 12], 3: [4, 14], 4: [7, 4], 5: [14, 4]})
    assert smite_suspect_sides(parts, stats) == {"BLUE"}


def test_no_spell_data_trusts_convention():
    parts = _side_participants("RED")
    assert smite_suspect_sides(parts, {}) == set()


def test_jungler_without_spell_data_is_not_flagged():
    # Only partial data and none for the jungler: no verifiable signal.
    parts = _side_participants("RED")
    stats = _spells({6: [SMITE_ID, 4], 8: [4, 14]})
    assert smite_suspect_sides(parts, stats) == set()


def test_sides_evaluated_independently():
    parts = _side_participants("BLUE") + _side_participants("RED")
    stats = _spells({
        1: [4, 12], 2: [SMITE_ID, 4], 3: [4, 14], 4: [7, 4], 5: [14, 4],   # clean
        6: [SMITE_ID, 4], 7: [4, 12], 8: [4, 14], 9: [7, 4], 10: [14, 4],  # shuffled
    })
    assert smite_suspect_sides(parts, stats) == {"RED"}


# --------------------------------------------------- normalize_team_position

def test_normalize_team_position():
    assert normalize_team_position("TOP") == "TOP"
    assert normalize_team_position("JUNGLE") == "JUNGLE"
    assert normalize_team_position("MIDDLE") == "MID"
    assert normalize_team_position("BOTTOM") == "ADC"
    assert normalize_team_position("UTILITY") == "SUPPORT"
    assert normalize_team_position("") is None
    assert normalize_team_position(None) is None
    assert normalize_team_position("AFK") is None  # tournament-code garbage


# ------------------------------------------------------------------- RunStats

def test_run_stats_aggregates_series_outcomes():
    totals = RunStats()
    totals.add(SeriesResult(skipped=True))
    totals.add(SeriesResult(no_events=True))
    totals.add(SeriesResult(games_new=2, games_skipped=1, errors=1))

    assert totals.series_skipped == 1
    assert totals.series_no_events == 1
    assert totals.series_processed == 1
    assert totals.games_new == 2
    assert totals.games_skipped == 1
    assert totals.errors == 1


# ------------------------------------------------ blind-pick scrims (no draft)

def _played(*champion_names: str | None):
    """Participants with only the champion_name attribute the helpers read."""
    return [SimpleNamespace(champion_name=name) for name in champion_names]


def test_draft_champ_ids_ignores_gaps():
    draft = {"fp": {"picks": [{"id": 1}, None, {"id": 3}]},
             "sp": {"picks": [{"id": 4}]}}
    assert draft_champ_ids(draft) == {1, 3, 4}


def test_draft_champ_ids_empty_draft():
    assert draft_champ_ids({"fp": {}, "sp": {}}) == set()


def test_played_champ_ids_resolves_by_id_and_skips_unknown():
    parts = _played("C1", "C2", "Unknown", None)
    assert played_champ_ids(parts, _LOOKUP) == {1, 2}


def _full_draft(ids: tuple[int, ...]) -> dict:
    picks = [{"id": i} for i in ids]
    return {"fp": {"picks": picks[:5]}, "sp": {"picks": picks[5:10]}}


def test_missing_reason_none_with_fewer_than_ten_known_champions():
    # Only 8 resolved champions: not enough evidence to distrust the draft.
    parts = _played(*[f"C{i}" for i in range(1, 9)])
    reason = draft_missing_reason_for(_full_draft(tuple(range(1, 11))),
                                      parts, _LOOKUP)
    assert reason is None


def test_missing_reason_draft_partial_when_ten_played_but_draft_short():
    parts = _played(*[f"C{i}" for i in range(1, 11)])
    short_draft = {"fp": {"picks": [{"id": i} for i in (1, 2, 3)]}, "sp": {}}
    assert draft_missing_reason_for(short_draft, parts, _LOOKUP) == "draft_partial"


def test_missing_reason_draft_mismatch_when_champions_differ():
    # Played 1..10, but the recorded draft is a different set of 10 champs —
    # a dodged draft left orphaned behind a blind-pick game.
    parts = _played(*[f"C{i}" for i in range(1, 11)])
    other_lookup = {f"D{i}": 100 + i for i in range(1, 11)}
    combined_lookup = {**_LOOKUP, **other_lookup}
    mismatched_draft = _full_draft(tuple(101 + i for i in range(10)))
    reason = draft_missing_reason_for(mismatched_draft, parts, combined_lookup)
    assert reason == "draft_mismatch"


def test_missing_reason_none_when_draft_matches_played():
    parts = _played(*[f"C{i}" for i in range(1, 11)])
    matching_draft = _full_draft(tuple(range(1, 11)))
    assert draft_missing_reason_for(matching_draft, parts, _LOOKUP) is None


def test_missing_reason_mismatch_on_mirror_pick():
    # 10 participants with a known champion, but only 9 unique ids (mirror) —
    # a real 10-pick draft never has duplicates, so it cannot match.
    parts = _played(*(["C1"] * 2 + [f"C{i}" for i in range(2, 10)]))
    drafted = _full_draft(tuple(range(1, 11)))
    assert draft_missing_reason_for(drafted, parts, _LOOKUP) == "draft_mismatch"
