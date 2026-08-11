/**
 * Dedicated server-side helper for the login/change-password flows (Phase 3
 * scope only). This is deliberately NOT routed through `backendFetch` --
 * `backendFetch` has no notion of cookies/Set-Cookie relaying today, and
 * generalizing it for credential-forwarding is explicitly Phase 4 work (see
 * `.claude/sprints/09_AUTHENTICATION.md` §7, §11 Phase 4). Keeping this
 * separate avoids half-modifying a shared choke point ahead of that phase.
 *
 * Never log request/response bodies here -- they can contain plaintext
 * passwords.
 */

import { apiBaseUrl, originHeader } from "@/lib/api/backendConfig";

// `apiBaseUrl`/`originHeader` moved to `lib/api/backendConfig.ts` in Phase 4
// so `lib/auth/session.ts` and `lib/api/backendFetch.ts` can share the same
// base-URL resolution and Origin-header logic rather than triplicating it.
// The Origin-header requirement itself is unchanged from Phase 3: the
// backend's CSRF/Origin-check middleware rejects any cookie-bearing or
// `/auth/*` request that lacks an `Origin` header matching `CORS_ORIGINS`.
// Confirmed necessary by live testing against the running backend -- omitting
// it produces a 403 that has nothing to do with credentials.

export interface PublicUser {
  id: number;
  email: string;
  role: "ADMIN" | "VIEWER";
  display_name: string;
  organization: string | null;
  must_change_password: boolean;
  [key: string]: unknown;
}

export interface LoginSuccess {
  ok: true;
  user: PublicUser;
  mustChangePassword: boolean;
  setCookie: string | null;
}

export interface LoginFailure {
  ok: false;
  status: number;
  detail: string;
}

export type LoginResult = LoginSuccess | LoginFailure;

/**
 * Calls `POST /auth/login` directly (not via backendFetch, see file header).
 * Returns the raw `Set-Cookie` header string (if present) so the caller
 * (the server action) can relay it onto the Next.js response via
 * `cookies()` from `next/headers`. `fetch`'s Headers API intentionally does
 * not expose Set-Cookie for security reasons in browser contexts, but
 * Node's `undici` (used by Next's server-side fetch) does surface it via
 * `res.headers.get("set-cookie")` -- verified by live testing (see report).
 */
export async function loginRequest(email: string, password: string): Promise<LoginResult> {
  let res: Response;
  try {
    res = await fetch(new URL("/auth/login", apiBaseUrl()), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Origin: originHeader(),
      },
      body: JSON.stringify({ email, password }),
      cache: "no-store",
    });
  } catch (err) {
    return {
      ok: false,
      status: 502,
      detail: `Failed to reach the authentication service: ${(err as Error).message}`,
    };
  }

  const setCookie = res.headers.get("set-cookie");

  let body: Record<string, unknown> = {};
  try {
    body = await res.json();
  } catch {
    // no/invalid JSON body -- fall through to generic handling below
  }

  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "Invalid email or password.";
    return { ok: false, status: res.status, detail };
  }

  return {
    ok: true,
    user: body.user as PublicUser,
    mustChangePassword: Boolean(body.must_change_password),
    setCookie,
  };
}

export interface ChangePasswordResult {
  ok: boolean;
  status: number;
  detail: string;
}

/**
 * Calls `POST /auth/change-password`. Requires the current session cookie,
 * which the caller must forward explicitly (server actions run in a
 * separate fetch context, not the browser's cookie jar).
 */
export async function changePasswordRequest(
  cookieHeader: string,
  currentPassword: string,
  newPassword: string
): Promise<ChangePasswordResult> {
  let res: Response;
  try {
    res = await fetch(new URL("/auth/change-password", apiBaseUrl()), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Origin: originHeader(),
        Cookie: cookieHeader,
      },
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      cache: "no-store",
    });
  } catch (err) {
    return { ok: false, status: 502, detail: `Failed to reach the authentication service: ${(err as Error).message}` };
  }

  let body: Record<string, unknown> = {};
  try {
    body = await res.json();
  } catch {
    // no/invalid JSON body
  }

  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "Unable to change password.";
    return { ok: false, status: res.status, detail };
  }

  return { ok: true, status: res.status, detail: "Password changed." };
}

/**
 * Parses the attributes off a single `Set-Cookie` header string so they can
 * be re-applied via `cookies().set()`. Only handles the single-cookie case
 * (the login endpoint sets exactly one cookie, `eparking_session`) -- does
 * not attempt to split multiple combined Set-Cookie values, which Node's
 * fetch implementation does not concatenate for this project's use case.
 */
export function parseSetCookie(setCookie: string): {
  name: string;
  value: string;
  path?: string;
  httpOnly: boolean;
  secure: boolean;
  sameSite?: "lax" | "strict" | "none";
  maxAge?: number;
} | null {
  const parts = setCookie.split(";").map((p) => p.trim());
  const [nameValue, ...attrs] = parts;
  const eqIdx = nameValue.indexOf("=");
  if (eqIdx === -1) return null;
  const name = nameValue.slice(0, eqIdx);
  const value = nameValue.slice(eqIdx + 1);

  let path: string | undefined;
  let httpOnly = false;
  let secure = false;
  let sameSite: "lax" | "strict" | "none" | undefined;
  let maxAge: number | undefined;

  for (const attr of attrs) {
    const [rawKey, rawVal] = attr.split("=");
    const key = rawKey.trim().toLowerCase();
    switch (key) {
      case "path":
        path = rawVal;
        break;
      case "httponly":
        httpOnly = true;
        break;
      case "secure":
        secure = true;
        break;
      case "samesite":
        sameSite = (rawVal?.trim().toLowerCase() as "lax" | "strict" | "none") ?? undefined;
        break;
      case "max-age":
        maxAge = rawVal ? Number(rawVal) : undefined;
        break;
      default:
        break;
    }
  }

  return { name, value, path, httpOnly, secure, sameSite, maxAge };
}
