import { useState } from "react";
import { AlertTriangle } from "lucide-react";

import { useTeamMatchups, type StatsFilters } from "../api/hooks";
import type { BaselineEntry, TeamMatchupEntry } from "../api/types";
import { ChampIcon } from "../components/icons";
import "./team-matchups.css";

const ROLES = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"] as const;
const ROLE_LABEL: Record<string, string> = {
  TOP: "TOP",
  JUNGLE: "JGL",
  MID: "MID",
  ADC: "ADC",
  SUPPORT: "SUP",
};

// Mínimo de partidas para fiarse de un WR (coherente con la pool de scouting).
const WR_MIN_GAMES = 3;
const COL_LIMIT = 10;

function wrClass(wr: number | null, games: number): string {
  if (wr == null || games < WR_MIN_GAMES) return "tm-wr-neutral";
  if (wr >= 55) return "tm-wr-pos";
  if (wr <= 45) return "tm-wr-neg";
  return "tm-wr-neutral";
}

// Glifo direccional no-cromático (daltonismo) — coherente con el resto del front.
function wrArrow(wr: number | null, games: number): string {
  if (wr == null || games < WR_MIN_GAMES) return "";
  if (wr >= 55) return "▲";
  if (wr <= 45) return "▼";
  return "";
}

function WrValue({ wr, games }: { wr: number | null; games: number }) {
  if (wr == null) return <>—</>;
  const arrow = wrArrow(wr, games);
  return (
    <>
      {arrow && <span className="tm-wr-arrow" aria-hidden="true">{arrow}</span>}
      {wr.toFixed(0)}%
    </>
  );
}

// Referencia "resto": el WR del campeón en ese rol contra los DEMÁS rivales,
// obtenido restando la fila del matchup al baseline (rol, campeón). Excluye el
// propio enfrentamiento y es role-specific. `otherWr` se muestra si hay ≥1
// partida; el `delta` solo se da si ambos lados tienen muestra suficiente.
function restAndDelta(entry: TeamMatchupEntry, roleBase: BaselineEntry | undefined) {
  if (!roleBase) return { otherGames: 0, otherWr: null as number | null, delta: null as number | null };
  const otherGames = roleBase.games - entry.games;
  const otherWins = roleBase.wins - entry.wins;
  const otherWr = otherGames > 0 ? Math.round((100 * otherWins) / otherGames * 10) / 10 : null;
  const delta =
    entry.win_rate != null && otherWr != null &&
    entry.games >= WR_MIN_GAMES && otherGames >= WR_MIN_GAMES
      ? Math.round((entry.win_rate - otherWr) * 10) / 10
      : null;
  return { otherGames, otherWr, delta };
}

