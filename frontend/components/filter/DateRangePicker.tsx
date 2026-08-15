"use client";

/**
 * Airbnb-style two-click date range picker. State machine:
 *
 *   idle (anchor === null)  --click day d-->  picking (anchor = d)
 *   picking (anchor = a)    --click day d-->
 *       d === a  -> commit(a, a)              single-day range
 *       d  >  a  -> commit(a, d)
 *       d  <  a  -> picking (anchor = d)       restart, d becomes new anchor
 *
 * Every selection is a fresh two-click gesture -- there is no transition
 * that shrinks/extends an existing complete range; reopening the popover
 * always starts a new pick from idle. `onChange` (which the caller wires to
 * `pushParams`) fires exactly once, at the moment a range is committed --
 * never per click, never on Escape/outside-click (those are pure cancels).
 */

import { useEffect, useRef, useState } from "react";
import {
  addMonths,
  buildMonthGrid,
  monthStart,
  monthTitle,
  todayIso,
  WEEKDAY_LABELS,
  type GridCell,
} from "@/lib/dateGrid";
import { formatFullDate, formatShortDate } from "@/lib/format";
import styles from "./DateRangePicker.module.css";

export interface DateRangePickerProps {
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
}

export function formatDateRangeLabel(from: string, to: string): string {
  if (from === to) {
    return formatFullDate(from);
  }
  const sameYear = from.slice(0, 4) === to.slice(0, 4);
  if (sameYear) {
    return `${formatShortDate(from)} to ${formatShortDate(to)}`;
  }
  return `${formatFullDate(from)} to ${formatFullDate(to)}`;
}

