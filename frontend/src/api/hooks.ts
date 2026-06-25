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
  PlayerShare,
  RolePickData,
  ScoutingPool,
  ScrimGame,
  Team,
  TeamMatchupData,
} from "./types";

// The catalog changes rarely: cache it aggressively.
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

// Game detail: the 10 picks with stats. Lazy fetch on expand.
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
  champ_id_b?: number; // 2v2: second ally
  champ_id2_b?: number; // 2v2: second rival
  role?: string;
  role_b?: string; // 2v2: Ally 2's role
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

// Filters for the draft-stats views (no champ_id or limit).
export type StatsFilters = {
  team_id?: number;
  rival_id?: number;
  game_type?: string;
  game_types?: string; // multi-source CSV: "OFFICIAL,SCRIM"
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

// "vs other teams" for ONE matchup, on-demand (on matchup inspect). Computed per
// pair so it does not penalize page load (see the endpoint comment).
export type LaneMatchupOthers = { games: number; wins: number; win_rate: number | null };

// Context filters only (Pick<> would clash with the imported LoL Pick type).
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
    staleTime: 5 * 60_000, // the others' sample changes little; cache 5 min
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

export function usePlayerShares(
  teamId: number | null,
  opts: { gameTypes?: string; patch?: string; dateFrom?: string } = {},
) {
  const { gameTypes, patch, dateFrom } = opts;
  return useQuery({
    queryKey: ["player-shares", teamId, gameTypes, patch, dateFrom],
    queryFn: () =>
      getJSON<PlayerShare[]>(
        "/scouting/player-shares" +
          buildQuery({ team_id: teamId, game_types: gameTypes, patch, date_from: dateFrom }),
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
