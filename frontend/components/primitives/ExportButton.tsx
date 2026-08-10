"use client";

import { useEffect } from "react";
import { downloadCsv } from "@/lib/csvExport";
import styles from "./ExportButton.module.css";

/**
 * Per-visual CSV export button. Also listens for the global FilterBar's
 * "Export" button click (a `CustomEvent`) so the global action exports
 * whichever instance registered `primary`, giving the toolbar button a
 * reasonable concrete target without a backend endpoint.
 */
export function ExportButton({
  filename,
  rows,
  eventName,
}: {
  filename: string;
  rows: Record<string, string | number>[];
  eventName?: string;
}) {
  useEffect(() => {
    if (!eventName) return;
    const handler = () => downloadCsv(filename, rows);
    window.addEventListener(eventName, handler);
    return () => window.removeEventListener(eventName, handler);
  }, [eventName, filename, rows]);

  return (
    <button
      type="button"
      className={styles.btn}
      onClick={() => downloadCsv(filename, rows)}
      title="Export this visual's data as CSV"
    >
      Export CSV
    </button>
  );
}
