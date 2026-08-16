"""Admin CRUD over `fee_categories` / `revenue_split_config`, plus the
manual reclassify trigger. All endpoints require the ADMIN role (see
`app.core.auth.require_admin`).

Every successful fee_categories/revenue_split write auto-enqueues a scoped
`reclassify_transactions` run (via `app.core.auto_reclassify`), clamped to
what's actually present in `raw_transactions`. `POST /admin/reclassify` is a
thin wrapper for arbitrary-range manual triggers (terminal remapping, bug
fixes) that does not go through the clamp-to-affected-effective-window logic
-- the caller supplies the exact range themselves.

See `.claude/sprints/07_ADMIN_RECLASSIFY.md` and
`.claude/skills/transform-classification/SKILL.md`.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.auth import require_admin
from app.core.auto_reclassify import trigger_scoped_reclassify
from app.core.db import get_pool
from app.core.passwords import PasswordPolicyError, hash_password, validate_password_policy
from app.core.reclassify_client import enqueue_reclassify
from app.core.sessions import destroy_all_for_user
from app.models.responses import (
    ConflictErrorResponse,
    FeeCategoryCreate,
    FeeCategoryListResponse,
    FeeCategoryResponse,
    FeeCategoryUpdate,
    FeeCategoryWriteResponse,
    ManualReclassifyRequest,
    ReclassifyTriggerInfo,
    RevenueSplitCreate,
    RevenueSplitConfigResponse,
    RevenueSplitListResponse,
    RevenueSplitWriteResponse,
    RunLogResponse,
)
from app.repositories import admin as admin_repo
from app.repositories import auth_audit
from app.repositories import users as users_repo
from app.repositories.admin import ExclusionConflict

router = APIRouter(prefix="/admin", tags=["admin"])

_RESET_TOKEN_TTL_HOURS = 1


def _conflict_response(exc: ExclusionConflict) -> HTTPException:
    """fee_categories-shaped 409 (amount range + code/label)."""
    return HTTPException(
        status_code=409,
        detail={
            "detail": (
                "This change conflicts with an existing effective-dated rule "
                "(overlapping amount range within an overlapping effective-date "
                "window). Adjust the amount range or effective dates so they do "
                "not overlap the row(s) below."
            ),
            "conflicting_rows": [
                {
                    "id": r["id"],
                    "code": r["code"],
                    "label": r["label"],
                    "amount_min": float(r["amount_min"]),
                    "amount_max": float(r["amount_max"]),
                    "effective_from": r["effective_from"].isoformat(),
                    "effective_to": r["effective_to"].isoformat() if r["effective_to"] else None,
                }
                for r in exc.conflicting_rows
            ],
        },
    )


def _revenue_split_conflict_response(exc: ExclusionConflict) -> HTTPException:
    """revenue_split_config-shaped 409 (no amount range/code/label -- just
    the effective-dated split percentages) -- kept separate from
    `_conflict_response` since the two tables' conflicting-row shapes don't
    overlap (fee_categories has code/label/amount_min/amount_max,
    revenue_split_config has aicl_pct/gsds_pct only)."""
    return HTTPException(
        status_code=409,
        detail={
            "detail": (
                "This change conflicts with an existing effective-dated revenue "
                "split window. Adjust the effective dates so they do not overlap "
                "the row(s) below."
            ),
            "conflicting_rows": [
                {
                    "id": r["id"],
                    "aicl_pct": float(r["aicl_pct"]),
                    "gsds_pct": float(r["gsds_pct"]),
                    "effective_from": r["effective_from"].isoformat(),
                    "effective_to": r["effective_to"].isoformat() if r["effective_to"] else None,
                }
                for r in exc.conflicting_rows
            ],
        },
    )


def _fee_category_to_response(row: dict) -> FeeCategoryResponse:
    return FeeCategoryResponse(
        id=row["id"],
        code=row["code"],
        revenue_stream=row["revenue_stream"],
        label=row["label"],
        vehicle_type=row["vehicle_type"],
        amount_min=float(row["amount_min"]),
        amount_max=float(row["amount_max"]),
        counts_as_entry=row["counts_as_entry"],
        is_revenue=row["is_revenue"],
        components=row["components"],
        is_provisional=row["is_provisional"],
        known_limitation=row["known_limitation"],
        priority=row["priority"],
        effective_from=row["effective_from"],
        effective_to=row["effective_to"],
    )


# --------------------------------------------------------------------------
# fee_categories
# --------------------------------------------------------------------------


@router.get("/fee-categories", response_model=FeeCategoryListResponse)
async def list_fee_categories(_role: str = Depends(require_admin)) -> FeeCategoryListResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await admin_repo.list_fee_categories(conn)
    return FeeCategoryListResponse(items=[_fee_category_to_response(r) for r in rows])


@router.post(
    "/fee-categories",
    response_model=FeeCategoryWriteResponse,
    status_code=202,
    responses={409: {"model": ConflictErrorResponse}},
)
async def create_fee_category(
    payload: FeeCategoryCreate, _role: str = Depends(require_admin)
) -> FeeCategoryWriteResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            row = await admin_repo.create_fee_category(
                conn,
                {
                    **payload.model_dump(exclude={"components"}),
                    "components": (
                        [c.model_dump() for c in payload.components] if payload.components else None
                    ),
                },
            )
        except ExclusionConflict as exc:
            raise _conflict_response(exc) from exc

        reclassify_info = await trigger_scoped_reclassify(
            conn,
            effective_from=row["effective_from"],
            effective_to=row["effective_to"],
            reason=f"fee_categories create: code={row['code']} (id={row['id']})",
        )

    return FeeCategoryWriteResponse(
        fee_category=_fee_category_to_response(row),
        reclassify=ReclassifyTriggerInfo(**reclassify_info),
    )


@router.patch(
    "/fee-categories/{fee_category_id}",
    response_model=FeeCategoryWriteResponse,
    status_code=202,
    responses={404: {"description": "Not found"}, 409: {"model": ConflictErrorResponse}},
)
async def update_fee_category(
    fee_category_id: int,
    payload: FeeCategoryUpdate,
    _role: str = Depends(require_admin),
) -> FeeCategoryWriteResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        existing = await admin_repo.get_fee_category(conn, fee_category_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"fee_category id={fee_category_id} not found")

        patch = payload.model_dump(exclude_unset=True)
        if "components" in patch and patch["components"] is not None:
            patch["components"] = [c if isinstance(c, dict) else c.model_dump() for c in patch["components"]]

        # Reclassify must cover both the old and new effective-date window,
        # since a date-range edit (e.g. retiring a rule earlier) affects
        # transactions in the *previous* range too, not just the new one.
        old_from, old_to = existing["effective_from"], existing["effective_to"]

        try:
            row = await admin_repo.update_fee_category(conn, fee_category_id, patch)
        except ExclusionConflict as exc:
            raise _conflict_response(exc) from exc

        combined_from = min(old_from, row["effective_from"])
        if old_to is None or row["effective_to"] is None:
            combined_to = None
        else:
            combined_to = max(old_to, row["effective_to"])

        reclassify_info = await trigger_scoped_reclassify(
            conn,
            effective_from=combined_from,
            effective_to=combined_to,
            reason=f"fee_categories update: code={row['code']} (id={row['id']})",
        )

    return FeeCategoryWriteResponse(
        fee_category=_fee_category_to_response(row),
        reclassify=ReclassifyTriggerInfo(**reclassify_info),
    )


# --------------------------------------------------------------------------
# revenue_split_config
# --------------------------------------------------------------------------


@router.get("/revenue-split", response_model=RevenueSplitListResponse)
async def list_revenue_split(_role: str = Depends(require_admin)) -> RevenueSplitListResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await admin_repo.list_revenue_split_config(conn)
    return RevenueSplitListResponse(
        items=[
            RevenueSplitConfigResponse(
                id=r["id"],
                aicl_pct=float(r["aicl_pct"]),
                gsds_pct=float(r["gsds_pct"]),
                effective_from=r["effective_from"],
                effective_to=r["effective_to"],
            )
            for r in rows
        ]
    )


@router.post(
    "/revenue-split",
    response_model=RevenueSplitWriteResponse,
    status_code=202,
    responses={409: {"model": ConflictErrorResponse}},
)
async def create_revenue_split(
    payload: RevenueSplitCreate, _role: str = Depends(require_admin)
) -> RevenueSplitWriteResponse:
    if round(payload.aicl_pct + payload.gsds_pct, 4) != 1.0:
        raise HTTPException(
            status_code=422,
            detail=f"aicl_pct + gsds_pct must equal 1.0 (got {payload.aicl_pct} + {payload.gsds_pct})",
        )

    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            row = await admin_repo.create_revenue_split_config(conn, payload.model_dump())
        except ExclusionConflict as exc:
            raise _revenue_split_conflict_response(exc) from exc

        # daily_revenue freezes aicl_amount/gsds_amount per-row at the split
        # rate in force on that row's transaction_date (see transform.py's
        # rebuild_daily_revenue docstring) -- a new/changed split window
        # must trigger the same scoped reclassify+rebuild as a
        # fee_categories edit so daily_revenue reflects the new rate.
        reclassify_info = await trigger_scoped_reclassify(
            conn,
            effective_from=row["effective_from"],
            effective_to=row["effective_to"],
            reason=f"revenue_split_config create: id={row['id']}",
        )

    return RevenueSplitWriteResponse(
        revenue_split=RevenueSplitConfigResponse(
            id=row["id"],
            aicl_pct=float(row["aicl_pct"]),
            gsds_pct=float(row["gsds_pct"]),
            effective_from=row["effective_from"],
            effective_to=row["effective_to"],
        ),
    )


# --------------------------------------------------------------------------
# manual reclassify trigger
# --------------------------------------------------------------------------


@router.post("/reclassify", status_code=202, response_model=ReclassifyTriggerInfo)
async def manual_reclassify(
    payload: ManualReclassifyRequest, _role: str = Depends(require_admin)
) -> ReclassifyTriggerInfo:
    """Thin wrapper directly triggering `reclassify_transactions` (via the
    same `eparking.ingest.reclassify` Celery task the auto-trigger path
    uses) for an arbitrary admin-supplied range -- terminal remapping,
    transform bug fixes, timezone corrections. Unlike the auto-trigger path,
    this does not clamp to raw_transactions' extent (the admin supplied the
    range deliberately) but does still no-op if there's genuinely no data in
    range, to avoid enqueueing a pointless run."""
    pool = get_pool()
    async with pool.acquire() as conn:
        clamped = await admin_repo.clamp_to_raw_transactions_range(
            conn, requested_from=payload.from_date, requested_to=payload.to_date
        )
        if clamped is None:
            return ReclassifyTriggerInfo(
                triggered=False,
                reason="no raw_transactions rows fall within the requested range",
                scoped_from=payload.from_date,
                scoped_to=payload.to_date,
            )

        celery_task_id = enqueue_reclassify(
            from_date_iso=payload.from_date.isoformat(),
            to_date_iso=payload.to_date.isoformat(),
            reason=payload.reason,
        )

        run_row = None
        for _ in range(20):
            await asyncio.sleep(0.25)
            candidate = await admin_repo.find_recent_reclassify_run(
                conn, window_from=payload.from_date, window_to=payload.to_date
            )
            if candidate is not None:
                run_row = candidate
                break

    return ReclassifyTriggerInfo(
        triggered=True,
        reason=payload.reason,
        scoped_from=payload.from_date,
        scoped_to=payload.to_date,
        run_id=run_row["id"] if run_row else None,
        celery_task_id=celery_task_id,
        status=run_row["status"] if run_row else "enqueued",
    )


@router.get("/reclassify/{run_id}", response_model=RunLogResponse)
async def get_reclassify_run(run_id: int, _role: str = Depends(require_admin)) -> RunLogResponse:
    """Poll a reclassify run's progress/result by `run_logs.id`."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await admin_repo.get_run_log(conn, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"run_logs id={run_id} not found")
    return RunLogResponse(
        id=row["id"],
        run_type=row["run_type"],
        status=row["status"],
        window_from=row["window_from"].isoformat() if row["window_from"] else None,
        window_to=row["window_to"].isoformat() if row["window_to"] else None,
        rows_fetched=row["rows_fetched"],
        rows_upserted=row["rows_upserted"],
        error_message=row["error_message"],
        started_at=row["started_at"].isoformat(),
        finished_at=row["finished_at"].isoformat() if row["finished_at"] else None,
    )


