import type { ChampRef, Draft, Side } from "../api/types";
import { ChampIcon } from "../components/icons";
import "./draftboard.css";

type TeamSide = { id: number; name: string; tag: string | null; side: Side | null } | null;

// El segundo pick es el equipo de la partida que NO es first pick; su lado es
// el contrario (first/second pick y blue/red son ejes independientes, 2026).
function secondPickTeam(d: Draft): TeamSide {
  const fpId = d.first_pick_team?.id ?? null;
  for (const t of [d.team1, d.team2]) {
    if (t && t.id !== fpId) {
      const side: Side = t.id === d.team1?.id ? "BLUE" : "RED";
      return { id: t.id, name: t.name, tag: t.tag, side };
    }
  }
  return null;
}

function TeamHead({ team, phase, result }: { team: TeamSide; phase: "fp" | "sp"; result: string }) {
  const win = team?.side && team.side === result;
  return (
    <div className={"dh-team " + phase}>
      <span className="dh-name">{team ? team.tag ?? team.name : "(?)"}</span>
      {team?.side && <span className={"pill " + team.side}>{team.side}</span>}
      {win && <span className="pill win">W</span>}
    </div>
  );
}

function Cell({ entry, align, ban }: { entry: ChampRef | null; align: "left" | "right"; ban?: boolean }) {
  const empty = !entry || entry.id == null;
  const label = empty ? "—" : (entry!.name ?? `#${entry!.id}`);
  const icon = empty ? null : <ChampIcon id={entry!.id} name={entry!.name} size={28} />;
  return (
    <div className={"cell " + align + (empty ? " empty" : "") + (ban ? " ban" : "")}>
      {align === "left" ? (
        <>
          <span className="cn">{label}</span>
          {icon}
        </>
      ) : (
        <>
          {icon}
          <span className="cn">{label}</span>
        </>
      )}
    </div>
  );
}

function PhaseRows({ d, kind, idx }: { d: Draft; kind: "bans" | "picks"; idx: number[] }) {
  return (
    <>
      {idx.map((i) => (
        <div key={`${kind}-${i}`} className={"row " + (kind === "bans" ? "ban-row" : "pick-row")}>
          <Cell entry={d.first_pick[kind][i]} align="left" ban={kind === "bans"} />
          <Cell entry={d.second_pick[kind][i]} align="right" ban={kind === "bans"} />
        </div>
      ))}
    </>
  );
}

const SK_KINDS = [
  "ban", "ban", "ban",
  "pick", "pick", "pick",
  "ban", "ban",
  "pick", "pick",
] as const;

export function DraftBoardSkeleton() {
  return (
    <div className="draftboard skeleton" aria-hidden="true">
      <div className="db-head">
        <div className="dh-team fp">
          <span className="sk-line" style={{ width: "55%", height: 12 }} />
        </div>
        <div className="db-meta">
          <span className="sk-line" style={{ width: 40, height: 8 }} />
          <span className="sk-line" style={{ width: 30, height: 8 }} />
        </div>
        <div className="dh-team sp">
          <span className="sk-line" style={{ width: "55%", height: 12 }} />
        </div>
      </div>
      {SK_KINDS.map((kind, i) => (
        <div key={i} className={"row " + (kind === "ban" ? "ban-row" : "pick-row")}>
          <div className="cell left">
            <span className="sk-line" style={{ width: "50%" }} />
            <span className="sk-chip" />
          </div>
          <div className="cell right">
            <span className="sk-chip" />
            <span className="sk-line" style={{ width: "50%" }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function DraftBoard({ d }: { d: Draft }) {
  const fp = d.first_pick_team;
  const sp = secondPickTeam(d);
  return (
    <div className="draftboard">
      <div className="db-head">
        <TeamHead team={fp} phase="fp" result={d.result} />
        <div className="db-meta">
          <span>{d.date}</span>
          <span className="muted">{d.game_type}</span>
          {d.version && <span className="muted">v{d.version}</span>}
          {d.tournament && <span className="muted db-tourn">{d.tournament}</span>}
        </div>
        <TeamHead team={sp} phase="sp" result={d.result} />
      </div>

      <PhaseRows d={d} kind="bans" idx={[0, 1, 2]} />
      <PhaseRows d={d} kind="picks" idx={[0, 1, 2]} />
      <PhaseRows d={d} kind="bans" idx={[3, 4]} />
      <PhaseRows d={d} kind="picks" idx={[3, 4]} />
    </div>
  );
}
