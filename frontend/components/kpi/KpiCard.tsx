"use client";

import { useTooltip, type TooltipContent } from "@/components/primitives/Tooltip";
import { InfoIcon } from "@/components/primitives/InfoIcon";
import { formatDeltaPct } from "@/lib/format";
import styles from "./KpiCard.module.css";

export interface KpiCardProps {
  label: string;
  value: string;
  sublabel: string;
  deltaPct?: number | null;
  infoTitle?: string;
  tooltip: TooltipContent;
  footnote?: string | null;
}

export function KpiCard({ label, value, sublabel, deltaPct, infoTitle, tooltip, footnote }: KpiCardProps) {
  const { bind } = useTooltip();
  const deltaText = deltaPct === undefined ? null : formatDeltaPct(deltaPct ?? null);
  const isPositive = (deltaPct ?? 0) >= 0;

  return (
    <div className={styles.card} {...bind(tooltip)}>
      <div className={styles.topRow}>
        <span className={styles.label}>{label}</span>
        {infoTitle ? (
          <InfoIcon title={infoTitle} />
        ) : deltaText ? (
          <span className={[styles.delta, isPositive ? styles.deltaUp : styles.deltaDown].join(" ")}>
            {deltaText}
          </span>
        ) : null}
      </div>
      <div className={styles.value}>{value}</div>
      <div className={styles.sublabel}>{sublabel}</div>
      {footnote ? <div className={styles.footnote}>{footnote}</div> : null}
    </div>
  );
}
