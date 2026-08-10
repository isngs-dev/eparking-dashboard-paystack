"use client";

import { useTooltip, type TooltipContent } from "@/components/primitives/Tooltip";
import styles from "./GroupedBarChart.module.css";

export interface GroupedBarGroup {
  label: string;
  values: { seriesKey: string; colorVar: string; value: number }[];
}

export interface GroupedBarChartProps {
  groups: GroupedBarGroup[];
  yLabels: string[];
  /** tooltips[groupIndex][seriesKey] -- pre-computed, not a callback (see SmoothAreaChart). */
  tooltips: Record<string, TooltipContent>[];
}

const HEIGHT = 200;
const GROUP_WIDTH = 56;
const BAR_GAP = 6;

export function GroupedBarChart({ groups, yLabels, tooltips }: GroupedBarChartProps) {
  const { bind } = useTooltip();
  const maxValue = Math.max(...groups.flatMap((g) => g.values.map((v) => v.value)), 1);
  const width = Math.max(groups.length * GROUP_WIDTH, 200);
  const seriesCount = groups[0]?.values.length ?? 1;
  const barWidth = (GROUP_WIDTH - BAR_GAP * (seriesCount + 1)) / seriesCount;

  return (
    <div className={styles.wrap}>
      <div className={styles.yAxis}>
        {yLabels.map((l, i) => (
          <span key={i}>{l}</span>
        ))}
      </div>
      <div className={styles.chartArea}>
        <svg viewBox={`0 0 ${width} ${HEIGHT}`} preserveAspectRatio="none" className={styles.svg}>
          {groups.map((group, gi) => {
            const groupX = gi * GROUP_WIDTH;
            return (
              <g key={group.label}>
                {group.values.map((v, si) => {
                  const barH = (v.value / maxValue) * (HEIGHT - 10);
                  const x = groupX + BAR_GAP + si * (barWidth + BAR_GAP);
                  const y = HEIGHT - barH;
                  return (
                    <rect
                      key={v.seriesKey}
                      x={x}
                      y={y}
                      width={barWidth}
                      height={Math.max(barH, 0)}
                      fill={`var(${v.colorVar})`}
                      rx={2}
                      className={styles.bar}
                      {...bind(tooltips[gi]?.[v.seriesKey] ?? { title: v.seriesKey, rows: [] })}
                    />
                  );
                })}
              </g>
            );
          })}
        </svg>
        <div className={styles.xAxis}>
          {groups.map((g, i) => (
            <span
              key={i}
              className={styles.xLabel}
              style={{ left: `${((i + 0.5) / groups.length) * 100}%` }}
            >
              {g.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
