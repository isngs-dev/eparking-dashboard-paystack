import styles from "./PageHeader.module.css";

export function PageHeader({ title, tag }: { title: string; tag?: string }) {
  return (
    <div className={styles.header}>
      <h1 className={styles.title}>{title}</h1>
      {tag ? <span className={styles.tag}>{tag}</span> : null}
    </div>
  );
}
