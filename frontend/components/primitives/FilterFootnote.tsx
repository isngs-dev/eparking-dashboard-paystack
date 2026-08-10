import styles from "./FilterFootnote.module.css";
import type { EndpointKey, FilterKind } from "@/lib/api/endpointFilters";
import { ignoredFiltersFootnote } from "@/lib/api/endpointFilters";

/**
 * Visible per-card footnote when an active filter is ignored by that card's
 * endpoint -- the UI must never silently imply a filter changed something
 * it didn't.
 */
export function FilterFootnote({
  endpoint,
  activeFilters,
}: {
  endpoint: EndpointKey;
  activeFilters: FilterKind[];
}) {
  const text = ignoredFiltersFootnote(endpoint, activeFilters);
  if (!text) return null;
  return <p className={styles.footnote}>{text}</p>;
}