# --------------------------------------------------------------------------
# /admin/users -- Sprint 09 (Authentication & Session Security), Phase 2.
#
# Guarded by the existing, unmodified `require_admin` dependency -- same as
# every other endpoint in this router. Never returns `hashed_password`
# (every response goes through `users_repo.to_public_dict`).
# --------------------------------------------------------------------------


class UserListResponse(BaseModel):
    items: list[dict]


class UserCreateRequest(BaseModel):
    email: str
    display_name: str
    role: str
    organization: str | None = None
    password: str


class UserCreateResponse(BaseModel):
    user: dict


class UserUpdateRequest(BaseModel):
    role: str | None = None
    display_name: str | None = None
    organization: str | None = None
    is_active: bool | None = None


class UserUpdateResponse(BaseModel):
    user: dict


class AdminPasswordUpdateRequest(BaseModel):
    new_password: str


class PasswordResetIssueResponse(BaseModel):
    reset_token: str
    expires_at: object


def _actor_from_request(request: Request) -> tuple[int | None, str | None]:
    """Attributes an admin mutation to a named person when the caller
    authenticated via a session (per §9's "attribution ... is one of the
    largest concrete security wins in this sprint"). Falls back to
    `(None, None)` for static-API-key/service callers -- `principal_type
    = 'SERVICE'` in spirit, per §12 (the audit table has no literal
    `principal_type` column; a NULL `actor_user_id` with a NULL
    `actor_email` is how a service-credential call is distinguished from a
    named admin's session in `auth_audit_log`)."""
    session = getattr(request.state, "session", None)
    if session is None:
        return None, None
    return session.user_id, session.email


