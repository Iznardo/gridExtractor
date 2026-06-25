import type { PickStats } from "../api/types";
import { ItemIcon, RuneIcon, RuneStyleIcon, SpellIcon } from "./icons";
import { mmss } from "../lib/format";

const SKILLS = ["Q", "W", "E", "R"] as const;

export function SkillGrid({ order }: { order: string }) {
  const letters = order.toUpperCase().split("").filter((c) => "QWER".includes(c));
  const levels = letters.length;
  return (
    <div className="skillgrid">
      {SKILLS.map((skill) => (
        <div key={skill} className="sg-row">
          <span className="sg-key">{skill}</span>
          {Array.from({ length: levels }, (_, i) => {
            const hit = letters[i] === skill;
            return (
              <span key={i} className={"sg-cell" + (hit ? " hit " + skill : "")}>
                {hit ? i + 1 : ""}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export function BuildCard({ stats }: { stats: PickStats | null }) {
  if (!stats) return <span className="muted">no data</span>;
  const buys = (stats.build_path ?? []).filter((b) => b.action === "BUY");
  const r = stats.runes;
  const spells = stats.summoner_spells ?? [];
  return (
    <div className="build-card">
      {spells.length > 0 && (
        <div className="build-spells">
          {spells.map((id, i) => (
            <SpellIcon key={i} id={id} size={26} />
          ))}
        </div>
      )}

      {r ? (
        <div className="build-runes">
          <div className="rc-row primary">
            {r.primary.map((id, i) => (
              <RuneIcon key={i} id={id} size={i === 0 ? 28 : 20} />
            ))}
          </div>
          <div className="rc-row">
            <RuneStyleIcon id={r.sub_style} size={16} />
            {r.sub.map((id, i) => (
              <RuneIcon key={i} id={id} size={20} />
            ))}
          </div>
          <div className="rc-row shards">
            {r.stat_perks.map((id, i) => (
              <RuneIcon key={i} id={id} size={15} />
            ))}
          </div>
        </div>
      ) : (
        <span className="muted">no runes</span>
      )}

      {buys.length > 0 ? (
        <div className="build-order">
          {buys.map((b, i) => (
            <span key={i} className="bo-item">
              <ItemIcon id={b.item_id} size={26} />
              <span className="bo-ts">{mmss(b.ts_s)}</span>
            </span>
          ))}
        </div>
      ) : (
        <span className="muted">no build order</span>
      )}

      {stats.skill_order ? (
        <SkillGrid order={stats.skill_order} />
      ) : (
        <span className="muted">no skill order</span>
      )}
    </div>
  );
}
