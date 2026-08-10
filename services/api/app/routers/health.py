"""Liveness/readiness endpoints.

/healthz  -> liveness: process is up, no dependency checks. Always 200 once
             the app has started.
/readyz   -> readiness: real per-dependency checks (DB, Redis) now that both
             are wired in the app lifespan (Sprint 5) -- reports "error" per
             dependency rather than raising, so an orchestrator sees which
             dependency is unhealthy instead of a bare 500.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.cache import get_redis
from app.core.db import get_pool

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict[str, object]:
    checks: dict[str, str] = {}

    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001 -- readiness probe must never raise
        checks["database"] = "error"

    try:
        redis = get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception:  # noqa: BLE001
        checks["redis"] = "error"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
