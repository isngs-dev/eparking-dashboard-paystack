"""Session-based authentication endpoints.

Sprint 09 (Authentication & Session Security), Phase 2, §5. Implements the
login/logout/me/change-password/password-reset-redeem flow described in the
sprint doc's "Login logic -- enumeration-safe path" pseudocode verbatim.

Every failure branch of `/auth/login` (unknown user, inactive, locked, bad
password) returns a byte-identical `401 {"detail": "Invalid email or
password."}` -- no path-specific wording, no differing headers -- so a caller
cannot distinguish "this email doesn't exist" from "this email exists but the
password was wrong" from timing or response shape. `verify_password(
DUMMY_HASH, password)` is called on every early-return path (unknown user,
inactive, locked) specifically to equalize timing against the real
bad-password path, which also runs one `verify_password` call.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.db import get_pool
from app.core.passwords import (
    DUMMY_HASH,
    PasswordPolicyError,
    hash_password,
    needs_rehash,
    validate_password_policy,
    verify_password,
)
from app.core.rate_limit import (
    RateLimitBackendError,
    RateLimitExceeded,
    check_login_rate_limit_by_account,
    check_login_rate_limit_by_ip,
)
from app.core.sessions import SessionData, create_session, destroy_all_for_user, destroy_session, read_session
from app.repositories import auth_audit
from app.repositories import users as users_repo
from eparking_common.config import get_settings

logger = logging.getLogger("app.routers.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

_GENERIC_LOGIN_FAILURE_DETAIL = "Invalid email or password."


# --------------------------------------------------------------------------
# Request/response bodies
# --------------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    user: dict
    must_change_password: bool


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=1)  # real bound enforced by validate_password_policy


class ChangePasswordResponse(BaseModel):
    ok: bool = True


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=120)


class ProfileUpdateResponse(BaseModel):
    user: dict


class PasswordResetRedeemRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=1)


class PasswordResetRedeemResponse(BaseModel):
    """Always the same shape/status regardless of whether the token was
    valid -- see `password_reset_redeem`'s docstring."""

    detail: str = "If the reset code was valid, your password has been updated."


class LogoutResponse(BaseModel):
    ok: bool = True


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _client_ip(request: Request) -> str:
    """Direct connecting client IP. `X-Forwarded-For` is deliberately not
    trusted here -- per the sprint doc's §2 adoption note ("X-Forwarded-For
    only honored for configured trusted hops"), and no trusted-proxy hop
    list exists yet in this deployment, so honoring an unauthenticated
    client-supplied header would let a caller spoof their rate-limit
    identity. Revisit if/when a reverse proxy config defines trusted hops."""
    if request.client is None:
        return "unknown"
    return request.client.host


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
        # No max_age/expires: session cookie, cleared when the browser
        # closes; server-side idle/absolute expiry is the real control.
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )


async def require_session(
    request: Request,
    eparking_session: str | None = Cookie(default=None),
) -> SessionData:
    """FastAPI dependency: 401 if the session cookie is missing, invalid, or
    expired (idle or absolute -- both checked inside `read_session`).
    Backs `/auth/logout`, `/auth/me`, `/auth/change-password`. Slides the
    session on every use, matching "every authenticated request" per
    `sessions.py`."""
    if not eparking_session:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    session = await read_session(eparking_session, slide=True)
    if session is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid.")
    request.state.session = session
    return session


