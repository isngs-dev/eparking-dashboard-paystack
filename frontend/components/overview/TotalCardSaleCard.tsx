import { getCardsTotal } from "@/lib/api/client";
import { tryFetch } from "@/lib/tryFetch";
import { activeFilterKinds, type ResolvedFilters } from "@/lib/filters";
import { ignoredFiltersFootnote } from "@/lib/api/endpointFilters";
import { formatInt, formatNaira } from "@/lib/format";
import { Card } from "@/components/primitives/Card";
import { ErrorCard } from "@/components/primitives/ErrorCard";
import styles from "./TotalCardSaleCard.module.css";

export async function TotalCardSaleCard({ filters }: { filters: ResolvedFilters }) {
  const { data: total, errorMessage } = await tryFetch(() => getCardsTotal(filters));
  if (!total) {
    return <ErrorCard title="Total Card Sale" message={errorMessage!} span={1} />;
  }
  const footnote = ignoredFiltersFootnote("cards_total", activeFilterKinds(filters));

  return (
    <Card span={1} className={styles.card}>
      <span className={styles.label}>Total Card Sale</span>
      <span className={styles.value}>{formatNaira(total.card_total_amount)}</span>
      <div className={styles.breakdown}>
        <div className={styles.row}>
          <span className={styles.swatch} style={{ background: "var(--s1)" }} />
          <span className={styles.rowLabel}>Annual</span>
          <span className={styles.rowValue}>{formatNaira(total.annual_amount)}</span>
        </div>
        <div className={styles.row}>
          <span className={styles.swatch} style={{ background: "var(--s3)" }} />
          <span className={styles.rowLabel}>Monthly</span>
          <span className={styles.rowValue}>{formatNaira(total.monthly_amount)}</span>
        </div>
      </div>
      <p className={styles.detail}>
        {formatInt(total.annual_count)} annual · {formatInt(total.monthly_count)} monthly cards.
        ₦12,500 bundles split across both sub-types.
      </p>
      {footnote ? <p className={styles.footnote}>{footnote}</p> : null}
    </Card>
  );
}
