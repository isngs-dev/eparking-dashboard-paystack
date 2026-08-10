import type { ReactNode } from "react";

/**
 * Bare layout for the auth route group (`/login`, `/change-password`) --
 * no navbar, no filter bar. As of Phase 4, the navbar lives exclusively in
 * `app/(dashboard)/layout.tsx` (moved there from a root-layout
 * `ConditionalNavbar` client-side pathname check, now that a real
 * `(dashboard)` vs `(auth)` route-group boundary exists), so this bare
 * layout correctly never renders one -- nothing to suppress here. This
 * layout is the place to add auth-only chrome later if needed.
 */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
