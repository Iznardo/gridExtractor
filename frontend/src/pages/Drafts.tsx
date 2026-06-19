import { useMemo, useRef, useState } from "react";
import { AlertTriangle, SearchX } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { useDrafts, useTeams, useTournaments, type DraftFilters, type StatsFilters } from "../api/hooks";
import { ChampionPicker } from "../components/ChampionPicker";
import { Field, FilterBar } from "../components/Field";
import { Tabs } from "../components/Tabs";
import { TeamPicker } from "../components/TeamPicker";
import { TournamentPicker } from "../components/TournamentPicker";
import { useChampMaps } from "../lib/champs";
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

  // El formulario se inicializa desde la URL: un link compartido pre-rellena
  // los filtros y lanza la misma búsqueda.
  const [teamId, setTeamId] = useState(() => params.get("team") ?? "");
  const [rivalId, setRivalId] = useState(() => params.get("rival") ?? "");
  const [gameType, setGameType] = useState(() => params.get("type") ?? "");
  const [phase, setPhase] = useState(() => params.get("phase") ?? "");
  const [champ, setChamp] = useState(() => params.get("champ") ?? "");
  const [patch, setPatch] = useState(() => params.get("patch") ?? "");
  const [tournament, setTournament] = useState(() => params.get("tournament") ?? "");
  const [limit, setLimit] = useState(() => params.get("limit") ?? LIMIT_DEFAULT);
  const [formError, setFormError] = useState("");

  // El tab activo vive en la URL para que sea compartible.
  const view = params.get("view") ?? "drafts";

  // La búsqueda activa vive en la URL (única fuente de verdad → compartible).
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

  // Filtros para las tabs de stats: igual que applied pero sin champ_id ni limit.
  const statsApplied = useMemo<StatsFilters>(() => ({
    team_id: applied.team_id,
    rival_id: applied.rival_id,
    game_type: applied.game_type,
    pick_phase: applied.pick_phase,
    patch: applied.patch,
    tournament: applied.tournament,
  }), [applied.team_id, applied.rival_id, applied.game_type, applied.pick_phase, applied.patch, applied.tournament]);

  const { data: drafts, isFetching, error, refetch } = useDrafts(applied, view === "drafts");

  // Indica si el error actual es específicamente del campo campeón.
  const champError = formError.startsWith("Campeón");

  function handleViewChange(v: string) {
    const next: Record<string, string> = { ...Object.fromEntries(params) };
    if (v === "drafts") delete next.view;
    else next.view = v;
    setParams(next);
  }

  function submit() {
    setFormError("");
    if (phase && !teamId) {
      setFormError("La fase de pick requiere seleccionar un equipo.");
      return;
    }
    if (champ.trim() && byName.get(champ.trim().toLowerCase()) == null) {
      setFormError(`Campeón no reconocido: "${champ}". Elige uno de la lista.`);
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
    if (params.get("rival")) out.push(`rival ${teamName(params.get("rival")!)}`);
    if (params.get("type")) out.push(params.get("type")!.toLowerCase());
    if (params.get("phase")) out.push(`${params.get("phase")} pick`);
    if (params.get("champ")) out.push(`«${params.get("champ")}»`);
    if (params.get("patch")) out.push(`parche ${params.get("patch")}`);
    if (params.get("tournament")) out.push(params.get("tournament")!);
    if (params.get("limit")) out.push(`${params.get("limit")} partidas`);
    return out;
  }

  let results;
  if (error) {
    results = (
      <div className="empty">
        <AlertTriangle size={22} className="empty-icon" style={{ color: "var(--red)" }} />
        <p className="empty-title">No se pudieron cargar los drafts.</p>
        <p className="empty-sub">{(error as Error).message}</p>
        <button type="button" className="btn-ghost" onClick={() => refetch()}>
          Reintentar
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
        <p className="empty-title">Sin drafts para estos filtros.</p>
        <p className="empty-sub">
          {hasFilters
            ? `Ningún draft coincide con ${labels.join(" · ")}. Prueba a relajar un filtro.`
            : "Todavía no hay drafts en la base de datos."}
        </p>
        {hasFilters && (
          <button type="button" className="btn-ghost" onClick={clearFilters}>
            Limpiar filtros
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
        <Field label="Equipo">
          <TeamPicker value={teamId} onChange={setTeamId} teams={teams ?? []} />
        </Field>
        <Field label="Rival">
          <TeamPicker value={rivalId} onChange={setRivalId} teams={teams ?? []} />
        </Field>
        <Field label="Tipo">
          <select value={gameType} onChange={(e) => setGameType(e.target.value)}>
            <option value="">(todos)</option>
            <option value="OFFICIAL">Oficiales</option>
            <option value="SCRIM">Scrims</option>
          </select>
        </Field>
        <Field label="Torneo">
          <TournamentPicker value={tournament} onChange={setTournament} tournaments={tournaments ?? []} />
        </Field>
        <Field label="Fase de pick">
          <select value={phase} onChange={(e) => setPhase(e.target.value)}>
            <option value="">(cualquiera)</option>
            <option value="first">First pick</option>
            <option value="second">Second pick</option>
          </select>
        </Field>
        <Field label="Campeón jugado">
          <ChampionPicker
            value={champ}
            onChange={(v) => { setChamp(v); setFormError(""); }}
            champions={champList}
            hasError={champError}
            inputRef={champRef}
          />
        </Field>
        <Field label="Parche">
          <input value={patch} onChange={(e) => setPatch(e.target.value)} placeholder="14.23" size={8} />
        </Field>
        <Field label="Mostrar">
          <select value={limit} onChange={(e) => setLimit(e.target.value)}>
            <option value="20">20</option>
            <option value="50">50</option>
            <option value="100">100</option>
            <option value="200">200</option>
          </select>
        </Field>
        <button type="submit" className="btn-primary">Buscar</button>
        {hasFilters && (
          <button type="button" className="btn-ghost" onClick={clearFilters}>Limpiar</button>
        )}
      </FilterBar>

      {/* Chip row: sticky, visible cuando hay filtros activos. Ancla el contexto
          de búsqueda mientras el analista scrollea el grid. */}
      {hasFilters && (
        <div className="filter-chips" aria-label="Filtros activos">
          {activeFilterLabels().map((label, i) => (
            <span key={i} className="filter-chip">{label}</span>
          ))}
          <button type="button" className="filter-chip-clear" onClick={clearFilters}>
            × limpiar
          </button>
        </div>
      )}

      {/* Error de formulario (campo inválido) — canal separado del status de carga. */}
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
                <p className={"status" + (error ? " error" : "")} role="status" aria-live="polite">
                  {error ? "Error al cargar." : isFetching ? "Buscando…" : `${drafts?.length ?? 0} drafts.`}
                </p>
                {results}
              </>
            ),
          },
          {
            id: "presencia",
            label: "Presencia",
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
