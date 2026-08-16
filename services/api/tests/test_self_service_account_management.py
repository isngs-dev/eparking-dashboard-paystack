from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, Response
from pydantic import ValidationError
from starlette.requests import Request

from app.core.sessions import SessionData
from app.routers.auth import (
    ChangePasswordRequest,
    ProfileUpdateRequest,
    change_password,
    update_profile,
)


class _AcquireContext:
    def __init__(self, conn: object) -> None:
        self.conn = conn

    async def __aenter__(self) -> object:
        return self.conn

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Connection:
    def transaction(self) -> _AcquireContext:
        return _AcquireContext(self)


class _Pool:
    def __init__(self, conn: object) -> None:
        self.conn = conn

    def acquire(self) -> _AcquireContext:
        return _AcquireContext(self.conn)


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/auth/me",
            "headers": [(b"user-agent", b"settings-test")],
            "client": ("127.0.0.1", 12345),
        }
    )


def _session(*, role: str = "VIEWER") -> SessionData:
    return SessionData(
        user_id=7,
        email="viewer@example.com",
        role=role,
        display_name="Old Name",
        organization="GSDS",
        created_at=1.0,
        last_seen_at=1.0,
        ip="127.0.0.1",
        ua_hash=None,
    )


def _user(**changes: object) -> dict:
    user = {
        "id": 7,
        "email": "viewer@example.com",
        "role": "VIEWER",
        "display_name": "Old Name",
        "organization": "GSDS",
        "is_active": True,
        "must_change_password": False,
        "hashed_password": "old-hash",
    }
    user.update(changes)
    return user


class SelfServiceAccountManagementTests(IsolatedAsyncioTestCase):
    async def test_both_roles_update_only_their_own_trimmed_display_name(self) -> None:
        for role in ("VIEWER", "ADMIN"):
            with self.subTest(role=role):
                conn = _Connection()
                updated = _user(role=role, display_name="New Name")
                payload = ProfileUpdateRequest(display_name="  New Name  ")

                with (
                    patch("app.routers.auth.get_pool", return_value=_Pool(conn)),
                    patch(
                        "app.routers.auth.users_repo.update_display_name",
                        new=AsyncMock(return_value=updated),
                    ) as update_mock,
                    patch(
                        "app.routers.auth.auth_audit.record_event",
                        new=AsyncMock(),
                    ) as audit_mock,
                ):
                    response = await update_profile(
                        payload, _request(), _session(role=role)
                    )

                update_mock.assert_awaited_once_with(conn, 7, "New Name")
                self.assertEqual(response.user["display_name"], "New Name")
                self.assertNotIn("hashed_password", response.user)
                audit_mock.assert_awaited_once()

    def test_profile_contract_rejects_authorization_fields(self) -> None:
        with self.assertRaises(ValidationError):
            ProfileUpdateRequest(display_name="New Name", role="ADMIN")

    async def test_profile_rejects_blank_display_name(self) -> None:
        payload = ProfileUpdateRequest(display_name="   ")

        with self.assertRaises(HTTPException) as raised:
            await update_profile(payload, _request(), _session(role="ADMIN"))

        self.assertEqual(raised.exception.status_code, 422)

    async def test_inactive_user_cannot_update_profile(self) -> None:
        conn = _Connection()
        payload = ProfileUpdateRequest(display_name="New Name")

        with (
            patch("app.routers.auth.get_pool", return_value=_Pool(conn)),
            patch(
                "app.routers.auth.users_repo.update_display_name",
                new=AsyncMock(return_value=None),
            ) as update_mock,
            patch(
                "app.routers.auth.auth_audit.record_event", new=AsyncMock()
            ) as audit_mock,
        ):
            with self.assertRaises(HTTPException) as raised:
                await update_profile(payload, _request(), _session())

        self.assertEqual(raised.exception.status_code, 401)
        update_mock.assert_awaited_once_with(conn, 7, "New Name")
        audit_mock.assert_not_awaited()

    async def test_password_is_not_changed_when_session_revocation_fails(self) -> None:
        conn = _Connection()
        payload = ChangePasswordRequest(
            current_password="Current secure passphrase 2026",
            new_password="Replacement secure passphrase 2026",
        )

        with (
            patch("app.routers.auth.get_pool", return_value=_Pool(conn)),
            patch(
                "app.routers.auth.users_repo.get_user_by_id",
                new=AsyncMock(return_value=_user()),
            ),
            patch("app.routers.auth.verify_password", return_value=True),
            patch("app.routers.auth.validate_password_policy"),
            patch("app.routers.auth.hash_password", return_value="new-hash"),
            patch(
                "app.routers.auth.users_repo.set_password", new=AsyncMock()
            ) as set_password_mock,
            patch(
                "app.routers.auth.destroy_all_for_user",
                new=AsyncMock(side_effect=RuntimeError("Redis unavailable")),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Redis unavailable"):
                await change_password(
                    payload,
                    _request(),
                    Response(),
                    _session(),
                    "current-session-token",
                )

        set_password_mock.assert_not_awaited()

    async def test_user_password_change_clears_forced_change_and_reissues_session(self) -> None:
        conn = _Connection()
        payload = ChangePasswordRequest(
            current_password="Temporary secure passphrase 2026",
            new_password="Personal secure passphrase 2026",
        )

        with (
            patch("app.routers.auth.get_pool", return_value=_Pool(conn)),
            patch(
                "app.routers.auth.users_repo.get_user_by_id",
                new=AsyncMock(return_value=_user(must_change_password=True)),
            ),
            patch("app.routers.auth.verify_password", return_value=True),
            patch("app.routers.auth.validate_password_policy"),
            patch("app.routers.auth.hash_password", return_value="new-hash"),
            patch(
                "app.routers.auth.destroy_all_for_user", new=AsyncMock(return_value=1)
            ) as revoke_mock,
            patch(
                "app.routers.auth.users_repo.set_password",
                new=AsyncMock(return_value=_user(hashed_password="new-hash")),
            ) as set_password_mock,
            patch(
                "app.routers.auth.create_session",
                new=AsyncMock(return_value="replacement-token"),
            ) as create_session_mock,
            patch("app.routers.auth.auth_audit.record_event", new=AsyncMock()),
        ):
            response = Response()
            result = await change_password(
                payload,
                _request(),
                response,
                _session(),
                "temporary-session-token",
            )

        revoke_mock.assert_awaited_once_with(7)
        set_password_mock.assert_awaited_once_with(
            conn, 7, "new-hash", must_change_password=False
        )
        create_session_mock.assert_awaited_once()
        self.assertTrue(result.ok)
        self.assertIn("eparking_session=replacement-token", response.headers["set-cookie"])
