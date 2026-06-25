import { AlertTriangle, SearchX } from "lucide-react";

import { usePickOrderStats, type StatsFilters } from "../api/hooks";
import type { PickSlotEntry, RoleDistEntry } from "../api/types";
import { ChampIcon } from "../components/icons";
import "./pick-order.css";

// ─── constants ────────────────────────────────────────────────────────────────

const BLUE_SLOTS = [
  { key: "b1",   label: "B1",   hint: "Blue 1st pick (first draft action)" },
  { key: "b2_3", label: "B2-3", hint: "Blue 2nd and 3rd picks (phase 1)" },
  { key: "b4_5", label: "B4-5", hint: "Blue 4th and 5th picks (phase 2)" },
] as const;

const RED_SLOTS = [
  { key: "r1_2", label: "R1-2", hint: "Red 1st and 2nd picks (phase 1)" },
  { key: "r3",   label: "R3",   hint: "Red 3rd pick (snake turn)" },
  { key: "r4",   label: "R4",   hint: "Red 4th pick (phase 2)" },
  { key: "r5",   label: "R5",   hint: "Red 5th pick (draft close)" },
] as const;

const ROLES = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"] as const;

// ─── helpers ─────────────────────────────────────────────────────────────────

function rdHeatClass(pct: number): string {
  if (pct >= 60) return "rd-heat-5";
  if (pct >= 45) return "rd-heat-4";
  if (pct >= 30) return "rd-heat-3";
  if (pct >= 15) return "rd-heat-2";
  if (pct > 0)   return "rd-heat-1";
  return "";
}

function wrColor(wr: number | null): string {
  if (wr == null) return "";
  if (wr >= 55) return "po-wr-pos";
  if (wr <= 45) return "po-wr-neg";
  return "";
}

// Directional glyph: WR is not conveyed by green/red alone (color blindness).
function wrArrow(wr: number | null): string {
  if (wr == null) return "";
  if (wr >= 55) return "▲";
  if (wr <= 45) return "▼";
  return "";
}

// ─── sub-components ───────────────────────────────────────────────────────────

function SlotColumn({
  slotKey,
  label,
  hint,
  side,
  entries,
  loading,
}: {
  slotKey: string;
  label: string;
  hint: string;
  side: "blue" | "red";
  entries: PickSlotEntry[];
  loading: boolean;
}) {
  return (
    <div className="po-col">
      <div className={`po-col-head ${side}`} title={hint} aria-label={hint}>{label}</div>
      <div className="po-col-body">
        {loading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="po-skel" aria-hidden="true" />
          ))
        ) : entries.length === 0 ? (
          <div className="po-entry" style={{ color: "var(--muted)", fontStyle: "italic" }}>
            —
          </div>
        ) : (
          entries.map((e) => (
            <div key={`${e.champ_id}-${slotKey}`} className="po-entry">
              <ChampIcon id={e.champ_id} name={e.champ_name ?? ""} size={20} />
              <span className="po-champ-name">{e.champ_name ?? `#${e.champ_id}`}</span>
              <span className={`po-stats ${wrColor(e.win_rate)}`}>
                {e.games}g
                {e.win_rate != null && (
                  <>
                    {" · "}
                    {wrArrow(e.win_rate) && (
                      <span className="po-wr-arrow" aria-hidden="true">{wrArrow(e.win_rate)}</span>
                    )}
                    {e.win_rate.toFixed(0)}%
                  </>
                )}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function RoleTable({
  side,
  slots,
  roleData,
}: {
  side: "blue" | "red";
  slots: readonly { key: string; label: string }[];
  roleData: RoleDistEntry[];
}) {
  return (
    <div className="rd-section">
      <div className={`rd-title ${side}`}>
        {side === "blue" ? "Blue Side" : "Red Side"} — distribution per role
      </div>
      <table className={`rd-table ${side}`}>
        <thead>
          <tr>
            <th>Role</th>
            {slots.map((s) => (
              <th key={s.key}>{s.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROLES.map((role) => (
            <tr key={role}>
              <td>{role}</td>
              {slots.map((s) => {
                const cell = roleData.find(
                  (r) => r.role === role && r.slot === s.key && r.pick_side === side,
                );
                if (!cell || cell.pct === 0) return <td key={s.key} className="muted">—</td>;
                return (
                  <td key={s.key} className={rdHeatClass(cell.pct)}>
                    {cell.pct.toFixed(0)}%
                    {cell.win_rate != null && (
                      <div className="rd-wr">{cell.win_rate.toFixed(0)}% WR</div>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── main component ───────────────────────────────────────────────────────────

export function PickOrderStats({ filters }: { filters: StatsFilters }) {
  const { data, isFetching, error, refetch } = usePickOrderStats(filters, true);

  if (error) {
    return (
      <div className="empty">
        <AlertTriangle size={22} className="empty-icon" style={{ color: "var(--red)" }} />
        <p className="empty-title">Could not load pick order data.</p>
        <p className="empty-sub">{(error as Error).message}</p>
        <button type="button" className="btn-ghost" onClick={() => refetch()}>
          Retry
        </button>
      </div>
    );
  }

  if (!isFetching && data && data.slots.length === 0) {
    return (
      <div className="empty">
        <SearchX size={22} className="empty-icon" />
        <p className="empty-title">No data for these filters.</p>
        <p className="empty-sub">No drafts match the current selection.</p>
      </div>
    );
  }

  const slotMap = new Map<string, PickSlotEntry[]>();
  if (data) {
    for (const entry of data.slots) {
      const list = slotMap.get(entry.slot) ?? [];
      list.push(entry);
      slotMap.set(entry.slot, list);
    }
  }

  const roleData = data?.role_dist ?? [];
  const totalGames = data?.slots[0]?.total_games ?? 0;

  return (
    <>
      <p className="status" role="status" aria-live="polite" style={{ padding: "0.5rem 1.2rem" }}>
        {isFetching ? "Loading…" : data ? `${totalGames} games` : ""}
      </p>

      <div className="po-legend" aria-label="Legend">
        <span className="po-legend-wr"><span className="po-wr-pos">▲ ≥55%</span> <span className="po-wr-neg">▼ ≤45%</span> WR · Ng = games in that slot</span>
      </div>

      <div className="po-page">
        {/* ── Blue Side ── */}
        <section aria-label="Blue Side picks">
          <div className="po-section-label blue">Blue Side</div>
          <div className="po-cols blue">
            {BLUE_SLOTS.map((s) => (
              <SlotColumn
                key={s.key}
                slotKey={s.key}
                label={s.label}
                hint={s.hint}
                side="blue"
                entries={slotMap.get(s.key) ?? []}
                loading={isFetching}
              />
            ))}
          </div>
        </section>

        {/* ── Red Side ── */}
        <section aria-label="Red Side picks">
          <div className="po-section-label red">Red Side</div>
          <div className="po-cols red">
            {RED_SLOTS.map((s) => (
              <SlotColumn
                key={s.key}
                slotKey={s.key}
                label={s.label}
                hint={s.hint}
                side="red"
                entries={slotMap.get(s.key) ?? []}
                loading={isFetching}
              />
            ))}
          </div>
        </section>

        {/* ── Role tables ── */}
        {!isFetching && roleData.length > 0 && (
          <div className="rd-pair">
            <RoleTable side="blue" slots={BLUE_SLOTS} roleData={roleData} />
            <RoleTable side="red"  slots={RED_SLOTS}  roleData={roleData} />
          </div>
        )}
      </div>
    </>
  );
}
