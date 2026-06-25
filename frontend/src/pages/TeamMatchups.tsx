import { useState } from "react";
import { AlertTriangle } from "lucide-react";

import {
  useTeamMatchups,
  useLaneMatchupOthers,
  type StatsFilters,
  type LaneMatchupCtx,
} from "../api/hooks";
import type { BaselineEntry, TeamMatchupEntry } from "../api/types";
import { ChampIcon } from "../components/icons";
import "./team-matchups.css";

// Context filters that "vs other teams" inherits from the view.
type CtxFilters = LaneMatchupCtx;

const ROLES = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"] as const;
const ROLE_LABEL: Record<string, string> = {
  TOP: "TOP",
  JUNGLE: "JGL",
  MID: "MID",
  ADC: "ADC",
  SUPPORT: "SUP",
};

// Minimum games to trust a WR (consistent with the scouting pool).
const WR_MIN_GAMES = 3;
const COL_LIMIT = 10;

function wrClass(wr: number | null, games: number): string {
  if (wr == null || games < WR_MIN_GAMES) return "tm-wr-neutral";
  if (wr >= 55) return "tm-wr-pos";
  if (wr <= 45) return "tm-wr-neg";
  return "tm-wr-neutral";
}

// Directional non-color glyph (color blindness) — consistent with the rest of the front.
function wrArrow(wr: number | null, games: number): string {
  if (wr == null || games < WR_MIN_GAMES) return "";
  if (wr >= 55) return "▲";
  if (wr <= 45) return "▼";
  return "";
}

function WrValue({ wr, games }: { wr: number | null; games: number }) {
  if (wr == null) return <>—</>;
  const arrow = wrArrow(wr, games);
  return (
    <>
      {arrow && <span className="tm-wr-arrow" aria-hidden="true">{arrow}</span>}
      {wr.toFixed(0)}%
    </>
  );
}

// Two references for each matchup:
//  1. This matchup (our team).
//  2. "Rest": our champion in that role vs ALL OTHER opponents — baseline (role,
//     champion) minus the matchup row. Role-specific, excludes the duel itself.
// The delta is only computed if both sides reach WR_MIN_GAMES.
function computeRefs(entry: TeamMatchupEntry, roleBase: BaselineEntry | undefined) {
  // other opponents (baseline − this matchup)
  const restGames = roleBase ? roleBase.games - entry.games : 0;
  const restWins = roleBase ? roleBase.wins - entry.wins : 0;
  const restWr = restGames > 0 ? Math.round((100 * restWins) / restGames * 10) / 10 : null;

  const deltaRest =
    entry.win_rate != null && restWr != null &&
    entry.games >= WR_MIN_GAMES && restGames >= WR_MIN_GAMES
      ? Math.round((entry.win_rate - restWr) * 10) / 10
      : null;

  return { restGames, restWr, deltaRest };
}

// Formats a lane diff (gold as integer, CS with 1 decimal) with sign.
function fmtLane(v: number | null, decimals = 0): string {
  if (v == null) return "—";
  const body = decimals ? v.toFixed(decimals) : Math.round(v).toString();
  return (v > 0 ? "+" : "") + body;
}

// Color class for any diff (positive = in our favor).
function diffClass(v: number | null): string {
  if (v == null) return "tm-wr-neutral";
  if (v > 0) return "tm-wr-pos";
  if (v < 0) return "tm-wr-neg";
  return "tm-wr-neutral";
}

// WR delta line with a directional non-color glyph.
function DeltaTag({ d }: { d: number | null }) {
  if (d == null) return <span className="tm-wr-neutral tm-pop-d">—</span>;
  return (
    <span className={"tm-pop-d " + diffClass(d)}>
      {d > 0 && <span aria-hidden="true">▲</span>}
      {d < 0 && <span aria-hidden="true">▼</span>}
      {d > 0 ? "+" : ""}{d}%
    </span>
  );
}

