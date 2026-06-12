"""Sincroniza las cuentas de config/soloq_accounts.yaml a la tabla `accounts`.

Lanzar:  python -m src.riot.accounts_sync

Por cada entrada del YAML (riot_id, player, region):
- `player` debe ser el nombre exacto en la tabla `players` (los jugadores
  vienen del discovery de GRID; aqui no se crean). Sin player o sin match
  en BD -> WARNING y skip.
- Resuelve el PUUID via Account-V1. El riot_id solo se usa para resolver:
  en BD la unica identidad es el puuid (los Riot IDs cambian).
- Region null -> autodetectar sondeando Match-V5 y avisar.
- INSERT idempotente por puuid (ON CONFLICT DO NOTHING).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.db.conn import get_conn

from .client import RiotClient, RiotError
from .resolve_run import probe_match_regions, resolve_account
from .soloq_run import match_sort_key

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "soloq_accounts.yaml"

log = logging.getLogger("riot")


def player_id_by_name(conn, name: str) -> int | None:
    """Busca jugador tolerando diferencias de casing y prefijos de equipo.

    Prioridad:
    1. Exacto case-insensitive: "Vladi" == "vladi".
    2. El input es sufijo tras espacio: "Vladi" encuentra "BDS Vladi".
    Si hay ambiguedad (varios candidatos) avisa y devuelve None.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name FROM players WHERE LOWER(name) = LOWER(%s)",
            (name,),
        )
        rows = cur.fetchall()
        if len(rows) == 1:
            if rows[0][1] != name:
                log.info("Nombre %r resuelto como %r (casing).", name, rows[0][1])
            return rows[0][0]
        if len(rows) > 1:
            log.warning("Nombre %r ambiguo (%d coincidencias) — usa el nombre "
                        "exacto en player:. Skip.", name, len(rows))
            return None

        # Fallback: el input es sufijo tras espacio ("T1 Faker" -> "Faker")
        cur.execute(
            "SELECT id, name FROM players WHERE LOWER(name) LIKE '% ' || LOWER(%s)",
            (name,),
        )
        rows = cur.fetchall()
        if len(rows) == 1:
            log.info("Nombre %r resuelto como %r (sufijo con tag de equipo).",
                     name, rows[0][1])
            return rows[0][0]
        if len(rows) > 1:
            candidates = [r[1] for r in rows]
            log.warning("Nombre %r ambiguo con sufijo %s — usa el nombre "
                        "exacto en player:. Skip.", name, candidates)
            return None

        return None


def insert_account(conn, player_id: int, region: str, puuid: str) -> bool:
    """True si la cuenta es nueva; False si el puuid ya estaba."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO accounts (player_id, region, puuid)
            VALUES (%s, %s, %s)
            ON CONFLICT (puuid) DO NOTHING
            RETURNING id
            """,
            (player_id, region, puuid),
        )
        return cur.fetchone() is not None


def sync_account(client: RiotClient, conn, entry: dict) -> str:
    """Procesa una entrada del YAML. Devuelve 'new'/'existing'/'skipped'."""
    riot_id = entry.get("riot_id")
    player_name = entry.get("player")
    if not player_name:
        log.warning("%s: sin 'player' en el YAML — rellenarlo con el nombre "
                    "exacto de la tabla players. Skip.", riot_id)
        return "skipped"

    player_id = player_id_by_name(conn, player_name)
    if player_id is None:
        log.warning("%s: player %r no encontrado en players "
                    "(¿discovery pendiente, typo o ambiguo?). Skip.",
                    riot_id, player_name)
        return "skipped"

    account = resolve_account(client, riot_id)
    if account is None:
        log.warning("%s: Riot ID no encontrado en Account-V1. Skip.", riot_id)
        return "skipped"
    puuid = account["puuid"]

    region = entry.get("region")
    if not region:
        found = probe_match_regions(client, puuid)
        if not found:
            log.warning("%s: sin partidas en ninguna region — no se puede "
                        "autodetectar. Fijar 'region' en el YAML. Skip.", riot_id)
            return "skipped"
        region = max(found, key=lambda r: match_sort_key(found[r]))
        log.warning("%s: region autodetectada '%s' — fijarla en %s.",
                    riot_id, region, CONFIG_PATH.name)

    is_new = insert_account(conn, player_id, region, puuid)
    log.info("%s -> player %r (id=%d), region=%s, puuid=%s... [%s]",
             riot_id, player_name, player_id, region, puuid[:12],
             "NUEVA" if is_new else "ya existia")
    return "new" if is_new else "existing"


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv(dotenv_path=REPO_ROOT / ".env")

    config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    accounts = config.get("accounts") or []
    if not accounts:
        log.error("Sin cuentas en %s.", CONFIG_PATH)
        return 1

    client = RiotClient()
    results = {"new": 0, "existing": 0, "skipped": 0}
    with get_conn() as conn:
        for entry in accounts:
            try:
                results[sync_account(client, conn, entry)] += 1
            except RiotError as e:
                log.error("RiotError en %s: %s", entry.get("riot_id"), e)
                results["skipped"] += 1
        conn.commit()

    log.info("Sync completado: %d nuevas, %d existentes, %d skip.",
             results["new"], results["existing"], results["skipped"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
