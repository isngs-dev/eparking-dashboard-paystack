import type { Metadata } from "next";
import Image from "next/image";
import { LoginForm } from "./LoginForm";
import { FloatingBrandBadge } from "@/components/shell/FloatingBrandBadge";
import styles from "./login.module.css";

export const metadata: Metadata = {
  title: "Sign In · E-Parking Revenue Dashboard",
  robots: { index: false, follow: false },
};

export default function LoginPage({
  searchParams,
}: {
  searchParams?: { next?: string };
}) {
  const next = sanitizeNextPath(searchParams?.next ?? "/");
  return (
    <div className={styles.page}>
      <div className={styles.formPanel}>
        <div className={styles.formInner}>
          <div className={styles.logoRow}>
            <Image
              src="/logos/aicl.png"
              alt="Abuja Investments Company Limited"
              width={100}
              height={100}
              className={styles.aiclLogo}
              priority
            />
          </div>

          <h1 className={styles.heading}>Welcome Back</h1>
          <p className={styles.subtext}>Please sign in to your account</p>

          <LoginForm next={next} />
        </div>
      </div>

      <div className={styles.brandPanel}>
        {/* Angular accent shape -- approximation, see .brandAccent in
            login.module.css for the note on replacing with a real asset. */}
        <div className={styles.brandAccent} aria-hidden="true" />

        <div className={styles.brandContent}>
          <h2 className={styles.brandHeading}>
            <span className={styles.brandHeadingLine}>
              Welcome to Garki International Market
            </span>
            <br />
            Parking Management Dashboard
          </h2>
          <p className={styles.brandSubtext}>
            Monitor and manage your parking facility with real-time insights
          </p>
        </div>

        <FloatingBrandBadge prominent className={styles.brandBadgePosition} />
      </div>
    </div>
  );
}


function sanitizeNextPath(path: string): string {
  if (!path || !path.startsWith("/") || path.startsWith("//")) {
    return "/";
  }
  if (path === "/login" || path.startsWith("/login?")) {
    return "/";
  }
  return path;
}