# --------------------------------------------------------------------------
# POST /auth/login
# --------------------------------------------------------------------------


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> LoginResponse:
    settings = get_settings()
    ip = _client_ip(request)
    user_agent = _user_agent(request)
    email = payload.email.strip()

    # Step 1: per-IP rate limit. Fails closed on Redis error (503), per §5
    # step 1 / §2's explicit "fails closed when Redis is down".
    try:
        await check_login_rate_limit_by_ip(ip)
    except RateLimitBackendError as exc:
        logger.error("login rate-limit backend error (ip): %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Login is temporarily unavailable. Please try again shortly.",
        ) from exc
    except RateLimitExceeded as exc:
        pool = get_pool()
        async with pool.acquire() as conn:
            await auth_audit.record_event(
                conn,
                event_type=auth_audit.RATE_LIMIT_TRIPPED,
                outcome=auth_audit.OUTCOME_FAILURE,
                actor_email=email,
                ip_address=ip,
                user_agent=user_agent,
                detail={"scope": "ip", "retry_after_seconds": exc.retry_after_seconds},
            )
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    # Step 2: per-account rate limit, keyed on sha256(lower(email)).
    try:
        await check_login_rate_limit_by_account(email)
    except RateLimitBackendError as exc:
        logger.error("login rate-limit backend error (account): %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Login is temporarily unavailable. Please try again shortly.",
        ) from exc
    except RateLimitExceeded as exc:
        pool = get_pool()
        async with pool.acquire() as conn:
            await auth_audit.record_event(
                conn,
                event_type=auth_audit.RATE_LIMIT_TRIPPED,
                outcome=auth_audit.OUTCOME_FAILURE,
                actor_email=email,
                ip_address=ip,
                user_agent=user_agent,
                detail={"scope": "account", "retry_after_seconds": exc.retry_after_seconds},
            )
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    pool = get_pool()
    async with pool.acquire() as conn:
        # Step 3.
        user = await users_repo.get_user_by_email(conn, email)

        # Step 4: unknown user.
        if user is None:
            verify_password(DUMMY_HASH, payload.password)
            await auth_audit.record_event(
                conn,
                event_type=auth_audit.LOGIN_FAILURE,
                outcome=auth_audit.OUTCOME_FAILURE,
                actor_email=email,
                ip_address=ip,
                user_agent=user_agent,
                detail={"reason": "unknown_user"},
            )
            raise HTTPException(status_code=401, detail=_GENERIC_LOGIN_FAILURE_DETAIL)

        # Step 5: inactive.
        if not user["is_active"]:
            verify_password(DUMMY_HASH, payload.password)
            await auth_audit.record_event(
                conn,
                event_type=auth_audit.LOGIN_FAILURE,
                outcome=auth_audit.OUTCOME_FAILURE,
                actor_user_id=user["id"],
                actor_email=email,
                ip_address=ip,
                user_agent=user_agent,
                detail={"reason": "inactive"},
            )
            raise HTTPException(status_code=401, detail=_GENERIC_LOGIN_FAILURE_DETAIL)

        # Step 6: locked.
        if users_repo.is_locked(user, now=datetime.now(timezone.utc)):
            verify_password(DUMMY_HASH, payload.password)
            await auth_audit.record_event(
                conn,
                event_type=auth_audit.LOGIN_FAILURE,
                outcome=auth_audit.OUTCOME_FAILURE,
                actor_user_id=user["id"],
                actor_email=email,
                ip_address=ip,
                user_agent=user_agent,
                detail={"reason": "locked"},
            )
            raise HTTPException(status_code=401, detail=_GENERIC_LOGIN_FAILURE_DETAIL)

        # Step 7: bad password.
        if not verify_password(user["hashed_password"], payload.password):
            result = await users_repo.record_login_failure(
                conn,
                user["id"],
                max_failed_attempts=settings.login_max_failed_attempts,
                lockout_minutes=settings.login_lockout_minutes,
            )
            await auth_audit.record_event(
                conn,
                event_type=auth_audit.LOGIN_FAILURE,
                outcome=auth_audit.OUTCOME_FAILURE,
                actor_user_id=user["id"],
                actor_email=email,
                ip_address=ip,
                user_agent=user_agent,
                detail={"reason": "bad_password", "failed_login_count": result["failed_login_count"]},
            )
            if result["locked"]:
                await auth_audit.record_event(
                    conn,
                    event_type=auth_audit.ACCOUNT_LOCKED,
                    outcome=auth_audit.OUTCOME_FAILURE,
                    actor_user_id=user["id"],
                    actor_email=email,
                    ip_address=ip,
                    user_agent=user_agent,
                    detail={"lockout_minutes": settings.login_lockout_minutes},
                )
            raise HTTPException(status_code=401, detail=_GENERIC_LOGIN_FAILURE_DETAIL)

        # Step 8: success.
        if needs_rehash(user["hashed_password"]):
            rehashed = hash_password(payload.password)
            await users_repo.set_password(
                conn, user["id"], rehashed, must_change_password=user["must_change_password"]
            )

        await users_repo.record_login_success(conn, user["id"])
        # Re-fetch so the response reflects the just-applied resets
        # (failed_login_count/locked_until/last_login_at) rather than the
        # pre-update snapshot.
        user = await users_repo.get_user_by_id(conn, user["id"])

        token = await create_session(
            user_id=user["id"],
            email=user["email"],
            role=user["role"],
            display_name=user["display_name"],
            organization=user["organization"],
            ip=ip,
            user_agent=user_agent,
        )
        _set_session_cookie(response, token)

        await auth_audit.record_event(
            conn,
            event_type=auth_audit.LOGIN_SUCCESS,
            outcome=auth_audit.OUTCOME_SUCCESS,
            actor_user_id=user["id"],
            actor_email=email,
            ip_address=ip,
            user_agent=user_agent,
        )

    return LoginResponse(
        user=users_repo.to_public_dict(user),
        must_change_password=user["must_change_password"],
    )


