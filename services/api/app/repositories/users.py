"""CRUD against `eparking.users`.

Sprint 09 (Authentication & Session Security), Phase 1. Mirrors the
`asyncpg.Connection`-per-call convention already established in
`app/repositories/admin.py` -- no ORM, per
`references/knowledge-base/02_BACKEND_PHILOSOPHY.md`.

`to_public_dict` is the ONLY sanctioned way any router/service in this
codebase should serialize a `users` row back to a caller -- it strips
`hashed_password` (and nothing else needs stripping; every other column is
safe to display, per the sprint doc's `/admin/users` response shape). Every
function in this module that returns a row returns the FULL row (including
`hashed_password`) for internal use (e.g. login verification needs the
hash) -- callers are responsible for routing through `to_public_dict` before
any HTTP response. Audited: `create_user`, `get_user_by_email`,
`get_user_by_id`, `update_user`, `list_users` all return raw rows; none of
them call `to_public_dict` themselves, so the caller must.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import asyncpg

from app.core.passwords import hash_password

_USER_COLUMNS = """
    id, email, hashed_password, role, display_name, organization, is_active,
    must_change_password, failed_login_count, locked_until, last_login_at,
    password_changed_at, created_at, updated_at
"""


def to_public_dict(user: dict[str, Any]) -> dict[str, Any]:
    """Strip `hashed_password` (and only `hashed_password`) from a `users`
    row. Every response path that ever serializes a user MUST go through
    this function -- never return a raw `users` row/dict to an HTTP
    response."""
    return {k: v for k, v in user.items() if k != "hashed_password"}


async def create_user(
    conn: asyncpg.Connection,
    *,
    email: str,
    password: str,
    role: str,
    display_name: str,
    organization: str | None = None,
    must_change_password: bool = True,
) -> dict:
    """Creates a user, hashing `password` here (callers must have already run
    `app.core.passwords.validate_password_policy` on the plaintext password
    before calling this -- this function does not re-validate policy, only
    hashes). Email is normalized to lowercase at the write path per the
    schema's `lower(email)` unique index."""
    hashed = hash_password(password)
    row = await conn.fetchrow(
        f"""
        INSERT INTO eparking.users
            (email, hashed_password, role, display_name, organization,
             must_change_password)
        VALUES (lower($1), $2, $3, $4, $5, $6)
        RETURNING {_USER_COLUMNS}
        """,
        email,
        hashed,
        role,
        display_name,
        organization,
        must_change_password,
    )
    return dict(row)


async def get_user_by_email(conn: asyncpg.Connection, email: str) -> dict | None:
    """Case-insensitive lookup, matching the `ux_users_email` unique index on
    `lower(email)`."""
    row = await conn.fetchrow(
        f"SELECT {_USER_COLUMNS} FROM eparking.users WHERE lower(email) = lower($1)",
        email,
    )
    return dict(row) if row else None


async def get_user_by_id(conn: asyncpg.Connection, user_id: int) -> dict | None:
    row = await conn.fetchrow(
        f"SELECT {_USER_COLUMNS} FROM eparking.users WHERE id = $1",
        user_id,
    )
    return dict(row) if row else None


async def list_users(conn: asyncpg.Connection) -> list[dict]:
    rows = await conn.fetch(
        f"SELECT {_USER_COLUMNS} FROM eparking.users ORDER BY created_at"
    )
    return [dict(r) for r in rows]


async def update_display_name(
    conn: asyncpg.Connection, user_id: int, display_name: str
) -> dict | None:
    """Updates an active user's self-service profile field atomically."""
    row = await conn.fetchrow(
        f"""
        UPDATE eparking.users SET
            display_name = $2,
            updated_at = now()
        WHERE id = $1 AND is_active = TRUE
        RETURNING {_USER_COLUMNS}
        """,
        user_id,
        display_name,
    )
    return dict(row) if row else None


