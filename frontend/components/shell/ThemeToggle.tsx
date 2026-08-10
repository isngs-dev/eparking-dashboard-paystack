"use client";

import { useEffect, useState } from "react";
import styles from "./ThemeToggle.module.css";

/**
 * Persists the theme in localStorage and sets `data-theme` on <html>.
 * The inline script in the root layout sets the initial attribute
 * synchronously (before hydration) to avoid a flash-of-wrong-theme on
 * reload; this component just keeps it in sync after mount.
 */
export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const current = document.documentElement.getAttribute("data-theme");
    setTheme(current === "dark" ? "dark" : "light");
  }, []);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      window.localStorage.setItem("eparking-theme", next);
    } catch {
      // localStorage unavailable -- theme just won't persist across reloads
    }
  }

  return (
    <button type="button" className={styles.toggle} onClick={toggle}>
      {theme === "dark" ? "☀ Light" : "☾ Dark"}
    </button>
  );
}
