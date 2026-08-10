import { Card } from "./Card";
import styles from "./InfoCallout.module.css";

/**
 * Renders unconditionally on the Occupancy page -- not dismissible, not
 * collapsible. Reads the live `entry_count_basis` so the derivation text
 * never goes stale relative to a runtime-flipped setting.
 */
export function InfoCallout({ entryCountBasis }: { entryCountBasis: string }) {
  const basisText =
    entryCountBasis === "all_transactions"
      ? "all successful revenue transactions"
      : "successful ticket transactions";

  return (
    <Card span={1} className={styles.callout}>
      <div className={styles.header}>
        <span className={styles.iconBadge} aria-hidden="true">
          i
        </span>
        <span className={styles.title}>Derived from ticket payments</span>
      </div>
      <p className={styles.body}>
        Counts on this page come from Paystack {basisText}. No gate sensor, no LPR.
      </p>
    </Card>
  );
}
