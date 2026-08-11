/**
 * SVG chart math ported from the design mock's `renderVals()` method --
 * catmull-rom smoothing for the area/line charts and donut arc geometry.
 * Only the math is ported; the surrounding render/templating (`support.js`)
 * is design-tool scaffolding and is not used here.
 */

export interface Point {
  x: number;
  y: number;
}

/**
 * Catmull-rom -> cubic bezier smoothing, producing an SVG path `d` string
 * through every point in order.
 */
export function smoothPath(points: Point[]): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;

  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i === 0 ? 0 : i - 1];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2 < points.length ? i + 2 : i + 1];

    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;

    d += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`;
  }
  return d;
}

/** Closed area path under a smoothed line, from baselineY down/up to close the shape. */
export function smoothAreaPath(points: Point[], baselineY: number): string {
  if (points.length === 0) return "";
  const line = smoothPath(points);
  const first = points[0];
  const last = points[points.length - 1];
  return `${line} L ${last.x} ${baselineY} L ${first.x} ${baselineY} Z`;
}

/** Scales a list of values into SVG x/y points within [0,width]x[0,height], y inverted (0=top). */
export function toChartPoints(
  values: number[],
  width: number,
  height: number,
  opts: { minValue?: number; maxValue?: number; padTop?: number } = {},
): Point[] {
  const { padTop = 8 } = opts;
  const maxValue = opts.maxValue ?? Math.max(...values, 1);
  const minValue = opts.minValue ?? 0;
  const range = maxValue - minValue || 1;
  const n = values.length;
  return values.map((v, i) => {
    const x = n <= 1 ? width / 2 : (i / (n - 1)) * width;
    const y = height - padTop - ((v - minValue) / range) * (height - padTop * 2);
    return { x, y };
  });
}

export interface DonutSegment {
  key: string;
  value: number;
  color: string;
}

export interface DonutArc {
  key: string;
  color: string;
  value: number;
  pct: number; // 0-100
  dashArray: string;
  dashOffset: number;
}

/**
 * Computes stroke-dasharray/offset for each segment of a multi-segment
 * donut built from stacked `<circle>` arcs (matches the mock's two-circle
 * AICL/GSDS pattern, generalized to N segments for Vehicle Type Distribution).
 */
export function donutArcs(segments: DonutSegment[], radius: number): DonutArc[] {
  const circumference = 2 * Math.PI * radius;
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  let cursor = 0;
  return segments.map((s) => {
    const pct = total > 0 ? (s.value / total) * 100 : 0;
    const arcLength = (pct / 100) * circumference;
    const dashArray = `${arcLength} ${circumference - arcLength}`;
    const dashOffset = -((cursor / 100) * circumference);
    cursor += pct;
    return { key: s.key, color: s.color, value: s.value, pct, dashArray, dashOffset };
  });
}

/** Evenly-spaced index picks for sparse axis labels, always including first/last. */
export function sparseIndices(count: number, want: number): number[] {
  if (count <= want) return Array.from({ length: count }, (_, i) => i);
  const step = (count - 1) / (want - 1);
  const out = new Set<number>();
  for (let i = 0; i < want; i++) {
    out.add(Math.round(i * step));
  }
  return Array.from(out).sort((a, b) => a - b);
}