# --------------------------------------------------------------------------
# POST /auth/logout
# --------------------------------------------------------------------------


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    response: Response,
    session: SessionData = Depends(require_session),
    eparking_session: str | None = Cookie(default=None),
) -> LogoutResponse:
    """Destroys the Redis session AND clears the cookie -- both steps are
    required (see `sessions.py`'s docstring citing the KB's "dead blacklist"
    audit finding: a revocation mechanism that exists but is never actually
    invoked on logout). `eparking_session` is guaranteed non-None here
    because `require_session` already validated it."""
    assert eparking_session is not None
    await destroy_session(eparking_session)
    _clear_session_cookie(response)

    pool = get_pool()
    async with pool.acquire() as conn:
        await auth_audit.record_event(
            conn,
            event_type=auth_audit.LOGOUT,
            outcome=auth_audit.OUTCOME_SUCCESS,
            actor_user_id=session.user_id,
            actor_email=session.email,
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )
    return LogoutResponse()


# --------------------------------------------------------------------------
# GET /auth/me
# --------------------------------------------------------------------------


@router.get("/me")
async def me(session: SessionData = Depends(require_session)) -> dict:
    """Current user's public dict -- the source of truth the (eventual)
    frontend RSC layer calls to determine auth state. Re-reads the DB row
    (rather than trusting the session payload alone) so a role/active-state
    change made by an admin elsewhere is reflected immediately, not just
    after the session's next full re-issue."""
    pool = get_pool()
    async with pool.acquire() as conn:
        user = await users_repo.get_user_by_id(conn, session.user_id)
    if user is None or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return users_repo.to_public_dict(user)


@router.patch("/me", response_model=ProfileUpdateResponse)
async def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    session: SessionData = Depends(require_session),
) -> ProfileUpdateResponse:
    """Updates the signed-in user's display name and no authorization fields."""
    display_name = payload.display_name.strip()
    if not display_name:
        raise HTTPException(status_code=422, detail="Display name cannot be blank.")

    pool = get_pool()
    async with pool.acquire() as conn:
        updated = await users_repo.update_display_name(
            conn, session.user_id, display_name
        )
        if updated is None:
            raise HTTPException(status_code=401, detail="Not authenticated.")

        await auth_audit.record_event(
            conn,
            event_type=auth_audit.PROFILE_UPDATED,
            outcome=auth_audit.OUTCOME_SUCCESS,
            actor_user_id=session.user_id,
            actor_email=session.email,
            target_user_id=session.user_id,
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
            detail={"display_name": display_name},
        )

    return ProfileUpdateResponse(user=users_repo.to_public_dict(updated))


