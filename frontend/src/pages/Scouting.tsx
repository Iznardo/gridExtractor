import { useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { useScouting, useTeams, type StatsFilters } from "../api/hooks";
import type { Medium, ScoutingPool } from "../api/types";
import { MediumBox, ScoutingSkeleton } from "../components/ChampionPool";
import { Field, FilterBar } from "../components/Field";
import { SourceChips } from "../components/SourceChips";
import { Tabs } from "../components/Tabs";
import { TeamPicker } from "../components/TeamPicker";
import { useScoutingContextSync } from "../lib/scoutingContext";
import { RolePickSection } from "./RolePickSection";
import { ScoutDashboard } from "./ScoutDashboard";
import { TeamMatchups } from "./TeamMatchups";
import { aggAsScoutPlayers, buildAggregate } from "./scouting/aggregate";
import "./scouting.css";

// ---- constants ----

const ALL_MEDIUMS: Medium[] = ["official", "scrim", "soloq"];
const MEDIUM_LABELS: Record<Medium, string> = {
  official: "Official",
  scrim: "Scrims",
  soloq: "SoloQ",
};

// Champion-pool sub-tabs (inside the "Pool" window).
type TabId = "official" | "scrim" | "soloq" | "aggregate";

// Top-level Scouting windows (?view=). "dashboard" is the initial one.
const VIEW_IDS = ["dashboard", "pool", "matchups", "blindcounter"] as const;

// Pool aggregation (buildAggregate/aggAsScoutPlayers) lives in
// ./scouting/aggregate — shared with the Dashboard.

// ---- AggregateBox (sources + MediumBox) ----

function AggregateBox({
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
      <SourceChips all={ALL_MEDIUMS} labels={MEDIUM_LABELS} active={sources} onToggle={onToggle} />
      <MediumBox players={aggPlayers} />
    </>
  );
}

// ---- draft tabs (Matchups, Blind/Counter): OFFICIAL + SCRIM only ----

const DRAFT_MEDIUMS: Medium[] = ["official", "scrim"];
const MEDIUM_TO_GAME_TYPE: Record<Medium, string> = {
  official: "OFFICIAL",
  scrim: "SCRIM",
  soloq: "SOLOQ",
};

function DraftTab({
  teamId,
  dateFrom,
  sources,
  onToggle,
  children,
}: {
  teamId: number;
  dateFrom?: string;
  sources: Set<Medium>;
  onToggle: (m: Medium) => void;
  children: (filters: StatsFilters) => ReactNode;
}) {
  const filters: StatsFilters = {
    team_id: teamId,
    game_types: DRAFT_MEDIUMS.filter((m) => sources.has(m))
      .map((m) => MEDIUM_TO_GAME_TYPE[m])
      .join(","),
    date_from: dateFrom,
  };
  return (
    <>
      <SourceChips all={DRAFT_MEDIUMS} labels={MEDIUM_LABELS} active={sources} onToggle={onToggle} />
      {children(filters)}
    </>
  );
}

// ---- Scouting ----

export function Scouting() {
  const { data: teams } = useTeams();
  const [params, setParams] = useSearchParams();

  // Scouting context: Scouting controls only the team (no patch); `undefined`
  // keeps the context patch set in Drafts/Games.
  useScoutingContextSync(params.get("team") ?? "", undefined);

  const [teamId, setTeamId] = useState(() => params.get("team") ?? "");
  const [dateFrom, setDateFrom] = useState(() => params.get("dateFrom") ?? "");
  const [submitError, setSubmitError] = useState("");

  const activeTab = (params.get("tab") as TabId) ?? "official";
  const viewParam = params.get("view");
  const activeView = (VIEW_IDS as readonly string[]).includes(viewParam ?? "")
    ? (viewParam as (typeof VIEW_IDS)[number])
    : "dashboard";
  const appliedTeamId = params.get("team") ? Number(params.get("team")) : null;
  const appliedDateFrom = params.get("dateFrom") || undefined;

  // Aggregate sources persisted in the URL (?sources=official,scrim,soloq)
  const sourcesParam = params.get("sources");
  const activeSources: Set<Medium> = sourcesParam
    ? new Set(sourcesParam.split(",").filter((s): s is Medium => (ALL_MEDIUMS as string[]).includes(s)))
    : new Set(ALL_MEDIUMS);

  // Draft-tab sources (?dsources=official,scrim) — no soloq.
  const dsourcesParam = params.get("dsources");
  const draftSources: Set<Medium> = dsourcesParam
    ? new Set(dsourcesParam.split(",").filter((s): s is Medium => (DRAFT_MEDIUMS as string[]).includes(s)))
    : new Set(DRAFT_MEDIUMS);

  const { data: pool, isFetching, error, refetch } = useScouting(appliedTeamId, { dateFrom: appliedDateFrom });

  function submit() {
    if (!teamId) {
      setSubmitError("Select a team before scouting.");
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

  function handleViewChange(id: string) {
    const next = new URLSearchParams(params);
    if (id === "dashboard") next.delete("view"); // default state, keep URL clean
    else next.set("view", id);
    setParams(next);
  }

  function toggleSource(m: Medium) {
    if (activeSources.has(m) && activeSources.size === 1) return;
    const next = new Set(activeSources);
    if (next.has(m)) next.delete(m); else next.add(m);
    const nextParams = new URLSearchParams(params);
    if (next.size === ALL_MEDIUMS.length) {
      nextParams.delete("sources"); // default state, keep URL clean
    } else {
      nextParams.set("sources", Array.from(next).join(","));
    }
    setParams(nextParams);
  }

  function toggleDraftSource(m: Medium) {
    if (draftSources.has(m) && draftSources.size === 1) return;
    const next = new Set(draftSources);
    if (next.has(m)) next.delete(m); else next.add(m);
    const nextParams = new URLSearchParams(params);
    if (next.size === DRAFT_MEDIUMS.length) {
      nextParams.delete("dsources"); // default state, keep URL clean
    } else {
      nextParams.set("dsources", Array.from(next).join(","));
    }
    setParams(nextParams);
  }

  // Champion-pool sub-tabs (sources), inside the "Pool" window.
  const poolTabs = [
    {
      id: "official",
      label: "Official",
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
      id: "aggregate",
      label: activeSources.size < ALL_MEDIUMS.length
        ? `Aggregate (${activeSources.size}/${ALL_MEDIUMS.length})`
        : "Aggregate",
      content: pool ? <AggregateBox pool={pool} sources={activeSources} onToggle={toggleSource} /> : null,
    },
  ];

  // "Pool" window content: skeleton while loading, then the tabs box.
  const poolWindow = isFetching ? (
    <ScoutingSkeleton />
  ) : pool ? (
    <div className="scout-box">
      <Tabs tabs={poolTabs} value={activeTab} onChange={handleTabChange} />
    </div>
  ) : null;

  // Top-level windows. Matchups and Blind/Counter are independent of the pool
  // (their own load); OFFICIAL+SCRIM only (no soloq).
  const windowTabs = [
    {
      id: "dashboard",
      label: "Dashboard",
      content: appliedTeamId != null ? <ScoutDashboard teamId={appliedTeamId} /> : null,
    },
    { id: "pool", label: "Champion pool", content: poolWindow },
    {
      id: "matchups",
      label: "Matchups",
      content: appliedTeamId != null ? (
        <DraftTab teamId={appliedTeamId} dateFrom={appliedDateFrom} sources={draftSources} onToggle={toggleDraftSource}>
          {(filters) => <TeamMatchups filters={filters} />}
        </DraftTab>
      ) : null,
    },
    {
      id: "blindcounter",
      label: "Blind/Counter",
      content: appliedTeamId != null ? (
        <DraftTab teamId={appliedTeamId} dateFrom={appliedDateFrom} sources={draftSources} onToggle={toggleDraftSource}>
          {(filters) => (
            <>
              <RolePickSection type="blind" filters={filters} initialLimit={10} />
              <RolePickSection type="counter" filters={filters} initialLimit={5} />
            </>
          )}
        </DraftTab>
      ) : null,
    },
  ];

  return (
    <div className="page">
      <FilterBar onSubmit={submit}>
        <Field label="Team *">
          <TeamPicker value={teamId} onChange={setTeamId} teams={teams ?? []} />
        </Field>
        <Field label="From date">
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </Field>
        <button
          type="submit"
          className="btn-primary"
          disabled={!teamId}
          title={!teamId ? "Select a team first" : undefined}
        >
          Scout
        </button>
      </FilterBar>

      {submitError && (
        <p className="field-error" role="alert">
          {submitError}
        </p>
      )}

      <p
        className={"status" + (error && activeView === "pool" ? " error" : "")}
        role="status"
        aria-live="polite"
      >
        {appliedTeamId == null
          ? "Pick a team to start."
          : activeView === "pool" && error
            ? <>{(error as Error).message} <button type="button" className="btn-ghost btn-ghost-sm" onClick={() => refetch()}>Retry</button></>
            : activeView === "pool" && isFetching
              ? "Loading…"
              : " "}
      </p>

      {appliedTeamId != null && (
        <div className="scout-results">
          <Tabs tabs={windowTabs} value={activeView} onChange={handleViewChange} />
        </div>
      )}
    </div>
  );
}
