"use client";

import { useTooltip, type TooltipContent } from "@/components/primitives/Tooltip";
import styles from "./HBarRowList.module.css";

export interface HBarRow {
  key: string;
  label: string;
  /** 0-100 */
  pct: number;
  colorVar: string;
  rightText: string;
  tooltip: TooltipContent;
}

/** Compact row style: used by Weekly Occupancy Pattern (thin bar, label left, count right). */
export function HBarRowList({ rows, labelWidth = 72 }: { rows: HBarRow[]; labelWidth?: number }) {
  const { bind } = useTooltip();
  return (
    <div className={styles.list}>
      {rows.map((row) => (
        <div className={styles.row} key={row.key} {...bind(row.tooltip)}>
          <span className={styles.label} style={{ width: labelWidth }}>
            {row.label}
          </span>
          <span className={styles.track}>
            <span
              className={styles.fill}
              style={{ width: `${row.pct}%`, background: `var(${row.colorVar})` }}
            />
          </span>
          <span className={styles.right}>{row.rightText}</span>
        </div>
      ))}
    </div>
  );
}