function MatchupEntryRow({
  entry,
  roleBase,
  role,
  roleLabel,
  teamId,
  ctx,
}: {
  entry: TeamMatchupEntry;
  roleBase: BaselineEntry | undefined;
  role: string;
  roleLabel: string;
  teamId?: number;
  ctx: CtxFilters;
}) {
  const { restGames, restWr, deltaRest } = computeRefs(entry, roleBase);
  const ourName = entry.our_champ_name ?? `#${entry.our_champ_id}`;
  const oppName = entry.opp_champ_name ?? `#${entry.opp_champ_id}`;
  const hasLane = entry.diff_games_7 > 0 || entry.diff_games_14 > 0;

  // "vs other teams": on-demand. Activated when inspecting the row (hover/focus)
  // to avoid firing 840 fetches on page load. React Query caches per pair.
  const [active, setActive] = useState(false);
  const others = useLaneMatchupOthers(
    { team_id: teamId, role, our: entry.our_champ_id, opp: entry.opp_champ_id },
    ctx,
    active,
  );
  const othersData = others.data;
  const deltaOthers =
    entry.win_rate != null && othersData?.win_rate != null &&
    entry.games >= WR_MIN_GAMES && othersData.games >= WR_MIN_GAMES
      ? Math.round((entry.win_rate - othersData.win_rate) * 10) / 10
      : null;

  const ariaLabel =
    `${ourName} vs ${oppName}: ${entry.games} games` +
    (entry.win_rate != null ? `, ${entry.win_rate.toFixed(0)}% WR` : "") +
    (deltaRest != null
      ? `. Difference for ${ourName} in ${roleLabel} against the rest of opponents: ${deltaRest > 0 ? "+" : ""}${deltaRest}%`
      : "");

  return (
    <li
      className="tm-entry"
      tabIndex={0}
      aria-label={ariaLabel}
      onMouseEnter={() => setActive(true)}
      onFocus={() => setActive(true)}
    >
      <div className="tm-entry-main">
        <div className="tm-side tm-our">
          <ChampIcon id={entry.our_champ_id} name={entry.our_champ_name ?? ""} size={20} />
          <span className="tm-champ-name">{ourName}</span>
        </div>
        <div className="tm-side tm-opp">
          <span className="tm-vs">vs</span>
          <ChampIcon id={entry.opp_champ_id} name={entry.opp_champ_name ?? ""} size={18} />
          <span className="tm-champ-name tm-opp-name">{oppName}</span>
          <span className="tm-meta">
            <span className="tm-games">{entry.games}g</span>
            <span className={"tm-wr " + wrClass(entry.win_rate, entry.games)}>
              <WrValue wr={entry.win_rate} games={entry.games} />
            </span>
          </span>
        </div>
      </div>

      {/* Popover — visible on hover/focus. Text already covered by aria-label. */}
      <div className="tm-pop" role="presentation">
        <div className="tm-pop-refs">
          <div className="tm-pop-ref">
            <span className="tm-pop-label">This matchup</span>
            <span className="tm-pop-val">
              {entry.win_rate != null ? `${entry.win_rate.toFixed(0)}%` : "—"}
              <span className="tm-pop-g"> · {entry.games}g</span>
            </span>
            <span className="tm-pop-d tm-pop-d-anchor" aria-hidden="true" />
          </div>
          <div className="tm-pop-ref">
            <span className="tm-pop-label">Other teams</span>
            <span className="tm-pop-val">
              {others.isLoading || !active ? (
                <span className="tm-pop-g">…</span>
              ) : othersData && othersData.games > 0 ? (
                <>
                  {othersData.win_rate != null ? `${othersData.win_rate.toFixed(0)}%` : "—"}
                  <span className="tm-pop-g"> · {othersData.games}g</span>
                </>
              ) : (
                <span className="tm-pop-g">no sample</span>
              )}
            </span>
            <DeltaTag d={deltaOthers} />
          </div>
          <div className="tm-pop-ref">
            <span className="tm-pop-label">{ourName} in {roleLabel} · rest</span>
            <span className="tm-pop-val">
              {restWr != null ? `${restWr.toFixed(0)}%` : "—"}
              <span className="tm-pop-g"> · {restGames}g</span>
            </span>
            <DeltaTag d={deltaRest} />
          </div>
        </div>

        {hasLane && (
          <div className="tm-pop-lane">
            <div className="tm-lane-row tm-lane-head">
              <span className="tm-lane-stat">Lane Δ</span>
              <span className="tm-lane-col">@7</span>
              <span className="tm-lane-col">@14</span>
            </div>
            <div className="tm-lane-row">
              <span className="tm-lane-stat">CS</span>
              <span className={"tm-lane-col " + diffClass(entry.cs_diff_7)}>{fmtLane(entry.cs_diff_7, 1)}</span>
              <span className={"tm-lane-col " + diffClass(entry.cs_diff_14)}>{fmtLane(entry.cs_diff_14, 1)}</span>
            </div>
            <div className="tm-lane-row">
              <span className="tm-lane-stat">Gold</span>
              <span className={"tm-lane-col " + diffClass(entry.gold_diff_7)}>{fmtLane(entry.gold_diff_7)}</span>
              <span className={"tm-lane-col " + diffClass(entry.gold_diff_14)}>{fmtLane(entry.gold_diff_14)}</span>
            </div>
          </div>
        )}
      </div>
    </li>
  );
}

