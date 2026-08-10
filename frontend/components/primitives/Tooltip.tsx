"use client";

/**
 * Shared floating tooltip system -- single absolutely-positioned div, shown
 * on hover/focus over any chart element or KPI card, tracks pointer position
 * relative to the viewport, auto-flips near viewport edges. Supports
 * onFocus/onBlur alongside onMouseEnter/onMouseLeave for keyboard
 * accessibility (a required improvement over the hover-only mock).
 */

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import styles from "./Tooltip.module.css";

export interface TooltipRow {
  label: string;
  value: string;
}

export interface TooltipContent {
  title: string;
  rows: TooltipRow[];
  note?: string;
}

interface TooltipState {
  content: TooltipContent;
  x: number;
  y: number;
}

interface TooltipContextValue {
  show: (content: TooltipContent, x: number, y: number) => void;
  hide: () => void;
}

const TooltipContext = createContext<TooltipContextValue | null>(null);

export function TooltipProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<TooltipState | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const show = useCallback((content: TooltipContent, x: number, y: number) => {
    if (hideTimer.current) {
      clearTimeout(hideTimer.current);
      hideTimer.current = null;
    }
    setState({ content, x, y });
  }, []);

  const hide = useCallback(() => {
    hideTimer.current = setTimeout(() => setState(null), 40);
  }, []);

  return (
    <TooltipContext.Provider value={{ show, hide }}>
      {children}
      {state ? <TooltipView state={state} /> : null}
    </TooltipContext.Provider>
  );
}

function TooltipView({ state }: { state: TooltipState }) {
  const flipX = state.x > (typeof window !== "undefined" ? window.innerWidth - 220 : 9999);
  const flipY = state.y > (typeof window !== "undefined" ? window.innerHeight - 160 : 9999);

  const style: React.CSSProperties = {
    left: flipX ? state.x - 12 : state.x + 12,
    top: flipY ? state.y - 12 : state.y + 12,
    transform: `${flipX ? "translateX(-100%)" : ""} ${flipY ? "translateY(-100%)" : ""}`.trim(),
  };

  return (
    <div className={styles.tooltip} style={style} role="tooltip">
      <div className={styles.title}>{state.content.title}</div>
      {state.content.rows.map((row, i) => (
        <div className={styles.row} key={i}>
          <span className={styles.label}>{row.label}</span>
          <span className={styles.value}>{row.value}</span>
        </div>
      ))}
      {state.content.note ? <div className={styles.note}>{state.content.note}</div> : null}
    </div>
  );
}

export function useTooltip() {
  const ctx = useContext(TooltipContext);
  if (!ctx) {
    throw new Error("useTooltip must be used within a TooltipProvider");
  }

  const bind = (content: TooltipContent) => ({
    onMouseEnter: (e: React.MouseEvent) => ctx.show(content, e.clientX, e.clientY),
    onMouseMove: (e: React.MouseEvent) => ctx.show(content, e.clientX, e.clientY),
    onMouseLeave: () => ctx.hide(),
    onFocus: (e: React.FocusEvent) => {
      const rect = (e.target as HTMLElement).getBoundingClientRect();
      ctx.show(content, rect.left + rect.width / 2, rect.top);
    },
    onBlur: () => ctx.hide(),
    tabIndex: 0,
  });

  return { ...ctx, bind };
}
