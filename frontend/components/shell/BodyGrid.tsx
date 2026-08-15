import type { ReactNode } from "react";
import styles from "./BodyGrid.module.css";

export function BodyGrid({
  children,
  layout = "default",
}: {
  children: ReactNode;
  layout?: "default" | "overview" | "occupancy";
}) {
  return (
    <div
      className={[
        styles.grid,
        layout === "overview" ? styles.overview : "",
        layout === "occupancy" ? styles.occupancy : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </div>
  );
}
