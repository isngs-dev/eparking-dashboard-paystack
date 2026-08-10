"""Direct-Redis cache invalidation, called from ingestion after any run that
changes `dashboard_transactions` / `daily_revenue`.

Sprint 5 built the API's SWR cache (`services/api/app/core/cache.py`) with a
`dash:keys` Redis SET tracking every live cache key, plus an `invalidate_all()`
function that was never wired to fire automatically (see Sprint 7 sprint doc,
"carried-forward follow-up from Sprint 5").

`services/ingestion` and `services/api` are separate processes/containers
with no shared application code (only the tiny `services/common` package),
but they share the same Redis instance. Rather than a cross-package import
(would couple ingestion to api's package layout) or an HTTP call to the API
just to invalidate a cache (adds a network dependency and a new admin-only
endpoint for no real benefit), this module talks to Redis directly and
replicates the same minimal invalidation logic api's `invalidate_all()` uses:
delete every key in `dash:keys`, then delete the SET itself. This is the
approach the sprint doc explicitly recommends ("(a) ... it's simple, Redis is
shared infrastructure, and it avoids a service-to-service HTTP call or a
cross-package import").

Kept deliberately tiny and dependency-light (plain `redis` client, not
`redis.asyncio`, since ingestion's Celery tasks already bridge sync Celery
task functions into `asyncio.run(...)` for DB work -- adding another asyncio
dependency here is unnecessary for a two-command Redis operation).
"""

from __future__ import annotations

import logging

import redis

from eparking_common.config import get_settings

logger = logging.getLogger("app.cache_invalidate")

_KEYS_SET = "dash:keys"


def invalidate_dashboard_cache() -> int:
    """Delete every key tracked in `dash:keys`, then the set itself.

    Mirrors `services/api/app/core/cache.py`'s `invalidate_all()` exactly
    (same key names, same two-step delete) so the two implementations can
    never drift into invalidating different things. Safe to call even if
    Redis is unreachable or `dash:keys` doesn't exist yet -- logs and
    swallows the error rather than failing the calling ingestion/reclassify
    run over a cache-only concern.
    """
    settings = get_settings()
    try:
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            keys = client.smembers(_KEYS_SET)
            if not keys:
                logger.info("cache invalidation: no tracked keys, nothing to do")
                return 0
            client.delete(*keys)
            client.delete(_KEYS_SET)
            logger.info("cache invalidation: cleared %d tracked key(s)", len(keys))
            return len(keys)
        finally:
            client.close()
    except Exception:  # noqa: BLE001 -- cache invalidation must never fail the run
        logger.exception("cache invalidation failed -- dashboard may serve stale data until hard TTL expiry")
        return 0
