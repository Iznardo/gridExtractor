import { useMemo, useRef, useState } from "react";
import { AlertTriangle, SearchX } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import {
  useMatchups,
  usePatches,
  useTournaments,
  type MatchupFilters,
} from "../api/hooks";
import { BuildCard } from "../components/BuildCard";
import { ChampionPicker } from "../components/ChampionPicker";
import { TournamentPicker } from "../components/TournamentPicker";
import { ReplayButton } from "../components/ReplayButton";
import { Field, FilterBar } from "../components/Field";
import { ChampIcon, ItemIcon, RuneIcon } from "../components/icons";
import { useChampMaps } from "../lib/champs";
import type { Matchup, MatchupSide } from "../api/types";
import "./matchups.css";
import "../pages/drafts.css"; // empty/skeleton styles

function numParam(v: string | null): number | undefined {
  if (!v) return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

// ---- componentes de fila ----

function SideBlock({
  side,
  flip,
}: {
  side: MatchupSide;
  flip?: boolean; // opponent — layout espejado, icono flanquea el VS por la derecha
}) {
  const won = side.result === true;
  const lost = side.result === false;
  const items = side.stats?.final_items ?? [];
  const kda = side.stats
    ? `${side.stats.kills ?? 0}/${side.stats.deaths ?? 0}/${side.stats.assists ?? 0}`
    : null;

  const icon = <ChampIcon id={side.champion.id} name={side.champion.name} size={32} />;

  const champBlock = (
    <div className="mu-champ-block">
      <span className="mu-champ-name">{side.champion.name}</span>
      {side.player && (
        <span className="mu-player-name">{side.player.name}</span>
      )}
      {side.pick_relation && (
        <span className={"mu-badge " + side.pick_relation}>{side.pick_relation}</span>
      )}
    </div>
  );

  const keystone = side.stats?.runes?.primary?.[0];

  const statsBlock = (
    <div className="mu-stats">
      {keystone != null && <RuneIcon id={keystone} size={16} />}
      {kda !== null ? (
        <span
          className={"mu-kda" + (won ? " won" : lost ? " lost" : "")}
          title={won ? "Victoria" : lost ? "Derrota" : undefined}
        >
          {kda}
          {side.result !== null && (
            <span className="mu-result-glyph" aria-hidden> {won ? "W" : "L"}</span>
          )}
        </span>
      ) : (
        <span className="mu-kda" style={{ color: "var(--muted)" }}>—</span>
      )}
      {items.length > 0 ? (
        <div className="mu-items">
          {items.slice(0, 6).map((id, i) => (
            <ItemIcon key={i} id={id} size={22} />
          ))}
        </div>
      ) : (
        <div className="mu-items-empty" />
      )}
    </div>
  );

  if (flip) {
    // Oponente (derecha): [Icono flanqueando VS] [Stats] [Nombre]
    return (
      <div className="mu-side opponent">
        {icon}
        {statsBlock}
        {champBlock}
      </div>
    );
  }

  // Focal (izquierda): [Nombre] [Stats] [Icono flanqueando VS]
  return (
    <div className="mu-side focal">
      {champBlock}
      {statsBlock}
      {icon}
    </div>
  );
}

function MatchupRow({ m }: { m: Matchup }) {
  const [open, setOpen] = useState(false);
  const { pick, opponent, role, date, version, tournament, game_type } = m;

  return (
    <div className={"mu-row" + (open ? " expanded" : "")}>
      <div
        className="mu-summary"
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setOpen((v) => !v)}
      >
        <div className="mu-match">
          <SideBlock side={pick} />

          <div className="mu-center">
            <span className="mu-vs">VS</span>
          </div>

          {opponent ? (
            <SideBlock side={opponent} flip />
          ) : (
            <div className="mu-side opponent">
              <span className="mu-no-opponent">sin rival en datos</span>
            </div>
          )}
        </div>

        <div className="mu-meta">
          {role && <span className="mu-role">{role}</span>}
          {role && <span className="mu-meta-sep">·</span>}
          <span>{date}</span>
          {tournament && (
            <>
              <span className="mu-meta-sep">·</span>
              <span>{tournament}</span>
            </>
          )}
          {version && (
            <>
              <span className="mu-meta-sep">·</span>
              <span>{version}</span>
            </>
          )}
          <span className="mu-type">{game_type}</span>
          <span className="mu-meta-actions">
            {game_type !== "SOLOQ" && <ReplayButton gameId={m.game_id} />}
            <span className="mu-expand" aria-hidden>{open ? "▲" : "▼"}</span>
          </span>
        </div>
      </div>

      {open && (
        <div className="mu-detail">
          <div className="mu-builds">
            <div className="mu-build-col">
              <div className="mu-build-header">
                <ChampIcon id={pick.champion.id} name={pick.champion.name} size={22} />
                <span>{pick.player?.name ?? pick.champion.name}</span>
                <span className={"pill " + pick.side}>{pick.side}</span>
              </div>
              <BuildCard stats={pick.stats} />
            </div>

            {opponent && (
              <div className="mu-build-col">
                <div className="mu-build-header">
                  <ChampIcon
                    id={opponent.champion.id}
                    name={opponent.champion.name}
                    size={22}
                  />
                  <span>{opponent.player?.name ?? opponent.champion.name}</span>
                  {opponent.side && (
                    <span className={"pill " + opponent.side}>{opponent.side}</span>
                  )}
                </div>
                {opponent.stats ? (
                  <BuildCard stats={opponent.stats} />
                ) : (
                  <div className="mu-no-data">Sin datos del rival</div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function MatchupSkeleton() {
  return (
    <>
      {Array.from({ length: 8 }, (_, i) => (
        <div key={i} className="mu-skeleton-row">
          <div className="mu-skel" style={{ height: 36, width: "100%" }} />
          <div className="mu-skel" style={{ height: 14, width: "40%" }} />
        </div>
      ))}
    </>
  );
}

// ---- página ----

const LIMIT_DEFAULT = 50;
const ROLES = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"];

export function Matchups() {
  const { byName, list: champList } = useChampMaps();
  const { data: tournaments } = useTournaments();
  const { data: patches } = usePatches();
  const [searchParams, setSearchParams] = useSearchParams();
  const focalRef = useRef<HTMLInputElement>(null);
  const rivalRef = useRef<HTMLInputElement>(null);

  const [focal, setFocal] = useState(() => searchParams.get("champ") ?? "");
  const [rival, setRival] = useState(() => searchParams.get("champ2") ?? "");
  const [role, setRole] = useState(() => searchParams.get("role") ?? "");
  const [relation, setRelation] = useState(() => searchParams.get("relation") ?? "");
  const [tournament, setTournament] = useState(() => searchParams.get("tournament") ?? "");
  const [patch, setPatch] = useState(() => searchParams.get("patch") ?? "");
  const [gameType, setGameType] = useState(() => searchParams.get("type") ?? "");
  const [formError, setFormError] = useState("");

  const applied = useMemo<MatchupFilters>(() => {
    const fName = searchParams.get("champ")?.trim().toLowerCase();
    const rName = searchParams.get("champ2")?.trim().toLowerCase();
    return {
      champ_id: fName ? byName.get(fName) : undefined,
      champ_id2: rName ? byName.get(rName) : undefined,
      role: searchParams.get("role") || undefined,
      pick_relation: (searchParams.get("relation") || undefined) as MatchupFilters["pick_relation"],
      tournament: searchParams.get("tournament") || undefined,
      patch: searchParams.get("patch") || undefined,
      game_type: searchParams.get("type") || undefined,
      limit: numParam(searchParams.get("limit")) ?? LIMIT_DEFAULT,
    };
  }, [searchParams, byName]);

  const { data: matchups, isFetching, error, refetch } = useMatchups(applied);

  function submit(e?: React.FormEvent) {
    e?.preventDefault();
    setFormError("");

    if (focal.trim() && byName.get(focal.trim().toLowerCase()) == null) {
      setFormError(`Campeón no reconocido: "${focal}".`);
      focalRef.current?.focus();
      return;
    }
    if (rival.trim() && byName.get(rival.trim().toLowerCase()) == null) {
      setFormError(`Campeón no reconocido: "${rival}".`);
      rivalRef.current?.focus();
      return;
    }

    const next: Record<string, string> = {};
    if (focal.trim()) next.champ = focal.trim();
    if (rival.trim()) next.champ2 = rival.trim();
    if (role) next.role = role;
    if (relation) next.relation = relation;
    if (tournament) next.tournament = tournament;
    if (patch) next.patch = patch;
    if (gameType) next.type = gameType;
    // limit se resetea al aplicar nuevos filtros
    setSearchParams(next);
  }

  function loadMore() {
    const currentLimit = numParam(searchParams.get("limit")) ?? LIMIT_DEFAULT;
    const next = new URLSearchParams(searchParams);
    next.set("limit", String(currentLimit + 50));
    setSearchParams(next);
  }

  function clearFilters() {
    setFocal(""); setRival(""); setRole(""); setRelation("");
    setTournament(""); setPatch(""); setGameType("");
    setFormError("");
    setSearchParams({});
  }

  // Chips de filtros activos
  const activeChips = [
    searchParams.get("champ") && { key: "champ", label: `Campeón: ${searchParams.get("champ")}` },
    searchParams.get("champ2") && { key: "champ2", label: `vs: ${searchParams.get("champ2")}` },
    searchParams.get("role") && { key: "role", label: `Rol: ${searchParams.get("role")}` },
    searchParams.get("relation") && { key: "relation", label: searchParams.get("relation")! },
    searchParams.get("tournament") && { key: "tournament", label: searchParams.get("tournament")! },
    searchParams.get("patch") && { key: "patch", label: `Parche ${searchParams.get("patch")}` },
    searchParams.get("type") && { key: "type", label: searchParams.get("type")! },
  ].filter(Boolean) as { key: string; label: string }[];

  function removeChip(key: string) {
    const map: Record<string, () => void> = {
      champ: () => setFocal(""),
      champ2: () => setRival(""),
      role: () => setRole(""),
      relation: () => setRelation(""),
      tournament: () => setTournament(""),
      patch: () => setPatch(""),
      type: () => setGameType(""),
    };
    map[key]?.();
    const next = new URLSearchParams(searchParams);
    next.delete(key === "champ2" ? "champ2" : key);
    setSearchParams(next);
  }

  const hasFilters = activeChips.length > 0;
  const isLoading = isFetching && !matchups;
  const atLimit = (matchups?.length ?? 0) >= (applied.limit ?? LIMIT_DEFAULT);

  return (
    <div className="page matchups-page">
      <FilterBar onSubmit={() => submit()}>
        {/* Grupo primario: campeón focal, rival, carril */}
        <Field label="Campeón focal">
          <ChampionPicker
            value={focal}
            onChange={setFocal}
            champions={champList}
            placeholder="ej. Aatrox"
            hasError={formError.startsWith("Campeón no reconocido") && formError.includes(`"${focal}"`)}
            inputRef={focalRef}
          />
        </Field>
        <Field label="vs Rival">
          <ChampionPicker
            value={rival}
            onChange={setRival}
            champions={champList}
            placeholder="cualquiera"
            hasError={formError.startsWith("Campeón no reconocido") && formError.includes(`"${rival}"`)}
            inputRef={rivalRef}
          />
        </Field>
        <Field label="Rol">
          <select value={role} onChange={(e) => setRole(e.target.value)} style={{ minWidth: 110 }}>
            <option value="">Todos</option>
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </Field>

        <div className="filter-divider" aria-hidden="true" />

        {/* Grupo secundario: tipo de pick, contexto */}
        <Field label="Blind / Counter">
          <select value={relation} onChange={(e) => setRelation(e.target.value)} style={{ minWidth: 110 }}>
            <option value="">Cualquiera</option>
            <option value="blind" title="Pickado antes que el rival de carril">Blind</option>
            <option value="counter" title="Pickado después que el rival de carril">Counter</option>
          </select>
        </Field>
        <Field label="Torneo">
          <TournamentPicker value={tournament} onChange={setTournament} tournaments={tournaments ?? []} />
        </Field>
        <Field label="Parche">
          <select value={patch} onChange={(e) => setPatch(e.target.value)} style={{ minWidth: 100 }}>
            <option value="">Todos</option>
            {(patches ?? []).map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </Field>
        <Field label="Tipo">
          <select value={gameType} onChange={(e) => setGameType(e.target.value)} style={{ minWidth: 100 }}>
            <option value="">Todos</option>
            <option value="OFFICIAL">Oficial</option>
            <option value="SCRIM">Scrim</option>
            <option value="SOLOQ">SoloQ</option>
          </select>
        </Field>

        <button type="submit" className="btn-primary">Buscar</button>
        {hasFilters && (
          <button type="button" className="btn-ghost" onClick={clearFilters}>
            Limpiar
          </button>
        )}
      </FilterBar>

      {formError && <p className="field-error">{formError}</p>}

      {activeChips.length > 0 && (
        <div className="filter-chips">
          {activeChips.map(({ key, label }) => (
            <span key={key} className="filter-chip">
              {label}
              <button
                type="button"
                className="filter-chip-clear"
                aria-label={`Quitar filtro ${label}`}
                onClick={() => removeChip(key)}
              >
                ×
              </button>
            </span>
          ))}
          <button type="button" className="btn-ghost btn-ghost-sm" onClick={clearFilters}>
            × limpiar
          </button>
        </div>
      )}

      {matchups && matchups.length > 0 && (
        <div className="mu-count-bar">
          <span>
            {atLimit
              ? `${matchups.length}+ picks`
              : `${matchups.length} pick${matchups.length !== 1 ? "s" : ""}`}
          </span>
          {atLimit && (
            <button type="button" className="btn-ghost btn-ghost-sm" onClick={loadMore}>
              Ver más
            </button>
          )}
        </div>
      )}

      <div className="mu-list">
        {isLoading ? (
          <MatchupSkeleton />
        ) : error ? (
          <div className="empty">
            <AlertTriangle className="empty-icon" size={36} />
            <p className="empty-title">Error al cargar</p>
            <p className="empty-sub">{(error as Error).message}</p>
            <button type="button" className="btn-ghost" onClick={() => refetch()}>
              Reintentar
            </button>
          </div>
        ) : matchups && matchups.length === 0 ? (
          <div className="empty">
            {hasFilters ? (
              <>
                <SearchX className="empty-icon" size={36} />
                <p className="empty-title">Sin resultados</p>
                <p className="empty-sub">Ningún pick coincide con los filtros aplicados.</p>
                <button type="button" className="btn-ghost" onClick={clearFilters}>
                  Limpiar filtros
                </button>
              </>
            ) : (
              <>
                <SearchX className="empty-icon" size={36} />
                <p className="empty-title">Sin datos</p>
                <p className="empty-sub">No hay picks en la base de datos todavía.</p>
              </>
            )}
          </div>
        ) : (
          (matchups ?? []).map((m) => (
            <MatchupRow key={`${m.game_id}-${m.pick.player?.id ?? m.pick.champion.id}`} m={m} />
          ))
        )}
      </div>
    </div>
  );
}
