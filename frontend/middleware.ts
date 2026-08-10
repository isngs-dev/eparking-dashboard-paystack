import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE_NAME } from "@/lib/auth/constants";

/**
 * Edge routing guard -- NOT the security boundary (Sprint 09 §7, §11 Phase 4,
 * §13 Risk 1). It only checks whether the `eparking_session` cookie is
 * *present*; it never validates the cookie's value against Redis/the
 * backend, because Edge middleware cannot cheaply reach the backend on every
 * request. A forged or expired cookie value passes this check and is caught
 * downstream by `app/(dashboard)/layout.tsx`'s `getCurrentUser()` call,
 * which is the real, authoritative check (`GET /auth/me` against the
 * backend). If a future edit removes the layout-level check assuming this
 * middleware alone covers it, the dashboard silently reopens -- do not let
 * that happen without re-reading Sprint 09 §13.
 *
 * Matcher excludes `/login`, `/change-password` (the `(auth)` group -- must
 * stay reachable without a session), `/api/auth` (none currently exist as
 * Next.js route handlers, excluded defensively per the sprint's exact spec),
 * Next's own static/image/favicon assets, and `/logos` (public brand assets
 * under `frontend/public/logos/` -- these must be reachable unauthenticated,
 * since the login page itself renders them before any session exists; added
 * after the initial Sprint 09 build predated the logos folder having real
 * content, which meant every logo request was being redirected to /login).
 */
export function middleware(request: NextRequest) {
  const sessionCookie = request.cookies.get(SESSION_COOKIE_NAME);

  if (sessionCookie) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/login", request.url);
  const next = sanitizeNextPath(request.nextUrl.pathname + request.nextUrl.search);
  if (next !== "/") {
    loginUrl.searchParams.set("next", next);
  }
  return NextResponse.redirect(loginUrl);
}

/**
 * Open-redirect guard for the post-login `next` param. Must start with a
 * single `/` (a relative, same-origin path) and must not start with `//`
 * (a protocol-relative URL that browsers treat as an absolute redirect to
 * another host, e.g. `//evil.example.com`). Anything else falls back to `/`.
 * Exported for isolated unit testing (see Phase 4 verification notes) --
 * this logic is intentionally pure so it can be exercised without spinning
 * up full Edge middleware.
 */
export function sanitizeNextPath(path: string): string {
  if (typeof path !== "string" || path.length === 0) {
    return "/";
  }
  if (!path.startsWith("/")) {
    return "/";
  }
  if (path.startsWith("//")) {
    return "/";
  }
  return path;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|logos|login|api/auth).*)"],
};
