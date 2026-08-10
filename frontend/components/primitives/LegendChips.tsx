import styles from "./LegendChips.module.css";

export interface LegendChip {
  colorVar: string; // e.g. "--s1"
  label: string;
}

export function LegendChips({ items }: { items: LegendChip[] }) {
  return (
    <div className={styles.legend}>
      {items.map((item) => (
        <span className={styles.chip} key={item.label}>
          <span className={styles.swatch} style={{ background: `var(${item.colorVar})` }} />
          {item.label}
        </span>
      ))}
    </div>
  );
}
