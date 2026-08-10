"""Redis sliding-window rate limiting for the login path.

Sprint 09 (Authentication & Session Security), Phase 2, §2/§5. Two limiters:

- Per-IP: `login_rate_limit_per_minute` (default 10/min) -- guards against a
  single client hammering the login endpoint regardless of which account it
  targets.
- Per-account: keyed on `sha256(lower(email))`, NOT the raw email, so the
  Redis keyspace itself never leaks the user directory (a `SCAN` or a Redis
  admin looking at keys should not be able to enumerate registered emails).

Both are implemented as a fixed-window-approximated sliding counter using
`INCR` + `EXPIRE NX`-once-per-window, which is the standard simple pattern
for this kind of guard (a true sliding log is unnecessary precision for a
10/min login guard) -- see `app.core.cache`'s docstring for the general
"reuse the shared Redis client" convention this module follows.

## Fail-closed, not fail-open

Per the sprint doc's §2 ("Rate limit ... fails closed when Redis is down")
and §5 step 1 ("Redis unavailable -> FAIL CLOSED, 503"): every function in
this module that the login path calls raises `RateLimitBackendError` on any
Redis error (connection refused, timeout, etc.) instead of swallowing it and
letting the request through unchecked. This is the opposite of the caching
layer's philosophy (`app.core.cache` degrades gracefully) -- rate limiting is
a security control, not a performance optimization, so "Redis is down" must
not silently mean "no rate limit."

2-second socket timeouts are applied to every Redis call this module makes
(via a dedicated client with `socket_timeout`/`socket_connect_timeout` set)
so a hung Redis backend fails fast instead of hanging every login request
behind it.
"""

from __future__ import annotations

import hashlib
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.cache import get_redis
from eparking_common.config import get_settings

logger = logging.getLogger("app.rate_limit")

_SOCKET_TIMEOUT_SECONDS = 2.0

_IP_KEY_PREFIX = "ratelimit:login:ip:"
_ACCOUNT_KEY_PREFIX = "ratelimit:login:acct:"

_WINDOW_SECONDS = 60

_rate_limit_redis: Redis | None = None


class RateLimitBackendError(Exception):
    """Raised when Redis is unreachable/times out while checking a rate
    limit. Callers on the login path MUST treat this as "reject the
    request" (503), per the sprint doc's explicit fail-closed requirement --
    never catch this and fall through to allowing the login attempt."""


class RateLimitExceeded(Exception):
    """Raised when a caller has exceeded the configured limit. Callers on
    the login path MUST treat this as 429."""

    def __init__(self, *, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"rate limit exceeded, retry after {retry_after_seconds}s")


def _get_rate_limit_redis() -> Redis:
    """A dedicated client (separate from `app.core.cache`'s shared instance)
    with a hard 2s socket timeout, per the module docstring -- the cache
    module's client has no such timeout (it's fine for it to wait on a slow
    Redis; the login path is not fine with that). Lazily constructed once
    and reused, mirroring `cache.py`'s single-client-per-process pattern."""
    global _rate_limit_redis
    if _rate_limit_redis is None:
        settings = get_settings()
        _rate_limit_redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=_SOCKET_TIMEOUT_SECONDS,
            socket_connect_timeout=_SOCKET_TIMEOUT_SECONDS,
        )
    return _rate_limit_redis


def _hash_email(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


async def _check_and_increment(key: str, *, limit: int) -> None:
    """Shared fixed-window counter: `INCR` the key, `EXPIRE` it only on the
    first increment of the window (so the window doesn't keep sliding
    forward forever under sustained traffic). Raises `RateLimitBackendError`
    on any Redis error, `RateLimitExceeded` if `limit` is exceeded."""
    redis = _get_rate_limit_redis()
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, _WINDOW_SECONDS)
        if count > limit:
            ttl = await redis.ttl(key)
            retry_after = ttl if ttl and ttl > 0 else _WINDOW_SECONDS
            raise RateLimitExceeded(retry_after_seconds=retry_after)
    except RedisError as exc:
        logger.error("rate limit backend error key=%s: %s", key, exc)
        raise RateLimitBackendError(str(exc)) from exc


async def check_login_rate_limit_by_ip(ip_address: str) -> None:
    """10/min (configurable) sliding window per client IP. Raises
    `RateLimitBackendError` (Redis down -> caller must return 503) or
    `RateLimitExceeded` (caller must return 429)."""
    settings = get_settings()
    key = f"{_IP_KEY_PREFIX}{ip_address}"
    await _check_and_increment(key, limit=settings.login_rate_limit_per_minute)


async def check_login_rate_limit_by_account(email: str) -> None:
    """Same window, keyed on `sha256(lower(email))` per §5 step 2 so the
    Redis keyspace never leaks the user directory. Uses the same per-minute
    limit as the IP check -- one configured rate, two independent
    dimensions."""
    settings = get_settings()
    key = f"{_ACCOUNT_KEY_PREFIX}{_hash_email(email)}"
    await _check_and_increment(key, limit=settings.login_rate_limit_per_minute)
