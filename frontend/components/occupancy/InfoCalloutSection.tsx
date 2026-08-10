import { getEntryCount } from "@/lib/api/client";
import { tryFetch } from "@/lib/tryFetch";
import type { ResolvedFilters } from "@/lib/filters";
import { InfoCallout } from "@/components/primitives/InfoCallout";

export async function InfoCalloutSection({ filters }: { filters: ResolvedFilters }) {
  const { data: entry } = await tryFetch(() => getEntryCount(filters));
  // Renders unconditionally per Sprint 6 spec -- falls back to the default
  // ticket_only basis text if the entry-count endpoint itself is failing,
  // rather than disappearing (this callout is never the card reporting the error).
  return <InfoCallout entryCountBasis={entry?.entry_count_basis ?? "ticket_only"} />;
}
