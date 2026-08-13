"use client";

import { useFormState, useFormStatus } from "react-dom";
import { changePasswordAction } from "./actions";
import { initialChangePasswordState } from "./types";
import styles from "../login/login.module.css";

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className={styles.submitButton} disabled={pending}>
      {pending ? "Updating..." : "Update Password"}
    </button>
  );
}

/** Voluntary password-change form for an authenticated user. */
export function ChangePasswordForm() {
  const [state, formAction] = useFormState(changePasswordAction, initialChangePasswordState);

  return (
    <form action={formAction} noValidate style={{ maxWidth: 340 }}>
      {state.error ? (
        <div className={styles.errorBanner} role="alert">
          {state.error}
        </div>
      ) : null}

      <div className={styles.field}>
        <label className={styles.label} htmlFor="current_password">
          Current Password
        </label>
        <input
          id="current_password"
          name="current_password"
          type="password"
          autoComplete="current-password"
          required
          className={styles.input}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="new_password">
          New Password
        </label>
        <input
          id="new_password"
          name="new_password"
          type="password"
          autoComplete="new-password"
          required
          minLength={12}
          className={styles.input}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label} htmlFor="confirm_password">
          Confirm New Password
        </label>
        <input
          id="confirm_password"
          name="confirm_password"
          type="password"
          autoComplete="new-password"
          required
          minLength={12}
          className={styles.input}
        />
      </div>

      <SubmitButton />
    </form>
  );
}
