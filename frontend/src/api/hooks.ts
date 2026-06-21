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

export function useScouting(teamId: number | null, dateFrom?: string) {
  return useQuery({
    queryKey: ["scouting", teamId, dateFrom],
    queryFn: () =>
      getJSON<ScoutingPool>(
        "/scouting/champion-pool" + buildQuery({ team_id: teamId, date_from: dateFrom }),
      ),
    enabled: teamId != null,
  });
}
