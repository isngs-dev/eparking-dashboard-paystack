"use client";

import { useTooltip, type TooltipContent } from "@/components/primitives/Tooltip";
import { InfoIcon } from "@/components/primitives/InfoIcon";
import styles from "./KpiCard.module.css";

export interface KpiCardProps {
  label: string;
  value: string;
  sublabel?: string;
  infoTitle?: string;
  tooltip: TooltipContent;
}

export function KpiCard({ label, value, sublabel, infoTitle, tooltip }: KpiCardProps) {
  const { bind } = useTooltip();

  return (
    <div className={styles.card} {...bind(tooltip)}>
      <div className={styles.topRow}>
        <span className={styles.label}>{label}</span>
        {infoTitle ? (
          <InfoIcon title={infoTitle} />
        ) : null}
      </div>
      <div className={styles.value}>{value}</div>
      {sublabel ? <div className={styles.sublabel}>{sublabel}</div> : null}
    </div>
  );
}
