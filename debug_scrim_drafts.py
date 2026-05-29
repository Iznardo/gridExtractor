"""Script de diagnostico para scrims con draft_found=False.

Para cada series_id pasado por CLI, descarga eventos y reporta:
- Conteo de eventos crudos relacionados con draft e invalidacion.
- Estado del DraftObserver: draft_found, is_complete, picks/bans actuales.
- Contenido de draft_history (drafts archivados por invalidaciones).
- Winner detectado y su fuente.

No escribe nada a BD. Solo lectura.

Uso:
    .venv/bin/python debug_scrim_drafts.py <series_id> [<series_id> ...]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent
load_dotenv(REPO_ROOT / ".env")

from grid_minion import GridRestClient, split_grid_series
from grid_minion.observers import (
    DraftObserver,
    GameEventProcessor,
    PostGameObserver,
    TeamsObserver,
)


_DRAFT_EVENT_TYPES = {
    "team-picked-character":   "pick",
    "team-banned-character":   "ban",
    "team-!picked-character":  "undo_pick",
    "team-!banned-character":  "undo_ban",
    "grid-invalidated-series": "invalidate",
    "game-aborted":            "abort",
}


def _iter_events(raw):
    """Maneja dos formatos: evento suelto o wrapper con clave 'events'."""
    for ev in raw:
        if not isinstance(ev, dict):
            continue
        inner = ev.get("events")
        if isinstance(inner, list):
            yield from inner
        else:
            yield ev


def _summarize_draft(d: dict, indent: str = "    ") -> None:
    fp = d.get("fp", {})
    sp = d.get("sp", {})
    fp_p = fp.get("picks") or []
    sp_p = sp.get("picks") or []
    fp_b = fp.get("bans")  or []
    sp_b = sp.get("bans")  or []
    print(f"{indent}fp.team_id={fp.get('team_id')}  sp.team_id={sp.get('team_id')}")
    print(f"{indent}fp.picks ({len(fp_p)}): {fp_p}")
    print(f"{indent}sp.picks ({len(sp_p)}): {sp_p}")
    print(f"{indent}fp.bans  ({len(fp_b)}): {fp_b}")
    print(f"{indent}sp.bans  ({len(sp_b)}): {sp_b}")


def diagnose(series_id: str) -> None:
    client = GridRestClient(api_key=os.environ["GRID_API_KEY"])
    print(f"\n========= Serie {series_id} =========")

    full = client.get_grid_events(series_id)
    if not full:
        print("Sin eventos disponibles.")
        return

    games = split_grid_series(full)
    print(f"Partidas (split_grid_series): {len(games)}")

    for i, raw in enumerate(games):
        n = i + 1
        print(f"\n--- Game {n} ---")

        counts = {v: 0 for v in _DRAFT_EVENT_TYPES.values()}
        total_events = 0
        for ev in _iter_events(raw):
            total_events += 1
            t = ev.get("type") or ev.get("rfc461Schema") or ""
            key = _DRAFT_EVENT_TYPES.get(t)
            if key:
                counts[key] += 1
        print(f"  total events: {total_events}")
        print(f"  draft event counts: {counts}")

        proc  = GameEventProcessor()
        teams = TeamsObserver()
        draft = DraftObserver()
        stats = PostGameObserver()
        for o in (teams, draft, stats):
            proc.attach(o)

        summary   = client.get_riot_summary(series_id, game_number=n)
        livestats = client.get_riot_livestats(series_id, game_number=n)
        proc.process_bundle(
            grid_livestats=raw,
            riot_summary=summary,
            riot_livestats=livestats,
        )

        d = draft.get_draft()
        print(f"  draft_found: {d['draft_found']}   is_complete: {d['is_complete']}")
        print("  draft actual:")
        _summarize_draft(d)

        history = getattr(draft, "draft_history", None)
        if history is None:
            print("  draft_history: <atributo no expuesto>")
        else:
            print(f"  draft_history: {len(history)} entrada(s)")
            for j, h in enumerate(history):
                fp_p = (h.get("fp") or {}).get("picks") or []
                sp_p = (h.get("sp") or {}).get("picks") or []
                fp_b = (h.get("fp") or {}).get("bans")  or []
                sp_b = (h.get("sp") or {}).get("bans")  or []
                done = (len(fp_p) == 5 and len(sp_p) == 5)
                non_null_bans = (
                    sum(1 for b in fp_b if b)
                    + sum(1 for b in sp_b if b)
                )
                print(f"    [{j}] complete={done}  "
                      f"fp.picks={len(fp_p)}  sp.picks={len(sp_p)}  "
                      f"bans no-null={non_null_bans}")
                _summarize_draft(h, indent="        ")

        gs = stats.get_game_stats(teams)
        meta = gs.get("meta", {})
        print(f"  winner: {meta.get('winner')}   "
              f"winner_source: {meta.get('winner_source')}   "
              f"version: {meta.get('version')}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: debug_scrim_drafts.py <series_id> [<series_id> ...]")
        sys.exit(1)
    for sid in sys.argv[1:]:
        diagnose(sid)