# --------------------------------------------------------------------------
# POST /auth/change-password
# --------------------------------------------------------------------------


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    session: SessionData = Depends(require_session),
    eparking_session: str | None = Cookie(default=None),
) -> ChangePasswordResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        user = await users_repo.get_user_by_id(conn, session.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated.")

        if not verify_password(user["hashed_password"], payload.current_password):
            raise HTTPException(status_code=401, detail="Current password is incorrect.")

        try:
            validate_password_policy(payload.new_password)
        except PasswordPolicyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        new_hash = hash_password(payload.new_password)

        # Revoke all OTHER sessions for this user, but keep the current
        # request working so changing your own password doesn't log you out
        # (per §7's "sensible judgment" call-out): destroy every session
        # (including this one), then immediately issue a fresh replacement
        # session and set it as the new cookie value on this response --
        # net effect is "every OTHER session dies, this one is transparently
        # re-issued", satisfying `destroy_all_for_user`'s "all sessions"
        # contract without local special-casing inside sessions.py.
        assert eparking_session is not None
        await destroy_all_for_user(user["id"])

        # Revocation must complete before the credential changes. If Redis
        # is unavailable, the request fails while the old password remains
        # valid instead of leaving stale sessions active after a partial
        # password update.
        await users_repo.set_password(
            conn, user["id"], new_hash, must_change_password=False
        )

        new_token = await create_session(
            user_id=user["id"],
            email=user["email"],
            role=user["role"],
            display_name=user["display_name"],
            organization=user["organization"],
            ip=_client_ip(request),
            user_agent=_user_agent(request),
        )
        _set_session_cookie(response, new_token)

        await auth_audit.record_event(
            conn,
            event_type=auth_audit.PASSWORD_CHANGED,
            outcome=auth_audit.OUTCOME_SUCCESS,
            actor_user_id=user["id"],
            actor_email=user["email"],
            ip_address=_client_ip(request),
            user_agent=_user_agent(request),
        )

    return ChangePasswordResponse()


# --------------------------------------------------------------------------
# POST /auth/password-reset/redeem
# --------------------------------------------------------------------------


@router.post("/password-reset/redeem", response_model=PasswordResetRedeemResponse)
async def password_reset_redeem(payload: PasswordResetRedeemRequest) -> PasswordResetRedeemResponse:
    """Always returns the same generic 200, regardless of whether `token`
    was valid, unknown, expired, or already consumed -- per §5/§6's
    enumeration-safety philosophy applied to reset tokens. The consuming
    UPDATE re-asserts `WHERE consumed_at IS NULL AND expires_at > now()` in
    the same statement that looks the token up, so a `rowcount == 0` result
    is treated as a full failure even if the row existed a moment earlier --
    closing the double-redeem race (two concurrent redeems of the same
    token: only one UPDATE can ever affect a row)."""
    token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()

    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            validate_password_policy(payload.new_password)
        except PasswordPolicyError:
            # Dummy work to equalize timing with the success path (which
            # also hashes a password), then fall through to the generic
            # failure/no-op response -- never reveal that the *token* was
            # fine but the *password* failed policy.
            verify_password(DUMMY_HASH, payload.new_password)
            return PasswordResetRedeemResponse()

        row = await conn.fetchrow(
            """
            SELECT id, user_id, expires_at, consumed_at
            FROM eparking.password_reset_tokens
            WHERE token_hash = $1
            """,
            token_hash,
        )

        if row is None:
            # Dummy hash verify to equalize timing against the success path.
            verify_password(DUMMY_HASH, payload.new_password)
            return PasswordResetRedeemResponse()

        new_hash = hash_password(payload.new_password)

        consumed = await conn.execute(
            """
            UPDATE eparking.password_reset_tokens
            SET consumed_at = now()
            WHERE id = $1 AND consumed_at IS NULL AND expires_at > now()
            """,
            row["id"],
        )
        # asyncpg's `execute` returns a string like "UPDATE 1"/"UPDATE 0".
        rowcount = int(consumed.split()[-1]) if consumed else 0
        if rowcount == 0:
            # Already consumed, or expired between the SELECT and the
            # UPDATE (race) -- treat identically to "token invalid".
            return PasswordResetRedeemResponse()

        user = await users_repo.get_user_by_id(conn, row["user_id"])
        if user is None:
            # Orphaned token (user deleted) -- nothing left to do, but the
            # token row is already consumed above so it can't be replayed.
            return PasswordResetRedeemResponse()

        await users_repo.set_password(conn, user["id"], new_hash, must_change_password=False)
        await destroy_all_for_user(user["id"])

        await auth_audit.record_event(
            conn,
            event_type=auth_audit.PASSWORD_RESET_REDEEMED,
            outcome=auth_audit.OUTCOME_SUCCESS,
            actor_user_id=user["id"],
            actor_email=user["email"],
            target_user_id=user["id"],
        )

    return PasswordResetRedeemResponse()
