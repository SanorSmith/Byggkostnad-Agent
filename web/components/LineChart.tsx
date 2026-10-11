import type { Row } from "@/lib/api";

const W = 360;
const H = 140;
const PAD = { top: 10, right: 8, bottom: 22, left: 44 };

/** Minimal dependency-free line chart for one index series. */
export function LineChart({ rows, label }: { rows: Row[]; label: string }) {
  const values = rows.map((r) => Number(r.value));
  if (values.length < 2) return null;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => PAD.left + (i / (values.length - 1)) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - (v - min) / span) * (H - PAD.top - PAD.bottom);
  const path = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");

  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      <line className="axis" x1={PAD.left} x2={W - PAD.right} y1={H - PAD.bottom} y2={H - PAD.bottom} />
      <text x={PAD.left - 6} y={y(max) + 4} textAnchor="end">{max.toFixed(1)}</text>
      <text x={PAD.left - 6} y={y(min) + 4} textAnchor="end">{min.toFixed(1)}</text>
      <text x={PAD.left} y={H - 6}>{rows[0].period.slice(0, 7)}</text>
      <text x={W - PAD.right} y={H - 6} textAnchor="end">{rows[rows.length - 1].period.slice(0, 7)}</text>
      <path className="line" d={path} />
    </svg>
  );
}
