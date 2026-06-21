// Barra de chips de fuentes (medios). Reutilizada por el Agregado de Scouting y
// por las pestañas de Matchups / Blind-Counter. Estilos en scouting.css (.agg-*).

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
      <span className="agg-source-label">Fuentes:</span>
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
          Mostrando {active.size}/{all.length} fuentes
        </span>
      )}
    </div>
  );
}
