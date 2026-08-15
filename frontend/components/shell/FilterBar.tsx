"use client";

/**
 * The only stateful client component driving navigation -- every visual is
 * an async server component reading from `searchParams`. State lives
 * entirely in the URL query string with param names matching the API's own
 * (`from`, `to`, `vehicle_types`, `days`).
 */

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useTransition } from "react";
import { DAY_OPTIONS, defaultDateRange } from "@/lib/filters";
import { vehicleTypeLabel } from "@/lib/seriesColors";
import {
  DateRangePicker,
  formatDateRangeLabel,
} from "@/components/filter/DateRangePicker";
import styles from "./FilterBar.module.css";

export function FilterBar({ vehicleTypes }: { vehicleTypes: string[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [, startTransition] = useTransition();

  const defaults = defaultDateRange();
  const from = searchParams.get("from") ?? defaults.from;
  const to = searchParams.get("to") ?? defaults.to;
  const vehicleTypesParam = searchParams.get("vehicle_types") ?? "";
  const daysParam = searchParams.get("days") ?? "";
  const dateLabel = formatDateRangeLabel(from, to);
  const vehicleLabel = vehicleTypesParam ? vehicleTypeLabel(vehicleTypesParam) : "All types";
  const dayLabel = DAY_OPTIONS.find((day) => day.value === daysParam)?.label ?? "All days";

  function pushParams(next: Record<string, string | undefined>) {
    const params = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(next)) {
      if (value === undefined || value === "") {
        params.delete(key);
      } else {
        params.set(key, value);
      }
    }
    startTransition(() => {
      router.push(`${pathname}?${params.toString()}`);
    });
  }

  function handleClearAll() {
    startTransition(() => {
      router.push(pathname);
    });
  }

  return (
    <div className={styles.bar}>
      <span className={styles.label}>Global filters</span>

      <DateRangePicker from={from} to={to} onChange={(f, t) => pushParams({ from: f, to: t })} />

      <div className={styles.chip}>
        <span className={styles.chipLabel}>Vehicle type</span>
        <select
          value={vehicleTypesParam}
          onChange={(e) => pushParams({ vehicle_types: e.target.value || undefined })}
        >
          <option value="">All types</option>
          {vehicleTypes.filter((vt) => vt !== "Porter").map((vt) => (
            <option key={vt} value={vt}>
              {vehicleTypeLabel(vt)}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.chip}>
        <span className={styles.chipLabel}>Day</span>
        <select
          value={daysParam}
          onChange={(e) => pushParams({ days: e.target.value || undefined })}
        >
          <option value="">All days</option>
          {DAY_OPTIONS.map((d) => (
            <option key={d.value} value={d.value}>
              {d.label}
            </option>
          ))}
        </select>
      </div>

      <div
        className={styles.currentFilters}
        aria-label={`Current filters: Date ${dateLabel}, Vehicle type ${vehicleLabel}, Day ${dayLabel}`}
      >
        <span className={styles.currentFiltersTitle}>Current Filters:</span>
        <span className={styles.currentFilter}>Date – {dateLabel}</span>
        <span className={styles.separator} aria-hidden="true">·</span>
        <span className={styles.currentFilter}>Vehicle type – {vehicleLabel}</span>
        <span className={styles.separator} aria-hidden="true">·</span>
        <span className={styles.currentFilter}>Day – {dayLabel}</span>
      </div>

      <div className={styles.spacer} />

      <button type="button" className={styles.clearBtn} onClick={handleClearAll}>
        Clear all filters
      </button>
    </div>
  );
}