function Column({
  role,
  entries,
  roleBaseline,
  loading,
  teamId,
  ctx,
}: {
  role: string;
  entries: TeamMatchupEntry[];
  roleBaseline: Record<number, BaselineEntry>;
  loading: boolean;
  teamId?: number;
  ctx: CtxFilters;
}) {
  const roleLabel = ROLE_LABEL[role] ?? role;
  const [shown, setShown] = useState(COL_LIMIT);
  const visible = entries.slice(0, shown);
  const hasMore = entries.length > shown;

  return (
    <div className="tm-col">
      <div className="tm-col-head">{roleLabel}</div>
      {loading ? (
        <div className="tm-col-skel">
          {Array.from({ length: COL_LIMIT }).map((_, i) => (
            <div key={i} className="tm-skel-entry" />
          ))}
        </div>
      ) : entries.length === 0 ? (
        <p className="tm-col-empty">No data</p>
      ) : (
        <>
          <ul className="tm-col-list">
            {visible.map((e) => (
              <MatchupEntryRow
                key={`${e.our_champ_id}-${e.opp_champ_id}`}
                entry={e}
                roleBase={roleBaseline[e.our_champ_id]}
                role={role}
                roleLabel={roleLabel}
                teamId={teamId}
                ctx={ctx}
              />
            ))}
          </ul>
          {hasMore && (
            <button
              type="button"
              className="tm-show-more"
              onClick={() => setShown((n) => n + COL_LIMIT)}
            >
              +{Math.min(COL_LIMIT, entries.length - shown)} more
            </button>
          )}
        </>
      )}
    </div>
  );
}

export function TeamMatchups({ filters }: { filters: StatsFilters }) {
  const { data, isFetching, error } = useTeamMatchups(filters, true);

  // "vs other teams" inherits the view context (type, patch, tournament)
  // but NOT the team (it's exactly what it excludes). Passed to each row on-demand.
  const ctx: CtxFilters = {
    game_types: filters.game_types,
    patch: filters.patch,
    tournament: filters.tournament,
  };

  if (error) {
    return (
      <div className="tm-load-error">
        <AlertTriangle size={14} />
        <span>Could not load matchups.</span>
      </div>
    );
  }

  return (
    <div className="tm-grid">
      {ROLES.map((role) => (
        <Column
          key={role}
          role={role}
          entries={data?.matchups[role] ?? []}
          roleBaseline={data?.baseline?.[role] ?? {}}
          loading={isFetching}
          teamId={filters.team_id}
          ctx={ctx}
        />
      ))}
    </div>
  );
}
