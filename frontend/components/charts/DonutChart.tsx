"use client";

import { useTooltip, type TooltipContent } from "@/components/primitives/Tooltip";
import { donutArcs, type DonutSegment } from "@/lib/chartMath";
import styles from "./DonutChart.module.css";

const R = 45;
const CX = 60;
const CY = 60;

export interface DonutChartProps {
  segments: DonutSegment[];
  centerValue: string;
  centerLabel: string;
  large?: boolean;
  /** Pre-computed tooltip content keyed by segment key -- see SmoothAreaChart for why this isn't a callback. */
  tooltips: Record<string, TooltipContent>;
}

export function DonutChart({
  segments,
  centerValue,
  centerLabel,
  large = false,
  tooltips,
}: DonutChartProps) {
  const { bind } = useTooltip();
  const arcs = donutArcs(segments, R);
  const circumference = 2 * Math.PI * R;

  return (
    <div className={styles.wrap}>
      <svg
        viewBox="0 0 120 120"
        className={[styles.svg, large && styles.large].filter(Boolean).join(" ")}
      >
        <circle cx={CX} cy={CY} r={R} fill="none" stroke="var(--grid)" strokeWidth={20} />
        <g transform={`rotate(-90 ${CX} ${CY})`}>
          {arcs.map((arc) =>
            arc.value > 0 ? (
              <circle
                key={arc.key}
                cx={CX}
                cy={CY}
                r={R}
                fill="none"
                stroke={`var(${arc.color})`}
                strokeWidth={20}
                strokeDasharray={arc.dashArray}
                strokeDashoffset={arc.dashOffset}
                className={styles.arc}
                {...bind(tooltips[arc.key] ?? { title: arc.key, rows: [] })}
              />
            ) : null,
          )}
        </g>
        <text x={CX} y={CY - 3} textAnchor="middle" className={styles.centerValue}>
          {centerValue}
        </text>
        <text x={CX} y={CY + 12} textAnchor="middle" className={styles.centerLabel}>
          {centerLabel}
        </text>
      </svg>
    </div>
  );
}
