import { useQuery } from "@tanstack/react-query";

import { buildQuery, getJSON, type QueryParams } from "./client";
import type {
  Champion,
  Draft,
  Game,
  Pick,
  ScoutingPool,
  Team,
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
