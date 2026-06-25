/**
 * Pure aggregations for the Scouting tab. No state or network: testable.
 *
 * - Pool aggregated across mediums (shared by the "Pool" window and the Dashboard).
 * - Series: group official games by `grid_series_id` for the dashboard.
 */
import type { Game, Medium, ScoutPlayer, ScoutingPool, TeamRef } from "../../api/types";

const ALL_MEDIUMS: Medium[] = ["official", "scrim", "soloq"];

// ---- pool aggregated across mediums ----

type AggCount = { games: number; wins: number };
type AggChamp = {
  champion: { id: number; name: string };
  total: AggCount;
};
export type AggPlayer = { player: ScoutPlayer["player"]; champions: AggChamp[] };

/** Merges the pool of several mediums into a single list per player. */
export function buildAggregate(pool: ScoutingPool, sources: Medium[] = ALL_MEDIUMS): AggPlayer[] {
  const players = new Map<
    number,
    { player: ScoutPlayer["player"]; champs: Map<number, AggChamp> }
  >();
  for (const medium of sources) {
    for (const p of pool.by_medium[medium]) {
      const entry = players.get(p.player.id) ?? {
        player: p.player,
        champs: new Map<number, AggChamp>(),
      };
      for (const ch of p.champions) {
        const c = entry.champs.get(ch.champion.id) ?? {
          champion: ch.champion,
          total: { games: 0, wins: 0 },
        };
        c.total.games += ch.games;
        c.total.wins += ch.wins;
        entry.champs.set(ch.champion.id, c);
      }
      players.set(p.player.id, entry);
    }
  }
  return Array.from(players.values()).map((e) => ({
    player: e.player,
    champions: Array.from(e.champs.values()).sort(
      (a, b) => b.total.games - a.total.games || a.champion.name.localeCompare(b.champion.name),
    ),
  }));
}

/** Adapts the aggregate to the shape `<MediumBox>` consumes. */
export function aggAsScoutPlayers(agg: AggPlayer[]): ScoutPlayer[] {
  return agg.map((ap) => ({
    player: ap.player,
    champions: ap.champions.map((ch) => ({
      champion: ch.champion,
      games: ch.total.games,
      wins: ch.total.wins,
    })),
  }));
}

// ---- series (dashboard: latest games grouped) ----

export type SeriesGame = {
  game: Game;
  our_side: "BLUE" | "RED";
  won: boolean;
  our_champs: { id: number; name: string | null }[];
  rival_champs: { id: number; name: string | null }[];
};

export type Series = {
  key: string;             // grid_series_id or `g${game_id}` if missing
  date: string;
  version: string | null;
  rival: TeamRef;
  games: SeriesGame[];     // sorted by game_number asc
  wins: number;
  total: number;
};

/** Groups games (already filtered to a team) into series by `grid_series_id`.
 *  Team-centric: `our_side`/`won`/champs are resolved relative to `teamId`.
 *  Returns the most recent series first. */
export function seriesBlocks(rows: Game[], teamId: number): Series[] {
  const map = new Map<string, Game[]>();
  for (const r of rows) {
    const key = r.grid_series_id != null ? `s${r.grid_series_id}` : `g${r.game_id}`;
    const arr = map.get(key) ?? [];
    arr.push(r);
    map.set(key, arr);
  }

  const out: Series[] = [];
  for (const [key, gs] of map) {
    const games = [...gs].sort(
      (a, b) => (a.game_number ?? 0) - (b.game_number ?? 0) || a.game_id - b.game_id,
    );
    const sgames: SeriesGame[] = games.map((g) => {
      const ourSide: "BLUE" | "RED" = g.team1?.id === teamId ? "BLUE" : "RED";
      return {
        game: g,
        our_side: ourSide,
        won: g.result === ourSide,
        our_champs: ourSide === "BLUE" ? g.blue_champions : g.red_champions,
        rival_champs: ourSide === "BLUE" ? g.red_champions : g.blue_champions,
      };
    });
    const first = games[0];
    const rival = first.team1?.id === teamId ? first.team2 : first.team1;
    out.push({
      key,
      date: first.date,
      version: first.version,
      rival,
      games: sgames,
      wins: sgames.filter((s) => s.won).length,
      total: sgames.length,
    });
  }

  // Most recent first: by date and, on ties, by the newest game.
  const maxId = (s: Series) => Math.max(...s.games.map((g) => g.game.game_id));
  out.sort((a, b) => b.date.localeCompare(a.date) || maxId(b) - maxId(a));
  return out;
}
