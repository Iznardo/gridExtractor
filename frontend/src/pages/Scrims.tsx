import { Fragment, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ExternalLink } from "lucide-react";

import {
  usePatches,
  useScouting,
  useScrimGames,
  useTeams,
  type ScrimGamesFilters,
  type StatsFilters,
} from "../api/hooks";
import type { ScrimGame, ScrimRole } from "../api/types";
import {
  MediumBox,
  ROLE_LABELS,
  ScoutingSkeleton,
  WR_MIN_GAMES,
} from "../components/ChampionPool";
import { Field, FilterBar } from "../components/Field";
import { Select } from "../components/Select";
import { ChampIcon } from "../components/icons";
import { Tabs } from "../components/Tabs";
import { TeamPicker } from "../components/TeamPicker";
import { TeamMatchups } from "./TeamMatchups";
import { useChampMaps } from "../lib/champs";
import { daysAgoISO } from "../lib/date";
import {
  blocks,
  combosByRoles,
  lastBlock,
  vsPicks,
  vsTeams,
  winRate,
  type BlockSummary,
  type Count,
} from "./scrims/aggregate";
import "./scrims.css";

const LS_KEY = "scrims:lastTeam";
const VIEW_IDS = ["dashboard", "bloques", "matchups", "duos", "trios", "vsteams", "vspicks"] as const;

const DUO_SETS: ScrimRole[][] = [
  ["TOP", "JUNGLE"],
  ["MID", "JUNGLE"],
  ["ADC", "SUPPORT"],
];
const TRIO_SETS: ScrimRole[][] = [
  ["TOP", "JUNGLE", "MID"],
  ["MID", "JUNGLE", "SUPPORT"],
  ["TOP", "ADC", "SUPPORT"],
  ["JUNGLE", "ADC", "SUPPORT"],
];

const COMBO_LIMIT = 10;
const VSPICK_LIMIT = 20;

type ById = ReturnType<typeof useChampMaps>["byId"];

// ---- helpers de WR (coherentes con TeamMatchups: glifo no-cromático) ----

function wrClass(c: Count): string {
  const wr = winRate(c);
  if (wr == null || c.games < WR_MIN_GAMES) return "scr-wr-neutral";
  if (wr >= 55) return "scr-wr-pos";
  if (wr <= 45) return "scr-wr-neg";
  return "scr-wr-neutral";
}

function WrValue({ c }: { c: Count }) {
  const wr = winRate(c);
  if (wr == null) return <span className="muted">—</span>;
  const arrow = c.games >= WR_MIN_GAMES ? (wr >= 55 ? "▲" : wr <= 45 ? "▼" : "") : "";
  return (
    <span className={wrClass(c)}>
      {arrow && <span className="scr-wr-arrow" aria-hidden="true">{arrow}</span>}
      {wr.toFixed(0)}%
    </span>
  );
}

function rec(c: Count): string {
  return `${c.wins}-${c.games - c.wins}`;
}

function Champ({ id, byId, size = 22 }: { id: number | null; byId: ById; size?: number }) {
  if (id == null) return <span className="scr-champ-empty">—</span>;
  const name = byId.get(id)?.name ?? `#${id}`;
  return <ChampIcon id={id} name={name} size={size} />;
}

// ---- bloque: resumen + tabla de games (reutilizados por #3 y la pestaña Bloques) ----

function BlockSummaryLine({ block }: { block: BlockSummary }) {
  const losses = block.total.games - block.total.wins;
  return (
    <span className="scr-block-summary">
      <strong className={block.total.wins >= losses ? "scr-wr-pos" : "scr-wr-neg"}>
        {block.total.wins}W {losses}L
      </strong>
      <span className="muted"> · BLUE {rec(block.blue)} · RED {rec(block.red)}</span>
    </span>
  );
}

