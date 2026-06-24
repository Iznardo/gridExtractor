// Tipos espejo de las respuestas de la API (src/api/ de gridExtractor).
// Verificados contra los routers reales; los campos nullables reflejan la
// realidad de los datos (soloq no tiene equipos, GRID no tiene team_position...).

export type Side = "BLUE" | "RED";
export type GameResult = "BLUE" | "RED" | "NONE";
export type GameType = "OFFICIAL" | "SCRIM" | "SOLOQ";

export type ChampRef = { id: number; name: string | null };
export type TeamRef = { id: number; name: string; tag: string | null } | null;

// ---- catálogo ----
export type Champion = { id: number; name: string; alias: string };
export type Team = { id: number; name: string; tag: string | null };
export type Player = {
  id: number;
  name: string;
  role: string | null;
  team_id: number | null;
  starter: boolean;
};

// ---- /drafts ----
export type DraftSideGroup = {
  bans: (ChampRef | null)[];
  picks: (ChampRef | null)[];
};
export type Draft = {
  game_id: number;
  date: string;
  version: string | null;
  game_type: GameType;
  tournament: string | null;
  result: GameResult;
  team1: TeamRef; // BLUE
  team2: TeamRef; // RED
  first_pick_team: { id: number; name: string; tag: string | null; side: Side | null } | null;
  first_pick: DraftSideGroup;
  second_pick: DraftSideGroup;
};

// ---- /games ----
export type Game = {
  game_id: number;
  date: string;
  version: string | null;
  game_type: GameType;
  tournament: string | null;
  result: GameResult;
  team1: TeamRef; // BLUE
  team2: TeamRef; // RED
  blue_champions: ChampRef[];
  red_champions: ChampRef[];
  grid_series_id: number | null;
  game_number: number | null;
};

// ---- /picks ----
export type Runes = {
  primary_style: number;
  primary: number[];
  sub_style: number;
  sub: number[];
  stat_perks: number[];
};
export type BuildStep = { ts_s: number; action: "BUY" | "SELL"; item_id: number };
export type MidGameMark = {
  cs: number | null;
  gold: number | null;
  xp: number | null;
  game_time_s: number | null;
};
export type PickStats = {
  kills?: number;
  deaths?: number;
  assists?: number;
  gold?: number;
  cs?: number;
  damage_dealt?: number; // GRID
  kda_str?: string; // GRID
  champ_level?: number; // SoloQ
  vision_score?: number; // SoloQ
  team_position?: string; // SoloQ
  summoner_spells?: number[]; // SoloQ
  runes?: Runes | null;
  final_items?: number[] | null;
  skill_order?: string | null;
  build_path?: BuildStep[] | null;
  midgame?: Record<string, MidGameMark> | null; // keys "7" and "14"
};
export type Pick = {
  pick_id: number;
  game_id: number;
  date: string;
  version: string | null;
  game_type: GameType;
  tournament: string | null;
  side: Side;
  result: boolean;
  pick_order: number | null;
  game_duration_s: number | null;
  player: { id: number; name: string; role: string | null };
  champion: { id: number; name: string };
  stats: PickStats;
};

// ---- /matchups ----
export type PickRelation = "blind" | "counter" | null;

export type MatchupSide = {
  side: Side;
  result: boolean | null;
  pick_order: number | null;
  pick_relation: PickRelation;
  player: { id: number; name: string } | null; // null = rival untrackeado (soloq)
  champion: ChampRef;
  stats: PickStats | null; // null = rival untrackeado (soloq)
};

export type Matchup = {
  game_id: number;
  date: string;
  version: string | null;
  game_type: GameType;
  tournament: string | null;
  role: string | null;
  game_result: GameResult;
  team1: TeamRef;
  team2: TeamRef;
  pick: MatchupSide;
  opponent: MatchupSide | null;
};

