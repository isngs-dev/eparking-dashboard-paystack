import styles from "./InfoIcon.module.css";

/** Small "i" info-icon with a native title tooltip, matching the mock's pattern. */
export function InfoIcon({ title }: { title: string }) {
  return (
    <span className={styles.icon} title={title} aria-label={title} tabIndex={0}>
      i
    </span>
  );
}
