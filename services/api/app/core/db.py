"""Shared asyncpg connection pool for the API service.

One pool per process, created on FastAPI startup and closed on shutdown (see
`app.main`'s lifespan). Every repository function takes a `asyncpg.Pool` (or
acquires a connection from it) -- never opens an ad-hoc connection per
request, per `references/knowledge-base/03_API_SERVICES.md`'s readiness-probe
guidance (applies equally to normal request handlers: connection-per-request
is a connection-exhaustion risk under load).
"""

from __future__ import annotations

import asyncpg

from eparking_common.config import get_settings

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(
        dsn=settings.asyncpg_dsn,
        min_size=1,
        max_size=10,
    )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError(
            "DB pool not initialized -- init_pool() must run in the app lifespan "
            "before any request handler touches the database."
        )
    return _pool
