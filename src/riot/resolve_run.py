"""Utilidad: Riot ID -> PUUID (+ deteccion de region de juego).

Lanzar:  python -m src.riot.resolve_run "Byron Love#1v9" [--region europe]

- Resuelve el PUUID via Account-V1 e imprime el gameName/tagLine canonicos.
- Sin --region, prueba europe -> americas -> asia (Account-V1 es global,
  cualquier cluster resuelve).
- Ademas sondea las 4 regiones de Match-V5 pidiendo 1 match id en cada una,
  para saber donde juega la cuenta (la plataforma sale del prefijo del id).

Es el embrion de la utilidad de carga de `accounts` de la fase 2: en BD las
cuentas se guardaran como PUUID (los Riot IDs cambian; el puuid no).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from .client import RiotClient, RiotError
from .endpoints import get_account_by_riot_id
from .routing import REGIONS

REPO_ROOT = Path(__file__).resolve().parents[2]

log = logging.getLogger("riot")

_ACCOUNT_CLUSTERS = ("europe", "americas", "asia")


def parse_riot_id(riot_id: str) -> tuple[str, str]:
    if "#" not in riot_id:
        raise ValueError(f"Riot ID invalido (falta '#'): {riot_id!r}")
    game_name, tag_line = riot_id.rsplit("#", 1)
    return game_name.strip(), tag_line.strip()


def resolve_account(
    client: RiotClient, riot_id: str, region: str | None = None
) -> dict | None:
    game_name, tag_line = parse_riot_id(riot_id)
    clusters = (region,) if region else _ACCOUNT_CLUSTERS
    for cluster in clusters:
        account = get_account_by_riot_id(client, cluster, game_name, tag_line)
        if account is not None:
            return account
    return None


def probe_match_regions(client: RiotClient, puuid: str) -> dict[str, str]:
    """region -> match id mas reciente, solo para regiones con partidas."""
    found = {}
    for region in REGIONS:
        page = client.get(
            region,
            f"/lol/match/v5/matches/by-puuid/{puuid}/ids",
            {"start": 0, "count": 1},
        )
        if page:
            found[region] = page[0]
    return found


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Resuelve un Riot ID a PUUID.")
    parser.add_argument("riot_id", help='Riot ID con formato "Nombre#TAG".')
    parser.add_argument("--region", choices=_ACCOUNT_CLUSTERS, default=None,
                        help="Cluster regional para Account-V1 (opcional).")
    args = parser.parse_args()

    client = RiotClient()
    try:
        account = resolve_account(client, args.riot_id, args.region)
    except RiotError as e:
        log.error("%s", e)
        return 1
    if account is None:
        log.error("Riot ID no encontrado: %s", args.riot_id)
        return 1

    print(f"riot_id : {account.get('gameName')}#{account.get('tagLine')}")
    print(f"puuid   : {account.get('puuid')}")

    regions = probe_match_regions(client, account["puuid"])
    if not regions:
        print("regiones: sin partidas en ninguna region (matchlist vacio)")
    for region, match_id in regions.items():
        platform = match_id.split("_", 1)[0]
        print(f"regiones: {region} (plataforma {platform}, ultima {match_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
