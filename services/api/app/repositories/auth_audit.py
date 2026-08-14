"""Writes to `eparking.auth_audit_log`.

Sprint 09 (Authentication & Session Security), Phase 1, §9. Reuses the same
manual `json.dumps`/JSONB-as-text pattern already established in
`app/repositories/admin.py` (`fee_categories.components`) -- this pool has no
jsonb codec registered, so asyncpg needs the JSON pre-serialized to a string
on write / decoded from a string on read, rather than a new pattern being
invented here.

**Audit writes must never fail the calling request.** `record_event` wraps
its INSERT in try/except and logs-and-continues on any DB error -- an
audit-table outage (e.g. a transient RDS blip) must not itself become a
denial-of-service against login, per the sprint doc's explicit instruction.
Callers should therefore never wrap `record_event` in their own try/except
expecting it to raise; it deliberately swallows its own failures.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

logger = logging.getLogger("app.auth_audit")

# Per §9 -- kept here as the canonical event-type vocabulary so Phase 2's
# routers import from one place rather than restating string literals.
LOGIN_SUCCESS = "LOGIN_SUCCESS"
LOGIN_FAILURE = "LOGIN_FAILURE"
LOGOUT = "LOGOUT"
SESSION_EXPIRED = "SESSION_EXPIRED"
PASSWORD_CHANGED = "PASSWORD_CHANGED"
PASSWORD_ADMIN_SET = "PASSWORD_ADMIN_SET"
PASSWORD_RESET_ISSUED = "PASSWORD_RESET_ISSUED"
PASSWORD_RESET_REDEEMED = "PASSWORD_RESET_REDEEMED"
PROFILE_UPDATED = "PROFILE_UPDATED"
USER_CREATED = "USER_CREATED"
USER_ROLE_CHANGED = "USER_ROLE_CHANGED"
USER_DEACTIVATED = "USER_DEACTIVATED"
USER_REACTIVATED = "USER_REACTIVATED"
ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
RATE_LIMIT_TRIPPED = "RATE_LIMIT_TRIPPED"

OUTCOME_SUCCESS = "SUCCESS"
OUTCOME_FAILURE = "FAILURE"


async def record_event(
    conn: asyncpg.Connection,
    *,
    event_type: str,
    outcome: str,
    actor_user_id: int | None = None,
    actor_email: str | None = None,
    target_user_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Writes one `auth_audit_log` row. NEVER raises -- any DB error is
    logged and swallowed so an audit-table outage cannot deny login/logout/
    admin actions. `detail` must never contain passwords, session tokens, or
    reset tokens (reason codes / old-new role diffs only)."""
    try:
        await conn.execute(
            """
            INSERT INTO eparking.auth_audit_log
                (event_type, actor_user_id, actor_email, target_user_id,
                 ip_address, user_agent, outcome, detail)
            VALUES ($1, $2, $3, $4, $5::inet, $6, $7, $8)
            """,
            event_type,
            actor_user_id,
            actor_email,
            target_user_id,
            ip_address,
            user_agent,
            outcome,
            json.dumps(detail) if detail is not None else None,
        )
    except Exception:  # noqa: BLE001 -- audit writes must never fail the caller
        logger.exception(
            "auth_audit_log write failed event_type=%s outcome=%s actor_email=%s",
            event_type,
            outcome,
            actor_email,
        )


def _decode_detail(row: dict) -> dict:
    """Mirror of admin.py's `_decode_fee_category_row` -- `detail` comes back
    as a raw JSON string (no jsonb codec on this pool), decode once here for
    any future read path (e.g. an admin audit-log viewer)."""
    out = dict(row)
    if isinstance(out.get("detail"), str):
        out["detail"] = json.loads(out["detail"])
    return out


async def list_recent_events(conn: asyncpg.Connection, *, limit: int = 100) -> list[dict]:
    """Not consumed by any endpoint in Phase 1 -- included so the table isn't
    write-only from day one and a future admin audit view has something to
    call. Newest first."""
    rows = await conn.fetch(
        """
        SELECT id, event_type, actor_user_id, actor_email, target_user_id,
               ip_address, user_agent, outcome, detail, created_at
        FROM eparking.auth_audit_log
        ORDER BY created_at DESC
        LIMIT $1
        """,
        limit,
    )
    return [_decode_detail(dict(r)) for r in rows]
