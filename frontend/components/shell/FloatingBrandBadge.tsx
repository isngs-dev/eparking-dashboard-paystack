import Image from "next/image";
import styles from "./FloatingBrandBadge.module.css";

/**
 * GSD Solutions brand badge using the full wordmark logo. It defaults to a
 * small wide-pill treatment and supports a prominent landing-page
 * variant without distorting the visible wordmark. Placements:
 *  - `fixed`: pinned to the viewport's bottom-right, rendered once per
 *    dashboard page from `app/(dashboard)/layout.tsx`.
 *  - default: absolutely positioned by the caller via `className`
 *    (the login page's brand panel corner).
 *
 * Decorative branding only -- deliberately NOT repeated per card.
 */
export function FloatingBrandBadge({
  fixed = false,
  prominent = false,
  className,
}: {
  fixed?: boolean;
  prominent?: boolean;
  className?: string;
}) {
  return (
    <div
      className={[
        styles.badge,
        fixed ? styles.fixed : "",
        prominent ? styles.prominent : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <Image
        src="/logos/gsds.png"
        alt="GSD Solutions"
        width={140}
        height={46}
        className={[styles.mark, prominent ? styles.prominentMark : ""]
          .filter(Boolean)
          .join(" ")}
      />
    </div>
  );
}
