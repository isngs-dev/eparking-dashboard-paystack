"""Bootstrap CLI -- creates the first admin user.

Sprint 09 (Authentication & Session Security), Phase 1, §6. A CLI command,
not a seeded migration password (`014_users.sql` deliberately seeds no
credentials). Must run BEFORE middleware enforcement is enabled (Phase 5) --
losing this order locks everyone out.

Usage:
    python -m app.create_admin --email admin@example.com --name "Jane Doe" --role ADMIN
    python -m app.create_admin --email viewer@example.com --name "John Doe" --role VIEWER --organization GSDS

Password input: interactive `getpass` prompt (not echoed), OR the
`BOOTSTRAP_ADMIN_PASSWORD` env var if set. NEVER accept the password as a
command-line argument -- argv is visible via `ps`/shell history on most
systems.

Refuses to run (no partial write) if:
- the password fails the policy (`app.password_policy.validate_password_policy`)
- a user with that email already exists (case-insensitive, matching the
  `ux_users_email` unique index on `lower(email)`)
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

import asyncpg

from app.db import get_connection
from app.password_policy import PasswordPolicyError, hash_password, validate_password_policy

_VALID_ROLES = {"ADMIN", "VIEWER"}
_VALID_ORGS = {"AICL", "GSDS"}


def _read_password() -> str:
    """`BOOTSTRAP_ADMIN_PASSWORD` env var takes precedence (e.g. for scripted/
    CI bootstrap) over the interactive prompt. Never read from argv."""
    env_password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
    if env_password:
        return env_password

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Error: passwords do not match.", file=sys.stderr)
        sys.exit(1)
    return password


async def _user_exists(conn: asyncpg.Connection, email: str) -> bool:
    row = await conn.fetchrow(
        "SELECT id FROM eparking.users WHERE lower(email) = lower($1)", email
    )
    return row is not None


async def create_admin(
    *,
    email: str,
    display_name: str,
    role: str,
    organization: str | None,
    password: str,
) -> int:
    """Creates the user row. Returns the new user's id. Raises on any
    refusal condition (policy failure, duplicate email) -- caller is
    responsible for translating to a clean CLI exit."""
    validate_password_policy(password)

    conn = await get_connection()
    try:
        if await _user_exists(conn, email):
            raise ValueError(f"A user with email '{email}' already exists.")

        hashed = hash_password(password)
        row = await conn.fetchrow(
            """
            INSERT INTO eparking.users
                (email, hashed_password, role, display_name, organization,
                 must_change_password)
            VALUES (lower($1), $2, $3, $4, $5, FALSE)
            RETURNING id
            """,
            email,
            hashed,
            role,
            display_name,
            organization,
        )
        return row["id"]
    finally:
        await conn.close()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap the first admin (or any) user account. "
        "Password is read from stdin or BOOTSTRAP_ADMIN_PASSWORD -- never "
        "pass it as a command-line argument."
    )
    parser.add_argument("--email", required=True, help="Login email (normalized to lowercase).")
    parser.add_argument("--name", required=True, dest="display_name", help="Display name.")
    parser.add_argument(
        "--role", required=True, choices=sorted(_VALID_ROLES), help="ADMIN or VIEWER."
    )
    parser.add_argument(
        "--organization",
        required=False,
        choices=sorted(_VALID_ORGS),
        default=None,
        help="Optional: AICL or GSDS (display/audit attribution only).",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args(sys.argv[1:])

    password = _read_password()

    try:
        validate_password_policy(password)
    except PasswordPolicyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        user_id = asyncio.run(
            create_admin(
                email=args.email,
                display_name=args.display_name,
                role=args.role,
                organization=args.organization,
                password=password,
            )
        )
    except ValueError as exc:
        # Duplicate email / policy failure surfaced from create_admin().
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 -- top-level CLI error reporting
        print(f"Failed to create user: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        f"Created user id={user_id} email={args.email} role={args.role} "
        f"organization={args.organization or '(none)'}. Password not shown."
    )


if __name__ == "__main__":
    main()