@router.get("/users", response_model=UserListResponse)
async def list_users(_role: str = Depends(require_admin)) -> UserListResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await users_repo.list_users(conn)
    return UserListResponse(items=[users_repo.to_public_dict(r) for r in rows])


@router.post("/users", response_model=UserCreateResponse, status_code=201)
async def create_user(
    payload: UserCreateRequest, request: Request, _role: str = Depends(require_admin)
) -> UserCreateResponse:
    if payload.role not in ("ADMIN", "VIEWER"):
        raise HTTPException(status_code=422, detail="role must be 'ADMIN' or 'VIEWER'")
    if payload.organization is not None and payload.organization not in ("AICL", "GSDS"):
        raise HTTPException(status_code=422, detail="organization must be 'AICL', 'GSDS', or null")

    try:
        validate_password_policy(payload.password)
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    pool = get_pool()
    async with pool.acquire() as conn:
        existing = await users_repo.get_user_by_email(conn, payload.email)
        if existing is not None:
            raise HTTPException(status_code=409, detail=f"A user with email '{payload.email}' already exists.")

        user = await users_repo.create_user(
            conn,
            email=payload.email,
            password=payload.password,
            role=payload.role,
            display_name=payload.display_name,
            organization=payload.organization,
            must_change_password=True,
        )

        actor_user_id, actor_email = _actor_from_request(request)
        await auth_audit.record_event(
            conn,
            event_type=auth_audit.USER_CREATED,
            outcome=auth_audit.OUTCOME_SUCCESS,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            target_user_id=user["id"],
            detail={"email": user["email"], "role": user["role"]},
        )

    return UserCreateResponse(user=users_repo.to_public_dict(user))


