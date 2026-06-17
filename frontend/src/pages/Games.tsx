import { Fragment, useMemo, useState } from "react";
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
import { useChampMaps } from "../lib/champs";
import { teamLabel } from "../lib/format";
import { GameDetail } from "./GameDetail";
import "./games.css";

function CompCell({ champions }: { champions: ChampRef[] }) {
  if (!champions.length) return <span className="muted">—</span>;
  return (
    <div className="comp">
      {champions.map((c, i) => (
        <ChampIcon key={i} id={c.id} name={c.name} size={24} />
      ))}
    </div>
  );
}

const col = createColumnHelper<Game>();

const columns = [
  col.display({
    id: "expander",
    header: () => null,
    cell: ({ row }) => (
      <button type="button" className="expander" aria-label="Desplegar">
        {row.getIsExpanded() ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </button>
    ),
  }),
  col.accessor("date", { header: "Fecha" }),
  col.accessor("game_type", { header: "Tipo" }),
  col.accessor((g) => g.tournament ?? "—", { id: "tournament", header: "Torneo" }),
  col.accessor((g) => (g.version ? `v${g.version}` : "—"), { id: "version", header: "Parche" }),
  col.accessor("team1", { header: "BLUE", cell: ({ getValue }) => teamLabel(getValue()) }),
  col.accessor("team2", { header: "RED", cell: ({ getValue }) => teamLabel(getValue()) }),
  col.display({ id: "blue", header: "Comp BLUE", cell: ({ row }) => <CompCell champions={row.original.blue_champions} /> }),
  col.display({ id: "red", header: "Comp RED", cell: ({ row }) => <CompCell champions={row.original.red_champions} /> }),
  col.accessor("result", { header: "Resultado" }),
];

export function Games() {
  const { data: teams } = useTeams();
  const { byName, list: champList } = useChampMaps();

  const [teamId, setTeamId] = useState("");
  const [gameType, setGameType] = useState("");
  const [champ, setChamp] = useState("");
  const [champ2, setChamp2] = useState("");
  const [opposing, setOpposing] = useState(false);
  const [patch, setPatch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [limit, setLimit] = useState("50");

  const [applied, setApplied] = useState<GameFilters>({ limit: 50 });
  const [formError, setFormError] = useState("");
  const [expanded, setExpanded] = useState<ExpandedState>({});

  const { data: games, isFetching, error } = useGames(applied);

  // Referencia estable: `games ?? []` crearía un array nuevo en cada render
  // mientras la query carga (games === undefined), y react-table dispararia
  // autoResetExpanded en bucle (microtask loop que congela la pestaña).
  const data = useMemo<Game[]>(() => games ?? [], [games]);

  function resolve(name: string): number | undefined | null {
    if (!name.trim()) return undefined;
    const id = byName.get(name.trim().toLowerCase());
    return id ?? null; // null = no reconocido
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
    setExpanded({});
    setApplied({
      team_id: teamId ? Number(teamId) : undefined,
      game_type: gameType || undefined,
      champ_id: c1 ?? undefined,
      champ_id2: c2 ?? undefined,
      opposing: opposing || undefined,
      patch: patch.trim() || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      limit: limit ? Number(limit) : undefined,
    });
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

  return (
    <div className="page">
      <FilterBar onSubmit={submit}>
        <Field label="Equipo">
          <select value={teamId} onChange={(e) => setTeamId(e.target.value)}>
            <option value="">(cualquiera)</option>
            {(teams ?? []).map((t) => (
              <option key={t.id} value={t.id}>{t.tag ? `${t.name} (${t.tag})` : t.name}</option>
            ))}
          </select>
        </Field>
        <Field label="Tipo">
          <select value={gameType} onChange={(e) => setGameType(e.target.value)}>
            <option value="">(todos)</option>
            <option value="OFFICIAL">Oficiales</option>
            <option value="SCRIM">Scrims</option>
            <option value="SOLOQ">SoloQ</option>
          </select>
        </Field>
        <Field label="Campeón">
          <ChampionPicker value={champ} onChange={setChamp} champions={champList} />
        </Field>
        <Field label="Campeón 2 (matchup)">
          <ChampionPicker value={champ2} onChange={setChamp2} champions={champList} placeholder="ej. Yasuo" />
        </Field>
        <label className="field check">
          <span className="field-label">Lados opuestos</span>
          <input type="checkbox" checked={opposing} onChange={(e) => setOpposing(e.target.checked)} />
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
      </FilterBar>

      <p className={"status" + (formError || error ? " error" : "")}>
        {formError ||
          (error ? (error as Error).message : isFetching ? "Buscando…" : `${games?.length ?? 0} partidas.`)}
      </p>

      <div className="games-table-wrap">
        <table className="games-table">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th key={h.id}>{flexRender(h.column.columnDef.header, h.getContext())}</th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <Fragment key={row.id}>
                <tr className="game-row" onClick={() => row.toggleExpanded()}>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                  ))}
                </tr>
                {row.getIsExpanded() && (
                  <tr className="detail-row">
                    <td colSpan={row.getVisibleCells().length}>
                      <GameDetail gameId={row.original.game_id} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
