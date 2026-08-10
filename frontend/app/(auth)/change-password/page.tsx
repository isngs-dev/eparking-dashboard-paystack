import type { Metadata } from "next";
import { ChangePasswordForm } from "./ChangePasswordForm";

export const metadata: Metadata = {
  title: "Change Password · E-Parking Revenue Dashboard",
  robots: { index: false, follow: false },
};

/**
 * Minimal stub per Sprint 09 Phase 3 -- just enough for the
 * `must_change_password` redirect target to exist and genuinely work.
 * Full enforcement (blocking dashboard routes until the password is
 * changed) is Phase 4's layout-level check, not this page's job.
 */
export default function ChangePasswordPage() {
  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 48 }}>
      <div style={{ width: "100%", maxWidth: 400 }}>
        <h1 style={{ marginBottom: 8 }}>Change Password</h1>
        <p style={{ color: "var(--mu)", marginBottom: 24, fontSize: 14 }}>
          You must set a new password before continuing.
        </p>
        <ChangePasswordForm />
      </div>
    </div>
  );
}