// ---- /draft-stats/champion-presence ----
export type ChampionPresenceRow = {
  champ_id: number;
  champ_name: string | null;
  picks: number;
  picked_by: number;
  picked_vs: number;
  wins: number;
  wins_by: number;
  wins_vs: number;
  phase1: number;
  phase2: number;
  bans: number;
  banned_by: number;
  banned_vs: number;
  total_games: number;
  presence_pct: number;
  picked_pct: number;
  win_rate: number | null;
  // picks y wins por game number
  picks_g1: number; wins_g1: number; picks_g1_by: number; picks_g1_vs: number;
  picks_g2: number; wins_g2: number; picks_g2_by: number; picks_g2_vs: number;
  picks_g3: number; wins_g3: number; picks_g3_by: number; picks_g3_vs: number;
  picks_g4: number; wins_g4: number; picks_g4_by: number; picks_g4_vs: number;
  picks_g5: number; wins_g5: number; picks_g5_by: number; picks_g5_vs: number;
  // total de partidas en cada game number (igual en todas las filas)
  total_g1: number;
  total_g2: number;
  total_g3: number;
  total_g4: number;
  total_g5: number;
};

// ---- /draft-stats/role-picks  y  /draft-stats/role-pick-matchups ----
export type RolePickEntry = {
  champ_id: number;
  champ_name: string | null;
  games: number;
  wins: number;
  win_rate: number | null;
};

/** Keyed by role (TOP/JUNGLE/MID/ADC/SUPPORT). */
export type RolePickData = Partial<Record<string, RolePickEntry[]>>;

export type MatchupEntry = {
  champ_id: number;
  champ_name: string | null;
  games: number;
  wins: number;
  win_rate: number | null;
};

// ---- /draft-stats/pick-order ----
export type PickSlotEntry = {
  champ_id: number;
  champ_name: string | null;
  slot: string;
  games: number;
  wins: number;
  win_rate: number | null;
  total_games: number;
};

export type RoleDistEntry = {
  role: string;
  slot: string;
  pick_side: "blue" | "red";
  cnt: number;
  wins: number;
  pct: number;
  win_rate: number | null;
};

export type PickOrderData = {
  slots: PickSlotEntry[];
  role_dist: RoleDistEntry[];
};

// ---- /draft-stats/team-matchups ----
export type TeamMatchupEntry = {
  our_champ_id: number;
  our_champ_name: string | null;
  opp_champ_id: number;
  opp_champ_name: string | null;
  games: number;
  wins: number;
  win_rate: number | null;
  // diferencias de carril (media nuestro − rival) desde midgame; null sin muestra
  cs_diff_7: number | null;
  gold_diff_7: number | null;
  cs_diff_14: number | null;
  gold_diff_14: number | null;
  diff_games_7: number;
  diff_games_14: number;
};
export type BaselineEntry = { games: number; wins: number; win_rate: number | null };
export type TeamMatchupData = {
  /** Keyed by role (TOP/JUNGLE/MID/ADC/SUPPORT). */
  matchups: Partial<Record<string, TeamMatchupEntry[]>>;
  /** role → champ_id → WR del equipo con ese campeón EN ESE ROL (todos los
   *  rivales). El front resta la fila del matchup para excluirlo del delta. */
  baseline: Partial<Record<string, Record<number, BaselineEntry>>>;
};

// ---- /scouting/champion-pool ----
export type ScoutChampion = {
  champion: { id: number; name: string };
  games: number;
  wins: number;
};
export type ScoutPlayer = {
  player: { id: number; name: string; role: string | null };
  champions: ScoutChampion[];
};
export type Medium = "official" | "scrim" | "soloq";
export type ScoutingPool = {
  team_id: number;
  by_medium: Record<Medium, ScoutPlayer[]>;
};

// ---- /scrims/games ----
export type ScrimRole = "TOP" | "JUNGLE" | "MID" | "ADC" | "SUPPORT";
/** Una fila por scrim del equipo trackeado. El front agrega (duos/trios/etc.). */
export type ScrimGame = {
  game_id: number;
  date: string;
  version: string | null;
  our_side: Side;
  won: boolean;
  first_pick: boolean;
  block_game_number: number; // posición dentro del bloque vs ese rival
  rival: { id: number; name: string; tag: string | null } | null;
  lineup: Record<ScrimRole, number | null>; // champ_id por rol (lado propio)
  rival_champs: number[]; // picks rivales, lista plana (sin rol)
};
