/**
 * Pure aggregations for the Scrims dashboard from /scrims/games rows
 * (one per team scrim). Stateless and network-free: testable.
 *
 * The endpoint is already team-centric (won = win of the tracked team,
 * lineup = its 5 champions per role, rival_champs = opponent picks).
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

// ---- #3 Latest block ----

export type BlockSummary = {
  key: string;              // `${date}|${rivalId}`
  date: string;
  version: string | null;   // block patch (from its first game)
  rival: ScrimGame["rival"];
  games: ScrimGame[];       // sorted by block_game_number asc
  total: Count;
  blue: Count;
  red: Count;
};

/** Groups all scrims into blocks (date, rival). Returns the most recent
 *  blocks first. rows arrive date DESC from the API. */
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
  // Most recent first: by date and, on a tie, by the newest game.
  const maxId = (b: BlockSummary) => Math.max(...b.games.map((g) => g.game_id));
  out.sort((a, b) => b.date.localeCompare(a.date) || maxId(b) - maxId(a));
  return out;
}

/** Latest block = the most recent one (date, rival). */
export function lastBlock(rows: ScrimGame[]): BlockSummary | null {
  return blocks(rows)[0] ?? null;
}

// ---- #4/#5 Duos and Trios (combos by role set) ----

export type Combo = { champs: number[]; count: Count };

/** For a set of roles, groups by the tuple of champions in those roles.
 *  Ignores games missing any of those roles (dirty scrim data). */
export function combosByRoles(rows: ScrimGame[], roles: ScrimRole[]): Combo[] {
  const map = new Map<string, Combo>();
  for (const r of rows) {
    const champs = roles.map((role) => r.lineup[role]);
    if (champs.some((c) => c == null)) continue; // missing a role → skip
    const key = (champs as number[]).join("-");
    const entry = map.get(key) ?? { champs: champs as number[], count: { games: 0, wins: 0 } };
    bump(entry.count, r.won);
    map.set(key, entry);
  }
  return Array.from(map.values()).sort(
    (a, b) => b.count.games - a.count.games || (winRate(b.count) ?? 0) - (winRate(a.count) ?? 0),
  );
}

// ---- #6 vs-Teams ----

export type VsTeam = {
  rival: NonNullable<ScrimGame["rival"]>;
  total: Count;
  firstPick: Count;
  secondPick: Count;
  byGame: Map<number, Count>; // block_game_number → count
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
    // r.first_pick is null when the game has no usable draft (blind pick) —
    // it counts toward the total above but not toward either FP/SP bucket.
    if (r.first_pick != null) {
      bump(r.first_pick ? entry.firstPick : entry.secondPick, r.won);
    }
    const gn = entry.byGame.get(r.block_game_number) ?? { games: 0, wins: 0 };
    bump(gn, r.won);
    entry.byGame.set(r.block_game_number, gn);
    map.set(r.rival.id, entry);
  }
  return Array.from(map.values()).sort((a, b) => b.total.games - a.total.games);
}

// ---- #7 vs-Picks ----

export type VsPick = { champ_id: number; count: Count };

/** Team WR against each champion the opponent picked (flat list). */
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
