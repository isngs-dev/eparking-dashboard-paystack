import { Card } from "./Card";
import styles from "./ErrorCard.module.css";

/**
 * Rendered by a visual's error boundary when its endpoint fails -- surfaces
 * the API's real error detail (e.g. a 422 validation message) instead of a
 * blank card, and never takes down the rest of the page.
 */
export function ErrorCard({
  title,
  message,
  span = 1,
  rowSpan = 1,
}: {
  title: string;
  message: string;
  span?: number;
  rowSpan?: number;
}) {
  return (
    <Card span={span} rowSpan={rowSpan} className={styles.errorCard}>
      <div className={styles.title}>{title}</div>
      <p className={styles.message}>{message}</p>
    </Card>
  );
}
