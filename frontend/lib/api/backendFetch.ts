/**
 * Single server-side choke point for all API calls. Never call `fetch`
 * directly against the API from a component -- go through this so timeouts,
 * error surfacing, and the base URL are handled in one place.
 *
 * Runs server-side (RSC / route handlers), so CORS never applies -- but we
 * still use an explicit absolute base URL since Next's server fetch has no
 * implicit origin.
 *
 * Phase 4 (Sprint 09 §7, §11) additions: every call now forwards the
 * browser's `eparking_session` cookie (read via `next/headers`, since a
 * server-side fetch doesn't automatically carry the incoming request's
 * cookies) and attaches a server-only `X-API-Key` selected by the current
 * user's role. Both are resolved via `getCurrentUser()` (the same React
 * `cache()`-wrapped lookup the dashboard layout uses), so this adds at most
 * one extra `/auth/me` call per request, not one per `backendFetch` call.
 *
 * The API-key attachment is currently inert: `/api/*` read endpoints don't
 * require auth yet (that's Phase 5 -- see the sprint doc's explicit
 * ordering, "adding auth to the read routers before backendFetch sends
 * credentials takes the live dashboard down"). Wiring it now means Phase
 * 5's backend flip needs zero frontend changes. Per the sprint's stated
 * precedence rule (§7 "The API-key exchange"), the backend treats a valid
 * session as authoritative over any attached key -- the key is a fallback
 * for service callers, never an escalation path -- so attaching it
 * pre-emptively here is safe even before Phase 5.
 */

import { cookies } from "next/headers";
import { apiBaseUrl } from "./backendConfig";
import { SESSION_COOKIE_NAME } from "@/lib/auth/constants";
import { getCurrentUser } from "@/lib/auth/session";

const DEFAULT_TIMEOUT_MS = 8000;

export class BackendFetchError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "BackendFetchError";
    this.status = status;
    this.detail = detail;
  }
}

export interface BackendFetchOptions {
  params?: Record<string, string | undefined>;
  timeoutMs?: number;
  /** Next.js fetch cache/revalidate controls -- default: no cache, always fresh (API has its own SWR cache layer). */
  revalidate?: number | false;
}

/**
 * Builds the `Cookie`/`X-API-Key` headers forwarded on every backend call.
 * Reads the incoming request's session cookie directly via `next/headers`
 * (not through `getCurrentUser()`, to avoid a hard dependency between "can
 * we forward a cookie" and "did `/auth/me` succeed") and separately calls
 * `getCurrentUser()` only to pick which static API key to attach as a
 * fallback. A missing/invalid session simply means no `Cookie` header and
 * the VIEWER key attached (least-privilege default) -- never ADMIN by
 * default.
 */
async function buildAuthHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {};

  const sessionCookie = cookies().get(SESSION_COOKIE_NAME);
  if (sessionCookie) {
    headers.Cookie = `${SESSION_COOKIE_NAME}=${sessionCookie.value}`;
  }

  const user = await getCurrentUser();
  const isAdmin = user?.role === "ADMIN";
  const apiKey = isAdmin ? process.env.ADMIN_API_KEY : process.env.VIEWER_API_KEY;
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }

  return headers;
}

export async function backendFetch<T>(path: string, options: BackendFetchOptions = {}): Promise<T> {
  const { params, timeoutMs = DEFAULT_TIMEOUT_MS, revalidate = 0 } = options;

  const url = new URL(path, apiBaseUrl());
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") {
        url.searchParams.set(key, value);
      }
    }
  }

  const authHeaders = await buildAuthHeaders();
  const hasCookie = "Cookie" in authHeaders;

  let res: Response;
  try {
    res = await fetch(url.toString(), {
      headers: authHeaders,
      signal: AbortSignal.timeout(timeoutMs),
      // No cross-user cache bleed: whenever a session cookie is attached,
      // force no-store regardless of the caller's requested revalidate
      // window (Sprint 09 §7 -- "no-store whenever a cookie is attached").
      next: hasCookie || revalidate === false ? { revalidate: undefined } : { revalidate },
      cache: hasCookie || revalidate === false ? "no-store" : undefined,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "TimeoutError") {
      throw new BackendFetchError(504, `Request to ${path} timed out after ${timeoutMs}ms.`);
    }
    throw new BackendFetchError(502, `Failed to reach the API at ${path}: ${(err as Error).message}`);
  }

  if (!res.ok) {
    let detail = `Request to ${path} failed with status ${res.status}.`;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") {
        detail = body.detail;
      } else if (body && body.detail) {
        detail = JSON.stringify(body.detail);
      }
    } catch {
      // body wasn't JSON -- keep the generic message
    }
    throw new BackendFetchError(res.status, detail);
  }

  return (await res.json()) as T;
}
