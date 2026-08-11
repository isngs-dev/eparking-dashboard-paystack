"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { apiBaseUrl, originHeader } from "@/lib/api/backendConfig";
import { SESSION_COOKIE_NAME } from "@/lib/auth/constants";

/**
 * Logout as a server action (Sprint 09 §7, §11 Phase 4) -- deliberately not
 * a client-side `fetch` to `/auth/logout`. Running server-side means the
 * Origin-header CSRF check is satisfied the same way the login/change-
 * password server actions satisfy it, and the cookie-clearing happens in
 * the same server response as the redirect, so there's no window where the
 * browser still holds a cookie the server has already forgotten about.
 *
 * Calls the real backend endpoint (not just a local cookie-delete) so the
 * Redis session is actually destroyed -- per the sprint's explicit "logout
 * must actually call the revocation endpoint" acceptance criterion (§2,
 * citing the KB's "dead blacklist" audit finding). A failed backend call
 * still clears the local cookie and redirects -- a user should never get
 * stuck unable to log out just because the revocation call had a hiccup,
 * even though that means the Redis session could outlive the browser
 * cookie until its own idle/absolute expiry in that edge case.
 */
export async function logoutAction(): Promise<void> {
  const sessionCookie = cookies().get(SESSION_COOKIE_NAME);

  if (sessionCookie) {
    try {
      await fetch(new URL("/auth/logout", apiBaseUrl()), {
        method: "POST",
        headers: {
          Origin: originHeader(),
          Cookie: `${SESSION_COOKIE_NAME}=${sessionCookie.value}`,
        },
        cache: "no-store",
      });
    } catch {
      // Backend unreachable -- still clear the local cookie below so the
      // user isn't stuck "logged in" in the browser even if the server-side
      // session outlives this request.
    }
  }

  cookies().delete(SESSION_COOKIE_NAME);
  redirect("/login");
}
