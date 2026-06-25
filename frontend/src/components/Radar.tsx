/**
 * Radar (star) chart in pure SVG — no dependencies. Flat and precise: 1px
 * hairline grid, no shadows, color per series (data encoding). Each axis is a
 * category; each series an overlaid polygon.
 */
import "./radar.css";

export type RadarSeries = { label: string; color: string; values: number[] };

function niceMax(v: number): number {
  if (v <= 0) return 10;
  return Math.ceil(v / 10) * 10;
}

export function Radar({
  axes,
  series,
  size = 260,
  max,
}: {
  axes: string[];
  series: RadarSeries[];
  size?: number;
  max?: number;
}) {
  const n = axes.length;
  if (n < 3) return null;

  const pad = 30; // room for the axis labels
  const cx = size / 2;
  const cy = size / 2;
  const R = size / 2 - pad;

  const allValues = series.flatMap((s) => s.values.filter((v) => Number.isFinite(v)));
  const axisMax = max ?? niceMax(Math.max(0, ...allValues));

  const angleFor = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2;
  const point = (i: number, frac: number): [number, number] => {
    const a = angleFor(i);
    return [cx + Math.cos(a) * R * frac, cy + Math.sin(a) * R * frac];
  };
  const poly = (fracs: number[]) =>
    fracs.map((f, i) => point(i, f).join(",")).join(" ");

  const rings = [0.25, 0.5, 0.75, 1];
  const ariaLabel =
    "Radar: " +
    series
      .map((s) => `${s.label} ${s.values.map((v, i) => `${axes[i]} ${v.toFixed(0)}%`).join(", ")}`)
      .join("; ");

  return (
    <div className="radar">
      <svg
        viewBox={`0 0 ${size} ${size}`}
        width={size}
        height={size}
        role="img"
        aria-label={ariaLabel}
        className="radar-svg"
      >
        {/* concentric grid */}
        {rings.map((r) => (
          <polygon
            key={r}
            points={poly(axes.map(() => r))}
            className="radar-grid"
          />
        ))}
        {/* spokes */}
        {axes.map((_, i) => {
          const [x, y] = point(i, 1);
          return <line key={i} x1={cx} y1={cy} x2={x} y2={y} className="radar-spoke" />;
        })}
        {/* series */}
        {series.map((s) => (
          <polygon
            key={s.label}
            points={poly(s.values.map((v) => (Number.isFinite(v) ? v / axisMax : 0)))}
            className="radar-area"
            style={{ stroke: s.color, fill: s.color }}
          />
        ))}
        {/* axis labels */}
        {axes.map((ax, i) => {
          const [x, y] = point(i, 1.16);
          return (
            <text
              key={ax}
              x={x}
              y={y}
              className="radar-axis-label"
              textAnchor="middle"
              dominantBaseline="middle"
            >
              {ax}
            </text>
          );
        })}
      </svg>
      <div className="radar-legend">
        {series.map((s) => (
          <span key={s.label} className="radar-legend-item">
            <span className="radar-swatch" style={{ background: s.color }} aria-hidden="true" />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
