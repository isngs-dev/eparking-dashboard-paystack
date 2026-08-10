import type { ReactNode } from "react";
import styles from "./BodyGrid.module.css";

export function BodyGrid({ children }: { children: ReactNode }) {
  return <div className={styles.grid}>{children}</div>;
}
