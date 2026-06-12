"""Runner de la fase 1 de SoloQ: extraccion + verificacion, sin BD.

Lanzar:  python -m src.riot.soloq_run --since YYYY-MM-DD [--account "X#Y"] [--limit N]

Flujo:
1. Lee las cuentas de config/soloq_accounts.yaml y resuelve sus PUUID
   (cacheado en data/riot/accounts/).
2. Lista los match ids de Ranked Solo/Duo (queue=420) desde --since.
3. Deduplica la union de todas las cuentas: si dos cuentas trackeadas
   comparten partida, se procesa una sola vez con el set completo de PUUIDs
   (mismo modelo que usara la persistencia de fase 2).
4. Por cada partida: detalle + timeline (cacheados en data/riot/matches/),
   extract_match, volcado a data/riot/extracted/{matchId}.json y resumen
   legible por pantalla para verificacion manual.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .cache import ACCOUNTS_DIR, EXTRACTED_DIR, fetch_match_cached, fetch_timeline_cached
from .client import RiotClient, RiotError
from .endpoints import RANKED_SOLO_QUEUE, get_match_ids
from .extract import extract_match
from .resolve_run import probe_match_regions, resolve_account

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "soloq_accounts.yaml"

log = logging.getLogger("riot")


def resolve_account_cached(client: RiotClient, riot_id: str) -> dict | None:
    path = ACCOUNTS_DIR / f"{riot_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    account = resolve_account(client, riot_id)
    if account is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(account, ensure_ascii=False))
    return account


def match_sort_key(match_id: str) -> int:
    """Numero del match id, para ordenar de mas reciente a mas antigua."""
    try:
        return int(match_id.split("_", 1)[1])
    except (IndexError, ValueError):
        return 0


def summary_line(extract: dict, player: dict) -> str:
    creation_ms = extract.get("game_creation") or 0
    date = datetime.fromtimestamp(creation_ms / 1000, tz=timezone.utc)
    kda = f"{player.get('kills')}/{player.get('deaths')}/{player.get('assists')}"
    result = "WIN " if player.get("win") else "LOSS"
    n_items = len(player.get("build_path") or [])
    return (f"{extract.get('match_id')}  {date:%Y-%m-%d %H:%M}  "
            f"{player.get('riot_id')}  {player.get('champion_name'):<12} "
            f"{player.get('team_position') or '?':<7} {result} {kda:<8} "
            f"cs {player.get('cs'):<3}  skill {player.get('skill_order') or '-'}  "
            f"build {n_items} eventos")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Extrae partidas de SoloQ (queue 420) de las cuentas trackeadas."
    )
    parser.add_argument("--since", metavar="YYYY-MM-DD", required=True,
                        help="Solo partidas desde esta fecha (UTC).")
    parser.add_argument("--account", default=None,
                        help="Procesar solo este Riot ID del YAML.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Tope de partidas a procesar (las mas recientes).")
    args = parser.parse_args()

    start_time = int(
        datetime.strptime(args.since, "%Y-%m-%d")
        .replace(tzinfo=timezone.utc).timestamp()
    )

    config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    accounts = config.get("accounts") or []
    if args.account:
        accounts = [a for a in accounts if a.get("riot_id") == args.account]
    if not accounts:
        log.error("Sin cuentas que procesar (revisar %s / --account).", CONFIG_PATH)
        return 1

    client = RiotClient()

    # 1-2. Resolver puuids y listar match ids por cuenta.
    tracked_puuids: set[str] = set()
    all_match_ids: set[str] = set()
    for entry in accounts:
        riot_id = entry.get("riot_id")
        account = resolve_account_cached(client, riot_id)
        if account is None:
            log.warning("Cuenta no encontrada en Account-V1: %s — skip.", riot_id)
            continue
        puuid = account["puuid"]
        tracked_puuids.add(puuid)

        region = entry.get("region")
        if not region:
            found = probe_match_regions(client, puuid)
            if not found:
                log.warning("%s: sin partidas en ninguna region — skip.", riot_id)
                continue
            region = max(found, key=lambda r: match_sort_key(found[r]))
            log.warning("%s: region autodetectada '%s' — fijarla en %s.",
                        riot_id, region, CONFIG_PATH.name)

        ids = get_match_ids(client, region, puuid,
                            queue=RANKED_SOLO_QUEUE, start_time=start_time)
        log.info("%s (%s): %d partidas de soloq desde %s.",
                 riot_id, region, len(ids), args.since)
        all_match_ids.update(ids)

    # 3. Union deduplicada, de mas reciente a mas antigua.
    match_ids = sorted(all_match_ids, key=match_sort_key, reverse=True)
    if args.limit is not None:
        match_ids = match_ids[: args.limit]
    log.info("Total a procesar: %d partidas (union deduplicada).", len(match_ids))

    # 4. Descargar, extraer y volcar.
    downloaded = cached = extracted = errors = 0
    for match_id in match_ids:
        try:
            match, m_cached = fetch_match_cached(client, match_id)
            timeline, t_cached = fetch_timeline_cached(client, match_id)
        except RiotError as e:
            log.error("RiotError en %s: %s", match_id, e)
            errors += 1
            continue
        if m_cached and t_cached:
            cached += 1
        else:
            downloaded += 1
        if match is None:
            log.warning("%s: detalle no disponible (404) — skip.", match_id)
            continue
        if timeline is None:
            log.warning("%s: timeline no disponible (404) — sin build/skills.", match_id)

        result = extract_match(match, timeline, tracked_puuids)
        if result is None:
            log.warning("%s: ningun puuid trackeado en la partida — skip.", match_id)
            continue
        EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
        (EXTRACTED_DIR / f"{match_id}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2)
        )
        extracted += 1
        for player in result["players"]:
            print(summary_line(result, player))

    log.info("Hecho. listadas=%d descargadas=%d desde_cache=%d extraidas=%d errores=%d",
             len(match_ids), downloaded, cached, extracted, errors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
