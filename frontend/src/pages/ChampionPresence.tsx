import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { AlertTriangle, SearchX } from "lucide-react";

import { useChampionPresence, type StatsFilters } from "../api/hooks";
import type { ChampionPresenceRow } from "../api/types";
import { ChampIcon } from "../components/icons";
import { useTooltip } from "../components/Tooltip";
import { RolePickSection } from "./RolePickSection";
import "./champion-presence.css";

const SKELETON_COUNT = 15;

// <td> cell with a custom tooltip (replaces the native `title`). At module level
// so the component is not recreated on every render (react-hooks rule).
function TipTd({
  content,
  className,
  children,
}: {
  content: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  const { anchorProps, tip } = useTooltip(content);
  return (
    <td className={className} {...anchorProps}>
      {children}
      {tip}
    </td>
  );
}

type SortCol =
  | "presence_pct"
  | "picks"
  | "picked_by"
  | "picked_vs"
  | "wins"
  | "win_rate"
  | "bans"
  | "banned_by"
  | "banned_vs"
  | "phase1"
  | "phase2";

type SortDir = "desc" | "asc";

// Heatmap class in 5 steps relative to the dataset's max.
function heatClass(value: number, max: number): string {
  if (max === 0 || value === 0) return "";
  const ratio = value / max;
  if (ratio > 0.8) return "cp-heat-5";
  if (ratio > 0.6) return "cp-heat-4";
  if (ratio > 0.4) return "cp-heat-3";
  if (ratio > 0.2) return "cp-heat-2";
  return "cp-heat-1";
}

function wrClass(wr: number | null): string {
  if (wr == null) return "cp-wr-neutral";
  if (wr >= 55) return "cp-wr-pos";
  if (wr <= 45) return "cp-wr-neg";
  return "cp-wr-neutral";
}

// Non-color glyph for WR: the direction (▲/▼) encodes good/bad without relying
// on green/red alone (color blindness).
function wrArrow(wr: number | null): string {
  if (wr == null) return "";
  if (wr >= 55) return "▲";
  if (wr <= 45) return "▼";
  return "";
}

// A real 0 (picked 0 times, 0 wins…) shows as a dimmed 0, never as «—»: the dash
// is reserved for a genuine absence of data (never present a gap as a zero — and
// vice versa).
function numCell(v: number) {
  return v === 0 ? <span className="cp-zero">0</span> : v;
}

function gnPct(picks: number, total: number): string {
  if (total === 0) return "—"; // no games in this position = real absence
  return `${((picks / total) * 100).toFixed(0)}%`; // picks=0 -> «0%», real datum
}

function gnTooltip(
  picks: number, wins: number, total: number, n: number,
  by?: number, vs?: number,
): string {
  if (total === 0) return `G${n}: no games in this series position`;
  if (picks === 0) return `G${n}: not picked (of ${total} games)`;
  const losses = picks - wins;
  const base = `G${n}: ${picks}g · ${wins}W / ${losses}L (of ${total} games)`;
  if (by == null || vs == null) return base;
  return `${base}\nBy: ${by}g · Vs: ${vs}g`;
}

function wrTooltip(
  winRate: number | null,
  pickedBy: number, winsBy: number,
  pickedVs: number, winsVs: number,
): string {
  if (winRate == null) return "";
  const wrBy = pickedBy > 0 ? `${((winsBy / pickedBy) * 100).toFixed(1)}%` : "—";
  const wrVs = pickedVs > 0 ? `${((winsVs / pickedVs) * 100).toFixed(1)}%` : "—";
  return `WR by: ${wrBy} (${winsBy}W / ${pickedBy - winsBy}L)\nWR vs: ${wrVs} (${winsVs}W / ${pickedVs - winsVs}L)`;
}

function Skeleton({ cols }: { cols: number }) {
  return (
    <>
      {Array.from({ length: SKELETON_COUNT }).map((_, i) => (
        <tr key={i} className="cp-skel-row" aria-hidden="true">
          {Array.from({ length: cols }).map((__, j) => (
            <td key={j}>
              <div className="cp-skel-bar" style={{ width: j === 0 ? 120 : 40 }} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

const TABLE_INITIAL_LIMIT = 50;

// Sortable column header. At module level (not inside the component) so it is
// not recreated on every render; the sort state arrives by props.
function ColHead({
  col,
  label,
  title,
  sort,
  toggleSort,
}: {
  col: SortCol;
  label: string;
  title?: string;
  sort: { col: SortCol; dir: SortDir };
  toggleSort: (col: SortCol) => void;
}) {
  const active = sort.col === col;
  const { anchorProps, tip } = useTooltip(title);
  return (
    <th
      className={active ? "cp-sorted" : undefined}
      onClick={() => toggleSort(col)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleSort(col); } }}
      tabIndex={0}
      aria-sort={active ? (sort.dir === "desc" ? "descending" : "ascending") : "none"}
      {...anchorProps}
    >
      {label}
      <span className="cp-sort-arrow" aria-hidden="true">
        {active ? (sort.dir === "desc" ? "▼" : "▲") : "⇅"}
      </span>
      {tip}
    </th>
  );
}

// Static non-sortable header (game number).
function GnHead({ n }: { n: number }) {
  return (
    <th className="cp-gn-head">
      G{n}%
      <span className="cp-gn-hint" aria-hidden="true"> (G{n})</span>
      <span className="sr-only">Percentage of times picked in game {n} of the series</span>
    </th>
  );
}

export function ChampionPresence({
  filters,
  teamId,
}: {
  filters: StatsFilters;
  teamId?: number;
}) {
  const { data, isFetching, error, refetch } = useChampionPresence(filters, true);

  const [sort, setSort] = useState<{ col: SortCol; dir: SortDir }>({
    col: "presence_pct",
    dir: "desc",
  });
  const [showAllRows, setShowAllRows] = useState(false);

  const hasTeam = teamId != null;

  const sorted = useMemo<ChampionPresenceRow[]>(() => {
    if (!data) return [];
    return [...data].sort((a, b) => {
      const av = a[sort.col] ?? -1;
      const bv = b[sort.col] ?? -1;
      return sort.dir === "desc" ? (bv as number) - (av as number) : (av as number) - (bv as number);
    });
  }, [data, sort.col, sort.dir]);

  const visibleRows = showAllRows ? sorted : sorted.slice(0, TABLE_INITIAL_LIMIT);

  const maxPresence = useMemo(
    () => Math.max(0, ...(data ?? []).map((r) => r.presence_pct)),
    [data],
  );

  // Active game-number columns (those with at least 1 game in that slot).
  const gnCols = useMemo(() => {
    const first = data?.[0];
    if (!first) return [1, 2, 3]; // reasonable fallback while loading
    return ([1, 2, 3, 4, 5] as const).filter(
      (n) => (first[`total_g${n}` as keyof ChampionPresenceRow] as number) > 0,
    );
  }, [data]);

  function toggleSort(col: SortCol) {
    setSort((prev) =>
      prev.col === col
        ? { col, dir: prev.dir === "desc" ? "asc" : "desc" }
        : { col, dir: "desc" },
    );
  }

  // Fixed + dynamic columns (By/Vs picks and bans with team) + game-number cols.
  const fixedCols = hasTeam ? 11 : 9;
  const colCount = fixedCols + gnCols.length;

  if (error) {
    return (
      <div className="empty">
        <AlertTriangle size={22} className="empty-icon" style={{ color: "var(--red)" }} />
        <p className="empty-title">Could not load presence data.</p>
        <p className="empty-sub">{(error as Error).message}</p>
        <button type="button" className="btn-ghost" onClick={() => refetch()}>
          Retry
        </button>
      </div>
    );
  }

  if (!isFetching && data && data.length === 0) {
    return (
      <div className="empty">
        <SearchX size={22} className="empty-icon" />
        <p className="empty-title">No data for these filters.</p>
        <p className="empty-sub">
          No drafts match the current selection.
        </p>
      </div>
    );
  }

  const totalGames = data?.[0]?.total_games ?? 0;

  return (
    <>
      <p className="status" role="status" aria-live="polite" style={{ padding: "0.5rem 1.2rem" }}>
        {isFetching
          ? "Loading…"
          : data
          ? `${data.length} champions · ${totalGames} games`
          : ""}
      </p>
      <div className="cp-legend" aria-label="Legend">
        <span className="cp-legend-heat">Presence: <span className="cp-heat-1">·</span><span className="cp-heat-2">·</span><span className="cp-heat-3">·</span><span className="cp-heat-4">·</span><span className="cp-heat-5">·</span> relative to max</span>
        <span className="cp-legend-sep" aria-hidden="true">·</span>
        <span className="cp-legend-wr"><span className="cp-wr-pos">▲ ≥55%</span> <span className="cp-wr-neg">▼ ≤45%</span> WR</span>
        <span className="cp-legend-sep" aria-hidden="true">·</span>
        <span className="cp-legend-phase">Phase 1: B1-B3, R1-R3 · Phase 2: B4-B5, R4-R5</span>
        <span className="cp-legend-sep" aria-hidden="true">·</span>
        <span className="cp-legend-zero">dimmed 0 = real datum · — = no data</span>
      </div>
      <div className="cp-wrap">
        <table className="cp-table">
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}>Champion</th>
              <ColHead col="presence_pct" label="Presence%" title="(picks + bans) / total" sort={sort} toggleSort={toggleSort} />
              {hasTeam ? (
                <>
                  <ColHead col="picked_by" label="By" title="Picked by the team" sort={sort} toggleSort={toggleSort} />
                  <ColHead col="picked_vs" label="Vs" title="Picked by the rival" sort={sort} toggleSort={toggleSort} />
                </>
              ) : (
                <ColHead col="picks" label="Picked" sort={sort} toggleSort={toggleSort} />
              )}
              <ColHead col="wins" label="Wins" sort={sort} toggleSort={toggleSort} />
              <ColHead col="win_rate" label="WR%" sort={sort} toggleSort={toggleSort} />
              {hasTeam ? (
                <>
                  <ColHead col="banned_by" label="Ban By" title="Banned by the team" sort={sort} toggleSort={toggleSort} />
                  <ColHead col="banned_vs" label="Ban Vs" title="Banned by the rival (against the team)" sort={sort} toggleSort={toggleSort} />
                </>
              ) : (
                <ColHead col="bans" label="Banned" sort={sort} toggleSort={toggleSort} />
              )}
              <ColHead col="phase1" label="Phase 1" title="Picks in phase 1 (B1-B3, R1-R3)" sort={sort} toggleSort={toggleSort} />
              <ColHead col="phase2" label="Phase 2" title="Picks in phase 2 (B4-B5, R4-R5)" sort={sort} toggleSort={toggleSort} />
              {gnCols.map((n) => <GnHead key={n} n={n} />)}
            </tr>
          </thead>
          <tbody>
            {isFetching ? (
              <Skeleton cols={colCount} />
            ) : (
              visibleRows.map((row) => (
                <tr key={row.champ_id}>
                  <td>
                    <div className="cp-champ-cell">
                      <ChampIcon id={row.champ_id} name={row.champ_name ?? ""} size={22} />
                      <span className="cp-champ-name">{row.champ_name ?? `#${row.champ_id}`}</span>
                    </div>
                  </td>
                  <td className={heatClass(row.presence_pct, maxPresence)}>
                    {row.presence_pct.toFixed(1)}%
                  </td>
                  {hasTeam ? (
                    <>
                      <td>{numCell(row.picked_by)}</td>
                      <td>{numCell(row.picked_vs)}</td>
                    </>
                  ) : (
                    <td>{numCell(row.picks)}</td>
                  )}
                  <td>{numCell(row.wins)}</td>
                  <TipTd
                    className={wrClass(row.win_rate)}
                    content={hasTeam ? wrTooltip(row.win_rate, row.picked_by, row.wins_by, row.picked_vs, row.wins_vs) : null}
                  >
                    {row.win_rate != null ? (
                      <>
                        {wrArrow(row.win_rate) && (
                          <span className="cp-wr-arrow" aria-hidden="true">
                            {wrArrow(row.win_rate)}
                          </span>
                        )}
                        {row.win_rate.toFixed(1)}%
                      </>
                    ) : (
                      "—"
                    )}
                  </TipTd>
                  {hasTeam ? (
                    <>
                      <td>{numCell(row.banned_by)}</td>
                      <td>{numCell(row.banned_vs)}</td>
                    </>
                  ) : (
                    <td>{numCell(row.bans)}</td>
                  )}
                  <td>{numCell(row.phase1)}</td>
                  <td>{numCell(row.phase2)}</td>
                  {gnCols.map((n) => {
                    const picks = row[`picks_g${n}` as keyof ChampionPresenceRow] as number;
                    const wins  = row[`wins_g${n}`  as keyof ChampionPresenceRow] as number;
                    const total = row[`total_g${n}` as keyof ChampionPresenceRow] as number;
                    const by    = hasTeam ? row[`picks_g${n}_by` as keyof ChampionPresenceRow] as number : undefined;
                    const vs    = hasTeam ? row[`picks_g${n}_vs` as keyof ChampionPresenceRow] as number : undefined;
                    return (
                      <TipTd
                        key={n}
                        className="cp-gn-cell"
                        content={gnTooltip(picks, wins, total, n, by, vs)}
                      >
                        {gnPct(picks, total)}
                      </TipTd>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>

        {!isFetching && !showAllRows && sorted.length > TABLE_INITIAL_LIMIT && (
          <button
            type="button"
            className="cp-show-more"
            onClick={() => setShowAllRows(true)}
          >
            Show {sorted.length - TABLE_INITIAL_LIMIT} more champions
          </button>
        )}
      </div>

      <RolePickSection type="blind"   filters={filters} initialLimit={10} />
      <RolePickSection type="counter" filters={filters} initialLimit={5} />
    </>
  );
}