function BlockGamesTable({ block, byId }: { block: BlockSummary; byId: ById }) {
  return (
    <table className="scr-table scr-block-table">
      <thead>
        <tr>
          <th>G</th><th>Lado</th><th>Res</th><th>Nuestro draft</th><th>Rival</th>
        </tr>
      </thead>
      <tbody>
        {block.games.map((g) => (
          <tr key={g.game_id}>
            <td>{g.block_game_number}</td>
            <td><span className={"pill " + g.our_side}>{g.our_side}</span></td>
            <td>
              <span className={g.won ? "scr-wr-pos" : "scr-wr-neg"}>{g.won ? "W" : "L"}</span>
            </td>
            <td>
              <div className="scr-champ-row">
                {(["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"] as ScrimRole[]).map((r) => (
                  <Champ key={r} id={g.lineup[r]} byId={byId} size={22} />
                ))}
              </div>
            </td>
            <td>
              <div className="scr-champ-row">
                {g.rival_champs.map((c, i) => <Champ key={i} id={c} byId={byId} size={20} />)}
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---- #3 Último bloque (dashboard) ----

function LastBlockCard({ rows, byId }: { rows: ScrimGame[]; byId: ById }) {
  const block = useMemo(() => lastBlock(rows), [rows]);
  if (!block) return <p className="scr-empty muted">Sin scrims para este equipo.</p>;
  return (
    <div className="scr-card">
      <div className="scr-block-head">
        <span className="scr-block-title">
          Último bloque · vs {block.rival?.tag ?? block.rival?.name ?? "(?)"} · {block.date}
        </span>
        <BlockSummaryLine block={block} />
      </div>
      <BlockGamesTable block={block} byId={byId} />
    </div>
  );
}

// ---- Pestaña Bloques: lista de todos los bloques, expandible ----

function BlocksView({ rows, byId }: { rows: ScrimGame[]; byId: ById }) {
  const all = useMemo(() => blocks(rows), [rows]);
  const [open, setOpen] = useState<Set<string>>(new Set());

  if (all.length === 0) return <p className="scr-empty muted">Sin scrims.</p>;

  function toggle(k: string) {
    setOpen((prev) => {
      const n = new Set(prev);
      if (n.has(k)) n.delete(k); else n.add(k);
      return n;
    });
  }

  return (
    <div className="scr-card">
      <table className="scr-table scr-blocks-table">
        <thead>
          <tr>
            <th aria-label="expandir" />
            <th>Día</th><th>Parche</th><th>Rival</th><th>Resultado</th>
          </tr>
        </thead>
        <tbody>
          {all.map((b) => {
            const isOpen = open.has(b.key);
            return (
              <Fragment key={b.key}>
                <tr
                  className="scr-block-row"
                  onClick={() => toggle(b.key)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(b.key); }
                  }}
                  tabIndex={0}
                  role="button"
                  aria-expanded={isOpen}
                >
                  <td className="scr-caret" aria-hidden="true">{isOpen ? "▾" : "▸"}</td>
                  <td>{b.date}</td>
                  <td>{b.version ?? "—"}</td>
                  <td className="scr-team-cell">{b.rival?.tag ?? b.rival?.name ?? "(?)"}</td>
                  <td><BlockSummaryLine block={b} /></td>
                </tr>
                {isOpen && (
                  <tr className="scr-block-detail-row">
                    <td colSpan={5}>
                      <BlockGamesTable block={b} byId={byId} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---- #4/#5 Combos (duos / trios) ----

function ComboTable({ rows, roles, byId }: { rows: ScrimGame[]; roles: ScrimRole[]; byId: ById }) {
  const combos = useMemo(() => combosByRoles(rows, roles), [rows, roles]);
  const title = roles.map((r) => ROLE_LABELS[r]).join(" + ");
  return (
    <div className="scr-card">
      <div className="scr-card-title">{title}</div>
      {combos.length === 0 ? (
        <p className="scr-empty muted">Sin datos.</p>
      ) : (
        <table className="scr-table">
          <thead>
            <tr><th>Combo</th><th className="scr-num">G</th><th className="scr-num">WR</th></tr>
          </thead>
          <tbody>
            {combos.slice(0, COMBO_LIMIT).map((c) => (
              <tr key={c.champs.join("-")}>
                <td>
                  <div className="scr-champ-row">
                    {c.champs.map((id, i) => <Champ key={i} id={id} byId={byId} size={22} />)}
                  </div>
                </td>
                <td className="scr-num">{c.count.games}</td>
                <td className="scr-num"><WrValue c={c.count} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ---- #6 vs-Equipos ----

function VsTeamsView({ rows }: { rows: ScrimGame[] }) {
  const data = useMemo(() => vsTeams(rows), [rows]);
  // columnas de game number presentes en los datos (1..maxBlock)
  const maxGn = useMemo(
    () => data.reduce((m, t) => Math.max(m, ...Array.from(t.byGame.keys())), 1),
    [data],
  );
  const gns = Array.from({ length: maxGn }, (_, i) => i + 1);

  if (data.length === 0) return <p className="scr-empty muted">Sin scrims.</p>;
  return (
    <div className="scr-card">
      <table className="scr-table">
        <thead>
          <tr>
            <th>Rival</th>
            <th className="scr-num">G</th>
            <th className="scr-num">WR</th>
            <th className="scr-num">1st pick</th>
            <th className="scr-num">2nd pick</th>
            {gns.map((n) => <th key={n} className="scr-num">G{n}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.map((t) => (
            <tr key={t.rival.id}>
              <td className="scr-team-cell">{t.rival.tag ?? t.rival.name}</td>
              <td className="scr-num">{t.total.games}</td>
              <td className="scr-num"><WrValue c={t.total} /></td>
              <td className="scr-num">
                <WrValue c={t.firstPick} /> <span className="muted scr-sub">{rec(t.firstPick)}</span>
              </td>
              <td className="scr-num">
                <WrValue c={t.secondPick} /> <span className="muted scr-sub">{rec(t.secondPick)}</span>
              </td>
              {gns.map((n) => {
                const c = t.byGame.get(n);
                return (
                  <td key={n} className="scr-num">
                    {c ? <WrValue c={c} /> : <span className="muted">·</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---- #7 vs-Picks ----

function VsPicksView({ rows, byId }: { rows: ScrimGame[]; byId: ById }) {
  const data = useMemo(() => vsPicks(rows), [rows]);
  if (data.length === 0) return <p className="scr-empty muted">Sin scrims.</p>;
  return (
    <div className="scr-card">
      <table className="scr-table">
        <thead>
          <tr><th>Campeón rival</th><th className="scr-num">G</th><th className="scr-num">Nuestro WR</th></tr>
        </thead>
        <tbody>
          {data.slice(0, VSPICK_LIMIT).map((p) => (
            <tr key={p.champ_id}>
              <td>
                <div className="scr-champ-name">
                  <Champ id={p.champ_id} byId={byId} size={22} />
                  <span>{byId.get(p.champ_id)?.name ?? `#${p.champ_id}`}</span>
                </div>
              </td>
              <td className="scr-num">{p.count.games}</td>
              <td className="scr-num"><WrValue c={p.count} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---- Scrims ----

export function Scrims() {
  const [params, setParams] = useSearchParams();
  const { byId } = useChampMaps();
  const { data: patches } = usePatches();
  const { data: teams } = useTeams();

  // Equipo recordado: URL manda; si no hay, cae a localStorage.
  const remembered = typeof localStorage !== "undefined" ? localStorage.getItem(LS_KEY) : null;
  const appliedTeam = params.get("team") ?? remembered ?? "";
  const appliedTeamId = appliedTeam ? Number(appliedTeam) : null;

  const [teamId, setTeamId] = useState(() => appliedTeam);
  const [dateFrom, setDateFrom] = useState(() => params.get("dateFrom") ?? "");
  const [patch, setPatch] = useState(() => params.get("patch") ?? "");

  const viewParam = params.get("view");
  const activeView = (VIEW_IDS as readonly string[]).includes(viewParam ?? "")
    ? (viewParam as string)
    : "dashboard";

  // Persistir el equipo aplicado en localStorage (recordatorio entre sesiones).
  useEffect(() => {
    if (appliedTeam) localStorage.setItem(LS_KEY, appliedTeam);
  }, [appliedTeam]);

  const appliedDateFrom = params.get("dateFrom") || undefined;
  const appliedPatch = params.get("patch") || undefined;

  // Una sola descarga de scrims; las vistas agregan en cliente. El filtro global
  // (parche / fecha) acota todo menos los dos pools fijos del dashboard.
  const scrimFilters: ScrimGamesFilters = {
    team_id: appliedTeamId,
    date_from: appliedDateFrom,
    patch: appliedPatch,
  };
  const { data: rows, isFetching, error, refetch } = useScrimGames(scrimFilters);

  // Pools del dashboard. "Último parche" = el parche más reciente CON scrims de
  // este equipo (no el global: un equipo puede no haber jugado scrims en el
  // último parche). Se deriva del dataset ya cargado (rows van date DESC).
  const dashPatch = (rows && rows.length > 0 ? rows[0].version : null) ?? patches?.[0];
  const { data: poolPatch } = useScouting(appliedTeamId, { patch: dashPatch });
  const { data: pool7 } = useScouting(appliedTeamId, { dateFrom: daysAgoISO(7) });

  function submit() {
    const next = new URLSearchParams(params);
    if (teamId) next.set("team", teamId);
    else next.delete("team");
    if (dateFrom) next.set("dateFrom", dateFrom);
    else next.delete("dateFrom");
    if (patch) next.set("patch", patch);
    else next.delete("patch");
    setParams(next);
  }

  function handleViewChange(id: string) {
    const next = new URLSearchParams(params);
    if (id === "dashboard") next.delete("view");
    else next.set("view", id);
    setParams(next);
  }

  const dashboard = (
    <div className="scr-dashboard">
      <section className="scr-section">
        <div className="scout-dash-head">
          <h3 className="scr-h3">
            Top picks por jugador · último parche {dashPatch ? `(${dashPatch})` : ""}
          </h3>
          <a
            className="btn-ghost btn-ghost-sm scout-dash-link"
            href={`/drafts?team=${appliedTeamId}&type=SCRIM`}
            target="_blank"
            rel="noopener"
          >
            <ExternalLink size={14} aria-hidden="true" /> Abrir drafts
          </a>
        </div>
        {poolPatch ? <MediumBox players={poolPatch.by_medium.scrim} /> : <ScoutingSkeleton />}
      </section>
      <section className="scr-section">
        <h3 className="scr-h3">Top picks por jugador · últimos 7 días</h3>
        {pool7 ? <MediumBox players={pool7.by_medium.scrim} /> : <ScoutingSkeleton />}
      </section>
      <section className="scr-section">
        <h3 className="scr-h3">Resumen del último bloque</h3>
        <LastBlockCard rows={rows ?? []} byId={byId} />
      </section>
    </div>
  );

  const duosView = (
    <div className="scr-grid">
      {DUO_SETS.map((roles) => (
        <ComboTable key={roles.join("-")} rows={rows ?? []} roles={roles} byId={byId} />
      ))}
    </div>
  );

  const triosView = (
    <div className="scr-grid">
      {TRIO_SETS.map((roles) => (
        <ComboTable key={roles.join("-")} rows={rows ?? []} roles={roles} byId={byId} />
      ))}
    </div>
  );

  // Matchups (campeón vs campeón por rol): reutiliza TeamMatchups, acotado a
  // scrims y al filtro de parche global.
  const matchupFilters: StatsFilters = {
    team_id: appliedTeamId ?? undefined,
    game_types: "SCRIM",
    patch: appliedPatch,
  };

  const windowTabs = [
    { id: "dashboard", label: "Dashboard", content: dashboard },
    { id: "bloques", label: "Bloques", content: <BlocksView rows={rows ?? []} byId={byId} /> },
    { id: "matchups", label: "Matchups", content: <TeamMatchups filters={matchupFilters} /> },
    { id: "duos", label: "Duos", content: duosView },
    { id: "trios", label: "Trios", content: triosView },
    { id: "vsteams", label: "vs Equipos", content: <VsTeamsView rows={rows ?? []} /> },
    { id: "vspicks", label: "vs Picks", content: <VsPicksView rows={rows ?? []} byId={byId} /> },
  ];

  return (
    <div className="page">
      <FilterBar onSubmit={submit}>
        <Field label="Equipo *">
          <TeamPicker value={teamId} onChange={setTeamId} teams={teams ?? []} />
        </Field>
        <Field label="Parche">
          <Select
            value={patch}
            onChange={setPatch}
            ariaLabel="Parche"
            options={[{ value: "", label: "(todos)" }, ...(patches ?? []).map((p) => ({ value: p, label: p }))]}
          />
        </Field>
        <Field label="Desde fecha">
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </Field>
        <button type="submit" className="btn-primary" disabled={!teamId}>
          Trackear
        </button>
      </FilterBar>

      <p className={"status" + (error ? " error" : "")} role="status" aria-live="polite">
        {appliedTeamId == null
          ? "Elige tu equipo para trackear sus scrims."
          : error
            ? <>{(error as Error).message} <button type="button" className="btn-ghost btn-ghost-sm" onClick={() => refetch()}>Reintentar</button></>
            : isFetching
              ? "Cargando scrims…"
              : `${rows?.length ?? 0} scrims.`}
      </p>

      {appliedTeamId != null && !error && (
        <div className="scr-results">
          <Tabs tabs={windowTabs} value={activeView} onChange={handleViewChange} />
        </div>
      )}
    </div>
  );
}
