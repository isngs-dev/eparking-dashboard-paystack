/**
 * Shared constants for the frontend's auth machinery. Single source of
 * truth for the session cookie name so `middleware.ts`, `lib/auth/login.ts`,
 * `lib/auth/session.ts`, and the change-password server action never drift
 * out of sync with each other or with the backend's `session_cookie_name`
 * setting (`services/common/eparking_common/config.py`, default
 * `"eparking_session"` -- see Sprint 09 §4).
 */
export const SESSION_COOKIE_NAME = "eparking_session";
