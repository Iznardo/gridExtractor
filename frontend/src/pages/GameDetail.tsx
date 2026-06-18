import { useState } from "react";
import type { Pick, Side, TeamRef } from "../api/types";
import { useGamePicks } from "../api/hooks";
import { BuildCard } from "../components/BuildCard";
import { ChampIcon, ItemIcon, RuneIcon, SpellIcon } from "../components/icons";
import { Tabs } from "../components/Tabs";
import { kdaRatio, kpPct } from "../lib/format";
import "./gamedetail.css";

const ROLE_RANK: Record<string, number> = {
  TOP: 0,
  JUNGLE: 1,
  MID: 2,
  ADC: 3,
  SUPPORT: 4,
};

function sortPlayers(picks: Pick[]): Pick[] {
  return [...picks].sort((a, b) => {
    const ra = ROLE_RANK[a.player.role ?? ""] ?? 9;
    const rb = ROLE_RANK[b.player.role ?? ""] ?? 9;
    return ra !== rb ? ra - rb : (a.pick_order ?? 0) - (b.pick_order ?? 0);
  });
}

function teamKills(picks: Pick[]): number {
  return picks.reduce((s, p) => s + (p.stats.kills ?? 0), 0);
}

// ----------------------------- General -----------------------------

function Scoreboard({
  blue, red, blueTeam, redTeam,
}: {
  blue: Pick[];
  red: Pick[];
  blueTeam?: TeamRef;
  redTeam?: TeamRef;
}) {
  const all = [...blue, ...red];
  const hasDamage = all.some((p) => p.stats.damage_dealt != null);
  const hasSpells = all.some((p) => p.stats.summoner_spells?.length);
  const hasLevel = all.some((p) => p.stats.champ_level != null);
  const hasVision = all.some((p) => p.stats.vision_score != null);

  function sideBlock(side: Side, picks: Pick[], team?: TeamRef) {
    const tk = teamKills(picks);
    const won = picks[0]?.result;
    return (
      <div className="sb-block">
        <div className="sb-side">
          <span className={"pill " + side}>{side}</span>
          {team && <span className="sb-team">{team.tag ?? team.name}</span>}
          <span className="muted">{won ? "Victoria" : "Derrota"}</span>
        </div>
        <table className="grid">
          <thead>
            <tr>
              <th scope="col">Campeón</th>
              {hasSpells && <th scope="col" />}
              <th scope="col">KDA</th>
              <th scope="col">KP</th>
              <th scope="col" className="num">CS</th>
              <th scope="col" className="num">Oro</th>
              {hasDamage && <th scope="col" className="num">Daño</th>}
              {hasLevel && <th scope="col" className="num">Nv</th>}
              {hasVision && <th scope="col" className="num">Vis</th>}
              <th scope="col">Items</th>
            </tr>
          </thead>
          <tbody>
            {picks.map((p) => {
              const s = p.stats;
              return (
                <tr key={p.pick_id}>
                  <td>
                    <div className="cell-champ">
                      <ChampIcon id={p.champion.id} name={p.champion.name} size={26} />
                      {s.runes?.primary?.[0] != null && <RuneIcon id={s.runes.primary[0]} size={18} />}
                      <span className="pname">{p.player.name}</span>
                    </div>
                  </td>
                  {hasSpells && (
                    <td>
                      <div className="spells">
                        {(s.summoner_spells ?? []).map((id, i) => (
                          <SpellIcon key={i} id={id} size={18} />
                        ))}
                      </div>
                    </td>
                  )}
                  <td>
                    <span className="kda">
                      {s.kills ?? 0}/{s.deaths ?? 0}/{s.assists ?? 0}
                    </span>{" "}
                    <span className="muted">({kdaRatio(s.kills, s.deaths, s.assists)})</span>
                  </td>
                  <td>{kpPct(s.kills ?? 0, s.assists ?? 0, tk)}</td>
                  <td className="num">{s.cs ?? "—"}</td>
                  <td className="num">{s.gold != null ? s.gold.toLocaleString() : "—"}</td>
                  {hasDamage && <td className="num">{s.damage_dealt?.toLocaleString() ?? "—"}</td>}
                  {hasLevel && <td className="num">{s.champ_level ?? "—"}</td>}
                  {hasVision && <td className="num">{s.vision_score ?? "—"}</td>}
                  <td>
                    <div className="items">
                      {(s.final_items ?? []).map((id, i) => (
                        <ItemIcon key={i} id={id} size={22} />
                      ))}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="scoreboard">
      {sideBlock("BLUE", blue, blueTeam)}
      {sideBlock("RED", red, redTeam)}
    </div>
  );
}

// ------------------------------ Build / Runas ------------------------------

function BuildView({ players }: { players: Pick[] }) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const effectiveId = selectedId ?? players[0]?.pick_id ?? null;
  const selected = players.find((p) => p.pick_id === effectiveId);

  return (
    <div className="build-view">
      <div className="build-player-bar">
        {players.map((p) => (
          <button
            key={p.pick_id}
            type="button"
            className={"build-player-btn" + (p.pick_id === effectiveId ? " active" : "") + " " + p.side}
            aria-pressed={p.pick_id === effectiveId}
            onClick={() => setSelectedId(p.pick_id)}
          >
            <ChampIcon id={p.champion.id} name={p.champion.name} size={22} />
            <span>{p.player.name}</span>
          </button>
        ))}
      </div>
      {selected && <BuildCard stats={selected.stats} />}
    </div>
  );
}

// ------------------------------ root ------------------------------

export function GameDetail({
  gameId,
  team1,
  team2,
}: {
  gameId: number;
  team1?: TeamRef;
  team2?: TeamRef;
}) {
  const { data: picks, isLoading, error } = useGamePicks(gameId);

  if (isLoading) return <div className="gd-msg muted">Cargando partida…</div>;
  if (error) return <div className="gd-msg error">{(error as Error).message}</div>;
  if (!picks?.length) return <div className="gd-msg muted">Sin picks para esta partida.</div>;

  const blue = sortPlayers(picks.filter((p) => p.side === "BLUE"));
  const red = sortPlayers(picks.filter((p) => p.side === "RED"));
  const ordered = [...blue, ...red];

  return (
    <div className="game-detail">
      <Tabs
        tabs={[
          {
            id: "general",
            label: "General",
            content: <Scoreboard blue={blue} red={red} blueTeam={team1} redTeam={team2} />,
          },
          { id: "build", label: "Build", content: <BuildView players={ordered} /> },
        ]}
      />
    </div>
  );
}
