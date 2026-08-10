"use client";

import { useTooltip, type TooltipContent } from "@/components/primitives/Tooltip";
import styles from "./PeakOffPeakRow.module.css";

export interface PeakOffPeakRowProps {
  title: string;
  rangeText: string;
  pct: number;
  colorVar: string;
  tooltip: TooltipContent;
}

export function PeakOffPeakRow({ title, rangeText, pct, colorVar, tooltip }: PeakOffPeakRowProps) {
  const { bind } = useTooltip();
  return (
    <div className={styles.row} {...bind(tooltip)}>
      <div className={styles.header}>
        <span className={styles.title}>{title}</span>
        <span className={styles.range}>{rangeText}</span>
      </div>
      <div className={styles.pct}>{pct.toFixed(1)}%</div>
      <div className={styles.track}>
        <div className={styles.fill} style={{ width: `${pct}%`, background: `var(${colorVar})` }} />
      </div>
    </div>
  );
}
