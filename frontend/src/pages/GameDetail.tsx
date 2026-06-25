import { useState } from "react";
import type { Pick, Side, TeamRef } from "../api/types";
import { useGamePicks } from "../api/hooks";
import { BuildCard } from "../components/BuildCard";
import { ChampIcon, ItemIcon, RuneIcon, SpellIcon } from "../components/icons";
import { Tabs } from "../components/Tabs";
import { kdaRatio } from "../lib/format";
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

function fmtGoldDiff(diff: number): string {
  return (diff >= 0 ? "+" : "") + diff.toLocaleString();
}

function goldDiffClass(diff: number): string {
  return diff > 0 ? "gd-pos" : diff < 0 ? "gd-neg" : "";
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
  const hasMidgame = all.some((p) => p.stats.midgame != null);
  const durationS = all.find((p) => p.game_duration_s != null)?.game_duration_s ?? null;
  const durationMin = durationS != null ? durationS / 60 : null;

  function sideBlock(side: Side, picks: Pick[], opponents: Pick[], team?: TeamRef) {
    const won = picks[0]?.result;
    const teamDmg = hasDamage
      ? picks.reduce((s, p) => s + (p.stats.damage_dealt ?? 0), 0)
      : 0;
    const teamGold = picks.reduce((s, p) => s + (p.stats.gold ?? 0), 0);

    return (
      <div className="sb-block">
        <div className="sb-side">
          <span className={"pill " + side}>{side}</span>
          {team && <span className="sb-team">{team.tag ?? team.name}</span>}
          <span className="muted">{won ? "Win" : "Loss"}</span>
        </div>
        <table className="grid">
          <thead>
            <tr>
              <th scope="col">Champion</th>
              {hasSpells && <th scope="col" />}
              <th scope="col">KDA</th>
              <th scope="col" className="num">CS</th>
              <th scope="col" className="num" title="% of team total gold">Gold%</th>
              {hasDamage && <th scope="col" className="num" title="% of team total damage">Damage%</th>}
              {hasDamage && durationMin != null && <th scope="col" className="num">DPM</th>}
              {durationMin != null && <th scope="col" className="num">CS/min</th>}
              {hasMidgame && <th scope="col" className="num" title="Gold diff vs laner at 7 min">GD@7</th>}
              {hasMidgame && <th scope="col" className="num" title="Gold diff vs laner at 14 min">GD@14</th>}
              {hasLevel && <th scope="col" className="num">Lvl</th>}
              {hasVision && <th scope="col" className="num">Vis</th>}
              <th scope="col">Items</th>
            </tr>
          </thead>
          <tbody>
            {picks.map((p, i) => {
              const s = p.stats;
              const opp = opponents[i];

              const goldPct = teamGold > 0 && s.gold != null
                ? ((s.gold / teamGold) * 100).toFixed(0) + "%"
                : "—";
              const dmgPct = hasDamage && teamDmg > 0 && s.damage_dealt != null
                ? ((s.damage_dealt / teamDmg) * 100).toFixed(0) + "%"
                : "—";
              const dpm = durationMin != null && s.damage_dealt != null
                ? Math.round(s.damage_dealt / durationMin).toLocaleString()
                : "—";
              const csMin = durationMin != null && s.cs != null
                ? (s.cs / durationMin).toFixed(1)
                : "—";

              const pg7  = s.midgame?.["7"]?.gold ?? null;
              const pg14 = s.midgame?.["14"]?.gold ?? null;
              const og7  = opp?.stats.midgame?.["7"]?.gold ?? null;
              const og14 = opp?.stats.midgame?.["14"]?.gold ?? null;
              const gd7  = pg7 != null && og7 != null ? pg7 - og7 : null;
              const gd14 = pg14 != null && og14 != null ? pg14 - og14 : null;

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
                  <td className="num">{s.cs ?? "—"}</td>
                  <td className="num" title={s.gold != null ? s.gold.toLocaleString() : undefined}>
                    {goldPct}
                  </td>
                  {hasDamage && (
                    <td className="num" title={s.damage_dealt != null ? s.damage_dealt.toLocaleString() : undefined}>
                      {dmgPct}
                    </td>
                  )}
                  {hasDamage && durationMin != null && <td className="num">{dpm}</td>}
                  {durationMin != null && <td className="num">{csMin}</td>}
                  {hasMidgame && (
                    <td className={`num ${gd7 != null ? goldDiffClass(gd7) : ""}`}>
                      {gd7 != null ? fmtGoldDiff(gd7) : "—"}
                    </td>
                  )}
                  {hasMidgame && (
                    <td className={`num ${gd14 != null ? goldDiffClass(gd14) : ""}`}>
                      {gd14 != null ? fmtGoldDiff(gd14) : "—"}
                    </td>
                  )}
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
      {sideBlock("BLUE", blue, red, blueTeam)}
      {sideBlock("RED", red, blue, redTeam)}
    </div>
  );
}

// ------------------------------ Build / Runes ------------------------------

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

// ------------------------------ skeleton ------------------------------

function GameDetailSkeleton() {
  return (
    <div className="game-detail">
      <span className="sr-only" role="status">Loading game…</span>
      <div className="scoreboard" aria-hidden="true">
        {["BLUE", "RED"].map((side) => (
          <div key={side} className="sb-block">
            <div className="sb-side">
              <span className="sk-line" style={{ width: 46, height: 16 }} />
              <span className="sk-line" style={{ width: 84, height: 11 }} />
            </div>
            <div className="gd-sk-table">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="gd-sk-row">
                  <span className="sk-chip" />
                  <span className="sk-line gd-sk-name" />
                  <span className="sk-line" style={{ width: 34, height: 8 }} />
                  <span className="sk-line" style={{ width: 26, height: 8 }} />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
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

  if (isLoading) return <GameDetailSkeleton />;
  if (error) return <div className="gd-msg error">{(error as Error).message}</div>;
  if (!picks?.length) return <div className="gd-msg muted">No picks for this game.</div>;

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
