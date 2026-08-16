import type { Metadata } from "next";
import Image from "next/image";
import { redirect } from "next/navigation";
import { FloatingBrandBadge } from "@/components/shell/FloatingBrandBadge";
import { getCurrentUser } from "@/lib/auth/session";
import { ChangePasswordForm } from "./ChangePasswordForm";
import styles from "../login/login.module.css";

export const metadata: Metadata = {
  title: "Change Password · E-Parking Revenue Dashboard",
  robots: { index: false, follow: false },
};

export default async function ChangePasswordPage() {
  const user = await getCurrentUser();

  if (!user) {
    redirect("/login");
  }

  if (!user.must_change_password) {
    redirect("/");
  }

  return (
    <div className={styles.page}>
      <div className={styles.formPanel}>
        <div className={styles.formInner}>
          <div className={styles.logoRow}>
            <Image
              src="/logos/aicl.png"
              alt="Abuja Investments Company Limited"
              width={64}
              height={64}
              className={styles.aiclLogo}
              priority
            />
          </div>

          <h1 className={styles.heading}>Create Your Password</h1>
          <p className={styles.subtext}>
            For security, replace the temporary password set by your administrator before continuing.
          </p>

          <ChangePasswordForm />
        </div>
      </div>

      <div className={styles.brandPanel}>
        <div className={styles.brandAccent} aria-hidden="true" />
        <div className={styles.brandContent}>
          <h2 className={styles.brandHeading}>Secure your account</h2>
          <p className={styles.brandSubtext}>
            Choose a private password that only you know. You can change it again later from Settings.
          </p>
        </div>
        <FloatingBrandBadge className={styles.brandBadgePosition} />
      </div>
    </div>
  );
}
