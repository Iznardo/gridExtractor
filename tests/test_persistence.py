"""Offline tests for the pure helpers in extraction/_persistence.py (no DB).

The DB-bound flow (run_series / process_one_game) is not covered here; these
target the correctness-critical mapping logic it depends on: global draft pick
order, the duration heuristic, blue/red assignment and run aggregation.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from src.extraction._persistence import (
    FP_PICK_ORDER,
    SP_PICK_ORDER,
    RunStats,
    SeriesResult,
    _assign_blue_red,
    _extract_duration_s,
    parse_date,
    pick_order_for,
    resolve_champ,
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
