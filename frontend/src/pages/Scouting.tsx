import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useScouting, useTeams } from "../api/hooks";
import type { Medium, ScoutPlayer, ScoutingPool } from "../api/types";
import { Field, FilterBar } from "../components/Field";
import { ChampIcon } from "../components/icons";
import { Tabs } from "../components/Tabs";
import { TeamPicker } from "../components/TeamPicker";
import "./scouting.css";

// ---- constantes ----

const ROLES = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"] as const;
type Role = (typeof ROLES)[number];

const ROLE_LABELS: Record<Role, string> = {
  TOP: "Top",
  JUNGLE: "Jungle",
  MID: "Mid",
  ADC: "ADC",
  SUPPORT: "Support",
};

const ALL_MEDIUMS: Medium[] = ["official", "scrim", "soloq"];
const MEDIUM_LABELS: Record<Medium, string> = {
  official: "Oficiales",
  scrim: "Scrims",
  soloq: "SoloQ",
};

const CHAMP_LIMIT = 5;
const WR_MIN_GAMES = 3;

const TAB_IDS = ["oficial", "scrim", "soloq", "agregado"] as const;
type TabId = (typeof TAB_IDS)[number];

// ---- agregado ----

type AggCount = { games: number; wins: number };
type AggChamp = {
  champion: { id: number; name: string };
  total: AggCount;
};
type AggPlayer = { player: ScoutPlayer["player"]; champions: AggChamp[] };

function buildAggregate(pool: ScoutingPool, sources: Medium[] = ALL_MEDIUMS): AggPlayer[] {
  const players = new Map<
    number,
    { player: ScoutPlayer["player"]; champs: Map<number, AggChamp> }
  >();
  for (const medium of sources) {
    for (const p of pool.by_medium[medium]) {
      const entry = players.get(p.player.id) ?? {
        player: p.player,
        champs: new Map<number, AggChamp>(),
      };
      for (const ch of p.champions) {
        const c = entry.champs.get(ch.champion.id) ?? {
          champion: ch.champion,
          total: { games: 0, wins: 0 },
        };
        c.total.games += ch.games;
        c.total.wins += ch.wins;
        entry.champs.set(ch.champion.id, c);
      }
      players.set(p.player.id, entry);
    }
  }
  return Array.from(players.values()).map((e) => ({
    player: e.player,
    champions: Array.from(e.champs.values()).sort(
      (a, b) => b.total.games - a.total.games || a.champion.name.localeCompare(b.champion.name),
    ),
  }));
}

function aggAsScoutPlayers(agg: AggPlayer[]): ScoutPlayer[] {
  return agg.map((ap) => ({
    player: ap.player,
    champions: ap.champions.map((ch) => ({
      champion: ch.champion,
      games: ch.total.games,
      wins: ch.total.wins,
    })),
  }));
}

// ---- WR display ----

function wrColor(games: number, wins: number): string | null {
  if (games < WR_MIN_GAMES) return null;
  const wr = Math.round((wins / games) * 100);
  if (wr >= 60) return "var(--win)";
  if (wr < 40) return "var(--red)";
  return "var(--wr-mid)";
}

function WrBar({ games, wins }: { games: number; wins: number }) {
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

function ScoutingSkeleton() {
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

function PoolColumn({
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
        <p className="pool-empty muted">Sin partidas</p>
      )}
    </div>
  );
}

// ---- MediumBox (grid + expand toggle) ----

function MediumBox({ players }: { players: ScoutPlayer[] }) {
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
            {expanded ? "Colapsar" : "Ver todo"}
          </button>
        </div>
      )}
    </>
  );
}

// ---- AggregadoBox (fuentes + MediumBox) ----

function AggregadoBox({
  pool,
  sources,
  onToggle,
}: {
  pool: ScoutingPool;
  sources: Set<Medium>;
  onToggle: (m: Medium) => void;
}) {
  const aggPlayers = useMemo(
    () => aggAsScoutPlayers(buildAggregate(pool, Array.from(sources))),
    [pool, sources],
  );

  return (
    <>
      <div className="agg-source-bar">
        <span className="agg-source-label">Fuentes:</span>
        {ALL_MEDIUMS.map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={sources.has(m)}
            className={"agg-chip" + (sources.has(m) ? " active" : "")}
            onClick={() => onToggle(m)}
          >
            {MEDIUM_LABELS[m]}
          </button>
        ))}
        {sources.size < ALL_MEDIUMS.length && (
          <span className="agg-partial-notice">
            Mostrando {sources.size}/{ALL_MEDIUMS.length} fuentes
          </span>
        )}
      </div>
      <MediumBox players={aggPlayers} />
    </>
  );
}

