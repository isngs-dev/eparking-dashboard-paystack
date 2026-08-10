"""Redis-backed server-side sessions.

Sprint 09 (Authentication & Session Security), Phase 1, §4. Opaque
server-side sessions in Redis, not a JWT -- Redis is already a hard
dependency with pooled lifecycle management (`main.py` calls
`init_redis()`/`close_redis()` from `app.core.cache`), so this is a new key
namespace on existing infrastructure, not new infra. This module
deliberately reuses `app.core.cache.get_redis()` -- the single shared Redis
client for the process -- rather than opening a second connection/pool; see
that module's docstring for the connection-acquisition/error-handling
pattern this file stays consistent with.

## Design (verbatim per the sprint doc's §4 table)

| Aspect | Decision |
|---|---|
| Token | `secrets.token_urlsafe(32)`. Opaque, no structure. |
| Redis key | `sess:{sha256(token)}` -- store the hash, not the raw token. |
| Redis value | JSON: `{user_id, email, role, display_name, organization, created_at, last_seen_at, ip, ua_hash}`. |
| Idle timeout | 30 min, sliding (refreshed on each authenticated request). |
| Absolute lifetime | 12 hours, checked against `created_at` on read -- cannot be slid indefinitely. |
| Logout | delete the Redis key. |
| Logout-all | `user_sessions:{user_id}` Redis SET of session-key hashes, cleaned on logout/expiry. |

The raw token is what's set in the cookie and handed to the browser; only its
SHA-256 digest is ever stored in Redis or logged. `create_session` returns
the raw token to the caller (Phase 2's login endpoint sets it as the cookie
value) -- it is never persisted anywhere in this module.

This module builds create/read/slide/destroy/destroy-all-for-user only. It
does not set/clear HTTP cookies (that's Phase 2's `routers/auth.py`) and does
not implement the `require_admin`/`require_viewer_or_admin` dual-mode
resolution (that's Phase 2's `auth.py` rewrite).
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

from app.core.cache import get_redis
from eparking_common.config import get_settings

logger = logging.getLogger("app.sessions")

_SESSION_KEY_PREFIX = "sess:"
_USER_SESSIONS_KEY_PREFIX = "user_sessions:"

_TOKEN_NBYTES = 32


@dataclass(frozen=True)
class SessionData:
    user_id: int
    email: str
    role: str
    display_name: str
    organization: str | None
    created_at: float
    last_seen_at: float
    ip: str | None
    ua_hash: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "role": self.role,
            "display_name": self.display_name,
            "organization": self.organization,
            "created_at": self.created_at,
            "last_seen_at": self.last_seen_at,
            "ip": self.ip,
            "ua_hash": self.ua_hash,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SessionData":
        return cls(
            user_id=payload["user_id"],
            email=payload["email"],
            role=payload["role"],
            display_name=payload["display_name"],
            organization=payload.get("organization"),
            created_at=payload["created_at"],
            last_seen_at=payload["last_seen_at"],
            ip=payload.get("ip"),
            ua_hash=payload.get("ua_hash"),
        )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session_key(token_hash: str) -> str:
    return f"{_SESSION_KEY_PREFIX}{token_hash}"


def _user_sessions_key(user_id: int) -> str:
    return f"{_USER_SESSIONS_KEY_PREFIX}{user_id}"


def hash_ua(user_agent: str | None) -> str | None:
    """SHA-256 of the User-Agent header, stored instead of the raw string so
    the session record doesn't retain more raw client identifying data than
    needed -- still enough to flag a session hijacked from a different
    browser/device in a future UI (see the sprint doc's deferred
    "session-management UI" item)."""
    if not user_agent:
        return None
    return hashlib.sha256(user_agent.encode("utf-8")).hexdigest()


async def create_session(
    *,
    user_id: int,
    email: str,
    role: str,
    display_name: str,
    organization: str | None,
    ip: str | None,
    user_agent: str | None,
) -> str:
    """Creates a new session and returns the RAW token (never store this
    anywhere else -- the caller sets it as the session cookie value)."""
    settings = get_settings()
    redis = get_redis()

    token = secrets.token_urlsafe(_TOKEN_NBYTES)
    token_hash = _hash_token(token)
    now = time.time()

    session = SessionData(
        user_id=user_id,
        email=email,
        role=role,
        display_name=display_name,
        organization=organization,
        created_at=now,
        last_seen_at=now,
        ip=ip,
        ua_hash=hash_ua(user_agent),
    )

    idle_ttl_seconds = settings.session_idle_minutes * 60
    key = _session_key(token_hash)
    await redis.set(key, json.dumps(session.to_dict()), ex=idle_ttl_seconds)
    await redis.sadd(_user_sessions_key(user_id), token_hash)
    # Bound the tracking set's own lifetime to the absolute session lifetime
    # so it doesn't outlive every session it could ever reference, mirroring
    # cache.py's self-healing bound on `dash:keys`.
    await redis.expire(
        _user_sessions_key(user_id), settings.session_absolute_hours * 60 * 60
    )

    logger.info("session created user_id=%s", user_id)
    return token


async def read_session(token: str, *, slide: bool = True) -> SessionData | None:
    """Reads a session by its raw token. Returns None if absent, expired
    (idle TTL), or past the 12h absolute lifetime (checked against
    `created_at` even if the idle TTL would otherwise still be fresh -- a
    hard cap, not just a TTL, per §4).

    When `slide` is True (the default -- every authenticated request), the
    idle TTL is refreshed and `last_seen_at` is updated. Pass `slide=False`
    for read-only inspection that must not extend a session's life.
    """
    settings = get_settings()
    redis = get_redis()

    token_hash = _hash_token(token)
    key = _session_key(token_hash)
    raw = await redis.get(key)
    if raw is None:
        return None

    payload = json.loads(raw)
    session = SessionData.from_dict(payload)

    absolute_lifetime_seconds = settings.session_absolute_hours * 60 * 60
    if time.time() - session.created_at > absolute_lifetime_seconds:
        # Absolute lifetime exceeded -- reject and clean up, even though the
        # idle TTL alone would still consider this key fresh.
        await _destroy_by_hash(token_hash, user_id=session.user_id)
        logger.info(
            "session rejected (absolute lifetime exceeded) user_id=%s",
            session.user_id,
        )
        return None

    if slide:
        idle_ttl_seconds = settings.session_idle_minutes * 60
        session = SessionData(
            user_id=session.user_id,
            email=session.email,
            role=session.role,
            display_name=session.display_name,
            organization=session.organization,
            created_at=session.created_at,
            last_seen_at=time.time(),
            ip=session.ip,
            ua_hash=session.ua_hash,
        )
        await redis.set(key, json.dumps(session.to_dict()), ex=idle_ttl_seconds)

    return session


async def destroy_session(token: str) -> None:
    """Deletes the session by raw token (logout). Idempotent -- destroying an
    already-absent session is a no-op, not an error."""
    redis = get_redis()
    token_hash = _hash_token(token)
    raw = await redis.get(_session_key(token_hash))
    user_id = None
    if raw is not None:
        try:
            user_id = json.loads(raw).get("user_id")
        except (ValueError, TypeError):
            user_id = None
    await _destroy_by_hash(token_hash, user_id=user_id)


async def _destroy_by_hash(token_hash: str, *, user_id: int | None) -> None:
    redis = get_redis()
    await redis.delete(_session_key(token_hash))
    if user_id is not None:
        await redis.srem(_user_sessions_key(user_id), token_hash)


async def destroy_all_for_user(user_id: int) -> int:
    """Destroys every live session for a user (logout-all) -- used on
    deactivation, role change, and password change (per §6, "revokes other
    sessions"). Returns the number of sessions destroyed."""
    redis = get_redis()
    set_key = _user_sessions_key(user_id)
    token_hashes = await redis.smembers(set_key)
    if not token_hashes:
        return 0

    session_keys = [_session_key(h) for h in token_hashes]
    await redis.delete(*session_keys)
    await redis.delete(set_key)
    logger.info("destroyed %d session(s) for user_id=%s", len(token_hashes), user_id)
    return len(token_hashes)