@router.patch("/users/{user_id}", response_model=UserUpdateResponse)
async def update_user(
    user_id: int, payload: UserUpdateRequest, request: Request, _role: str = Depends(require_admin)
) -> UserUpdateResponse:
    if payload.role is not None and payload.role not in ("ADMIN", "VIEWER"):
        raise HTTPException(status_code=422, detail="role must be 'ADMIN' or 'VIEWER'")
    if payload.organization is not None and payload.organization not in ("AICL", "GSDS"):
        raise HTTPException(status_code=422, detail="organization must be 'AICL', 'GSDS', or null")

    patch = payload.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=422, detail="No fields supplied to update.")

    pool = get_pool()
    async with pool.acquire() as conn:
        existing = await users_repo.get_user_by_id(conn, user_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"user id={user_id} not found")

        updated = await users_repo.update_user(conn, user_id, patch)
        if updated is None:
            raise HTTPException(status_code=404, detail=f"user id={user_id} not found")

        actor_user_id, actor_email = _actor_from_request(request)

        if "role" in patch and patch["role"] != existing["role"]:
            await auth_audit.record_event(
                conn,
                event_type=auth_audit.USER_ROLE_CHANGED,
                outcome=auth_audit.OUTCOME_SUCCESS,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                target_user_id=user_id,
                detail={"old_role": existing["role"], "new_role": patch["role"]},
            )

        if "is_active" in patch and patch["is_active"] != existing["is_active"]:
            if patch["is_active"] is False:
                # A deactivated user's existing session must not keep
                # working -- destroy every live session for this user
                # immediately, don't wait for idle/absolute expiry.
                await destroy_all_for_user(user_id)
                await auth_audit.record_event(
                    conn,
                    event_type=auth_audit.USER_DEACTIVATED,
                    outcome=auth_audit.OUTCOME_SUCCESS,
                    actor_user_id=actor_user_id,
                    actor_email=actor_email,
                    target_user_id=user_id,
                    detail={"old_is_active": existing["is_active"], "new_is_active": False},
                )
            else:
                await auth_audit.record_event(
                    conn,
                    event_type=auth_audit.USER_REACTIVATED,
                    outcome=auth_audit.OUTCOME_SUCCESS,
                    actor_user_id=actor_user_id,
                    actor_email=actor_email,
                    target_user_id=user_id,
                    detail={"old_is_active": existing["is_active"], "new_is_active": True},
                )

    return UserUpdateResponse(user=users_repo.to_public_dict(updated))


