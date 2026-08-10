"""FastAPI application entrypoint.

Sprint 5 scope: DB pool + Redis lifecycle wiring, all dashboard routers
mounted (Overview, Revenue/Cards/Tickets, Occupancy, Traffic, Filters).

Sprint 09 (Authentication & Session Security), Phase 2, §8 adds: the `auth`
router, security-response-headers middleware, an Origin-header CSRF check on
state-changing methods, and narrows CORS `allow_methods`/`allow_headers`
from the prior wildcard.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.core.cache import close_redis, init_redis
from app.core.db import close_pool, init_pool
from app.routers import admin, auth, filters, health, occupancy, ops, overview, revenue, traffic
from eparking_common.config import get_settings

settings = get_settings()

_CSRF_PROTECTED_METHODS = {"POST", "PATCH", "DELETE"}

# Ensure app.* loggers (cache HIT/STALE/MISS lines, etc.) actually reach
# stdout under uvicorn -- uvicorn configures its own namespaced loggers but
# leaves the root logger at WARNING by default, which would otherwise
# silently swallow our INFO-level cache evidence.
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    init_redis()
    try:
        yield
    finally:
        await close_redis()
        await close_pool()


app = FastAPI(
    title="E-Parking Revenue Dashboard API",
    version="0.1.0",
    lifespan=lifespan,
)

_allowed_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    # Narrowed from the prior wildcard (Sprint 09 §8) -- only the methods
    # and headers this API's routers actually use. `X-API-Key` stays listed
    # since the Next.js server (and any other service caller) still
    # attaches it per Sprint 09 §12's "service credential" fallback path.
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Adds the baseline security headers (Sprint 09 §8) to every response,
    independent of any reverse-proxy configuration -- these survive even if
    a proxy in front of this service is misconfigured or absent (e.g. local
    dev, or a future deployment that forgets to set them).

    CSP is scoped to API responses only in v1 -- `default-src 'self'` is
    correct for a JSON API that serves no HTML/inline scripts itself; the
    frontend's own CSP (which needs nonce plumbing for its inline theme
    script) is explicitly out of scope here per §8/§12's deferred item.
    """
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


@app.middleware("http")
async def csrf_origin_check_middleware(request: Request, call_next):
    """Second-layer CSRF defense (Sprint 09 §8) on top of the session
    cookie's `SameSite=Lax` (the primary defense -- blocks cross-site POST
    while still allowing top-level cross-site GET navigation). Rejects a
    state-changing request (`POST`/`PATCH`/`DELETE`) that carries the
    session cookie but whose `Origin` header is absent or not in the
    configured allow-list.

    **Scoped to cookie-authenticated requests only.** CSRF is an attack
    against ambient/automatic credentials (cookies) that a malicious page
    can trigger a browser into sending without the attacker ever seeing
    them -- it does not apply to `X-API-Key`-authenticated requests, since a
    malicious third-party page has no way to read or attach a caller's API
    key (it isn't ambient the way a cookie is). Blanket-rejecting every
    POST/PATCH/DELETE without an `Origin` header would also break every
    legitimate non-browser caller of `/admin/*`/`/api/ops/*` (curl, cron
    jobs, monitoring, a future Next.js server-to-server call that doesn't
    set `Origin`) -- exactly the static-API-key "service credential" path
    Sprint 09 §12 repositions those keys as, and Phase 2's own backward-
    compatibility acceptance criterion ("existing `/admin/*` endpoints...
    work exactly as before using ONLY the static API key"). So this check
    So this check fires when either (a) `session_cookie_name` is present on
    the request (an already-authenticated cookie-auth call), or (b) the path
    is under `/auth/` (the login/reset endpoints that establish or replace
    that cookie in the first place, and so are squarely part of the
    browser-facing surface even though no cookie exists yet on that specific
    request) -- i.e. exactly the surface a browser's ambient cookie can
    reach or create. `/admin/*`/`/api/ops/*` calls authenticated purely via
    `X-API-Key` (no cookie, not under `/auth/`) are left alone, preserving
    the Phase 2 backward-compatibility requirement that those keep working
    unchanged for non-browser/service callers.

    Deliberately does NOT check `GET`/`HEAD`/`OPTIONS` -- those are not
    state-changing and browsers don't reliably send `Origin` on simple GET
    navigation.
    """
    if request.method in _CSRF_PROTECTED_METHODS:
        is_cookie_auth_surface = (
            settings.session_cookie_name in request.cookies
            or request.url.path.startswith("/auth/")
        )
        if is_cookie_auth_surface:
            origin = request.headers.get("origin")
            if not origin or origin not in _allowed_origins:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Request rejected: missing or disallowed Origin header."},
                )
    return await call_next(request)


app.include_router(health.router)
app.include_router(overview.router)
app.include_router(revenue.router)
app.include_router(occupancy.router)
app.include_router(traffic.router)
app.include_router(filters.router)
app.include_router(admin.router)
app.include_router(ops.router)
app.include_router(auth.router)
