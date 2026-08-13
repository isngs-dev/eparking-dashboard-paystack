import type { Metadata } from "next";
import { ChangePasswordForm } from "./ChangePasswordForm";

export const metadata: Metadata = {
  title: "Change Password · E-Parking Revenue Dashboard",
  robots: { index: false, follow: false },
};

/** Voluntary password-change page; first-login use is not required. */
export default function ChangePasswordPage() {
  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 48 }}>
      <div style={{ width: "100%", maxWidth: 400 }}>
        <h1 style={{ marginBottom: 8 }}>Change Password</h1>
        <p style={{ color: "var(--mu)", marginBottom: 24, fontSize: 14 }}>
          Update your password using your current sign-in details.
        </p>
        <ChangePasswordForm />
      </div>
    </div>
  );
}
