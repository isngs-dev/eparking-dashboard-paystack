"use client";

import { useState } from "react";
import { useFormState, useFormStatus } from "react-dom";
import { loginAction } from "./actions";
import { initialLoginState } from "./types";
import styles from "./login.module.css";

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className={styles.submitButton} disabled={pending}>
      {pending ? "Signing in..." : "Sign In"}
    </button>
  );
}

export function LoginForm({ next = "/" }: { next?: string }) {
  const [state, formAction] = useFormState(loginAction, initialLoginState);
  const [showPassword, setShowPassword] = useState(false);

  return (
    <form action={formAction} noValidate>
      <input type="hidden" name="next" value={next} />
      {state.error ? (
        <div className={styles.errorBanner} role="alert">
          {state.error}
        </div>
      ) : null}

      <div className={styles.field}>
        <label className={styles.label} htmlFor="email">
          Email Address
        </label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="username"
          placeholder="you@example.com"
          required
          className={styles.input}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="password">
          Password
        </label>
        <div className={styles.passwordRow}>
          <input
            id="password"
            name="password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            required
            className={`${styles.input} ${styles.passwordInput}`}
          />
          <button
            type="button"
            className={styles.toggleVisibility}
            onClick={() => setShowPassword((v) => !v)}
            aria-pressed={showPassword}
            aria-label={showPassword ? "Hide password" : "Show password"}
          >
            {showPassword ? <EyeOffIcon /> : <EyeIcon />}
          </button>
        </div>
      </div>

      <SubmitButton />

      <p className={styles.helperText}>Contact your administrator to reset your password.</p>
    </form>
  );
}

function EyeIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a19.9 19.9 0 0 1 5.06-6.06M9.9 4.24A10.4 10.4 0 0 1 12 4c7 0 11 8 11 8a19.9 19.9 0 0 1-3.22 4.4M14.12 14.12a3 3 0 1 1-4.24-4.24"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M1 1l22 22" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
