"""Entry point del extractor de SoloQ (fase 2: persistencia en BD).

Lanzar:  python -m src.extraction.soloq_run --since YYYY-MM-DD [--limit N]

Flujo (CLAUDE.md §5):
1. Refresca champions desde Data Dragon (barato; evita perder picks cuando
   sale un campeon nuevo).
2. Carga las cuentas trackeadas de la tabla accounts (poblada por
   src/riot/accounts_sync.py).
3. Lista los match ids de Ranked Solo/Duo (queue 420) por region desde
   --since, deduplicando entre cuentas.
4. Filtra contra BD por riot_api_id ANTES de descargar nada.
5. Inserta cada partida en su propia transaccion (games + picks). Los
   remakes se saltan. Sin cache en disco: la BD es la idempotencia.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.db.conn import get_conn
from src.riot.client import RiotClient, RiotError
from src.riot.endpoints import RANKED_SOLO_QUEUE, get_match_ids
from src.riot.soloq_run import match_sort_key

from .soloq import (
    ChampionIds,
    filter_new_match_ids,
    load_tracked_accounts,
    process_match,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger("extraction")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Extrae soloq de la Riot API y la vuelca a la BD."
    )
    parser.add_argument("--since", metavar="YYYY-MM-DD", required=True,
                        help="Solo partidas desde esta fecha (UTC).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Tope de partidas nuevas a procesar.")
    args = parser.parse_args()

    start_time = int(
        datetime.strptime(args.since, "%Y-%m-%d")
        .replace(tzinfo=timezone.utc).timestamp()
    )

    client = RiotClient()
    stats: Counter[str] = Counter()

    with get_conn() as conn:
        tracked = load_tracked_accounts(conn)
        if not tracked:
            log.error("La tabla accounts esta vacia — lanzar primero "
                      "`python -m src.riot.accounts_sync`.")
            return 1
        log.info("Cuentas trackeadas: %d.", len(tracked))

        champions = ChampionIds(conn)

        # Match ids por region, union deduplicada entre cuentas.
        by_region: dict[str, list] = defaultdict(list)
        for account in tracked.values():
            by_region[account.region].append(account)
        all_ids: set[str] = set()
        for region, accounts in by_region.items():
            for account in accounts:
                ids = get_match_ids(client, region, account.puuid,
                                    queue=RANKED_SOLO_QUEUE,
                                    start_time=start_time)
                log.info("puuid %s... (%s): %d partidas desde %s.",
                         account.puuid[:12], region, len(ids), args.since)
                all_ids.update(ids)

        match_ids = sorted(all_ids, key=match_sort_key, reverse=True)
        new_ids = filter_new_match_ids(conn, match_ids)
        stats["ya_en_bd"] = len(match_ids) - len(new_ids)
        if args.limit is not None:
            new_ids = new_ids[: args.limit]
        log.info("%d partidas listadas, %d ya en BD, %d a procesar.",
                 len(match_ids), stats["ya_en_bd"], len(new_ids))

        for match_id in new_ids:
            try:
                stats[process_match(client, conn, match_id, tracked, champions)] += 1
                conn.commit()
            except RiotError as e:
                log.error("RiotError en %s: %s", match_id, e)
                conn.rollback()
                stats["errores"] += 1
            except Exception:
                conn.rollback()
                raise

    log.info("Extraccion de soloq completada. insertadas=%d remakes=%d "
             "ya_en_bd=%d sin_detalle=%d sin_trackeados=%d dup=%d errores=%d",
             stats["inserted"], stats["remake"], stats["ya_en_bd"],
             stats["no_detail"], stats["no_tracked"], stats["dup"],
             stats["errores"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
