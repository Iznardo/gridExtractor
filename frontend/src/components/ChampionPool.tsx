/**
 * Champion pool by role — component shared between Scouting and Scrims.
 *
 * The CSS classes live in pages/scouting.css (global once imported); imported
 * here so the component is self-contained wherever it is used.
 */
import { useState } from "react";

import type { ScoutPlayer } from "../api/types";
import { ChampIcon } from "./icons";
import "../pages/scouting.css";

export const ROLES = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"] as const;
export type Role = (typeof ROLES)[number];

export const ROLE_LABELS: Record<Role, string> = {
  TOP: "Top",
  JUNGLE: "Jungle",
  MID: "Mid",
  ADC: "ADC",
  SUPPORT: "Support",
};

export const CHAMP_LIMIT = 5;
export const WR_MIN_GAMES = 3;

// ---- WR display ----

export function wrColor(games: number, wins: number): string | null {
  if (games < WR_MIN_GAMES) return null;
  const wr = Math.round((wins / games) * 100);
  if (wr >= 60) return "var(--win)";
  if (wr < 40) return "var(--red)";
  return "var(--wr-mid)";
}

export function WrBar({ games, wins }: { games: number; wins: number }) {
  if (games < WR_MIN_GAMES) {
    return <span className="pool-n muted">{games} G</span>;
  }
  const wr = Math.round((wins / games) * 100);
  const color = wrColor(games, wins)!;
  return (
    <span className="pool-wr">
      <span className="wr-pct" style={{ color }}>{wr}%</span>
      <span className="wr-games">{games} G</span>
    </span>
  );
}

// ---- Skeleton ----

export function ScoutingSkeleton() {
  return (
    <div className="scout-skeleton" aria-hidden="true">
      <div className="pool-grid">
        {ROLES.map((r) => (
          <div key={r} className="pool-col">
            <div className="sk-head">
              <span className="sk-bar sk-role" />
              <span className="sk-bar sk-player" />
            </div>
            <div className="pool-champs">
              {Array.from({ length: CHAMP_LIMIT }, (_, i) => (
                <div key={i} className="pool-champ">
                  <span className="sk-icon" />
                  <span className="sk-bar sk-cn" />
                  <span className="sk-bar sk-n" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---- PoolColumn ----

export function PoolColumn({
  role,
  player,
  sectionExpanded,
}: {
  role: Role;
  player: ScoutPlayer | null;
  sectionExpanded: boolean;
}) {
  const champs = player?.champions ?? [];
  const visible = sectionExpanded ? champs : champs.slice(0, CHAMP_LIMIT);

  return (
    <div className="pool-col">
      <div className="pool-col-head">
        <span className="pool-role">{ROLE_LABELS[role]}</span>
        {player ? (
          <span className="pool-player">{player.player.name}</span>
        ) : (
          <span className="pool-player muted">—</span>
        )}
      </div>
      {player ? (
        <div className="pool-champs">
          {visible.map((ch) => {
            const color = wrColor(ch.games, ch.wins);
            return (
              <div
                key={ch.champion.id}
                className="pool-champ"
                style={color ? { background: `color-mix(in srgb, ${color} 9%, transparent)` } : undefined}
              >
                <ChampIcon id={ch.champion.id} name={ch.champion.name} size={20} />
                <span className="pool-cn">{ch.champion.name}</span>
                <WrBar games={ch.games} wins={ch.wins} />
              </div>
            );
          })}
        </div>
      ) : (
        <p className="pool-empty muted">No games</p>
      )}
    </div>
  );
}

// ---- MediumBox (grid + expand toggle) ----

export function MediumBox({ players }: { players: ScoutPlayer[] }) {
  const [expanded, setExpanded] = useState(false);
  const hasMore = players.some((p) => (p.champions?.length ?? 0) > CHAMP_LIMIT);

  function playerForRole(role: string): ScoutPlayer | null {
    return players.find((p) => p.player.role === role) ?? null;
  }

  return (
    <>
      <div className="pool-grid">
        {ROLES.map((role) => (
          <PoolColumn
            key={role}
            role={role}
            player={playerForRole(role)}
            sectionExpanded={expanded}
          />
        ))}
      </div>
      {hasMore && (
        <div className="pool-expand-footer">
          <button
            type="button"
            className="pool-expand-toggle"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "Collapse" : "Show all"}
          </button>
        </div>
      )}
    </>
  );
}
