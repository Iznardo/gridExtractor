import { Fragment, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getExpandedRowModel,
  useReactTable,
  type ExpandedState,
} from "@tanstack/react-table";
import { ChevronDown, ChevronRight } from "lucide-react";

import { useGames, useTeams, type GameFilters } from "../api/hooks";
import type { ChampRef, Game } from "../api/types";
import { ChampionPicker } from "../components/ChampionPicker";
import { Field, FilterBar } from "../components/Field";
import { ChampIcon } from "../components/icons";
import { TeamPicker } from "../components/TeamPicker";
import { useChampMaps } from "../lib/champs";
import { teamLabel } from "../lib/format";
import { GameDetail } from "./GameDetail";
import "./games.css";

function numParam(v: string | null): number | undefined {
  if (!v) return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

const LIMIT_DEFAULT = "50";

function CompCell({ champions, side }: { champions: ChampRef[]; side?: "BLUE" | "RED" }) {
  if (!champions.length) return <span className="muted">—</span>;
  return (
    <div className="comp" aria-label={side ? `Composición ${side}` : undefined}>
      {champions.map((c, i) => (
        <ChampIcon key={i} id={c.id} name={c.name} size={24} />
      ))}
    </div>
  );
}

function ResultCell({ result, team1, team2 }: Pick<Game, "result" | "team1" | "team2">) {
  if (result === "NONE") return <span className="muted">—</span>;
  const winner = result === "BLUE" ? team1 : team2;
  return (
    <span className={"pill " + result}>
      {winner ? (winner.tag ?? winner.name) : result}
    </span>
  );
}

const col = createColumnHelper<Game>();

const columns = [
  col.display({
    id: "expander",
    header: () => null,
    cell: ({ row }) => (
      <button
        type="button"
        className="expander"
        aria-label={row.getIsExpanded() ? "Colapsar" : "Desplegar"}
        aria-expanded={row.getIsExpanded()}
      >
        {row.getIsExpanded() ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </button>
    ),
  }),
  col.accessor("game_number", {
    header: () => <span title="Número de partida dentro de la serie">G#</span>,
    cell: ({ getValue }) => {
      const n = getValue();
      return n != null ? <span className="game-num">G{n}</span> : <span className="muted">—</span>;
    },
  }),
  col.accessor("date", { header: "Fecha" }),
  col.accessor((g) => g.tournament ?? "—", { id: "tournament", header: "Torneo" }),
  col.accessor((g) => (g.version ? `v${g.version}` : "—"), { id: "version", header: "Parche" }),
  col.accessor("team1", { header: "BLUE", cell: ({ getValue }) => teamLabel(getValue()) }),
  col.accessor("team2", { header: "RED", cell: ({ getValue }) => teamLabel(getValue()) }),
  col.display({
    id: "blue",
    header: "Comp BLUE",
    cell: ({ row }) => <CompCell champions={row.original.blue_champions} side="BLUE" />,
  }),
  col.display({
    id: "red",
    header: "Comp RED",
    cell: ({ row }) => <CompCell champions={row.original.red_champions} side="RED" />,
  }),
  col.display({
    id: "result",
    header: "Ganador",
    cell: ({ row }) => (
      <ResultCell
        result={row.original.result}
        team1={row.original.team1}
        team2={row.original.team2}
      />
    ),
  }),
];

export function Games() {
  const { data: teams } = useTeams();
  const { byName, list: champList } = useChampMaps();
  const [params, setParams] = useSearchParams();

  // Formulario inicializado desde la URL — un link compartido pre-rellena filtros.
  const [teamId, setTeamId] = useState(() => params.get("team") ?? "");
  const [champ, setChamp] = useState(() => params.get("champ") ?? "");
  const [champ2, setChamp2] = useState(() => params.get("champ2") ?? "");
  const [opposing, setOpposing] = useState(() => params.get("opposing") === "1");
  const [patch, setPatch] = useState(() => params.get("patch") ?? "");
  const [dateFrom, setDateFrom] = useState(() => params.get("dateFrom") ?? "");
  const [dateTo, setDateTo] = useState(() => params.get("dateTo") ?? "");
  const [limit, setLimit] = useState(() => params.get("limit") ?? LIMIT_DEFAULT);

  const [formError, setFormError] = useState("");
  const [expanded, setExpanded] = useState<ExpandedState>({});

  // La búsqueda activa vive en la URL (única fuente de verdad → compartible/bookmarkeable).
  const applied = useMemo<GameFilters>(() => {
    const champName = params.get("champ")?.trim().toLowerCase();
    const champ2Name = params.get("champ2")?.trim().toLowerCase();
    return {
      game_type: "OFFICIAL",
      team_id: numParam(params.get("team")),
      champ_id: champName ? byName.get(champName) : undefined,
      champ_id2: champ2Name ? byName.get(champ2Name) : undefined,
      opposing: params.get("opposing") === "1" ? true : undefined,
      patch: params.get("patch")?.trim() || undefined,
      date_from: params.get("dateFrom") || undefined,
      date_to: params.get("dateTo") || undefined,
      limit: numParam(params.get("limit")) ?? 50,
    };
  }, [params, byName]);

  const { data: games, isFetching, error } = useGames(applied);
  const data = useMemo<Game[]>(() => games ?? [], [games]);

  function resolve(name: string): number | undefined | null {
    if (!name.trim()) return undefined;
    const id = byName.get(name.trim().toLowerCase());
    return id ?? null;
  }

  function submit() {
    setFormError("");
    const c1 = resolve(champ);
    const c2 = resolve(champ2);
    if (c1 === null) return setFormError(`Campeón no reconocido: "${champ}".`);
    if (c2 === null) return setFormError(`Campeón no reconocido: "${champ2}".`);
    if (opposing && (c1 == null || c2 == null)) {
      return setFormError("«Lados opuestos» requiere dos campeones.");
    }
    if (dateFrom && dateTo && dateFrom > dateTo) {
      return setFormError("La fecha «Desde» no puede ser posterior a «Hasta».");
    }
    const effectiveLimit = limit.trim() || LIMIT_DEFAULT;
    if (effectiveLimit !== limit) setLimit(effectiveLimit);
    const next: Record<string, string> = {};
    if (teamId) next.team = teamId;
    if (champ.trim()) next.champ = champ.trim();
    if (champ2.trim()) next.champ2 = champ2.trim();
    if (opposing) next.opposing = "1";
    if (patch.trim()) next.patch = patch.trim();
    if (dateFrom) next.dateFrom = dateFrom;
    if (dateTo) next.dateTo = dateTo;
    if (effectiveLimit !== LIMIT_DEFAULT) next.limit = effectiveLimit;
    setExpanded({});
    setParams(next);
  }

  function clearFilters() {
    setTeamId("");
    setChamp("");
    setChamp2("");
    setOpposing(false);
    setPatch("");
    setDateFrom("");
    setDateTo("");
    setLimit(LIMIT_DEFAULT);
    setFormError("");
    setExpanded({});
    setParams({});
  }

  const hasFilters = [...params.keys()].length > 0;

  function activeFilterLabels(): string[] {
    const teamName = (id: string) => teams?.find((t) => String(t.id) === id)?.name ?? `#${id}`;
    const out: string[] = [];
    if (params.get("team")) out.push(teamName(params.get("team")!));
    if (params.get("champ")) out.push(`«${params.get("champ")}»`);
    if (params.get("champ2")) out.push(`matchup ${params.get("champ2")}`);
    if (params.get("opposing") === "1") out.push("lados opuestos");
    if (params.get("patch")) out.push(`parche ${params.get("patch")}`);
    if (params.get("dateFrom")) out.push(`desde ${params.get("dateFrom")}`);
    if (params.get("dateTo")) out.push(`hasta ${params.get("dateTo")}`);
    if (params.get("limit")) out.push(`${params.get("limit")} partidas`);
    return out;
  }

  const table = useReactTable({
    data,
    columns,
    state: { expanded },
    onExpandedChange: setExpanded,
    getRowCanExpand: () => true,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getRowId: (g) => String(g.game_id),
    autoResetExpanded: false,
    autoResetAll: false,
  });

  const rows = table.getRowModel().rows;

  return (
    <div className="page">
      <FilterBar onSubmit={submit}>
        <Field label="Equipo">
          <TeamPicker value={teamId} onChange={setTeamId} teams={teams ?? []} />
        </Field>
        <Field label="Campeón">
          <ChampionPicker value={champ} onChange={setChamp} champions={champList} />
        </Field>
        <Field label="Campeón 2 (matchup)">
          <ChampionPicker value={champ2} onChange={setChamp2} champions={champList} placeholder="ej. Yasuo" />
        </Field>
        <label className="field check">
          <span className="field-label">Lados opuestos</span>
          <input
            type="checkbox"
            checked={opposing}
            onChange={(e) => setOpposing(e.target.checked)}
            title="Marcado: los dos campeones en lados contrarios. Sin marcar: cualquier equipo."
          />
        </label>
        <Field label="Parche">
          <input value={patch} onChange={(e) => setPatch(e.target.value)} placeholder="14.23" size={8} />
        </Field>
        <Field label="Desde">
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </Field>
        <Field label="Hasta">
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </Field>
        <Field label="Límite">
          <input type="number" value={limit} min={1} max={500} onChange={(e) => setLimit(e.target.value)} size={5} />
        </Field>
        <button type="submit" className="btn-primary">Buscar</button>
        {hasFilters && (
          <button type="button" className="btn-ghost" onClick={clearFilters}>Limpiar</button>
        )}
      </FilterBar>

      {hasFilters && (
        <div className="filter-chips" aria-label="Filtros activos">
          {activeFilterLabels().map((label, i) => (
            <span key={i} className="filter-chip">{label}</span>
          ))}
          <button type="button" className="filter-chip-clear" onClick={clearFilters}>
            × limpiar
          </button>
        </div>
      )}

      {formError && (
        <p className="field-error" role="alert">{formError}</p>
      )}

      <p className={"status" + (error ? " error" : "")} role="status" aria-live="polite">
        {error ? (error as Error).message : isFetching ? "Buscando…" : games == null ? " " : `${games.length} partidas.`}
      </p>

      <div className="games-table-wrap">
        <table className="games-table">
          <caption className="sr-only">Partidas oficiales</caption>
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th key={h.id} scope="col">{flexRender(h.column.columnDef.header, h.getContext())}</th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {rows.map((row, idx) => {
              const prev = rows[idx - 1];
              const sid = row.original.grid_series_id;
              const prevSid = prev?.original.grid_series_id;
              const isNewSeries = !prev || sid == null || sid !== prevSid;

              return (
                <Fragment key={row.id}>
                  <tr
                    className={"game-row" + (isNewSeries && idx > 0 ? " series-sep" : "")}
                    onClick={() => row.toggleExpanded()}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                    ))}
                  </tr>
                  {row.getIsExpanded() && (
                    <tr className="detail-row">
                      <td colSpan={row.getVisibleCells().length}>
                        <GameDetail
                          gameId={row.original.game_id}
                          team1={row.original.team1}
                          team2={row.original.team2}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
