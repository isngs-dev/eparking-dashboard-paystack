import { cache } from "react";
import { cookies } from "next/headers";
import { apiBaseUrl, originHeader } from "@/lib/api/backendConfig";
import { SESSION_COOKIE_NAME } from "@/lib/auth/constants";
import type { PublicUser } from "@/lib/auth/login";

/**
 * `getCurrentUser()` is the AUTHORITATIVE auth check (Sprint 09 §7, §11
 * Phase 4). Unlike `middleware.ts` (a routing guard that only checks cookie
 * *presence*), this calls `GET /auth/me` on the real backend, which
 * re-reads the user row from Postgres and validates the session against
 * Redis (idle/absolute expiry, revocation) -- see
 * `services/api/app/routers/auth.py::me`. `app/(dashboard)/layout.tsx` is
 * the only place this function's result is allowed to gate rendering; if
 * that layout-level check is ever removed on the assumption that middleware
 * alone covers it, the dashboard silently reopens to anonymous access
 * (Sprint 09 §13 Risk 1).
 *
 * Wrapped in React's `cache()` so multiple server components rendered
 * during one request (the dashboard layout, the navbar user chip,
 * `backendFetch`'s own internal role lookup) collapse into a single
 * `/auth/me` call per request, not one per caller.
 *
 * Returns `null` on any non-200 response OR any network failure -- never
 * throws. This is a genuine trade-off, not an oversight: treating a backend
 * outage identically to "no session" means a real API outage will look to
 * users like "everyone got logged out" rather than a distinguishable
 * service-unavailable state. Accepted for Phase 4 because the alternative
 * (letting the error propagate) would crash every page's render on a
 * transient backend hiccup, which is worse for an unauthenticated-looking
 * dashboard than a moment of "please log in again". Revisit if outage
 * reports trace back to this ambiguity.
 */
export const getCurrentUser = cache(async (): Promise<PublicUser | null> => {
  const sessionCookie = cookies().get(SESSION_COOKIE_NAME);
  if (!sessionCookie) {
    return null;
  }

  let res: Response;
  try {
    res = await fetch(new URL("/auth/me", apiBaseUrl()), {
      method: "GET",
      headers: {
        Origin: originHeader(),
        Cookie: `${SESSION_COOKIE_NAME}=${sessionCookie.value}`,
      },
      // Per-user response -- never let Next's fetch cache serve one user's
      // `/auth/me` result to another request. GET requests aren't subject
      // to the backend's CSRF/Origin check, but the Origin header is
      // attached anyway for consistency with the other auth calls.
      cache: "no-store",
    });
  } catch {
    return null;
  }

  if (!res.ok) {
    return null;
  }

  try {
    return (await res.json()) as PublicUser;
  } catch {
    return null;
  }
});
