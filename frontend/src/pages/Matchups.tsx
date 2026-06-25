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
import { Select } from "../components/Select";
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

// ---- row components ----

function SideBlock({
  side,
  flip,
}: {
  side: MatchupSide;
  flip?: boolean; // opponent — mirrored layout, icon flanks the VS on the right
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
          title={won ? "Win" : lost ? "Loss" : undefined}
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
    // Opponent (right): [Icon flanking VS] [Stats] [Name]
    return (
      <div className="mu-side opponent">
        {icon}
        {statsBlock}
        {champBlock}
      </div>
    );
  }

  // Focal (left): [Name] [Stats] [Icon flanking VS]
  return (
    <div className="mu-side focal">
      {champBlock}
      {statsBlock}
      {icon}
    </div>
  );
}

// A side can be a single pick (1v1) or a stacked duo (2v2).
function SideStack({
  primary,
  secondary,
  flip,
}: {
  primary: MatchupSide | null;
  secondary?: MatchupSide | null;
  flip?: boolean;
}) {
  if (!primary) {
    return (
      <div className={"mu-side " + (flip ? "opponent" : "focal")}>
        <span className="mu-no-opponent">no opponent in data</span>
      </div>
    );
  }
  if (secondary === undefined) {
    // 1v1 mode: a single block
    return <SideBlock side={primary} flip={flip} />;
  }
  return (
    <div className={"mu-duo" + (flip ? " opponent" : "")}>
      <SideBlock side={primary} flip={flip} />
      {secondary ? (
        <SideBlock side={secondary} flip={flip} />
      ) : (
        <div className={"mu-side " + (flip ? "opponent" : "focal")}>
          <span className="mu-no-opponent">no opponent in data</span>
        </div>
      )}
    </div>
  );
}

function BuildCol({ side }: { side: MatchupSide }) {
  return (
    <div className="mu-build-col">
      <div className="mu-build-header">
        <ChampIcon id={side.champion.id} name={side.champion.name} size={22} />
        <span>{side.player?.name ?? side.champion.name}</span>
        {side.side && <span className={"pill " + side.side}>{side.side}</span>}
      </div>
      {side.stats ? <BuildCard stats={side.stats} /> : <div className="mu-no-data">No opponent data</div>}
    </div>
  );
}

