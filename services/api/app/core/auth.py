"""Two-role auth: `ADMIN` / `VIEWER` -- now dual-mode (session-first, static
API key as fallback).

Sprint 7 originally built this as a static-API-key-per-role scheme (see git
history / the sprint 7 doc for that reasoning) on the premise that there was
no user directory and no individual-identity requirement. Sprint 09
(Authentication & Session Security) added a real per-person login flow
(`routers/auth.py`, `core/sessions.py`, `repositories/users.py`) and this
module's internals were rewritten to consume it -- **the dependency boundary
survives untouched**: `require_admin`/`require_viewer_or_admin` keep the same
names, same import path, same signatures, same 401/403 contract. The 10
`Depends()` call sites in `routers/admin.py`/`routers/ops.py` did not change
for this rewrite, by design (this was the whole point of keeping this
boundary thin from the start).

## Dual-mode resolution, in order (Sprint 09 §7) -- READ THIS BEFORE EDITING

1. **Session cookie, if present and valid, wins -- ALWAYS**, even if an
   `X-API-Key` header is also attached to the same request. The role comes
   from the session's user record. This is a deliberate anti-privilege-
   escalation measure: in the recommended architecture (browser -> Next.js
   server -> FastAPI), the Next.js server attaches its own server-only
   `ADMIN_API_KEY` to every backend call so `/admin/*` keeps working for
   server-rendered admin UI. If a VIEWER's browser session were forwarded
   alongside that ADMIN key and the key were allowed to win (or even just
   "either, whichever is present"), a VIEWER's request would silently
   escalate to ADMIN purely because it happened to transit through a server
   that also holds the admin key. Session-wins closes that: a real logged-in
   VIEWER can never come out of this function as ADMIN, no matter what
   headers ride alongside their cookie.
2. **No valid session -> fall back to the static API key**, exactly as
   Sprint 7 built it (`ADMIN_API_KEY`/`VIEWER_API_KEY` via `X-API-Key`).
   Post-Sprint-09, this path is for non-interactive/service callers only
   (see §12 "Fate of ADMIN_API_KEY/VIEWER_API_KEY" below) -- it is the
   fallback, not the primary mechanism, even though the code path is
   unchanged from Sprint 7.
3. **Neither present/valid -> 401**, exactly as before.

## Fate of `ADMIN_API_KEY`/`VIEWER_API_KEY` (Sprint 09 §12)

Kept permanently, but repositioned: they are no longer the primary browser
auth mechanism, they are service credentials for non-interactive callers --
the Next.js server's server-to-server calls to this API, any future
automation/monitoring script, and the break-glass path if Redis (and
therefore sessions) is down. Per step 1 above, a valid session always takes
precedence over a key attached to the same request, so these keys can safely
keep flowing through every server-side dashboard request without becoming a
privilege-escalation vector for a lower-privileged logged-in user.
"""

from __future__ import annotations

import logging

from fastapi import Cookie, Header, HTTPException, Request

from app.core.sessions import SessionData, read_session
from eparking_common.config import get_settings

logger = logging.getLogger("app.auth")

ROLE_ADMIN = "ADMIN"
ROLE_VIEWER = "VIEWER"


def _role_for_key(api_key: str | None) -> str | None:
    """Static-API-key lookup -- unchanged from Sprint 7. Only consulted when
    no valid session is present (see module docstring, step 2)."""
    if not api_key:
        return None
    settings = get_settings()
    if api_key == settings.admin_api_key:
        return ROLE_ADMIN
    if api_key == settings.viewer_api_key:
        return ROLE_VIEWER
    return None


async def _session_from_cookie(session_cookie: str | None) -> SessionData | None:
    """Reads and validates the session cookie (idle + absolute expiry both
    enforced inside `read_session`). Returns None on any missing/invalid/
    expired session -- callers fall back to the static-key path per step 2.
    Slides the session (refreshes idle TTL) on every use, matching "every
    authenticated request" per `sessions.py`'s docstring."""
    if not session_cookie:
        return None
    return await read_session(session_cookie, slide=True)


async def _resolve_role(
    *,
    session_cookie: str | None,
    api_key: str | None,
) -> tuple[str | None, SessionData | None]:
    """Implements the precedence rule verbatim: session (if valid) wins
    unconditionally; API key is only ever consulted when there is no valid
    session. Returns `(role, session)` -- `session` is non-None only when
    the role came from a session, letting callers attribute an audit/log
    line to a specific user_id rather than just "ADMIN key holder"."""
    session = await _session_from_cookie(session_cookie)
    if session is not None:
        return session.role, session

    role = _role_for_key(api_key)
    return role, None


async def require_admin(
    request: Request,
    x_api_key: str | None = Header(default=None),
    eparking_session: str | None = Cookie(default=None),
) -> str:
    """FastAPI dependency: 401 if no/unrecognized session AND no/unrecognized
    key, 403 if recognized but not ADMIN. Protects every `/admin/*`
    endpoint. Session (if valid) takes precedence over any attached API key
    -- see module docstring."""
    role, session = await _resolve_role(session_cookie=eparking_session, api_key=x_api_key)
    if role is None:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid session/API key. Log in, or provide 'X-API-Key' with a valid ADMIN key.",
        )
    if role != ROLE_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="This endpoint requires the ADMIN role.",
        )
    if session is not None:
        request.state.session = session
    return role


async def require_viewer_or_admin(
    request: Request,
    x_api_key: str | None = Header(default=None),
    eparking_session: str | None = Cookie(default=None),
) -> str:
    """FastAPI dependency: any recognized session or key (ADMIN or VIEWER)
    is enough. Used for `/api/ops/unmapped` -- see that router's docstring
    for the ADMIN-or-VIEWER reasoning, unchanged by this rewrite. Session
    precedence rule applies identically to `require_admin`."""
    role, session = await _resolve_role(session_cookie=eparking_session, api_key=x_api_key)
    if role is None:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid session/API key. Log in, or provide 'X-API-Key' with a valid ADMIN or VIEWER key.",
        )
    if session is not None:
        request.state.session = session
    return role
