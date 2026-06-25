// Source (medium) chip bar. Reused by the Scouting aggregate and the Matchups /
// Blind-Counter tabs. Styles in scouting.css (.agg-*).

export function SourceChips<T extends string>({
  all,
  labels,
  active,
  onToggle,
}: {
  all: readonly T[];
  labels: Record<T, string>;
  active: Set<T>;
  onToggle: (m: T) => void;
}) {
  return (
    <div className="agg-source-bar">
      <span className="agg-source-label">Sources:</span>
      {all.map((m) => (
        <button
          key={m}
          type="button"
          aria-pressed={active.has(m)}
          className={"agg-chip" + (active.has(m) ? " active" : "")}
          onClick={() => onToggle(m)}
        >
          {labels[m]}
        </button>
      ))}
      {active.size < all.length && (
        <span className="agg-partial-notice">
          Showing {active.size}/{all.length} sources
        </span>
      )}
    </div>
  );
}
