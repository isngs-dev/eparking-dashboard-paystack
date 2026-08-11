/**
 * Shared server-only config for every module that talks to the FastAPI
 * backend directly (`lib/api/backendFetch.ts`, `lib/auth/login.ts`,
 * `lib/auth/session.ts`). Extracted in Phase 4 (Sprint 09 §7/§11) so the
 * base-URL resolution and the Origin-header value aren't triplicated across
 * those three call sites -- see `lib/auth/login.ts`'s original comment for
 * why the Origin header is required at all (the backend's CSRF/Origin-check
 * middleware, Sprint 09 §8).
 */

export function apiBaseUrl(): string {
  return process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8080";
}

/**
 * The Origin a real browser on this app would send. Only load-bearing for
 * state-changing (`POST`/`PATCH`/`DELETE`) requests that carry the session
 * cookie or hit `/auth/*` -- the backend's CSRF middleware does not check
 * `GET`/`HEAD`/`OPTIONS` (see `services/api/app/main.py`'s
 * `csrf_origin_check_middleware`). Harmless to attach on GET calls too.
 */
export function originHeader(): string {
  return process.env.APP_ORIGIN ?? "http://localhost:3000";
}