async def update_user(conn: asyncpg.Connection, user_id: int, patch: dict) -> dict | None:
    """Partial update of role/display_name/organization/is_active/
    must_change_password. `patch` should already be the caller's
    `model_dump(exclude_unset=True)`-equivalent -- only keys genuinely
    present are applied; an explicit `None` for `organization` clears it.
    Does not touch `email`/`hashed_password`/lockout fields -- those go
    through their own dedicated functions (`record_login_success`,
    `record_login_failure`, password-change/reset flows)."""
    existing = await get_user_by_id(conn, user_id)
    if existing is None:
        return None

    allowed_keys = {"role", "display_name", "organization", "is_active", "must_change_password"}
    unknown = set(patch) - allowed_keys
    if unknown:
        raise ValueError(f"update_user: unsupported field(s) {sorted(unknown)}")

    merged = {**existing, **patch}

    row = await conn.fetchrow(
        f"""
        UPDATE eparking.users SET
            role = $2, display_name = $3, organization = $4, is_active = $5,
            must_change_password = $6, updated_at = now()
        WHERE id = $1
        RETURNING {_USER_COLUMNS}
        """,
        user_id,
        merged["role"],
        merged["display_name"],
        merged["organization"],
        merged["is_active"],
        merged["must_change_password"],
    )
    return dict(row) if row else None


async def set_password(conn: asyncpg.Connection, user_id: int, new_password_hash: str, *, must_change_password: bool = False) -> dict | None:
    """Overwrites `hashed_password` directly with an ALREADY-HASHED value
    (change-password / reset-redeem / rehash-on-login flows all hash first,
    then call this -- kept separate from `create_user`'s hash-on-write so a
    rehash-on-login doesn't need to round-trip a plaintext password)."""
    row = await conn.fetchrow(
        f"""
        UPDATE eparking.users SET
            hashed_password = $2,
            must_change_password = $3,
            password_changed_at = now(),
            updated_at = now()
        WHERE id = $1
        RETURNING {_USER_COLUMNS}
        """,
        user_id,
        new_password_hash,
        must_change_password,
    )
    return dict(row) if row else None


async def record_login_success(conn: asyncpg.Connection, user_id: int) -> None:
    """Resets `failed_login_count`, clears `locked_until`, sets
    `last_login_at = now()` -- per the sprint doc's §5 step 8."""
    await conn.execute(
        """
        UPDATE eparking.users SET
            failed_login_count = 0,
            locked_until = NULL,
            last_login_at = now(),
            updated_at = now()
        WHERE id = $1
        """,
        user_id,
    )


async def record_login_failure(
    conn: asyncpg.Connection, user_id: int, *, max_failed_attempts: int, lockout_minutes: int
) -> dict:
    """Increments `failed_login_count`; when it reaches `max_failed_attempts`,
    sets `locked_until = now() + lockout_minutes` and resets the counter to 0
    (per §5 step 7 -- lockout is timed and self-releasing, not permanent).
    Returns `{"locked": bool, "failed_login_count": int}` so the caller can
    decide the audit `detail` payload without a second read."""
    row = await conn.fetchrow(
        """
        UPDATE eparking.users SET
            failed_login_count = failed_login_count + 1,
            updated_at = now()
        WHERE id = $1
        RETURNING failed_login_count
        """,
        user_id,
    )
    failed_count = row["failed_login_count"] if row else 0

    locked = False
    if failed_count >= max_failed_attempts:
        await conn.execute(
            """
            UPDATE eparking.users SET
                locked_until = now() + make_interval(mins => $2),
                failed_login_count = 0,
                updated_at = now()
            WHERE id = $1
            """,
            user_id,
            lockout_minutes,
        )
        locked = True

    return {"locked": locked, "failed_login_count": failed_count}


def is_locked(user: dict, *, now: datetime | None = None) -> bool:
    """True if `user["locked_until"]` is set and still in the future."""
    locked_until = user.get("locked_until")
    if locked_until is None:
        return False
    reference = now or datetime.now(timezone.utc)
    return locked_until > reference