function MatchupRow({ m }: { m: Matchup }) {
  const [open, setOpen] = useState(false);
  const { pick, opponent, pick_ally, opponent_ally, role, date, version, tournament, game_type } = m;
  const is2v2 = pick_ally != null;

  // Detail builds: focal (+ ally in 2v2) | opponents with stats.
  const buildSides: MatchupSide[] = [pick];
  if (pick_ally) buildSides.push(pick_ally);
  if (opponent) buildSides.push(opponent);
  if (opponent_ally) buildSides.push(opponent_ally);

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
          <SideStack primary={pick} secondary={is2v2 ? pick_ally : undefined} />

          <div className="mu-center">
            <span className="mu-vs">VS</span>
          </div>

          <SideStack
            primary={opponent}
            secondary={is2v2 ? opponent_ally : undefined}
            flip
          />
        </div>

        <div className="mu-meta">
          {role && !is2v2 && <span className="mu-role">{role}</span>}
          {role && !is2v2 && <span className="mu-meta-sep">·</span>}
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
          <div className={"mu-builds" + (buildSides.length > 2 ? " quad" : "")}>
            {buildSides.map((side, i) => (
              <BuildCol key={i} side={side} />
            ))}
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

// ---- page ----

const LIMIT_DEFAULT = 50;
const ROLES = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"];
const ROLE_OPTIONS = [{ value: "", label: "All" }, ...ROLES.map((r) => ({ value: r, label: r }))];

export function Matchups() {
  const { byName, list: champList } = useChampMaps();
  const { data: tournaments } = useTournaments();
  const { data: patches } = usePatches();
  const [searchParams, setSearchParams] = useSearchParams();
  const focalRef = useRef<HTMLInputElement>(null);
  const rivalRef = useRef<HTMLInputElement>(null);
  const allyBRef = useRef<HTMLInputElement>(null);
  const rivalBRef = useRef<HTMLInputElement>(null);

  const [mode, setMode] = useState<"1v1" | "2v2">(() =>
    searchParams.get("mode") === "2v2" ? "2v2" : "1v1",
  );
  const [focal, setFocal] = useState(() => searchParams.get("champ") ?? "");
  const [rival, setRival] = useState(() => searchParams.get("champ2") ?? "");
  const [allyB, setAllyB] = useState(() => searchParams.get("champ_b") ?? "");
  const [rivalB, setRivalB] = useState(() => searchParams.get("champ2_b") ?? "");
  const [role, setRole] = useState(() => searchParams.get("role") ?? "");
  const [roleB, setRoleB] = useState(() => searchParams.get("role_b") ?? "");
  const [relation, setRelation] = useState(() => searchParams.get("relation") ?? "");
  const [tournament, setTournament] = useState(() => searchParams.get("tournament") ?? "");
  const [patch, setPatch] = useState(() => searchParams.get("patch") ?? "");
  const [gameType, setGameType] = useState(() => searchParams.get("type") ?? "");
  const [formError, setFormError] = useState("");

  const applied = useMemo<MatchupFilters>(() => {
    const is2v2 = searchParams.get("mode") === "2v2";
    const fName = searchParams.get("champ")?.trim().toLowerCase();
    const rName = searchParams.get("champ2")?.trim().toLowerCase();
    const aName = searchParams.get("champ_b")?.trim().toLowerCase();
    const rbName = searchParams.get("champ2_b")?.trim().toLowerCase();
    return {
      champ_id: fName ? byName.get(fName) : undefined,
      champ_id2: rName ? byName.get(rName) : undefined,
      champ_id_b: is2v2 && aName ? byName.get(aName) : undefined,
      champ_id2_b: is2v2 && rbName ? byName.get(rbName) : undefined,
      role: searchParams.get("role") || undefined,
      role_b: is2v2 ? searchParams.get("role_b") || undefined : undefined,
      pick_relation: is2v2
        ? undefined
        : ((searchParams.get("relation") || undefined) as MatchupFilters["pick_relation"]),
      tournament: searchParams.get("tournament") || undefined,
      patch: searchParams.get("patch") || undefined,
      game_type: searchParams.get("type") || undefined,
      limit: numParam(searchParams.get("limit")) ?? LIMIT_DEFAULT,
    };
  }, [searchParams, byName]);

  const { data: matchups, isFetching, error, refetch } = useMatchups(applied);

  function badChamp(v: string) {
    return v.trim() && byName.get(v.trim().toLowerCase()) == null;
  }

  function submit(e?: React.FormEvent) {
    e?.preventDefault();
    setFormError("");

    if (badChamp(focal)) {
      setFormError(`Unrecognized champion: "${focal}".`);
      focalRef.current?.focus();
      return;
    }
    if (badChamp(rival)) {
      setFormError(`Unrecognized champion: "${rival}".`);
      rivalRef.current?.focus();
      return;
    }
    if (mode === "2v2") {
      if (badChamp(allyB)) {
        setFormError(`Unrecognized champion: "${allyB}".`);
        allyBRef.current?.focus();
        return;
      }
      if (badChamp(rivalB)) {
        setFormError(`Unrecognized champion: "${rivalB}".`);
        rivalBRef.current?.focus();
        return;
      }
      if (!focal.trim() || !allyB.trim()) {
        setFormError("In 2v2, specify both ally champions (Ally 1 and Ally 2).");
        (focal.trim() ? allyBRef : focalRef).current?.focus();
        return;
      }
    }

    const next: Record<string, string> = {};
    if (mode === "2v2") next.mode = "2v2";
    if (focal.trim()) next.champ = focal.trim();
    if (rival.trim()) next.champ2 = rival.trim();
    if (mode === "2v2" && allyB.trim()) next.champ_b = allyB.trim();
    if (mode === "2v2" && rivalB.trim()) next.champ2_b = rivalB.trim();
    if (role) next.role = role;
    if (mode === "2v2" && roleB) next.role_b = roleB;
    if (mode !== "2v2" && relation) next.relation = relation;
    if (tournament) next.tournament = tournament;
    if (patch) next.patch = patch;
    if (gameType) next.type = gameType;
    // limit resets when applying new filters
    setSearchParams(next);
  }

  function loadMore() {
    const currentLimit = numParam(searchParams.get("limit")) ?? LIMIT_DEFAULT;
    const next = new URLSearchParams(searchParams);
    next.set("limit", String(currentLimit + 50));
    setSearchParams(next);
  }

  function clearFilters() {
    setFocal(""); setRival(""); setAllyB(""); setRivalB("");
    setRole(""); setRoleB(""); setRelation("");
    setTournament(""); setPatch(""); setGameType("");
    setFormError("");
    // keep the active mode (1v1/2v2), only filters are cleared
    setSearchParams(mode === "2v2" ? { mode: "2v2" } : {});
  }

  function switchMode(next: "1v1" | "2v2") {
    if (next === mode) return;
    setMode(next);
    setFormError("");
    // re-apply with the new mode, keeping whatever still makes sense
    const params = new URLSearchParams(searchParams);
    if (next === "2v2") {
      params.set("mode", "2v2");
    } else {
      params.delete("mode");
      params.delete("champ_b");
      params.delete("champ2_b");
      params.delete("role_b");
    }
    setSearchParams(params);
  }

  // Active filter chips
  const is2v2 = searchParams.get("mode") === "2v2";
  const activeChips = [
    searchParams.get("champ") && { key: "champ", label: `${is2v2 ? "Ally 1" : "Champion"}: ${searchParams.get("champ")}` },
    searchParams.get("champ2") && { key: "champ2", label: `vs: ${searchParams.get("champ2")}` },
    is2v2 && searchParams.get("champ_b") && { key: "champ_b", label: `Ally 2: ${searchParams.get("champ_b")}` },
    is2v2 && searchParams.get("champ2_b") && { key: "champ2_b", label: `vs2: ${searchParams.get("champ2_b")}` },
    searchParams.get("role") && { key: "role", label: `Role: ${searchParams.get("role")}` },
    is2v2 && searchParams.get("role_b") && { key: "role_b", label: `Role 2: ${searchParams.get("role_b")}` },
    !is2v2 && searchParams.get("relation") && { key: "relation", label: searchParams.get("relation")! },
    searchParams.get("tournament") && { key: "tournament", label: searchParams.get("tournament")! },
    searchParams.get("patch") && { key: "patch", label: `Patch ${searchParams.get("patch")}` },
    searchParams.get("type") && { key: "type", label: searchParams.get("type")! },
  ].filter(Boolean) as { key: string; label: string }[];

  function removeChip(key: string) {
    const map: Record<string, () => void> = {
      champ: () => setFocal(""),
      champ2: () => setRival(""),
      champ_b: () => setAllyB(""),
      champ2_b: () => setRivalB(""),
      role: () => setRole(""),
      role_b: () => setRoleB(""),
      relation: () => setRelation(""),
      tournament: () => setTournament(""),
      patch: () => setPatch(""),
      type: () => setGameType(""),
    };
    map[key]?.();
    const next = new URLSearchParams(searchParams);
    next.delete(key);
    setSearchParams(next);
  }

  const hasFilters = activeChips.length > 0;
  const isLoading = isFetching && !matchups;
  const atLimit = (matchups?.length ?? 0) >= (applied.limit ?? LIMIT_DEFAULT);

  return (
    <div className="page matchups-page">
      <FilterBar onSubmit={() => submit()}>
        {/* Search mode: first control, aligned with the filters */}
        <div className="field">
          <span className="field-label">Mode</span>
          <div className="mu-mode-seg" role="group" aria-label="Search mode">
            <button
              type="button"
              className={"mu-mode-btn" + (mode === "1v1" ? " active" : "")}
              aria-pressed={mode === "1v1"}
              onClick={() => switchMode("1v1")}
            >
              1v1
            </button>
            <button
              type="button"
              className={"mu-mode-btn" + (mode === "2v2" ? " active" : "")}
              aria-pressed={mode === "2v2"}
              onClick={() => switchMode("2v2")}
            >
              2v2
            </button>
          </div>
        </div>

        <div className="filter-divider" aria-hidden="true" />

        {/* Primary group: champions, roles, opponents */}
        {mode === "2v2" ? (
          <>
            <Field label="Champion 1">
              <ChampionPicker
                value={focal}
                onChange={setFocal}
                champions={champList}
                placeholder="e.g. Aatrox"
                hasError={formError.includes(`"${focal}"`) && focal.trim() !== ""}
                inputRef={focalRef}
              />
            </Field>
            <Field label="Champion 2">
              <ChampionPicker
                value={allyB}
                onChange={setAllyB}
                champions={champList}
                placeholder="e.g. Thresh"
                hasError={formError.includes(`"${allyB}"`) && allyB.trim() !== ""}
                inputRef={allyBRef}
              />
            </Field>
            <Field label="Role 1">
              <Select value={role} onChange={setRole} options={ROLE_OPTIONS} minWidth={110} ariaLabel="Role 1" />
            </Field>
            <Field label="Role 2">
              <Select value={roleB} onChange={setRoleB} options={ROLE_OPTIONS} minWidth={110} ariaLabel="Role 2" />
            </Field>
            <Field label="Opponent 1">
              <ChampionPicker
                value={rival}
                onChange={setRival}
                champions={champList}
                placeholder="any"
                hasError={formError.includes(`"${rival}"`) && rival.trim() !== ""}
                inputRef={rivalRef}
              />
            </Field>
            <Field label="Opponent 2">
              <ChampionPicker
                value={rivalB}
                onChange={setRivalB}
                champions={champList}
                placeholder="any"
                hasError={formError.includes(`"${rivalB}"`) && rivalB.trim() !== ""}
                inputRef={rivalBRef}
              />
            </Field>
          </>
        ) : (
          <>
            <Field label="Focal champion">
              <ChampionPicker
                value={focal}
                onChange={setFocal}
                champions={champList}
                placeholder="e.g. Aatrox"
                hasError={formError.includes(`"${focal}"`) && focal.trim() !== ""}
                inputRef={focalRef}
              />
            </Field>
            <Field label="vs Opponent">
              <ChampionPicker
                value={rival}
                onChange={setRival}
                champions={champList}
                placeholder="any"
                hasError={formError.includes(`"${rival}"`) && rival.trim() !== ""}
                inputRef={rivalRef}
              />
            </Field>
            <Field label="Role">
              <Select value={role} onChange={setRole} options={ROLE_OPTIONS} minWidth={110} ariaLabel="Role" />
            </Field>
          </>
        )}

        <div className="filter-divider" aria-hidden="true" />

        {/* Secondary group: pick type, context */}
        {mode !== "2v2" && (
          <Field label="Blind / Counter">
            <Select
              value={relation}
              onChange={setRelation}
              minWidth={110}
              ariaLabel="Blind / Counter"
              options={[
                { value: "", label: "Any" },
                { value: "blind", label: "Blind", title: "Picked before the lane opponent" },
                { value: "counter", label: "Counter", title: "Picked after the lane opponent" },
              ]}
            />
          </Field>
        )}
        <Field label="Tournament">
          <TournamentPicker value={tournament} onChange={setTournament} tournaments={tournaments ?? []} />
        </Field>
        <Field label="Patch">
          <Select
            value={patch}
            onChange={setPatch}
            minWidth={100}
            ariaLabel="Patch"
            options={[{ value: "", label: "All" }, ...(patches ?? []).map((p) => ({ value: p, label: p }))]}
          />
        </Field>
        <Field label="Type">
          <Select
            value={gameType}
            onChange={setGameType}
            minWidth={100}
            ariaLabel="Type"
            options={[
              { value: "", label: "All" },
              { value: "OFFICIAL", label: "Official" },
              { value: "SCRIM", label: "Scrim" },
              { value: "SOLOQ", label: "SoloQ" },
            ]}
          />
        </Field>

        <button type="submit" className="btn-primary">Search</button>
        {hasFilters && (
          <button type="button" className="btn-ghost" onClick={clearFilters}>
            Clear
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
                aria-label={`Remove filter ${label}`}
                onClick={() => removeChip(key)}
              >
                ×
              </button>
            </span>
          ))}
          <button type="button" className="btn-ghost btn-ghost-sm" onClick={clearFilters}>
            × clear
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
              Load more
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
            <p className="empty-title">Failed to load</p>
            <p className="empty-sub">{(error as Error).message}</p>
            <button type="button" className="btn-ghost" onClick={() => refetch()}>
              Retry
            </button>
          </div>
        ) : matchups && matchups.length === 0 ? (
          <div className="empty">
            {hasFilters ? (
              <>
                <SearchX className="empty-icon" size={36} />
                <p className="empty-title">No results</p>
                <p className="empty-sub">No pick matches the applied filters.</p>
                <button type="button" className="btn-ghost" onClick={clearFilters}>
                  Clear filters
                </button>
              </>
            ) : (
              <>
                <SearchX className="empty-icon" size={36} />
                <p className="empty-title">No data</p>
                <p className="empty-sub">There are no picks in the database yet.</p>
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
