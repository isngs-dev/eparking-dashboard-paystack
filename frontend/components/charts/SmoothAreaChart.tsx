"use client";

import { useTooltip, type TooltipContent } from "@/components/primitives/Tooltip";
import { smoothAreaPath, smoothPath, sparseIndices, toChartPoints } from "@/lib/chartMath";
import styles from "./SmoothAreaChart.module.css";

const VB_WIDTH = 1000;
const VB_HEIGHT = 200;

export interface AxisLabel {
  value: string;
}

export interface PeakBandRect {
  /** 0..1 fraction of chart width for start/end. Can be two rects if wrapping. */
  x0: number;
  x1: number;
  label?: string;
}

export interface SmoothAreaChartProps {
  values: number[];
  xLabels: string[];
  yLabels: string[];
  /**
   * Pre-computed tooltip content, one per data point (index-aligned with
   * `values`). Plain data, not a callback -- functions cannot cross the
   * server/client component boundary (RSC serialization constraint), and
   * every caller here is an async Server Component.
   */
  tooltips: TooltipContent[];
  peakBands?: PeakBandRect[];
  xLabelCount?: number;
}

export function SmoothAreaChart({
  values,
  xLabels,
  yLabels,
  tooltips,
  peakBands,
  xLabelCount = 11,
}: SmoothAreaChartProps) {
  const { bind } = useTooltip();

  const maxValue = Math.max(...values, 1);
  const points = toChartPoints(values, VB_WIDTH, VB_HEIGHT, { maxValue, minValue: 0, padTop: 10 });
  const areaPath = smoothAreaPath(points, VB_HEIGHT);
  const linePath = smoothPath(points);

  const hitWidth = values.length > 1 ? VB_WIDTH / (values.length - 1) : VB_WIDTH;
  const labelIdx = new Set(sparseIndices(xLabels.length, xLabelCount));

  return (
    <div className={styles.wrap}>
      <div className={styles.yAxis}>
        {yLabels.map((l, i) => (
          <span key={i}>{l}</span>
        ))}
      </div>
      <div className={styles.chartArea}>
        {peakBands?.map((band, i) => (
          <div
            key={i}
            className={styles.peakBand}
            style={{
              left: `${band.x0 * 100}%`,
              width: `${(band.x1 - band.x0) * 100}%`,
            }}
          />
        ))}
        <svg viewBox={`0 0 ${VB_WIDTH} ${VB_HEIGHT}`} preserveAspectRatio="none" className={styles.svg}>
          <path d={areaPath} fill="var(--cyansoft)" stroke="none" />
          <path d={linePath} fill="none" stroke="var(--s1)" strokeWidth={2} />
          {points.map((p, i) => (
            <rect
              key={i}
              x={p.x - hitWidth / 2}
              y={0}
              width={hitWidth}
              height={VB_HEIGHT}
              fill="transparent"
              className={styles.hitRect}
              {...bind(tooltips[i])}
            />
          ))}
        </svg>
        {peakBands?.map((band, i) =>
          band.label ? (
            <span
              key={i}
              className={styles.peakBandLabel}
              style={{
                left: `${((band.x0 + band.x1) / 2) * 100}%`,
              }}
            >
              {band.label}
            </span>
          ) : null,
        )}
        <div className={styles.xAxis}>
          {xLabels.map((label, i) =>
            labelIdx.has(i) ? (
              <span
                key={i}
                className={styles.xLabel}
                style={{ left: `${xLabels.length > 1 ? (i / (xLabels.length - 1)) * 100 : 50}%` }}
              >
                {label}
              </span>
            ) : null,
          )}
        </div>
      </div>
    </div>
  );
}
