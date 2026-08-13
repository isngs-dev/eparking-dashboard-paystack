import type { ReactNode } from "react";
import { Card } from "./Card";
import styles from "./SectionCard.module.css";

export function SectionCard({
  title,
  subtitle,
  span,
  rowSpan,
  infoTitle,
  headerRight,
  children,
}: {
  title: string;
  subtitle?: string;
  span: number;
  rowSpan?: number;
  infoTitle?: string;
  headerRight?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card span={span} rowSpan={rowSpan} className={styles.section}>
      <div className={styles.headerRow}>
        <div className={styles.titleGroup}>
          <h2 className={styles.title}>{title}</h2>
          {infoTitle ? (
            <span className={styles.infoIcon} title={infoTitle} tabIndex={0}>
              i
            </span>
          ) : null}
          {subtitle ? <span className={styles.subtitle}>{subtitle}</span> : null}
        </div>
        {headerRight}
      </div>
      {children}
    </Card>
  );
}
