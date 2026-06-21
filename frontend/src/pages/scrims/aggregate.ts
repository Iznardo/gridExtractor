/**
 * Agregaciones puras del dashboard de Scrims a partir de las filas de
 * /scrims/games (una por scrim del equipo). Sin estado ni red: testeables.
 *
 * El endpoint ya viene team-céntrico (won = victoria del equipo trackeado,
 * lineup = sus 5 campeones por rol, rival_champs = picks rivales).
 */
import type { ScrimGame, ScrimRole } from "../../api/types";

export type Count = { games: number; wins: number };

export function winRate(c: Count): number | null {
  return c.games > 0 ? Math.round((c.wins / c.games) * 1000) / 10 : null;
}

function bump(c: Count, won: boolean): void {
  c.games += 1;
  if (won) c.wins += 1;
}

// ---- #3 Último bloque ----

export type BlockSummary = {
  key: string;              // `${date}|${rivalId}`
  date: string;
  version: string | null;   // parche del bloque (de su primer game)
  rival: ScrimGame["rival"];
  games: ScrimGame[];       // ordenadas por block_game_number asc
  total: Count;
  blue: Count;
  red: Count;
};

/** Agrupa todas las scrims en bloques (date, rival). Devuelve los bloques más
 *  recientes primero. rows vienen date DESC desde la API. */
export function blocks(rows: ScrimGame[]): BlockSummary[] {
  const map = new Map<string, ScrimGame[]>();
  for (const r of rows) {
    const key = `${r.date}|${r.rival?.id ?? "none"}`;
    const arr = map.get(key) ?? [];
    arr.push(r);
    map.set(key, arr);
  }
  const out: BlockSummary[] = [];
  for (const [key, gs] of map) {
    const games = [...gs].sort((a, b) => a.block_game_number - b.block_game_number);
    const total: Count = { games: 0, wins: 0 };
    const blue: Count = { games: 0, wins: 0 };
    const red: Count = { games: 0, wins: 0 };
    for (const g of games) {
      bump(total, g.won);
      bump(g.our_side === "BLUE" ? blue : red, g.won);
    }
    out.push({
      key,
      date: games[0].date,
      version: games[0].version,
      rival: games[0].rival,
      games,
      total,
      blue,
      red,
    });
  }
  // Más reciente primero: por fecha y, a igualdad, por el game más nuevo.
  const maxId = (b: BlockSummary) => Math.max(...b.games.map((g) => g.game_id));
  out.sort((a, b) => b.date.localeCompare(a.date) || maxId(b) - maxId(a));
  return out;
}

/** Último bloque = el más reciente (date, rival). */
export function lastBlock(rows: ScrimGame[]): BlockSummary | null {
  return blocks(rows)[0] ?? null;
}

// ---- #4/#5 Duos y Trios (combos por conjunto de roles) ----

export type Combo = { champs: number[]; count: Count };

/** Para un conjunto de roles, agrupa por la tupla de campeones de esos roles.
 *  Ignora games donde falte alguno de esos roles (datos sucios de scrim). */
export function combosByRoles(rows: ScrimGame[], roles: ScrimRole[]): Combo[] {
  const map = new Map<string, Combo>();
  for (const r of rows) {
    const champs = roles.map((role) => r.lineup[role]);
    if (champs.some((c) => c == null)) continue; // falta un rol → fuera
    const key = (champs as number[]).join("-");
    const entry = map.get(key) ?? { champs: champs as number[], count: { games: 0, wins: 0 } };
    bump(entry.count, r.won);
    map.set(key, entry);
  }
  return Array.from(map.values()).sort(
    (a, b) => b.count.games - a.count.games || (winRate(b.count) ?? 0) - (winRate(a.count) ?? 0),
  );
}

// ---- #6 vs-Equipos ----

export type VsTeam = {
  rival: NonNullable<ScrimGame["rival"]>;
  total: Count;
  firstPick: Count;
  secondPick: Count;
  byGame: Map<number, Count>; // block_game_number → conteo
};

export function vsTeams(rows: ScrimGame[]): VsTeam[] {
  const map = new Map<number, VsTeam>();
  for (const r of rows) {
    if (!r.rival) continue;
    const entry =
      map.get(r.rival.id) ?? {
        rival: r.rival,
        total: { games: 0, wins: 0 },
        firstPick: { games: 0, wins: 0 },
        secondPick: { games: 0, wins: 0 },
        byGame: new Map<number, Count>(),
      };
    bump(entry.total, r.won);
    bump(r.first_pick ? entry.firstPick : entry.secondPick, r.won);
    const gn = entry.byGame.get(r.block_game_number) ?? { games: 0, wins: 0 };
    bump(gn, r.won);
    entry.byGame.set(r.block_game_number, gn);
    map.set(r.rival.id, entry);
  }
  return Array.from(map.values()).sort((a, b) => b.total.games - a.total.games);
}

// ---- #7 vs-Picks ----

export type VsPick = { champ_id: number; count: Count };

/** WR del equipo contra cada campeón que el rival pickeó (lista plana). */
export function vsPicks(rows: ScrimGame[]): VsPick[] {
  const map = new Map<number, VsPick>();
  for (const r of rows) {
    for (const champ of r.rival_champs) {
      const entry = map.get(champ) ?? { champ_id: champ, count: { games: 0, wins: 0 } };
      bump(entry.count, r.won);
      map.set(champ, entry);
    }
  }
  return Array.from(map.values()).sort(
    (a, b) => b.count.games - a.count.games || (winRate(b.count) ?? 0) - (winRate(a.count) ?? 0),
  );
}