// ---- Scouting ----

export function Scouting() {
  const { data: teams } = useTeams();
  const [params, setParams] = useSearchParams();

  const [teamId, setTeamId] = useState(() => params.get("team") ?? "");
  const [dateFrom, setDateFrom] = useState(() => params.get("dateFrom") ?? "");
  const [submitError, setSubmitError] = useState("");

  const activeTab = (params.get("tab") as TabId) ?? "oficial";
  const appliedTeamId = params.get("team") ? Number(params.get("team")) : null;
  const appliedDateFrom = params.get("dateFrom") || undefined;

  // Fuentes del Agregado persistidas en URL (?sources=official,scrim,soloq)
  const sourcesParam = params.get("sources");
  const activeSources: Set<Medium> = sourcesParam
    ? new Set(sourcesParam.split(",").filter((s): s is Medium => (ALL_MEDIUMS as string[]).includes(s)))
    : new Set(ALL_MEDIUMS);

  const { data: pool, isFetching, error, refetch } = useScouting(appliedTeamId, appliedDateFrom);

  function submit() {
    if (!teamId) {
      setSubmitError("Selecciona un equipo antes de scoutear.");
      return;
    }
    setSubmitError("");
    const next = new URLSearchParams(params);
    next.set("team", teamId);
    next.set("tab", activeTab);
    if (dateFrom) next.set("dateFrom", dateFrom);
    else next.delete("dateFrom");
    setParams(next);
  }

  function handleTabChange(id: string) {
    const next = new URLSearchParams(params);
    next.set("tab", id);
    setParams(next);
  }

  function toggleSource(m: Medium) {
    if (activeSources.has(m) && activeSources.size === 1) return;
    const next = new Set(activeSources);
    next.has(m) ? next.delete(m) : next.add(m);
    const nextParams = new URLSearchParams(params);
    if (next.size === ALL_MEDIUMS.length) {
      nextParams.delete("sources"); // estado por defecto, no ensuciar URL
    } else {
      nextParams.set("sources", Array.from(next).join(","));
    }
    setParams(nextParams);
  }

  const tabs = [
    {
      id: "oficial",
      label: "Oficiales",
      content: pool ? <MediumBox players={pool.by_medium.official} /> : null,
    },
    {
      id: "scrim",
      label: "Scrims",
      content: pool ? <MediumBox players={pool.by_medium.scrim} /> : null,
    },
    {
      id: "soloq",
      label: "SoloQ",
      content: pool ? <MediumBox players={pool.by_medium.soloq} /> : null,
    },
    {
      id: "agregado",
      label: activeSources.size < ALL_MEDIUMS.length
        ? `Agregado (${activeSources.size}/${ALL_MEDIUMS.length})`
        : "Agregado",
      content: pool ? <AggregadoBox pool={pool} sources={activeSources} onToggle={toggleSource} /> : null,
    },
  ];

  return (
    <div className="page">
      <FilterBar onSubmit={submit}>
        <Field label="Equipo *">
          <TeamPicker value={teamId} onChange={setTeamId} teams={teams ?? []} />
        </Field>
        <Field label="Desde fecha">
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </Field>
        <button
          type="submit"
          className="btn-primary"
          disabled={!teamId}
          title={!teamId ? "Selecciona un equipo primero" : undefined}
        >
          Scoutear
        </button>
      </FilterBar>

      {submitError && (
        <p className="field-error" role="alert">
          {submitError}
        </p>
      )}

      <p
        className={"status" + (error ? " error" : "")}
        role="status"
        aria-live="polite"
      >
        {error
          ? <>{(error as Error).message} <button type="button" className="btn-ghost btn-ghost-sm" onClick={() => refetch()}>Reintentar</button></>
          : appliedTeamId == null
            ? "Elige un equipo para empezar."
            : isFetching
              ? "Cargando…"
              : " "}
      </p>

      {isFetching && appliedTeamId != null && <ScoutingSkeleton />}

      {pool && appliedTeamId != null && !isFetching && (
        <div className="scout-results">
          <div className="scout-box">
            <Tabs tabs={tabs} value={activeTab} onChange={handleTabChange} />
          </div>
        </div>
      )}
    </div>
  );
}