export function DateRangePicker({ from, to, onChange }: DateRangePickerProps) {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [month, setMonth] = useState<string>(() => monthStart(to));
  const [focusedDay, setFocusedDay] = useState<string>(to);

  const wrapRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const dayRefs = useRef<Map<string, HTMLButtonElement>>(new Map());

  const today = todayIso();

  function closeCancel() {
    setOpen(false);
    setAnchor(null);
    setHover(null);
  }

  function commit(f: string, t: string) {
    setAnchor(null);
    setHover(null);
    setOpen(false);
    onChange(f, t);
    triggerRef.current?.focus();
  }

  function openPicker() {
    setMonth(monthStart(to));
    setAnchor(null);
    setHover(null);
    setFocusedDay(to);
    setOpen(true);
  }

  function isDisabled(iso: string): boolean {
    return iso > today;
  }

  function onDayClick(d: string) {
    if (isDisabled(d)) return;

    if (anchor === null) {
      // row 1 -- begin new selection
      setAnchor(d);
      setHover(d);
      return;
    }

    if (d < anchor) {
      // row 5 -- restart, earlier day becomes new anchor
      setAnchor(d);
      setHover(d);
      return;
    }

    // rows 3 & 4 -- d >= anchor, range complete (d === anchor => single day)
    commit(anchor, d);
  }

  // Dismissal: pointerdown (not click) + Escape.
  useEffect(() => {
    if (!open) return;
    function onDocPointerDown(e: PointerEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) {
        closeCancel();
      }
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        closeCancel();
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", onDocPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onDocPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Focus the roving-tabindex day whenever it (or the visible month) changes.
  useEffect(() => {
    if (!open) return;
    const el = dayRefs.current.get(focusedDay);
    el?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedDay, month, open]);

  function moveFocus(deltaDays: number) {
    const [y, m, d] = focusedDay.split("-").map(Number);
    const dt = new Date(Date.UTC(y, m - 1, d, 12));
    dt.setUTCDate(dt.getUTCDate() + deltaDays);
    const next = `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, "0")}-${String(dt.getUTCDate()).padStart(2, "0")}`;
    const nextMonth = monthStart(next);
    if (nextMonth !== month) setMonth(nextMonth);
    setFocusedDay(next);
  }

  function movePageMonth(deltaMonths: number) {
    const [y, m, d] = focusedDay.split("-").map(Number);
    const dt = new Date(Date.UTC(y, m - 1, d, 12));
    dt.setUTCMonth(dt.getUTCMonth() + deltaMonths);
    const next = `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, "0")}-${String(dt.getUTCDate()).padStart(2, "0")}`;
    const nextMonth = monthStart(next);
    if (nextMonth !== month) setMonth(nextMonth);
    setFocusedDay(next);
  }

  function onGridKeyDown(e: React.KeyboardEvent) {
    switch (e.key) {
      case "ArrowLeft":
        e.preventDefault();
        moveFocus(-1);
        break;
      case "ArrowRight":
        e.preventDefault();
        moveFocus(1);
        break;
      case "ArrowUp":
        e.preventDefault();
        moveFocus(-7);
        break;
      case "ArrowDown":
        e.preventDefault();
        moveFocus(7);
        break;
      case "PageUp":
        e.preventDefault();
        movePageMonth(-1);
        break;
      case "PageDown":
        e.preventDefault();
        movePageMonth(1);
        break;
      case "Home": {
        e.preventDefault();
        const dow = new Date(`${focusedDay}T12:00:00Z`).getUTCDay();
        moveFocus(-dow);
        break;
      }
      case "End": {
        e.preventDefault();
        const dow = new Date(`${focusedDay}T12:00:00Z`).getUTCDay();
        moveFocus(6 - dow);
        break;
      }
      case "Enter":
      case " ":
        e.preventDefault();
        onDayClick(focusedDay);
        break;
      default:
        break;
    }
  }

  const cells = buildMonthGrid(month);
  const canGoNext = month < monthStart(today);

  const shownFrom = anchor ?? from;
  const shownTo = anchor === null ? to : hover && hover >= anchor ? hover : anchor;

  const liveMessage =
    anchor === null
      ? `${formatFullDate(from)} to ${formatFullDate(to)} selected.`
      : `Start date ${formatFullDate(anchor)} selected. Now select an end date.`;

  const weeks: GridCell[][] = [];
  for (let i = 0; i < 6; i++) {
    weeks.push(cells.slice(i * 7, i * 7 + 7));
  }

  return (
    <div className={styles.wrap} ref={wrapRef}>
      <button
        ref={triggerRef}
        type="button"
        className={`${styles.trigger} ${open ? styles.triggerOpen : ""}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => (open ? closeCancel() : openPicker())}
      >
        <span className={styles.chipLabel}>Date range</span>
        <span className={styles.value}>{formatDateRangeLabel(from, to)}</span>
      </button>

      {open ? (
        <div
          className={styles.popover}
          role="dialog"
          aria-modal="false"
          aria-label="Select date range"
        >
          <div className={styles.header}>
            <button
              type="button"
              className={styles.navBtn}
              aria-label="Previous month"
              onClick={() => setMonth(addMonths(month, -1))}
            >
              &#8249;
            </button>
            <span className={styles.monthTitle}>{monthTitle(month)}</span>
            <button
              type="button"
              className={styles.navBtn}
              aria-label="Next month"
              disabled={!canGoNext}
              onClick={() => setMonth(addMonths(month, 1))}
            >
              &#8250;
            </button>
          </div>

          <div className={styles.weekdayRow}>
            {WEEKDAY_LABELS.map((label, i) => (
              <span key={i} className={styles.weekday}>
                {label}
              </span>
            ))}
          </div>

          <div
            className={styles.grid}
            role="grid"
            onKeyDown={onGridKeyDown}
            onMouseLeave={() => setHover(anchor)}
          >
            {weeks.map((week, wi) => (
              <div className={styles.row} role="row" key={wi}>
                {week.map((cell) => {
                  const disabled = isDisabled(cell.iso);
                  const isToday = cell.iso === today;
                  const isStart = cell.iso === shownFrom;
                  const isEnd = cell.iso === shownTo;
                  const inRange = cell.iso > shownFrom && cell.iso < shownTo;
                  const preview = anchor !== null;
                  const isSingle = isStart && isEnd;
                  const isAnchorOnly = anchor !== null && cell.iso === anchor && shownFrom === shownTo;

                  const classes = [styles.day];
                  if (!cell.inMonth) classes.push(styles.dayOutside);
                  if (isToday && !isStart && !isEnd) classes.push(styles.dayToday);
                  if (inRange) classes.push(preview ? styles.dayInRangePreview : styles.dayInRange);
                  if (isSingle || isAnchorOnly) {
                    classes.push(anchor !== null ? styles.dayAnchor : styles.daySingle);
                  } else if (isStart) {
                    classes.push(styles.dayStart);
                  } else if (isEnd) {
                    classes.push(styles.dayEnd);
                  }
                  if (disabled) classes.push(styles.dayDisabled);

                  return (
                    <div className={styles.cell} role="gridcell" key={cell.iso}>
                      <button
                        ref={(el) => {
                          if (el) dayRefs.current.set(cell.iso, el);
                          else dayRefs.current.delete(cell.iso);
                        }}
                        type="button"
                        className={classes.join(" ")}
                        tabIndex={cell.iso === focusedDay ? 0 : -1}
                        disabled={disabled}
                        aria-label={formatFullDate(cell.iso)}
                        aria-selected={isStart || isEnd || inRange}
                        onClick={() => onDayClick(cell.iso)}
                        onMouseEnter={() => {
                          if (anchor !== null) setHover(cell.iso);
                        }}
                        onFocus={() => setFocusedDay(cell.iso)}
                      >
                        {Number(cell.iso.slice(8, 10))}
                      </button>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>

          <div className={styles.srOnly} aria-live="polite">
            {liveMessage}
          </div>
        </div>
      ) : null}
    </div>
  );
}
