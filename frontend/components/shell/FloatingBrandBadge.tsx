import Image from "next/image";
import styles from "./FloatingBrandBadge.module.css";

/**
 * Small floating GSD Solutions brand badge (wide-pill variant using the
 * full wordmark logo, per client decision -- no icon-only crop needed).
 * Two placements:
 *  - `fixed`: pinned to the viewport's bottom-right, rendered once per
 *    dashboard page from `app/(dashboard)/layout.tsx`.
 *  - default: absolutely positioned by the caller via `className`
 *    (the login page's brand panel corner).
 *
 * Decorative branding only -- deliberately NOT repeated per card.
 */
export function FloatingBrandBadge({
  fixed = false,
  className,
}: {
  fixed?: boolean;
  className?: string;
}) {
  return (
    <div
      className={[styles.badge, fixed ? styles.fixed : "", className]
        .filter(Boolean)
        .join(" ")}
    >
      <Image
        src="/logos/gsds.png"
        alt="GSD Solutions"
        width={140}
        height={46}
        className={styles.mark}
      />
    </div>
  );
}
