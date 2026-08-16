import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth/session";
import { Navbar } from "@/components/shell/Navbar";
import { FloatingBrandBadge } from "@/components/shell/FloatingBrandBadge";

/**
 * Layout for the `(dashboard)` route group (`/`, `/occupancy`) -- the
 * AUTHORITATIVE security boundary for the dashboard (Sprint 09 §7, §11
 * Phase 4, §13 Risk 1). `middleware.ts` only checks whether the session
 * cookie is *present*; THIS layout is what actually validates it, by
 * calling `getCurrentUser()` (which hits the real backend's `GET /auth/me`,
 * re-reading the user row and validating the Redis session). Do not remove
 * this check on the assumption middleware alone covers it -- see the
 * comment in `middleware.ts` and Sprint 09 §13 Risk 1 for the same warning
 * from the other side.
 *
 * The navbar now lives here rather than in the root layout + a client-side
 * `ConditionalNavbar` pathname check. Now that a real `(dashboard)` vs
 * `(auth)` route-group boundary exists, this is the more correct home for
 * it: navbar rendering becomes a property of "which layout tree renders
 * this route" rather than a runtime guess based on the current pathname,
 * and it means `/login`/`/change-password` correctly never render a navbar
 * without depending on a prefix list staying in sync with real routes.
 */
export default async function DashboardLayout({ children }: { children: ReactNode }) {
  const user = await getCurrentUser();

  if (!user) {
    redirect("/login");
  }

  if (user.must_change_password) {
    redirect("/change-password");
  }

  return (
    <>
      <Navbar user={user} />
      {children}
      <FloatingBrandBadge fixed />
    </>
  );
}
