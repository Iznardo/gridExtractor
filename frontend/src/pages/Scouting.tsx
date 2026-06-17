import { useState } from "react";

import { useScouting, useTeams } from "../api/hooks";
import type { Medium, ScoutPlayer, ScoutingPool } from "../api/types";
import { Field, FilterBar } from "../components/Field";
import { ChampIcon } from "../components/icons";
import "./scouting.css";

const ROLE_ORDER: Record<string, number> = { TOP: 0, JUNGLE: 1, MID: 2, ADC: 3, SUPPORT: 4 };

function roleRank(role: string | null): number {
  return role ? ROLE_ORDER[role] ?? 99 : 99;
}

// ---- agregado por jugador (todos los medios) derivado de by_medium ----
type AggCount = { games: number; wins: number };
type AggChamp = {
  champion: { id: number; name: string };
  official: AggCount;
  scrim: AggCount;
  soloq: AggCount;
  total: AggCount;
};
type AggPlayer = { player: ScoutPlayer["player"]; champions: AggChamp[] };

function buildAggregate(pool: ScoutingPool): AggPlayer[] {
  const players = new Map<number, { player: ScoutPlayer["player"]; champs: Map<number, AggChamp> }>();
  const mediums: Medium[] = ["official", "scrim", "soloq"];
  for (const medium of mediums) {
    for (const p of pool.by_medium[medium]) {
      const entry =
        players.get(p.player.id) ?? { player: p.player, champs: new Map<number, AggChamp>() };
      for (const ch of p.champions) {
        const c =
          entry.champs.get(ch.champion.id) ??
          {
            champion: ch.champion,
            official: { games: 0, wins: 0 },
            scrim: { games: 0, wins: 0 },
            soloq: { games: 0, wins: 0 },
            total: { games: 0, wins: 0 },
          };
        c[medium].games += ch.games;
        c[medium].wins += ch.wins;
        c.total.games += ch.games;
        c.total.wins += ch.wins;
        entry.champs.set(ch.champion.id, c);
      }
      players.set(p.player.id, entry);
    }
  }
  return Array.from(players.values())
    .map((e) => ({
      player: e.player,
      champions: Array.from(e.champs.values()).sort(
        (a, b) => b.total.games - a.total.games || a.champion.name.localeCompare(b.champion.name),
      ),
    }))
    .sort((a, b) => roleRank(a.player.role) - roleRank(b.player.role) || a.player.name.localeCompare(b.player.name));
}

// ---- render ----
function MediumSection({ title, players }: { title: string; players: ScoutPlayer[] }) {
  return (
    <section className="scout-block">
      <h2>
        {title} <span className="muted count">{players.length ? `${players.length} jugadores` : "sin datos"}</span>
      </h2>
      {players.map((p) => (
        <div key={p.player.id} className="player-card">
          <div className="phead">
            <span className="pname">{p.player.name}</span>
            {p.player.role && <span className="prole">{p.player.role}</span>}
          </div>
          <div className="chips">
            {p.champions.map((ch) => (
              <span key={ch.champion.id} className="chip">
                <ChampIcon id={ch.champion.id} name={ch.champion.name} size={24} />
                <span className="cn">{ch.champion.name}</span>
                <span className="n">{ch.wins ? `${ch.games} (${ch.wins}W)` : ch.games}</span>
              </span>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

function fmt(c: AggCount): string {
  return c.games ? (c.wins ? `${c.games} (${c.wins}W)` : `${c.games}`) : "—";
}

function AggregateSection({ players }: { players: AggPlayer[] }) {
  return (
    <section className="scout-block">
      <h2>Agregado por jugador (todos los medios)</h2>
      {players.map((p) => (
        <div key={p.player.id} className="player-card">
          <div className="phead">
            <span className="pname">{p.player.name}</span>
            {p.player.role && <span className="prole">{p.player.role}</span>}
          </div>
          <table className="grid">
            <thead>
              <tr>
                <th>Campeón</th>
                <th>Oficiales</th>
                <th>Scrims</th>
                <th>SoloQ</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {p.champions.map((ch) => (
                <tr key={ch.champion.id}>
                  <td>
                    <div className="cell-champ">
                      <ChampIcon id={ch.champion.id} name={ch.champion.name} size={22} />
                      {ch.champion.name}
                    </div>
                  </td>
                  <td className="num">{fmt(ch.official)}</td>
                  <td className="num">{fmt(ch.scrim)}</td>
                  <td className="num">{fmt(ch.soloq)}</td>
                  <td className="num">{fmt(ch.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  );
}

export function Scouting() {
  const { data: teams } = useTeams();
  const [teamId, setTeamId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [applied, setApplied] = useState<{ teamId: number | null; dateFrom?: string }>({ teamId: null });

  const { data: pool, isFetching, error } = useScouting(applied.teamId, applied.dateFrom);

  function submit() {
    setApplied({ teamId: teamId ? Number(teamId) : null, dateFrom: dateFrom || undefined });
  }

  return (
    <div className="page">
      <FilterBar onSubmit={submit}>
        <Field label="Equipo *">
          <select value={teamId} onChange={(e) => setTeamId(e.target.value)}>
            <option value="">(elige equipo)</option>
            {(teams ?? []).map((t) => (
              <option key={t.id} value={t.id}>{t.tag ? `${t.name} (${t.tag})` : t.name}</option>
            ))}
          </select>
        </Field>
        <Field label="Desde fecha">
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </Field>
        <button type="submit" className="btn-primary">Scoutear</button>
      </FilterBar>

      <p className={"status" + (error ? " error" : "")}>
        {error
          ? (error as Error).message
          : applied.teamId == null
            ? "Elige un equipo para scoutear."
            : isFetching
              ? "Cargando…"
              : ""}
      </p>

      {pool && applied.teamId != null && (
        <div className="scout-results">
          <MediumSection title="Oficiales" players={pool.by_medium.official} />
          <MediumSection title="Scrims" players={pool.by_medium.scrim} />
          <MediumSection title="SoloQ" players={pool.by_medium.soloq} />
          <AggregateSection players={buildAggregate(pool)} />
        </div>
      )}
    </div>
  );
}
