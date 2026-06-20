import { useMemo, useState } from "react";
import { AlertTriangle, SearchX } from "lucide-react";

import { useChampionPresence, type StatsFilters } from "../api/hooks";
import type { ChampionPresenceRow } from "../api/types";
import { ChampIcon } from "../components/icons";
import { RolePickSection } from "./RolePickSection";
import "./champion-presence.css";

const SKELETON_COUNT = 15;

type SortCol =
  | "presence_pct"
  | "picks"
  | "picked_by"
  | "picked_vs"
  | "wins"
  | "win_rate"
  | "bans"
  | "phase1"
  | "phase2";

type SortDir = "desc" | "asc";

// Clase de heatmap en 5 escalones relativos al máximo del dataset.
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

// Glifo no-cromático para el WR: la dirección (▲/▼) codifica bueno/malo sin
// depender solo del verde/rojo (daltonismo — PRODUCT.md, DESIGN.md).
function wrArrow(wr: number | null): string {
  if (wr == null) return "";
  if (wr >= 55) return "▲";
  if (wr <= 45) return "▼";
  return "";
}

// Un 0 real (pickeado 0 veces, 0 wins…) se muestra como 0 atenuado, nunca como
// «—»: el guion se reserva para la ausencia genuina de dato (PRODUCT.md:
// «nunca presentar un hueco como un cero» — y a la inversa).
function numCell(v: number) {
  return v === 0 ? <span className="cp-zero">0</span> : v;
}

function gnPct(picks: number, total: number): string {
  if (total === 0) return "—"; // sin partidas en esta posición = ausencia real
  return `${((picks / total) * 100).toFixed(0)}%`; // picks=0 → «0%», dato real
}

function gnTooltip(picks: number, wins: number, total: number, n: number): string {
  if (total === 0) return `G${n}: sin partidas en esta posición de serie`;
  if (picks === 0) return `G${n}: no pickeado (de ${total} partidas)`;
  const losses = picks - wins;
  return `G${n}: ${picks}g · ${wins}W / ${losses}L (de ${total} partidas)`;
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

  // Columnas de game number activas (las que tienen al menos 1 partida en ese game).
  const gnCols = useMemo(() => {
    const first = data?.[0];
    if (!first) return [1, 2, 3]; // fallback razonable mientras carga
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

  function ColHead({
    col,
    label,
    title,
  }: {
    col: SortCol;
    label: string;
    title?: string;
  }) {
    const active = sort.col === col;
    return (
      <th
        className={active ? "cp-sorted" : undefined}
        onClick={() => toggleSort(col)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleSort(col); } }}
        tabIndex={0}
        aria-sort={active ? (sort.dir === "desc" ? "descending" : "ascending") : "none"}
        title={title}
      >
        {label}
        <span className="cp-sort-arrow" aria-hidden="true">
          {active ? (sort.dir === "desc" ? "▼" : "▲") : "⇅"}
        </span>
      </th>
    );
  }

  // Cabecera estática no sortable (game number).
  function GnHead({ n }: { n: number }) {
    return (
      <th className="cp-gn-head">
        G{n}%
        <span className="cp-gn-hint" aria-hidden="true"> (G{n})</span>
        <span className="sr-only">Porcentaje de veces que se pickeó en el game {n} de la serie</span>
      </th>
    );
  }

  // Columnas fijas + dinámica (By/Vs o Picked) + game number cols.
  const fixedCols = hasTeam ? 10 : 9;
  const colCount = fixedCols + gnCols.length;

  if (error) {
    return (
      <div className="empty">
        <AlertTriangle size={22} className="empty-icon" style={{ color: "var(--red)" }} />
        <p className="empty-title">No se pudieron cargar los datos de presencia.</p>
        <p className="empty-sub">{(error as Error).message}</p>
        <button type="button" className="btn-ghost" onClick={() => refetch()}>
          Reintentar
        </button>
      </div>
    );
  }

  if (!isFetching && data && data.length === 0) {
    return (
      <div className="empty">
        <SearchX size={22} className="empty-icon" />
        <p className="empty-title">Sin datos para estos filtros.</p>
        <p className="empty-sub">
          No hay drafts que coincidan con la selección actual.
        </p>
      </div>
    );
  }

  const totalGames = data?.[0]?.total_games ?? 0;

  return (
    <>
      <p className="status" role="status" aria-live="polite" style={{ padding: "0.5rem 1.2rem" }}>
        {isFetching
          ? "Cargando…"
          : data
          ? `${data.length} campeones · ${totalGames} partidas`
          : ""}
      </p>
      <div className="cp-legend" aria-label="Leyenda">
        <span className="cp-legend-heat">Presence: <span className="cp-heat-1">·</span><span className="cp-heat-2">·</span><span className="cp-heat-3">·</span><span className="cp-heat-4">·</span><span className="cp-heat-5">·</span> relativo al máximo</span>
        <span className="cp-legend-sep" aria-hidden="true">·</span>
        <span className="cp-legend-wr"><span className="cp-wr-pos">▲ ≥55%</span> <span className="cp-wr-neg">▼ ≤45%</span> WR</span>
        <span className="cp-legend-sep" aria-hidden="true">·</span>
        <span className="cp-legend-phase">1ª Fase: B1-B3, R1-R2 · 2ª Fase: B4-B5, R3-R5</span>
        <span className="cp-legend-sep" aria-hidden="true">·</span>
        <span className="cp-legend-zero">0 atenuado = dato real · — = sin dato</span>
      </div>
      <div className="cp-wrap">
        <table className="cp-table">
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}>Campeón</th>
              <ColHead col="presence_pct" label="Presence%" title="(picks + bans) / total" />
              {hasTeam ? (
                <>
                  <ColHead col="picked_by" label="By" title="Pickeado por el equipo" />
                  <ColHead col="picked_vs" label="Vs" title="Pickeado por el rival" />
                </>
              ) : (
                <ColHead col="picks" label="Picked" />
              )}
              <ColHead col="wins" label="Wins" />
              <ColHead col="win_rate" label="WR%" />
              <ColHead col="bans" label="Banned" />
              <ColHead col="phase1" label="1ª Fase" title="Picks en la 1ª fase (B1-B3, R1-R2)" />
              <ColHead col="phase2" label="2ª Fase" title="Picks en la 2ª fase (B4-B5, R3-R5)" />
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
                  <td className={wrClass(row.win_rate)}>
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
                  </td>
                  <td>{numCell(row.bans)}</td>
                  <td>{numCell(row.phase1)}</td>
                  <td>{numCell(row.phase2)}</td>
                  {gnCols.map((n) => {
                    const picks = row[`picks_g${n}` as keyof ChampionPresenceRow] as number;
                    const wins  = row[`wins_g${n}`  as keyof ChampionPresenceRow] as number;
                    const total = row[`total_g${n}` as keyof ChampionPresenceRow] as number;
                    return (
                      <td
                        key={n}
                        className="cp-gn-cell"
                        title={gnTooltip(picks, wins, total, n)}
                      >
                        {gnPct(picks, total)}
                      </td>
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
            Mostrar {sorted.length - TABLE_INITIAL_LIMIT} campeones más
          </button>
        )}
      </div>

      <RolePickSection type="blind"   filters={filters} initialLimit={10} />
      <RolePickSection type="counter" filters={filters} initialLimit={5} />
    </>
  );
}
