import type { CSSProperties, ReactNode } from "react";
import styles from "./Card.module.css";

export function Card({
  children,
  span = 1,
  rowSpan = 1,
  className,
  style,
}: {
  children: ReactNode;
  span?: number;
  rowSpan?: number;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div
      className={[styles.card, className].filter(Boolean).join(" ")}
      style={{ gridColumn: `span ${span}`, gridRow: `span ${rowSpan}`, ...style }}
    >
      {children}
    </div>
  );
}
