import { Card } from "./Card";
import styles from "./Skeleton.module.css";

/** Suspense fallback for an async visual -- matches the target card's chrome/span. */
export function SkeletonCard({
  span = 1,
  rowSpan = 1,
  height = 120,
}: {
  span?: number;
  rowSpan?: number;
  height?: number;
}) {
  return (
    <Card span={span} rowSpan={rowSpan}>
      <div className={styles.bar} style={{ width: "60%" }} />
      <div className={styles.block} style={{ height }} />
    </Card>
  );
}