function MatchupEntryRow({
  entry,
  roleBase,
  roleLabel,
}: {
  entry: TeamMatchupEntry;
  roleBase: BaselineEntry | undefined;
  roleLabel: string;
}) {
  const { otherGames, otherWr, delta } = restAndDelta(entry, roleBase);
  const ourName = entry.our_champ_name ?? `#${entry.our_champ_id}`;
  const oppName = entry.opp_champ_name ?? `#${entry.opp_champ_id}`;

  const ariaLabel =
    `${ourName} vs ${oppName}: ${entry.games} partidas` +
    (entry.win_rate != null ? `, ${entry.win_rate.toFixed(0)}% WR` : "") +
    (delta != null
      ? `. Diferencia con ${ourName} en ${roleLabel} contra el resto de rivales: ${delta > 0 ? "+" : ""}${delta}%`
      : "");

  return (
    <li className="tm-entry" tabIndex={0} aria-label={ariaLabel}>
      <div className="tm-entry-main">
        <div className="tm-side tm-our">
          <ChampIcon id={entry.our_champ_id} name={entry.our_champ_name ?? ""} size={20} />
          <span className="tm-champ-name">{ourName}</span>
        </div>
        <div className="tm-side tm-opp">
          <span className="tm-vs">vs</span>
          <ChampIcon id={entry.opp_champ_id} name={entry.opp_champ_name ?? ""} size={18} />
          <span className="tm-champ-name tm-opp-name">{oppName}</span>
          <span className="tm-meta">
            <span className="tm-games">{entry.games}g</span>
            <span className={"tm-wr " + wrClass(entry.win_rate, entry.games)}>
              <WrValue wr={entry.win_rate} games={entry.games} />
            </span>
          </span>
        </div>
      </div>

      {/* Popover de delta — visible en hover/focus. Texto ya cubierto por aria-label. */}
      <div className="tm-pop" role="presentation">
        <div className="tm-pop-row">
          <span className="tm-pop-label">Este matchup</span>
          <span className="tm-pop-val">
            {entry.win_rate != null ? `${entry.win_rate.toFixed(0)}%` : "—"} · {entry.games}g
          </span>
        </div>
        <div className="tm-pop-row">
          <span className="tm-pop-label">{ourName} en {roleLabel} · resto</span>
          <span className="tm-pop-val">
            {otherWr != null ? `${otherWr.toFixed(0)}% · ${otherGames}g` : "—"}
          </span>
        </div>
        <div className="tm-pop-delta">
          {delta != null ? (
            <span className={delta > 0 ? "tm-wr-pos" : delta < 0 ? "tm-wr-neg" : "tm-wr-neutral"}>
              {delta > 0 && <span aria-hidden="true">▲</span>}
              {delta < 0 && <span aria-hidden="true">▼</span>}
              {" Δ "}
              {delta > 0 ? "+" : ""}
              {delta}%
            </span>
          ) : (
            <span className="tm-wr-neutral">Δ — (muestra insuficiente)</span>
          )}
        </div>
      </div>
    </li>
  );
}

function Column({
  role,
  entries,
  roleBaseline,
  loading,
}: {
  role: string;
  entries: TeamMatchupEntry[];
  roleBaseline: Record<number, BaselineEntry>;
  loading: boolean;
}) {
  const roleLabel = ROLE_LABEL[role] ?? role;
  const [shown, setShown] = useState(COL_LIMIT);
  const visible = entries.slice(0, shown);
  const hasMore = entries.length > shown;

  return (
    <div className="tm-col">
      <div className="tm-col-head">{roleLabel}</div>
      {loading ? (
        <div className="tm-col-skel">
          {Array.from({ length: COL_LIMIT }).map((_, i) => (
            <div key={i} className="tm-skel-entry" />
          ))}
        </div>
      ) : entries.length === 0 ? (
        <p className="tm-col-empty">Sin datos</p>
      ) : (
        <>
          <ul className="tm-col-list">
            {visible.map((e) => (
              <MatchupEntryRow
                key={`${e.our_champ_id}-${e.opp_champ_id}`}
                entry={e}
                roleBase={roleBaseline[e.our_champ_id]}
                roleLabel={roleLabel}
              />
            ))}
          </ul>
          {hasMore && (
            <button
              type="button"
              className="tm-show-more"
              onClick={() => setShown((n) => n + COL_LIMIT)}
            >
              +{Math.min(COL_LIMIT, entries.length - shown)} más
            </button>
          )}
        </>
      )}
    </div>
  );
}

export function TeamMatchups({ filters }: { filters: StatsFilters }) {
  const { data, isFetching, error } = useTeamMatchups(filters, true);

  if (error) {
    return (
      <div className="tm-load-error">
        <AlertTriangle size={14} />
        <span>No se pudieron cargar los matchups.</span>
      </div>
    );
  }

  return (
    <div className="tm-grid">
      {ROLES.map((role) => (
        <Column
          key={role}
          role={role}
          entries={data?.matchups[role] ?? []}
          roleBaseline={data?.baseline?.[role] ?? {}}
          loading={isFetching}
        />
      ))}
    </div>
  );
}
