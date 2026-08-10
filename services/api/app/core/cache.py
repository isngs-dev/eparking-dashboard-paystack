"""Redis-backed SWR (stale-while-revalidate) caching for dashboard endpoints.

Mirrors the pattern documented in `references/knowledge-base/03_API_SERVICES.md`
and `.claude/skills/api-layer/SKILL.md`, trimmed for this project's
single-tenant scope (no `t:{tenant_id}` prefix).

Envelope stored per key: `{"v": <json-serializable value>, "soft": <unix ts>}`.
- Within the soft TTL: serve straight from cache, no DB hit.
- Past soft TTL but still present (within the hard TTL / Redis expiry): serve
  the stale value immediately, kick a single background refresh guarded by a
  short-lived `SET NX` lock so a burst of stale hits doesn't stampede the DB.
- Cache miss (key absent, e.g. hard TTL expired or never set): caller must
  compute fresh and `set_swr` populate it -- this module never returns a
  fabricated empty value on miss.

Every key written is registered in the single `dash:keys` SET (per-project
convention -- no tenant partitioning needed) so a later sprint can bulk
invalidate after ingestion/reclassify without a keyspace SCAN. This sprint
only builds the mechanism; wiring the invalidation trigger into ingestion is
documented as a follow-up (see Sprint 5 report).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from redis.asyncio import Redis

from eparking_common.config import get_settings

logger = logging.getLogger("app.cache")

_KEYS_SET = "dash:keys"
_LOCK_TTL_SECONDS = 30

_redis: Redis | None = None


def init_redis() -> Redis:
    global _redis
    settings = get_settings()
    _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None


def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError(
            "Redis client not initialized -- init_redis() must run in the app "
            "lifespan before any request handler touches the cache."
        )
    return _redis


def cache_key(resource: str, params: dict[str, Any]) -> str:
    """`dash:{resource}:{sha256(sorted params)[:16]}` per the skill's scheme."""
    canonical = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"dash:{resource}:{digest}"


@dataclass(frozen=True)
class CacheResult:
    value: Any
    status: str  # "HIT" | "STALE" | "MISS"


async def get_swr(
    key: str,
    *,
    soft_ttl_seconds: int,
    hard_ttl_seconds: int,
    loader: Callable[[], Awaitable[Any]],
) -> CacheResult:
    """Cache-aside read with stale-while-revalidate semantics.

    `loader` computes a fresh, JSON-serializable value from the DB. Called
    synchronously (and awaited) on a cold miss; called in a fire-and-forget
    background task on a stale (soft-TTL-expired) hit.
    """
    redis = get_redis()
    raw = await redis.get(key)

    if raw is not None:
        envelope = json.loads(raw)
        soft_expires_at = envelope["soft"]
        if time.time() < soft_expires_at:
            logger.info("cache HIT key=%s", key)
            return CacheResult(value=envelope["v"], status="HIT")

        # Stale: serve immediately, refresh in the background (single-flight).
        logger.info("cache STALE key=%s -- serving stale, scheduling refresh", key)
        lock_key = f"{key}:refresh-lock"
        got_lock = await redis.set(lock_key, "1", nx=True, ex=_LOCK_TTL_SECONDS)
        if got_lock:
            asyncio.create_task(
                _refresh(
                    key,
                    loader=loader,
                    soft_ttl_seconds=soft_ttl_seconds,
                    hard_ttl_seconds=hard_ttl_seconds,
                    lock_key=lock_key,
                )
            )
        return CacheResult(value=envelope["v"], status="STALE")

    logger.info("cache MISS key=%s -- loading fresh", key)
    value = await loader()
    await set_swr(
        key,
        value,
        soft_ttl_seconds=soft_ttl_seconds,
        hard_ttl_seconds=hard_ttl_seconds,
    )
    return CacheResult(value=value, status="MISS")


async def _refresh(
    key: str,
    *,
    loader: Callable[[], Awaitable[Any]],
    soft_ttl_seconds: int,
    hard_ttl_seconds: int,
    lock_key: str,
) -> None:
    redis = get_redis()
    try:
        value = await loader()
        await set_swr(
            key,
            value,
            soft_ttl_seconds=soft_ttl_seconds,
            hard_ttl_seconds=hard_ttl_seconds,
        )
    except Exception:  # noqa: BLE001 -- background task, must not crash the loop
        logger.exception("background cache refresh failed key=%s", key)
    finally:
        await redis.delete(lock_key)


async def set_swr(
    key: str,
    value: Any,
    *,
    soft_ttl_seconds: int,
    hard_ttl_seconds: int,
) -> None:
    redis = get_redis()
    envelope = {"v": value, "soft": time.time() + soft_ttl_seconds}
    await redis.set(key, json.dumps(envelope, default=str), ex=hard_ttl_seconds)
    await redis.sadd(_KEYS_SET, key)
    # Self-healing bound on the tracking set itself, same rationale as the
    # sibling platform: if invalidation is ever missed, the set doesn't grow
    # unbounded with keys that have already expired individually.
    await redis.expire(_KEYS_SET, 24 * 60 * 60)


async def invalidate_all() -> int:
    """Bulk-invalidate every tracked key. Not wired into ingestion yet (see
    Sprint 5 report) -- exposed here so that follow-up wiring is a one-line
    call, and so this sprint can prove the mechanism works end-to-end.
    """
    redis = get_redis()
    keys = await redis.smembers(_KEYS_SET)
    if not keys:
        return 0
    await redis.delete(*keys)
    await redis.delete(_KEYS_SET)
    return len(keys)
