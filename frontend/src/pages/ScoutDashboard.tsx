import { Fragment, useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";

import {
  useChampionPresence,
  useGames,
  usePlayerShares,
  useRolePicks,
  useScouting,
} from "../api/hooks";
import { MediumBox, ROLE_LABELS, ScoutingSkeleton, type Role } from "../components/ChampionPool";
import { ChampIcon } from "../components/icons";
import { Radar } from "../components/Radar";
import { daysAgoISO } from "../lib/date";
import { aggAsScoutPlayers, buildAggregate, seriesBlocks, type Series } from "./scouting/aggregate";
import "./scrims.css"; // reutiliza estilos de card/tabla/bloque desplegable
import "./scouting.css";

const RECENT_DAYS = 14;
const GAMES_LIMIT = 40; // suficiente para cubrir las 5 series más recientes (Bo5 = 5 games)
const OFFICIAL = "OFFICIAL";
const ROLES: Role[] = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"];
const ROLE_SHORT: Record<Role, string> = {
  TOP: "TOP", JUNGLE: "JNG", MID: "MID", ADC: "ADC", SUPPORT: "SUP",
};

// ---- #1 Últimos picks (2 semanas, agregado de todas las fuentes) ----

function RecentPicks({ teamId }: { teamId: number }) {
  const { data: pool } = useScouting(teamId, { dateFrom: daysAgoISO(RECENT_DAYS) });
  const players = useMemo(
    () => (pool ? aggAsScoutPlayers(buildAggregate(pool)) : []),
    [pool],
  );
  if (!pool) return <ScoutingSkeleton />;
  if (players.length === 0)
    return <p className="scr-empty muted">Sin partidas en las últimas {RECENT_DAYS} días.</p>;
  return <MediumBox players={players} />;
}

// ---- #2 Últimas series (oficiales, desplegables) ----

function ChampRow({
  champs,
  size = 22,
}: {
  champs: { id: number; name: string | null }[];
  size?: number;
}) {
  return (
    <div className="scr-champ-row">
      {champs.map((c, i) => (
        <ChampIcon key={i} id={c.id} name={c.name ?? `#${c.id}`} size={size} />
      ))}
    </div>
  );
}

function SeriesTable({ s }: { s: Series }) {
  return (
    <table className="scr-table scr-block-table">
      <thead>
        <tr>
          <th>G</th><th>Lado</th><th>Res</th><th>Nuestra comp</th><th>Rival</th>
        </tr>
      </thead>
      <tbody>
        {s.games.map((g) => (
          <tr key={g.game.game_id}>
            <td>{g.game.game_number ?? "—"}</td>
            <td><span className={"pill " + g.our_side}>{g.our_side}</span></td>
            <td><span className={g.won ? "scr-wr-pos" : "scr-wr-neg"}>{g.won ? "W" : "L"}</span></td>
            <td><ChampRow champs={g.our_champs} /></td>
            <td><ChampRow champs={g.rival_champs} size={20} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RecentSeries({ teamId }: { teamId: number }) {
  const { data: games, isFetching } = useGames({
    team_id: teamId,
    game_type: "OFFICIAL",
    limit: GAMES_LIMIT,
  });
  const all = useMemo(
    () => (games ? seriesBlocks(games, teamId).slice(0, 5) : []),
    [games, teamId],
  );
  const [open, setOpen] = useState<Set<string>>(new Set());

  // Récord de series (gana la serie quien gana la mayoría de sus games).
  const wins = all.filter((s) => s.wins * 2 > s.total).length;
  const losses = all.length - wins;

  const header = (
    <div className="scout-series-head">
      <h3 className="scr-h3">Últimas 5 series oficiales</h3>
      {all.length > 0 && (
        <strong className={"scout-series-rec " + (wins >= losses ? "scr-wr-pos" : "scr-wr-neg")}>
          {wins}W {losses}L
        </strong>
      )}
    </div>
  );

  function toggle(k: string) {
    setOpen((prev) => {
      const n = new Set(prev);
      n.has(k) ? n.delete(k) : n.add(k);
      return n;
    });
  }

  if (isFetching && !games) return <>{header}<ScoutingSkeleton /></>;
  if (all.length === 0) return <>{header}<p className="scr-empty muted">Sin partidas oficiales.</p></>;

  return (
    <>
      {header}
      <div className="scr-card">
      <table className="scr-table scr-blocks-table">
        <thead>
          <tr>
            <th aria-label="expandir" />
            <th>Día</th><th>Parche</th><th>Rival</th><th>Resultado</th>
          </tr>
        </thead>
        <tbody>
          {all.map((s) => {
            const isOpen = open.has(s.key);
            const losses = s.total - s.wins;
            return (
              <Fragment key={s.key}>
                <tr
                  className="scr-block-row"
                  onClick={() => toggle(s.key)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(s.key); }
                  }}
                  tabIndex={0}
                  role="button"
                  aria-expanded={isOpen}
                >
                  <td className="scr-caret" aria-hidden="true">{isOpen ? "▾" : "▸"}</td>
                  <td>{s.date}</td>
                  <td>{s.version ?? "—"}</td>
                  <td className="scr-team-cell">{s.rival?.tag ?? s.rival?.name ?? "(?)"}</td>
                  <td>
                    <strong className={s.wins >= losses ? "scr-wr-pos" : "scr-wr-neg"}>
                      {s.wins}W {losses}L
                    </strong>
                  </td>
                </tr>
                {isOpen && (
                  <tr className="scr-block-detail-row">
                    <td colSpan={5}><SeriesTable s={s} /></td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      </div>
    </>
  );
}

// ---- #4 Bans más baneados en 1ª fase vs el equipo (oficiales) ----

function BansFaced({ teamId }: { teamId: number }) {
  const { data } = useChampionPresence({ team_id: teamId, game_types: OFFICIAL });
  const top = useMemo(
    () =>
      (data ?? [])
        .filter((r) => r.banned_vs_p1 > 0)
        .sort((a, b) => b.banned_vs_p1 - a.banned_vs_p1)
        .slice(0, 8),
    [data],
  );
  if (!data) return <ScoutingSkeleton />;
  if (top.length === 0) return <p className="scr-empty muted">Sin bans de 1ª fase registrados.</p>;
  return (
    <div className="scout-ban-list">
      {top.map((r) => (
        <div key={r.champ_id} className="scout-ban" title={`${r.champ_name ?? r.champ_id}: ${r.banned_vs_p1} bans en 1ª fase`}>
          <ChampIcon id={r.champ_id} name={r.champ_name ?? `#${r.champ_id}`} size={40} />
          <span className="scout-ban-count">{r.banned_vs_p1}</span>
        </div>
      ))}
    </div>
  );
}

// ---- #5 % counterpick por rol (oficiales) ----

function CounterRate({ teamId }: { teamId: number }) {
  const filters = { team_id: teamId, game_types: OFFICIAL };
  const { data: blind } = useRolePicks("blind", filters);
  const { data: counter } = useRolePicks("counter", filters);
  const rows = useMemo(() => {
    if (!blind || !counter) return null;
    const sum = (arr: { games: number }[] | undefined) => (arr ?? []).reduce((s, e) => s + e.games, 0);
    return ROLES.map((role) => {
      const c = sum(counter[role]);
      const total = sum(blind[role]) + c;
      return { role, counter: c, total, pct: total ? Math.round((100 * c) / total) : null };
    });
  }, [blind, counter]);

  if (!rows) return <ScoutingSkeleton />;
  if (rows.every((r) => r.total === 0))
    return <p className="scr-empty muted">Sin datos de pick order.</p>;

  return (
    <div className="scout-counter">
      {rows.map((r) => (
        <div key={r.role} className="scout-counter-row">
          <span className="scout-counter-role">{ROLE_LABELS[r.role]}</span>
          <div className="scout-counter-track" aria-hidden="true">
            <div className="scout-counter-fill" style={{ width: `${r.pct ?? 0}%` }} />
          </div>
          <span className="scout-counter-val">
            {r.pct == null ? "—" : `${r.pct}%`}
            <span className="muted scr-sub"> ({r.total})</span>
          </span>
        </div>
      ))}
    </div>
  );
}

// ---- #6 Radar de % oro / % daño por jugador (oficiales) ----

function SharesRadar({ teamId }: { teamId: number }) {
  const { data } = usePlayerShares(teamId, { gameTypes: OFFICIAL });
  if (!data) return <ScoutingSkeleton />;
  if (data.length === 0) return <p className="scr-empty muted">Sin datos de oro/daño.</p>;

  const axes = data.map((d) => ROLE_SHORT[d.role as Role] ?? d.role);
  return (
    <div className="scout-radar-wrap">
      <Radar
        axes={axes}
        series={[
          { label: "% oro", color: "#fde68a", values: data.map((d) => d.gold_pct ?? 0) },
          { label: "% daño", color: "#3b82f6", values: data.map((d) => d.dmg_pct ?? 0) },
        ]}
      />
      <table className="scr-table scout-radar-table">
        <thead>
          <tr>
            <th>Rol</th><th>Jugador</th>
            <th className="scr-num">Oro%</th><th className="scr-num">Daño%</th>
          </tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.role}>
              <td>{ROLE_LABELS[d.role as Role] ?? d.role}</td>
              <td className="scr-team-cell">{d.player ?? "—"}</td>
              <td className="scr-num">{d.gold_pct?.toFixed(1) ?? "—"}</td>
              <td className="scr-num">{d.dmg_pct?.toFixed(1) ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---- Dashboard ----

export function ScoutDashboard({ teamId }: { teamId: number }) {
  return (
    <div className="scr-dashboard">
      <section className="scr-section">
        <div className="scout-dash-head">
          <h3 className="scr-h3">Últimos picks por jugador · últimas {RECENT_DAYS} días (agregado)</h3>
          <a
            className="btn-ghost btn-ghost-sm scout-dash-link"
            href={`/drafts?team=${teamId}`}
            target="_blank"
            rel="noopener"
          >
            <ExternalLink size={14} aria-hidden="true" /> Abrir drafts
          </a>
        </div>
        <RecentPicks teamId={teamId} />
      </section>

      <section className="scr-section">
        <RecentSeries teamId={teamId} />
      </section>

      <div className="scout-dash-grid">
        <section className="scr-section">
          <h3 className="scr-h3">Más baneados en 1ª fase · vs este equipo</h3>
          <BansFaced teamId={teamId} />
        </section>
        <section className="scr-section">
          <h3 className="scr-h3">% counterpick por rol</h3>
          <CounterRate teamId={teamId} />
        </section>
      </div>

      <section className="scr-section">
        <h3 className="scr-h3">Reparto de oro y daño por jugador</h3>
        <SharesRadar teamId={teamId} />
      </section>
    </div>
  );
}