@router.patch("/users/{user_id}/password", response_model=UserUpdateResponse)
async def update_user_password(
    user_id: int,
    payload: AdminPasswordUpdateRequest,
    request: Request,
    _role: str = Depends(require_admin),
) -> UserUpdateResponse:
    """Sets a user password directly from the admin console.

    The plaintext password is policy-validated and hashed in-process, never
    returned or written to logs. All existing sessions for the target user
    are revoked before the database update so a revocation failure cannot
    leave the new credential active alongside stale sessions.
    """
    try:
        validate_password_policy(payload.new_password)
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    pool = get_pool()
    async with pool.acquire() as conn:
        existing = await users_repo.get_user_by_id(conn, user_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"user id={user_id} not found")

        new_hash = hash_password(payload.new_password)

        # Revocation must succeed before the credential changes. If Redis is
        # unavailable, leave the old password in place instead of returning
        # an error after partially applying a security-sensitive operation.
        await destroy_all_for_user(user_id)

        actor_user_id, actor_email = _actor_from_request(request)
        async with conn.transaction():
            updated = await users_repo.set_password(
                conn, user_id, new_hash, must_change_password=True
            )
            if updated is None:
                raise HTTPException(status_code=404, detail=f"user id={user_id} not found")

            # Keep the password write and its audit event in one database
            # transaction so they cannot report contradictory outcomes.
            await auth_audit.record_event(
                conn,
                event_type=auth_audit.PASSWORD_ADMIN_SET,
                outcome=auth_audit.OUTCOME_SUCCESS,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                target_user_id=user_id,
            )

    return UserUpdateResponse(user=users_repo.to_public_dict(updated))


@router.post("/users/{user_id}/password-reset", response_model=PasswordResetIssueResponse)
async def issue_password_reset(
    user_id: int, request: Request, _role: str = Depends(require_admin)
) -> PasswordResetIssueResponse:
    """Issues a one-time password-reset token (v1's admin-issued,
    out-of-band flow per §6 -- no self-service email reset exists yet). The
    RAW token is returned once in this response; only its SHA-256 digest is
    ever persisted (high-entropy `token_urlsafe`, so a fast, unsalted digest
    is an accepted tradeoff per §6 -- unlike a low-entropy user password,
    which always goes through argon2id)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        user = await users_repo.get_user_by_id(conn, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail=f"user id={user_id} not found")

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        row = await conn.fetchrow(
            """
            INSERT INTO eparking.password_reset_tokens (user_id, token_hash, expires_at)
            VALUES ($1, $2, now() + make_interval(hours => $3))
            RETURNING expires_at
            """,
            user_id,
            token_hash,
            _RESET_TOKEN_TTL_HOURS,
        )

        actor_user_id, actor_email = _actor_from_request(request)
        await auth_audit.record_event(
            conn,
            event_type=auth_audit.PASSWORD_RESET_ISSUED,
            outcome=auth_audit.OUTCOME_SUCCESS,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            target_user_id=user_id,
        )

    return PasswordResetIssueResponse(reset_token=raw_token, expires_at=row["expires_at"])
