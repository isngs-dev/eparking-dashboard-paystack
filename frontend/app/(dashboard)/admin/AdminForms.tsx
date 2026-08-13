"use client";

import { useFormState, useFormStatus } from "react-dom";
import {
  createUserAction,
  updatePasswordAction,
} from "./actions";
import { initialAdminActionState } from "./state";
import styles from "./admin.module.css";

function PendingButton({
  children,
  className,
}: {
  children: string;
  className?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className={className ?? styles.primaryButton} disabled={pending}>
      {pending ? "Working..." : children}
    </button>
  );
}

export function CreateUserForm() {
  const [state, formAction] = useFormState(createUserAction, initialAdminActionState);

  return (
    <form action={formAction} className={styles.createForm}>
      <div className={styles.field}>
        <label htmlFor="email">Email</label>
        <input id="email" name="email" type="email" autoComplete="off" required />
      </div>
      <div className={styles.field}>
        <label htmlFor="display_name">Display Name</label>
        <input id="display_name" name="display_name" type="text" autoComplete="off" required />
      </div>
      <div className={styles.field}>
        <label htmlFor="role">Role</label>
        <select id="role" name="role" defaultValue="VIEWER">
          <option value="VIEWER">VIEWER</option>
          <option value="ADMIN">ADMIN</option>
        </select>
      </div>
      <div className={styles.field}>
        <label htmlFor="organization">Organization</label>
        <select id="organization" name="organization" defaultValue="">
          <option value="">None</option>
          <option value="AICL">AICL</option>
          <option value="GSDS">GSDS</option>
        </select>
      </div>
      <div className={styles.field}>
        <label htmlFor="password">Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="new-password"
          minLength={12}
          maxLength={160}
          required
        />
      </div>
      <div className={styles.field}>
        <label htmlFor="confirm_password">Confirm Password</label>
        <input
          id="confirm_password"
          name="confirm_password"
          type="password"
          autoComplete="new-password"
          minLength={12}
          maxLength={160}
          required
        />
      </div>
      <p className={styles.passwordHint}>Use 12-160 characters and avoid common passwords.</p>
      <PendingButton>Create User</PendingButton>
      <ActionResult state={state} />
    </form>
  );
}

export function EditPasswordForm({ userId }: { userId: number }) {
  const [state, formAction] = useFormState(updatePasswordAction, initialAdminActionState);

  return (
    <details className={styles.passwordEditor}>
      <summary>Edit password</summary>
      <form action={formAction} className={styles.passwordAction}>
        <input type="hidden" name="user_id" value={userId} />
        <label htmlFor={`new-password-${userId}`}>New password</label>
        <input
          id={`new-password-${userId}`}
          name="new_password"
          type="password"
          autoComplete="new-password"
          minLength={12}
          maxLength={160}
          required
        />
        <label htmlFor={`confirm-password-${userId}`}>Confirm password</label>
        <input
          id={`confirm-password-${userId}`}
          name="confirm_password"
          type="password"
          autoComplete="new-password"
          minLength={12}
          maxLength={160}
          required
        />
        <PendingButton className={styles.secondaryButton}>Update Password</PendingButton>
        <ActionResult state={state} />
      </form>
    </details>
  );
}

function ActionResult({ state }: { state: typeof initialAdminActionState }) {
  if (!state.message) {
    return null;
  }

  return (
    <div className={state.ok ? styles.successBox : styles.errorBox}>
      <p>{state.message}</p>
    </div>
  );
}
