import { useState } from "react";
import { AlertTriangle } from "lucide-react";

import { useRolePicks, useRolePickMatchups, type StatsFilters } from "../api/hooks";
import type { MatchupEntry, RolePickEntry } from "../api/types";
import { ChampIcon } from "../components/icons";
import "./role-pick-section.css";

const ROLES = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"] as const;
const ROLE_LABEL: Record<string, string> = {
  TOP: "TOP",
  JUNGLE: "JGL",
  MID: "MID",
  ADC: "ADC",
  SUPPORT: "SUP",
};

function wrClass(wr: number | null): string {
  if (wr == null) return "";
  if (wr >= 55) return "rps-wr-pos";
  if (wr <= 45) return "rps-wr-neg";
  return "rps-wr-neutral";
}

// Glifo direccional: el WR no se apoya solo en verde/rojo (daltonismo).
function wrArrow(wr: number | null): string {
  if (wr == null) return "";
  if (wr >= 55) return "▲";
  if (wr <= 45) return "▼";
  return "";
}

// WR con su refuerzo no-cromático. Devuelve el % precedido del glifo cuando
// procede; «—» cuando no hay dato.
function WrValue({ wr }: { wr: number | null }) {
  if (wr == null) return <>—</>;
  const arrow = wrArrow(wr);
  return (
    <>
      {arrow && <span className="rps-wr-arrow" aria-hidden="true">{arrow}</span>}
      {wr.toFixed(1)}%
    </>
  );
}

function DetailPanel({
  champ,
  role,
  type,
  filters,
  onClose,
}: {
  champ: RolePickEntry;
  role: string;
  type: "blind" | "counter";
  filters: StatsFilters;
  onClose: () => void;
}) {
  const { data, isFetching, error } = useRolePickMatchups(champ.champ_id, role, type, filters);

  const label =
    type === "blind"
      ? `Pickeado como blind pick ${champ.games}g · WR ${champ.win_rate != null ? champ.win_rate.toFixed(1) + "%" : "—"} — Counterpicks recibidos:`
      : `Pickeado como counterpick ${champ.games}g · WR ${champ.win_rate != null ? champ.win_rate.toFixed(1) + "%" : "—"} — Blind picks respondidos:`;

  return (
    <div className="rps-detail-panel" role="region" aria-label="Detalle de matchups">
      <div className="rps-detail-header">
        <div className="rps-detail-champ">
          <ChampIcon id={champ.champ_id} name={champ.champ_name ?? ""} size={24} />
          <span className="rps-detail-name">{champ.champ_name ?? `#${champ.champ_id}`}</span>
          <span className="rps-detail-meta">{label}</span>
        </div>
        <button className="rps-detail-close" onClick={onClose} aria-label="Cerrar detalle">
          ×
        </button>
      </div>

      <div className="rps-detail-body">
        {error ? (
          <div className="rps-detail-error">
            <AlertTriangle size={14} />
            <span>No se pudieron cargar los matchups.</span>
          </div>
        ) : isFetching ? (
          <div className="rps-detail-skeleton">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="rps-skel-row" />
            ))}
          </div>
        ) : !data || data.length === 0 ? (
          <p className="rps-detail-empty">Sin matchups registrados para estos filtros.</p>
        ) : (
          <ul className="rps-matchup-list">
            {data.map((m: MatchupEntry) => (
              <li key={m.champ_id} className="rps-matchup-row">
                <ChampIcon id={m.champ_id} name={m.champ_name ?? ""} size={20} />
                <span className="rps-matchup-name">{m.champ_name ?? `#${m.champ_id}`}</span>
                <span className="rps-matchup-games">{m.games}g</span>
                <span className={"rps-matchup-wr " + wrClass(m.win_rate)}>
                  <WrValue wr={m.win_rate} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function RoleColumn({
  role,
  entries,
  initialLimit,
  selected,
  onSelect,
}: {
  role: string;
  entries: RolePickEntry[];
  initialLimit: number;
  selected: number | null;
  onSelect: (entry: RolePickEntry | null, role: string) => void;
}) {
  const [shown, setShown] = useState(initialLimit);
  const visible = entries.slice(0, shown);
  const hasMore = entries.length > shown;

  return (
    <div className="rps-col">
      <div className="rps-col-head">{ROLE_LABEL[role] ?? role}</div>
      <ul className="rps-col-list">
        {visible.map((e) => {
          const isSelected = selected === e.champ_id;
          return (
            <li
              key={e.champ_id}
              className={"rps-entry" + (isSelected ? " rps-entry--selected" : "")}
              onClick={() => onSelect(isSelected ? null : e, role)}
              role="button"
              tabIndex={0}
              onKeyDown={(ev) => ev.key === "Enter" && onSelect(isSelected ? null : e, role)}
            >
              <ChampIcon id={e.champ_id} name={e.champ_name ?? ""} size={20} />
              <span className="rps-entry-name">{e.champ_name ?? `#${e.champ_id}`}</span>
              <span className="rps-entry-meta">
                <span className="rps-entry-games">{e.games}g</span>
                <span className={"rps-entry-wr " + wrClass(e.win_rate)}>
                  <WrValue wr={e.win_rate} />
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      {hasMore && (
        <button
          className="rps-show-more"
          onClick={() => setShown((n) => n + initialLimit)}
        >
          +{Math.min(initialLimit, entries.length - shown)} más
        </button>
      )}
    </div>
  );
}

export function RolePickSection({
  type,
  filters,
  initialLimit,
}: {
  type: "blind" | "counter";
  filters: StatsFilters;
  initialLimit: number;
}) {
  const [selected, setSelected] = useState<{ champ: RolePickEntry; role: string } | null>(null);
  const { data, isFetching, error } = useRolePicks(type, filters, true);

  const title = type === "blind" ? "Blind Picks" : "Counterpicks";

  function handleSelect(entry: RolePickEntry | null, role: string) {
    setSelected((prev) =>
      prev?.champ.champ_id === entry?.champ_id && prev?.role === role
        ? null
        : entry ? { champ: entry, role } : null,
    );
  }

  return (
    <section className="rps-section">
      <h3 className="rps-title">{title}</h3>

      {error ? (
        <div className="rps-load-error">
          <AlertTriangle size={14} />
          <span>No se pudieron cargar los datos.</span>
        </div>
      ) : (
        <>
          <div className="rps-grid">
            {ROLES.map((role) => {
              const entries = data?.[role] ?? [];
              return isFetching ? (
                <div key={role} className="rps-col">
                  <div className="rps-col-head">{ROLE_LABEL[role]}</div>
                  <div className="rps-col-skel">
                    {Array.from({ length: initialLimit }).map((_, i) => (
                      <div key={i} className="rps-skel-entry" />
                    ))}
                  </div>
                </div>
              ) : entries.length === 0 ? (
                <div key={role} className="rps-col">
                  <div className="rps-col-head">{ROLE_LABEL[role]}</div>
                  <p className="rps-col-empty">Sin datos</p>
                </div>
              ) : (
                <RoleColumn
                  key={role}
                  role={role}
                  entries={entries}
                  initialLimit={initialLimit}
                  selected={
                    selected?.role === role ? selected.champ.champ_id : null
                  }
                  onSelect={handleSelect}
                />
              );
            })}
          </div>

          {selected && (
            <DetailPanel
              champ={selected.champ}
              role={selected.role}
              type={type}
              filters={filters}
              onClose={() => setSelected(null)}
            />
          )}
        </>
      )}
    </section>
  );
}
