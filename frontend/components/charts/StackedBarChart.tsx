"use client";

import { useTooltip, type TooltipContent } from "@/components/primitives/Tooltip";
import { sparseIndices } from "@/lib/chartMath";
import styles from "./StackedBarChart.module.css";

export interface StackedBarSegment {
  seriesKey: string;
  colorVar: string;
  value: number;
}

export interface StackedBarGroup {
  label: string;
  segments: StackedBarSegment[];
}

export interface StackedBarChartProps {
  groups: StackedBarGroup[];
  yLabels: string[];
  /**
   * Pre-computed tooltip content, not a callback (see SmoothAreaChart).
   * `tooltips[groupIndex].bySeries[seriesKey]` for a segment hover,
   * `tooltips[groupIndex].dayTotal` for the full-bar hit-overlay hover.
   */
  tooltips: { bySeries: Record<string, TooltipContent>; dayTotal: TooltipContent }[];
  xLabelCount?: number;
}

const VB_WIDTH = 1000;
const HEIGHT = 200;

export function StackedBarChart({ groups, yLabels, tooltips, xLabelCount = 14 }: StackedBarChartProps) {
  const { bind } = useTooltip();
  const totals = groups.map((g) => g.segments.reduce((sum, s) => sum + s.value, 0));
  const maxTotal = Math.max(...totals, 1);
  const n = groups.length;
  const slotWidth = VB_WIDTH / n;
  const barWidth = Math.min(slotWidth * 0.6, 40);

  const labelIdx = new Set(sparseIndices(n, Math.min(xLabelCount, n)));

  return (
    <div className={styles.wrap}>
      <div className={styles.yAxis}>
        {yLabels.map((l, i) => (
          <span key={i}>{l}</span>
        ))}
      </div>
      <div className={styles.chartArea}>
        <svg viewBox={`0 0 ${VB_WIDTH} ${HEIGHT}`} preserveAspectRatio="none" className={styles.svg}>
          {groups.map((group, gi) => {
            const x = gi * slotWidth + (slotWidth - barWidth) / 2;
            let cursorY = HEIGHT;
            return (
              <g key={gi}>
                {group.segments.map((seg) => {
                  const segH = (seg.value / maxTotal) * (HEIGHT - 10);
                  const y = cursorY - segH;
                  cursorY = y;
                  if (seg.value <= 0) return null;
                  return (
                    <rect
                      key={seg.seriesKey}
                      x={x}
                      y={y}
                      width={barWidth}
                      height={segH}
                      fill={`var(${seg.colorVar})`}
                      className={styles.segment}
                      {...bind(tooltips[gi]?.bySeries[seg.seriesKey] ?? { title: seg.seriesKey, rows: [] })}
                    />
                  );
                })}
                {/* full-height invisible hit rect for days with zero total, so hover still shows the day total */}
                <rect
                  x={x}
                  y={0}
                  width={barWidth}
                  height={HEIGHT}
                  fill="transparent"
                  className={styles.hitOverlay}
                  {...bind(tooltips[gi]?.dayTotal ?? { title: group.label, rows: [] })}
                />
              </g>
            );
          })}
        </svg>
        <div className={styles.xAxis}>
          {groups.map((g, i) =>
            labelIdx.has(i) ? (
              <span
                key={i}
                className={styles.xLabel}
                style={{ left: `${((i + 0.5) / n) * 100}%` }}
              >
                {g.label}
              </span>
            ) : null,
          )}
        </div>
      </div>
    </div>
  );
}
