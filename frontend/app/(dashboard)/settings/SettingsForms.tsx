"use client";

import { useFormState, useFormStatus } from "react-dom";
import type { PublicUser } from "@/lib/auth/login";
import { updateOwnPasswordAction, updateProfileAction } from "./actions";
import { initialSettingsActionState } from "./state";
import styles from "./settings.module.css";

function SubmitButton({ children }: { children: string }) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className={styles.primaryButton} disabled={pending}>
      {pending ? "Saving..." : children}
    </button>
  );
}

function ActionMessage({
  state,
}: {
  state: typeof initialSettingsActionState;
}) {
  if (!state.message) return null;
  return (
    <p
      className={state.ok ? styles.successMessage : styles.errorMessage}
      role={state.ok ? "status" : "alert"}
    >
      {state.message}
    </p>
  );
}

export function ProfileForm({ user }: { user: PublicUser }) {
  const [state, action] = useFormState(
    updateProfileAction,
    initialSettingsActionState,
  );

  return (
    <form action={action} className={styles.form}>
      <div className={styles.field}>
        <label htmlFor="settings-display-name">Display name</label>
        <input
          id="settings-display-name"
          name="display_name"
          type="text"
          defaultValue={user.display_name}
          maxLength={120}
          autoComplete="name"
          required
        />
      </div>
      <div className={styles.readonlyGrid}>
        <div>
          <span>Email</span>
          <strong>{user.email}</strong>
        </div>
        <div>
          <span>Role</span>
          <strong>{user.role}</strong>
        </div>
        <div>
          <span>Organization</span>
          <strong>{user.organization ?? "None"}</strong>
        </div>
      </div>
      <SubmitButton>Save name</SubmitButton>
      <ActionMessage state={state} />
    </form>
  );
}

export function PasswordForm() {
  const [state, action] = useFormState(
    updateOwnPasswordAction,
    initialSettingsActionState,
  );

  return (
    <form action={action} className={styles.form}>
      <div className={styles.field}>
        <label htmlFor="settings-current-password">Current password</label>
        <input
          id="settings-current-password"
          name="current_password"
          type="password"
          autoComplete="current-password"
          maxLength={160}
          required
        />
      </div>
      <div className={styles.field}>
        <label htmlFor="settings-new-password">New password</label>
        <input
          id="settings-new-password"
          name="new_password"
          type="password"
          autoComplete="new-password"
          minLength={12}
          maxLength={160}
          required
        />
      </div>
      <div className={styles.field}>
        <label htmlFor="settings-confirm-password">Confirm new password</label>
        <input
          id="settings-confirm-password"
          name="confirm_password"
          type="password"
          autoComplete="new-password"
          minLength={12}
          maxLength={160}
          required
        />
      </div>
      <p className={styles.hint}>
        Use 12-160 characters and avoid common passwords. Other active sessions
        will be logged out.
      </p>
      <SubmitButton>Update password</SubmitButton>
      <ActionMessage state={state} />
    </form>
  );
}
