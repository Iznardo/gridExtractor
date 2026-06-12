"""Extraccion de los datos que nos interesan de una partida de SoloQ.

Entrada: detalle de Match-V5 + timeline (cruda) + set de PUUIDs trackeados.
Salida: dict con los datos generales de la partida y una entrada por cada
jugador trackeado presente (multi-jugador: si N cuentas de la BD coinciden
en la partida, una sola pasada las extrae todas).

Parseo tolerante en todo el modulo: el esquema de Riot crece por parche,
ningun campo se asume presente (.get() siempre).
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("riot")

_SIDE = {100: "BLUE", 200: "RED"}
_SKILL_LETTER = {1: "Q", 2: "W", 3: "E", 4: "R"}


def normalize_version(game_version: str | None) -> str:
    """'16.10.776.5552' -> '16.10' (formato de games.version)."""
    if not game_version:
        return "Unknown"
    parts = game_version.split(".")
    if len(parts) < 2:
        return "Unknown"
    return f"{parts[0]}.{parts[1]}"


def game_duration_s(info: dict) -> int | None:
    """gameDuration esta en segundos si existe gameEndTimestamp; en partidas
    antiguas sin el, esta en milisegundos (RIOT_API.md §6.3)."""
    duration = info.get("gameDuration")
    if duration is None:
        return None
    if "gameEndTimestamp" in info:
        return int(duration)
    return int(duration / 1000)


def _winner(info: dict) -> str:
    for team in info.get("teams", []):
        if team.get("win"):
            return _SIDE.get(team.get("teamId"), "NONE")
    return "NONE"


# Una partida abortada por AFK en los primeros minutos. No cuenta para stats
# (mismo criterio que op.gg); el umbral de duracion cubre datos antiguos sin
# el flag de early surrender.
_REMAKE_MAX_DURATION_S = 300


def is_remake(match: dict) -> bool:
    info = match.get("info", {})
    if any(p.get("gameEndedInEarlySurrender")
           for p in info.get("participants", [])):
        return True
    duration = game_duration_s(info)
    return duration is not None and duration < _REMAKE_MAX_DURATION_S


def _bans(info: dict) -> dict:
    """{'blue': [ids...], 'red': [ids...]} desde teams[].bans, en pickTurn.
    En soloq los bans son simultaneos, asi que el orden es solo cosmetico."""
    bans: dict[str, list] = {"blue": [], "red": []}
    for team in info.get("teams", []):
        side = _SIDE.get(team.get("teamId"))
        if side is None:
            continue
        entries = sorted(team.get("bans", []), key=lambda b: b.get("pickTurn", 0))
        # Riot usa -1 cuando no se baneo en ese turno; lo normalizamos a None
        # (coherente con la convencion NULL de drafts, CLAUDE.md §4.2).
        bans[side.lower()] = [
            None if b.get("championId") == -1 else b.get("championId")
            for b in entries
        ]
    return bans


def _composition(info: dict) -> list[dict]:
    """Los 10 participantes (aliados y enemigos) con lo minimo para pintar la
    partida completa: puuid, campeon, lado y posicion. Sin riot_ids."""
    return [
        {
            "puuid": p.get("puuid"),
            "champion_id": p.get("championId"),
            "team_side": _SIDE.get(p.get("teamId")),
            "team_position": p.get("teamPosition"),
        }
        for p in info.get("participants", [])
    ]


def _runes(participant: dict) -> dict | None:
    perks = participant.get("perks")
    if not perks:
        return None
    runes: dict[str, Any] = {}
    for style in perks.get("styles", []):
        perk_ids = [s.get("perk") for s in style.get("selections", [])]
        if style.get("description") == "primaryStyle":
            runes["primary_style"] = style.get("style")
            runes["primary"] = perk_ids
        elif style.get("description") == "subStyle":
            runes["sub_style"] = style.get("style")
            runes["sub"] = perk_ids
    stat = perks.get("statPerks") or {}
    runes["stat_perks"] = [stat.get("offense"), stat.get("flex"), stat.get("defense")]
    return runes


def _iter_events(timeline: dict):
    for frame in timeline.get("info", {}).get("frames", []):
        yield from frame.get("events", [])


def _timeline_pid(timeline: dict, puuid: str) -> int | None:
    for p in timeline.get("info", {}).get("participants", []):
        if p.get("puuid") == puuid:
            return p.get("participantId")
    return None


def build_path(timeline: dict, participant_id: int) -> list[dict]:
    """Compras (BUY) y ventas (SELL) en orden cronologico. ITEM_UNDO deshace
    el ultimo evento que coincida: beforeId != 0 anula la ultima compra de ese
    item; afterId != 0 anula la ultima venta (semantica observada en los
    fixtures: vender y deshacer la venta emite UNDO con beforeId=0)."""
    path: list[dict] = []

    def _remove_last(action: str, item_id: int) -> None:
        for i in range(len(path) - 1, -1, -1):
            if path[i]["action"] == action and path[i]["item_id"] == item_id:
                del path[i]
                return
        log.debug("ITEM_UNDO sin evento que deshacer (%s %s)", action, item_id)

    for ev in _iter_events(timeline):
        if ev.get("participantId") != participant_id:
            continue
        ts_s = int(ev.get("timestamp", 0) / 1000)
        etype = ev.get("type")
        if etype == "ITEM_PURCHASED":
            path.append({"ts_s": ts_s, "action": "BUY", "item_id": ev.get("itemId")})
        elif etype == "ITEM_SOLD":
            path.append({"ts_s": ts_s, "action": "SELL", "item_id": ev.get("itemId")})
        elif etype == "ITEM_UNDO":
            if ev.get("beforeId"):
                _remove_last("BUY", ev["beforeId"])
            elif ev.get("afterId"):
                _remove_last("SELL", ev["afterId"])
    return path


def skill_order(timeline: dict, participant_id: int) -> str:
    """'QEWEER...' a partir de los SKILL_LEVEL_UP. Los EVOLVE (Kha'Zix,
    Viktor...) no consumen punto de habilidad y se excluyen."""
    letters = []
    for ev in _iter_events(timeline):
        if (ev.get("type") == "SKILL_LEVEL_UP"
                and ev.get("participantId") == participant_id
                and ev.get("levelUpType", "NORMAL") == "NORMAL"):
            letter = _SKILL_LETTER.get(ev.get("skillSlot"))
            if letter:
                letters.append(letter)
    return "".join(letters)


def _extract_participant(
    participant: dict, timeline: dict | None
) -> dict:
    puuid = participant.get("puuid")
    game_name = participant.get("riotIdGameName") or ""
    tag_line = participant.get("riotIdTagline") or ""
    out: dict[str, Any] = {
        "puuid": puuid,
        # Solo metadato de verificacion humana; NUNCA va a BD (cambia, el puuid no).
        "riot_id": f"{game_name}#{tag_line}" if game_name else None,
        "champion_id": participant.get("championId"),
        "champion_name": participant.get("championName"),
        "team_side": _SIDE.get(participant.get("teamId")),
        # teamPosition es la verdad de la posicion jugada; lane/role mienten (§6.3).
        "team_position": participant.get("teamPosition"),
        "win": participant.get("win"),
        "kills": participant.get("kills"),
        "deaths": participant.get("deaths"),
        "assists": participant.get("assists"),
        "cs": (participant.get("totalMinionsKilled", 0)
               + participant.get("neutralMinionsKilled", 0)),
        "gold": participant.get("goldEarned"),
        "champ_level": participant.get("champLevel"),
        "vision_score": participant.get("visionScore"),
        "summoner_spells": [participant.get("summoner1Id"),
                            participant.get("summoner2Id")],
        # item0..item6; Riot rellena con 0 los slots vacios al acabar la
        # partida. Filtramos esos huecos (un 0 en lista plana no aporta nada).
        "final_items": [it for i in range(7)
                        if (it := participant.get(f"item{i}"))],
        "runes": _runes(participant),
        "build_path": None,
        "skill_order": None,
    }
    if timeline is not None:
        pid = _timeline_pid(timeline, puuid) or participant.get("participantId")
        if pid is not None:
            out["build_path"] = build_path(timeline, pid)
            out["skill_order"] = skill_order(timeline, pid)
    return out


def extract_match(
    match: dict, timeline: dict | None, tracked_puuids: set[str]
) -> dict | None:
    """Devuelve el extracto de la partida con una entrada en `players` por
    cada puuid trackeado presente, o None si ninguno participa."""
    info = match.get("info", {})
    players = [
        _extract_participant(p, timeline)
        for p in info.get("participants", [])
        if p.get("puuid") in tracked_puuids
    ]
    if not players:
        return None
    return {
        "match_id": match.get("metadata", {}).get("matchId"),
        "platform": info.get("platformId"),
        "queue_id": info.get("queueId"),
        "game_creation": info.get("gameCreation"),
        "game_duration_s": game_duration_s(info),
        "game_version": normalize_version(info.get("gameVersion")),
        "winner": _winner(info),
        "bans": _bans(info),
        "participants": _composition(info),
        "players": players,
    }
