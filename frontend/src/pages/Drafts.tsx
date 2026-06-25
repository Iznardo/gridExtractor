import { useMemo, useRef, useState } from "react";
import { AlertTriangle, SearchX } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { useDrafts, useTeams, useTournaments, type DraftFilters, type StatsFilters } from "../api/hooks";
import { ChampionPicker } from "../components/ChampionPicker";
import { Field, FilterBar } from "../components/Field";
import { Select } from "../components/Select";
import { Tabs } from "../components/Tabs";
import { TeamPicker } from "../components/TeamPicker";
import { TournamentPicker } from "../components/TournamentPicker";
import { useChampMaps } from "../lib/champs";
import { useScoutingContextSync } from "../lib/scoutingContext";
import { ChampionPresence } from "./ChampionPresence";
import { DraftBoard, DraftBoardSkeleton } from "./DraftBoard";
import { PickOrderStats } from "./PickOrderStats";
import "./drafts.css";

function numParam(v: string | null): number | undefined {
  if (!v) return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

const SKELETON_COUNT = 8;
const LIMIT_DEFAULT = "50";

export function Drafts() {
  const { data: teams } = useTeams();
  const { data: tournaments } = useTournaments();
  const { byName, list: champList } = useChampMaps();
  const [params, setParams] = useSearchParams();
  const champRef = useRef<HTMLInputElement>(null);

  // Shared scouting context: carries the applied team+patch.
  useScoutingContextSync(params.get("team") ?? "", params.get("patch") ?? "");

  // The form is seeded from the URL: a shared link pre-fills the filters and
  // runs the same search.
  const [teamId, setTeamId] = useState(() => params.get("team") ?? "");
  const [rivalId, setRivalId] = useState(() => params.get("rival") ?? "");
  const [gameType, setGameType] = useState(() => params.get("type") ?? "");
  const [phase, setPhase] = useState(() => params.get("phase") ?? "");
  const [champ, setChamp] = useState(() => params.get("champ") ?? "");
  const [patch, setPatch] = useState(() => params.get("patch") ?? "");
  const [tournament, setTournament] = useState(() => params.get("tournament") ?? "");
  const [limit, setLimit] = useState(() => params.get("limit") ?? LIMIT_DEFAULT);
  const [formError, setFormError] = useState("");

  // The active tab lives in the URL so it is shareable.
  const view = params.get("view") ?? "drafts";

  // The active search lives in the URL (single source of truth -> shareable).
  const applied = useMemo<DraftFilters>(() => {
    const champName = params.get("champ")?.trim().toLowerCase();
    return {
      team_id: numParam(params.get("team")),
      rival_id: numParam(params.get("rival")),
      game_type: params.get("type") || undefined,
      pick_phase: (params.get("phase") || undefined) as DraftFilters["pick_phase"],
      champ_id: champName ? byName.get(champName) : undefined,
      patch: params.get("patch")?.trim() || undefined,
      tournament: params.get("tournament") || undefined,
      limit: numParam(params.get("limit")) ?? 50,
    };
  }, [params, byName]);

  // Filters for the stats tabs: same as applied but without champ_id or limit.
  const statsApplied = useMemo<StatsFilters>(() => ({
    team_id: applied.team_id,
    rival_id: applied.rival_id,
    game_type: applied.game_type,
    pick_phase: applied.pick_phase,
    patch: applied.patch,
    tournament: applied.tournament,
  }), [applied.team_id, applied.rival_id, applied.game_type, applied.pick_phase, applied.patch, applied.tournament]);

  const { data: drafts, isFetching, error, refetch } = useDrafts(applied, view === "drafts");

  // Whether the current error is specifically about the champion field.
  const champError = formError.startsWith("Unrecognized champion");

  function handleViewChange(v: string) {
    const next: Record<string, string> = { ...Object.fromEntries(params) };
    if (v === "drafts") delete next.view;
    else next.view = v;
    setParams(next);
  }

  function submit() {
    setFormError("");
    if (phase && !teamId) {
      setFormError("Pick phase requires selecting a team.");
      return;
    }
    if (champ.trim() && byName.get(champ.trim().toLowerCase()) == null) {
      setFormError(`Unrecognized champion: "${champ}". Pick one from the list.`);
      champRef.current?.focus();
      return;
    }
    const next: Record<string, string> = {};
    if (view !== "drafts") next.view = view;
    if (teamId) next.team = teamId;
    if (rivalId) next.rival = rivalId;
    if (gameType) next.type = gameType;
    if (phase) next.phase = phase;
    if (champ.trim()) next.champ = champ.trim();
    if (patch.trim()) next.patch = patch.trim();
    if (tournament) next.tournament = tournament;
    if (limit && limit !== LIMIT_DEFAULT) next.limit = limit;
    setParams(next);
  }

  function clearFilters() {
    setTeamId("");
    setRivalId("");
    setGameType("");
    setPhase("");
    setChamp("");
    setPatch("");
    setTournament("");
    setLimit(LIMIT_DEFAULT);
    setFormError("");
    const next: Record<string, string> = {};
    if (view !== "drafts") next.view = view;
    setParams(next);
  }

  const hasFilters = [...params.keys()].some((k) => k !== "view");

  function activeFilterLabels(): string[] {
    const teamName = (id: string) => teams?.find((t) => String(t.id) === id)?.name ?? `#${id}`;
    const out: string[] = [];
    if (params.get("team")) out.push(teamName(params.get("team")!));
    if (params.get("rival")) out.push(`vs ${teamName(params.get("rival")!)}`);
    if (params.get("type")) out.push(params.get("type")!.toLowerCase());
    if (params.get("phase")) out.push(`${params.get("phase")} pick`);
    if (params.get("champ")) out.push(`«${params.get("champ")}»`);
    if (params.get("patch")) out.push(`patch ${params.get("patch")}`);
    if (params.get("tournament")) out.push(params.get("tournament")!);
    if (params.get("limit")) out.push(`${params.get("limit")} games`);
    return out;
  }

  let results;
  if (error) {
    results = (
      <div className="empty">
        <AlertTriangle size={22} className="empty-icon" style={{ color: "var(--red)" }} />
        <p className="empty-title">Could not load the drafts.</p>
        <p className="empty-sub">{(error as Error).message}</p>
        <button type="button" className="btn-ghost" onClick={() => refetch()}>
          Retry
        </button>
      </div>
    );
  } else if (isFetching) {
    results = (
      <div className="draft-grid" aria-hidden="true">
        {Array.from({ length: SKELETON_COUNT }).map((_, i) => (
          <DraftBoardSkeleton key={i} />
        ))}
      </div>
    );
  } else if (drafts && drafts.length === 0) {
    const labels = activeFilterLabels();
    results = (
      <div className="empty">
        <SearchX size={22} className="empty-icon" />
        <p className="empty-title">No drafts for these filters.</p>
        <p className="empty-sub">
          {hasFilters
            ? `No draft matches ${labels.join(" · ")}. Try relaxing a filter.`
            : "No drafts in the database yet."}
        </p>
        {hasFilters && (
          <button type="button" className="btn-ghost" onClick={clearFilters}>
            Clear filters
          </button>
        )}
      </div>
    );
  } else {
    results = (
      <div className="draft-grid results">
        {(drafts ?? []).map((d) => (
          <DraftBoard key={d.game_id} d={d} />
        ))}
      </div>
    );
  }

  return (
    <div className="page">
      <FilterBar onSubmit={submit}>
        <Field label="Team">
          <TeamPicker value={teamId} onChange={setTeamId} teams={teams ?? []} />
        </Field>
        <Field label="Rival">
          <TeamPicker value={rivalId} onChange={setRivalId} teams={teams ?? []} />
        </Field>
        <Field label="Type">
          <Select
            value={gameType}
            onChange={setGameType}
            ariaLabel="Type"
            options={[
              { value: "", label: "(all)" },
              { value: "OFFICIAL", label: "Official" },
              { value: "SCRIM", label: "Scrims" },
            ]}
          />
        </Field>
        <Field label="Tournament">
          <TournamentPicker value={tournament} onChange={setTournament} tournaments={tournaments ?? []} />
        </Field>
        <Field label="Pick phase">
          <Select
            value={phase}
            onChange={setPhase}
            ariaLabel="Pick phase"
            options={[
              { value: "", label: "(any)" },
              { value: "first", label: "First pick" },
              { value: "second", label: "Second pick" },
            ]}
          />
        </Field>
        <Field label="Champion played">
          <ChampionPicker
            value={champ}
            onChange={(v) => { setChamp(v); setFormError(""); }}
            champions={champList}
            hasError={champError}
            inputRef={champRef}
          />
        </Field>
        <Field label="Patch">
          <input value={patch} onChange={(e) => setPatch(e.target.value)} placeholder="14.23" size={8} />
        </Field>
        <Field label="Show">
          <Select
            value={limit}
            onChange={setLimit}
            ariaLabel="Show"
            options={[
              { value: "20", label: "20" },
              { value: "50", label: "50" },
              { value: "100", label: "100" },
              { value: "200", label: "200" },
            ]}
          />
        </Field>
        <button type="submit" className="btn-primary">Search</button>
        {hasFilters && (
          <button type="button" className="btn-ghost" onClick={clearFilters}>Clear</button>
        )}
      </FilterBar>

      {/* Chip row: sticky, visible when there are active filters. Anchors the
          search context while the analyst scrolls the grid. */}
      {hasFilters && (
        <div className="filter-chips" aria-label="Active filters">
          {activeFilterLabels().map((label, i) => (
            <span key={i} className="filter-chip">{label}</span>
          ))}
          <button type="button" className="filter-chip-clear" onClick={clearFilters}>
            × clear
          </button>
        </div>
      )}

      {/* Form error (invalid field) — separate channel from the load status. */}
      {formError && (
        <p className="field-error" role="alert">{formError}</p>
      )}

      <Tabs
        value={view}
        onChange={handleViewChange}
        tabs={[
          {
            id: "drafts",
            label: "Drafts",
            content: (
              <>
                {/* Transient feedback only: the "N drafts" counter is redundant
                    since the user picks the limit in the "Show" filter. */}
                {(isFetching || error) && (
                  <p className={"status" + (error ? " error" : "")} role="status" aria-live="polite">
                    {error ? "Failed to load." : "Searching…"}
                  </p>
                )}
                {results}
              </>
            ),
          },
          {
            id: "presence",
            label: "Presence",
            content: <ChampionPresence filters={statsApplied} teamId={applied.team_id} />,
          },
          {
            id: "pick-order",
            label: "Pick Order",
            content: <PickOrderStats filters={statsApplied} />,
          },
        ]}
      />
    </div>
  );
}
