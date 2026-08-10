"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "./ThemeToggle";
import { logoutAction } from "@/lib/auth/logout";
import type { PublicUser } from "@/lib/auth/login";
import styles from "./Navbar.module.css";

const NAV_ITEMS = [
  { href: "/", label: "Overview · Revenue" },
  { href: "/occupancy", label: "Occupancy & Traffic" },
];

function initials(displayName: string): string {
  const parts = displayName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function Navbar({ user }: { user: PublicUser }) {
  const pathname = usePathname();

  return (
    <nav className={styles.navbar}>
      <div className={styles.brand}>
        <Image
          src="/logos/aicl.png"
          alt="Abuja Investments Company Limited"
          width={64}
          height={64}
          className={styles.brandLogo}
        />
        <div className={styles.brandText}>
          <span className={styles.brandName}>Smart Parking Dashboard</span>
          <span className={styles.brandSub}>Powered by GSD Solutions</span>
        </div>
      </div>

      <div className={styles.pills}>
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={[styles.pill, active ? styles.pillActive : ""].join(" ")}
            >
              {item.label}
            </Link>
          );
        })}
      </div>

      <div className={styles.actions}>
        <ThemeToggle />
        <div className={styles.userChip} title={user.email}>
          <div className={styles.avatar}>{initials(user.display_name)}</div>
          <div className={styles.userMeta}>
            <span className={styles.userName}>{user.display_name}</span>
            <span className={styles.userRole}>
              {user.role}
              {user.organization ? ` · ${user.organization}` : ""}
            </span>
          </div>
        </div>
        <form action={logoutAction}>
          <button type="submit" className={styles.logoutButton}>
            Log out
          </button>
        </form>
      </div>
    </nav>
  );
}
