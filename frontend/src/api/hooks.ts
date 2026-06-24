import { useQuery } from "@tanstack/react-query";

import { buildQuery, getJSON, type QueryParams } from "./client";
import type {
  Champion,
  ChampionPresenceRow,
  Draft,
  Game,
  MatchupEntry,
  Matchup,
  Pick,
  PickOrderData,
  RolePickData,
  ScoutingPool,
  ScrimGame,
  Team,
  TeamMatchupData,
} from "./types";

// El catálogo cambia poco: cachéalo agresivamente.
const CATALOG_OPTS = { staleTime: 60 * 60 * 1000 } as const;

export function useChampions() {
  return useQuery({
    queryKey: ["champions"],
    queryFn: () => getJSON<Champion[]>("/champions"),
    ...CATALOG_OPTS,
  });
}

export function useTeams() {
  return useQuery({
    queryKey: ["teams"],
    queryFn: () => getJSON<Team[]>("/teams"),
    ...CATALOG_OPTS,
  });
}

export type DraftFilters = {
  team_id?: number;
  rival_id?: number;
  patch?: string;
  pick_phase?: "first" | "second";
  champ_id?: number;
  game_type?: string;
  tournament?: string;
  limit?: number;
};

export function useDrafts(filters: DraftFilters, enabled = true) {
  return useQuery({
    queryKey: ["drafts", filters],
    queryFn: () => getJSON<Draft[]>("/drafts" + buildQuery(filters as QueryParams)),
    enabled,
  });
}

export type GameFilters = {
  team_id?: number;
  game_type?: string;
  champ_id?: number;
  champ_id2?: number;
  opposing?: boolean;
  patch?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
};

export function useGames(filters: GameFilters, enabled = true) {
  return useQuery({
    queryKey: ["games", filters],
    queryFn: () => getJSON<Game[]>("/games" + buildQuery(filters as QueryParams)),
    enabled,
  });
}

// Detalle de una partida: las 10 picks con stats. Fetch perezoso al expandir.
export function useGamePicks(gameId: number | null) {
  return useQuery({
    queryKey: ["picks", gameId],
    queryFn: () => getJSON<Pick[]>("/picks" + buildQuery({ game_id: gameId, limit: 10 })),
    enabled: gameId != null,
  });
}

export function useTournaments() {
  return useQuery({
    queryKey: ["tournaments"],
    queryFn: () => getJSON<string[]>("/tournaments"),
    ...CATALOG_OPTS,
  });
}

export function usePatches() {
  return useQuery({
    queryKey: ["patches"],
    queryFn: () => getJSON<string[]>("/patches"),
    ...CATALOG_OPTS,
  });
}

export type MatchupFilters = {
  champ_id?: number;
  champ_id2?: number;
  role?: string;
  tournament?: string;
  patch?: string;
  pick_relation?: "blind" | "counter";
  game_type?: string;
  limit?: number;
};

export function useMatchups(filters: MatchupFilters, enabled = true) {
  return useQuery({
    queryKey: ["matchups", filters],
    queryFn: () => getJSON<Matchup[]>("/matchups" + buildQuery(filters as QueryParams)),
    enabled,
  });
}

// Filtros para las vistas de stats de draft (sin champ_id ni limit).
export type StatsFilters = {
  team_id?: number;
  rival_id?: number;
  game_type?: string;
  game_types?: string; // CSV multi-fuente: "OFFICIAL,SCRIM"
  pick_phase?: "first" | "second";
  patch?: string;
  tournament?: string;
};

export function useChampionPresence(filters: StatsFilters, enabled = true) {
  return useQuery({
    queryKey: ["champion-presence", filters],
    queryFn: () =>
      getJSON<ChampionPresenceRow[]>(
        "/draft-stats/champion-presence" + buildQuery(filters as QueryParams),
      ),
    enabled,
  });
}

export function usePickOrderStats(filters: StatsFilters, enabled = true) {
  return useQuery({
    queryKey: ["pick-order-stats", filters],
    queryFn: () =>
      getJSON<PickOrderData>(
        "/draft-stats/pick-order" + buildQuery(filters as QueryParams),
      ),
    enabled,
  });
}

export function useRolePicks(
  type: "blind" | "counter",
  filters: StatsFilters,
  enabled = true,
) {
  return useQuery({
    queryKey: ["role-picks", type, filters],
    queryFn: () =>
      getJSON<RolePickData>(
        "/draft-stats/role-picks" + buildQuery({ ...filters, type } as QueryParams),
      ),
    enabled,
  });
}

export function useRolePickMatchups(
  champId: number | null,
  role: string | null,
  type: "blind" | "counter",
  filters: StatsFilters,
) {
  return useQuery({
    queryKey: ["role-pick-matchups", champId, role, type, filters],
    queryFn: () =>
      getJSON<MatchupEntry[]>(
        "/draft-stats/role-pick-matchups" +
          buildQuery({ ...filters, type, champ_id: champId, role } as QueryParams),
      ),
    enabled: champId != null && role != null,
  });
}

export function useTeamMatchups(filters: StatsFilters, enabled = true) {
  return useQuery({
    queryKey: ["team-matchups", filters],
    queryFn: () =>
      getJSON<TeamMatchupData>(
        "/draft-stats/team-matchups" + buildQuery(filters as QueryParams),
      ),
    enabled,
  });
}

// "vs otros equipos" de UN matchup, on-demand (al inspeccionar el matchup). Se
// calcula por par para no penalizar la carga (ver comentario en el endpoint).
export type LaneMatchupOthers = { games: number; wins: number; win_rate: number | null };

// Solo los filtros de contexto (Pick<> chocaría con el tipo Pick de LoL importado).
export type LaneMatchupCtx = { game_types?: string; patch?: string; tournament?: string };

export function useLaneMatchupOthers(
  args: { team_id?: number; role: string; our: number; opp: number },
  filters: LaneMatchupCtx,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["lane-matchup", args, filters],
    queryFn: () =>
      getJSON<LaneMatchupOthers>(
        "/draft-stats/lane-matchup" +
          buildQuery({ ...args, ...filters } as QueryParams),
      ),
    enabled: enabled && args.team_id != null,
    staleTime: 5 * 60_000, // el sample ajeno cambia poco; cachear 5 min
  });
}

export function useScouting(
  teamId: number | null,
  opts: { dateFrom?: string; patch?: string } = {},
) {
  const { dateFrom, patch } = opts;
  return useQuery({
    queryKey: ["scouting", teamId, dateFrom, patch],
    queryFn: () =>
      getJSON<ScoutingPool>(
        "/scouting/champion-pool" +
          buildQuery({ team_id: teamId, date_from: dateFrom, patch }),
      ),
    enabled: teamId != null,
  });
}

export type ScrimGamesFilters = {
  team_id: number | null;
  date_from?: string;
  patch?: string;
};

export function useScrimGames(filters: ScrimGamesFilters, enabled = true) {
  return useQuery({
    queryKey: ["scrim-games", filters],
    queryFn: () =>
      getJSON<ScrimGame[]>("/scrims/games" + buildQuery(filters as QueryParams)),
    enabled: enabled && filters.team_id != null,
  });
}
