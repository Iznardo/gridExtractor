"""Parche de CS para partidas LPL: corrige picks.stats.cs sumando campamentos de jungla.

El bug estaba en tencent.py (grid-minion < 0.4.1): cs = creepsKilled sin sumar
totalNeutralMinKilled. Se corrige descargando el Tencent Details de cada partida
LPL y actualizando picks.stats con el CS recalculado.

Match participant → pick: por (game_id, champ_id). El heroId de Tencent es el
ID de campeón de Riot/Data Dragon, igual que picks.champ_id.

Lanzar:
    python -m src.extraction.patch_lpl_cs [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from grid_minion import GridError, GridRestClient
from grid_minion.sources import normalize_tencent_details

from src.db.conn import get_conn

REPO_ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("patch_lpl_cs")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Corrige CS de jungla en partidas LPL.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Muestra qué se actualizaría sin tocar la BD.")
    args = parser.parse_args()

    api_key = os.environ.get("GRID_API_KEY")
    if not api_key:
        log.error("Falta GRID_API_KEY en .env.")
        return 1

    client = GridRestClient(api_key=api_key)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, grid_series_id, game_number, tournament
                FROM games
                WHERE game_type = 'OFFICIAL'
                  AND tournament ILIKE '%LPL%'
                  AND grid_series_id IS NOT NULL
                ORDER BY date ASC, id ASC
            """)
            games = cur.fetchall()

    total = len(games)
    log.info("%d partidas LPL a parchear.", total)
    if total == 0:
        return 0

    updated_games = 0
    updated_picks = 0
    failed = 0

    with get_conn() as conn:
        for i, (game_id, series_id, game_number, tournament) in enumerate(games, 1):
            tencent_raw = None
            try:
                tencent_raw = client.get_tencent_details(str(series_id), game_number)
            except GridError as e:
                log.warning("[%d/%d] %s g%d: error descargando Tencent: %s",
                            i, total, series_id, game_number, e)
                failed += 1
                time.sleep(0.2)
                continue

            if not tencent_raw:
                log.warning("[%d/%d] series=%d g%d: sin Tencent Details, skip.",
                            i, total, series_id, game_number)
                failed += 1
                time.sleep(0.1)
                continue

            norm = normalize_tencent_details(tencent_raw)
            participants = norm.get("participants") or []

            # champ_id (heroId) → cs corregido
            cs_by_champ: dict[int, int] = {}
            for p in participants:
                champ_id = p.get("championId")
                cs = p.get("cs")
                if champ_id is not None and cs is not None:
                    cs_by_champ[int(champ_id)] = int(cs)

            if not cs_by_champ:
                log.warning("[%d/%d] series=%d g%d: sin participantes, skip.",
                            i, total, series_id, game_number)
                failed += 1
                time.sleep(0.1)
                continue

            # Recuperar picks existentes para esta partida
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT pk.id, pk.champ_id, pk.stats
                    FROM picks pk
                    WHERE pk.game_id = %s
                """, (game_id,))
                picks = cur.fetchall()

            game_pick_updates = 0
            for pick_id, champ_id, stats in picks:
                new_cs = cs_by_champ.get(champ_id)
                if new_cs is None:
                    log.debug("  pick_id=%d champ_id=%d: sin match en Tencent, skip.",
                              pick_id, champ_id)
                    continue

                old_cs = (stats or {}).get("cs")
                if old_cs == new_cs:
                    continue  # ya correcto

                log.debug("  pick_id=%d champ_id=%d: cs %s → %d",
                          pick_id, champ_id, old_cs, new_cs)

                if not args.dry_run:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE picks
                            SET stats = jsonb_set(stats, '{cs}', %s::jsonb)
                            WHERE id = %s
                        """, (json.dumps(new_cs), pick_id))
                game_pick_updates += 1
                updated_picks += 1

            if game_pick_updates > 0:
                if not args.dry_run:
                    conn.commit()
                updated_games += 1
                log.info("[%d/%d] series=%d g%d: %d picks actualizados.",
                         i, total, series_id, game_number, game_pick_updates)
            else:
                log.debug("[%d/%d] series=%d g%d: sin cambios.",
                          i, total, series_id, game_number)

            time.sleep(0.15)

    label = "actualizaría" if args.dry_run else "actualizadas"
    log.info("Hecho. %d partidas %s, %d picks %s, %d fallos.",
             updated_games, label, updated_picks, label, failed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
