import type { Pick, Side } from "../api/types";
import { useGamePicks } from "../api/hooks";
import { ChampIcon, ItemIcon, RuneIcon, RuneStyleIcon, SpellIcon } from "../components/icons";
import { Tabs } from "../components/Tabs";
import { kdaRatio, kpPct, mmss } from "../lib/format";
import "./gamedetail.css";

const ROLE_RANK: Record<string, number> = {
  TOP: 0,
  JUNGLE: 1,
  MIDDLE: 2,
  BOTTOM: 3,
  UTILITY: 4,
};

function sortPlayers(picks: Pick[]): Pick[] {
  return [...picks].sort((a, b) => {
    const ra = a.stats.team_position ? ROLE_RANK[a.stats.team_position] ?? 9 : 9;
    const rb = b.stats.team_position ? ROLE_RANK[b.stats.team_position] ?? 9 : 9;
    if (ra !== rb) return ra - rb;
    return (a.pick_order ?? 0) - (b.pick_order ?? 0);
  });
}

function teamKills(picks: Pick[]): number {
  return picks.reduce((s, p) => s + (p.stats.kills ?? 0), 0);
}

// ----------------------------- General -----------------------------

function Scoreboard({ blue, red }: { blue: Pick[]; red: Pick[] }) {
  const all = [...blue, ...red];
  const hasDamage = all.some((p) => p.stats.damage_dealt != null);
  const hasSpells = all.some((p) => p.stats.summoner_spells?.length);
  const hasLevel = all.some((p) => p.stats.champ_level != null);
  const hasVision = all.some((p) => p.stats.vision_score != null);

  function sideBlock(side: Side, picks: Pick[]) {
    const tk = teamKills(picks);
    const won = picks[0]?.result;
    return (
      <div className="sb-block">
        <div className="sb-side">
          <span className={"pill " + side}>{side}</span>
          <span className={"muted"}>{won ? "Victoria" : "Derrota"}</span>
        </div>
        <table className="grid">
          <thead>
            <tr>
              <th>Campeón</th>
              {hasSpells && <th />}
              <th>KDA</th>
              <th>KP</th>
              <th className="num">CS</th>
              <th className="num">Oro</th>
              {hasDamage && <th className="num">Daño</th>}
              {hasLevel && <th className="num">Nv</th>}
              {hasVision && <th className="num">Vis</th>}
              <th>Items</th>
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
      {sideBlock("BLUE", blue)}
      {sideBlock("RED", red)}
    </div>
  );
}

// ------------------------------ Runas ------------------------------

function RunesView({ players }: { players: Pick[] }) {
  return (
    <div className="runes-grid">
      {players.map((p) => {
        const r = p.stats.runes;
        if (!r) {
          return (
            <div key={p.pick_id} className="rune-card">
              <ChampIcon id={p.champion.id} name={p.champion.name} size={32} />
              <span className="muted">sin runas</span>
            </div>
          );
        }
        return (
          <div key={p.pick_id} className="rune-card">
            <div className="rc-head">
              <ChampIcon id={p.champion.id} name={p.champion.name} size={32} />
              <span className="pname">{p.player.name}</span>
            </div>
            <div className="rc-row primary">
              {r.primary.map((id, i) => (
                <RuneIcon key={i} id={id} size={i === 0 ? 30 : 22} />
              ))}
            </div>
            <div className="rc-row">
              <RuneStyleIcon id={r.sub_style} size={18} />
              {r.sub.map((id, i) => (
                <RuneIcon key={i} id={id} size={22} />
              ))}
            </div>
            <div className="rc-row shards">
              {r.stat_perks.map((id, i) => (
                <RuneIcon key={i} id={id} size={16} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ------------------------------ Build ------------------------------

const SKILLS = ["Q", "W", "E", "R"] as const;

function SkillGrid({ order }: { order: string }) {
  const letters = order.toUpperCase().split("").filter((c) => "QWER".includes(c));
  const levels = letters.length;
  return (
    <div className="skillgrid">
      {SKILLS.map((skill) => (
        <div key={skill} className="sg-row">
          <span className="sg-key">{skill}</span>
          {Array.from({ length: levels }, (_, i) => {
            const hit = letters[i] === skill;
            return (
              <span key={i} className={"sg-cell" + (hit ? " hit " + skill : "")}>
                {hit ? i + 1 : ""}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function BuildView({ players }: { players: Pick[] }) {
  return (
    <div className="build-list">
      {players.map((p) => {
        const buys = (p.stats.build_path ?? []).filter((b) => b.action === "BUY");
        return (
          <div key={p.pick_id} className="build-card">
            <div className="bc-head">
              <ChampIcon id={p.champion.id} name={p.champion.name} size={28} />
              <span className="pname">{p.player.name}</span>
            </div>

            {buys.length > 0 ? (
              <div className="build-order">
                {buys.map((b, i) => (
                  <span key={i} className="bo-item">
                    <ItemIcon id={b.item_id} size={26} />
                    <span className="bo-ts">{mmss(b.ts_s)}</span>
                  </span>
                ))}
              </div>
            ) : (
              <span className="muted">sin build order</span>
            )}

            {p.stats.skill_order ? (
              <SkillGrid order={p.stats.skill_order} />
            ) : (
              <span className="muted">sin skill order</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ------------------------------ root ------------------------------

export function GameDetail({ gameId }: { gameId: number }) {
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
          { id: "general", label: "General", content: <Scoreboard blue={blue} red={red} /> },
          { id: "runes", label: "Runas", content: <RunesView players={ordered} /> },
          { id: "build", label: "Build", content: <BuildView players={ordered} /> },
        ]}
      />
    </div>
  );
}
