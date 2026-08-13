from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from app.routers.admin import (
    AdminPasswordUpdateRequest,
    UserCreateRequest,
    create_user,
    update_user_password,
)


class _AcquireContext:
    def __init__(self, conn: object) -> None:
        self.conn = conn

    async def __aenter__(self) -> object:
        return self.conn

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Pool:
    def __init__(self, conn: object) -> None:
        self.conn = conn

    def acquire(self) -> _AcquireContext:
        return _AcquireContext(self.conn)


class _Connection:
    def transaction(self) -> _AcquireContext:
        return _AcquireContext(self)


def _request() -> Request:
    request = Request({"type": "http", "method": "POST", "path": "/admin/users"})
    request.state.session = SimpleNamespace(user_id=1, email="admin@example.com")
    return request


class AdminPasswordManagementTests(IsolatedAsyncioTestCase):
    async def test_create_user_uses_admin_password_without_forcing_change(self) -> None:
        conn = _Connection()
        created = {
            "id": 9,
            "email": "viewer@example.com",
            "role": "VIEWER",
            "display_name": "Viewer",
            "organization": None,
            "must_change_password": False,
            "hashed_password": "not-public",
        }
        payload = UserCreateRequest(
            email="viewer@example.com",
            display_name="Viewer",
            role="VIEWER",
            organization=None,
            password="A secure unique passphrase 2026",
        )

        with (
            patch("app.routers.admin.get_pool", return_value=_Pool(conn)),
            patch(
                "app.routers.admin.users_repo.get_user_by_email",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.routers.admin.users_repo.create_user",
                new=AsyncMock(return_value=created),
            ) as create_mock,
            patch("app.routers.admin.auth_audit.record_event", new=AsyncMock()),
        ):
            response = await create_user(payload, _request(), "ADMIN")

        create_mock.assert_awaited_once_with(
            conn,
            email="viewer@example.com",
            password="A secure unique passphrase 2026",
            role="VIEWER",
            display_name="Viewer",
            organization=None,
            must_change_password=False,
        )
        self.assertFalse(response.user["must_change_password"])
        self.assertFalse(hasattr(response, "initial_password"))

    async def test_create_user_rejects_password_below_policy(self) -> None:
        payload = UserCreateRequest(
            email="viewer@example.com",
            display_name="Viewer",
            role="VIEWER",
            password="short",
        )

        with self.assertRaises(HTTPException) as raised:
            await create_user(payload, _request(), "ADMIN")

        self.assertEqual(raised.exception.status_code, 422)

    async def test_admin_password_update_hashes_and_revokes_sessions(self) -> None:
        conn = _Connection()
        existing = {
            "id": 9,
            "email": "viewer@example.com",
            "role": "VIEWER",
            "display_name": "Viewer",
            "organization": None,
            "is_active": True,
            "must_change_password": False,
            "hashed_password": "old-hash",
        }
        updated = {**existing, "hashed_password": "new-hash"}
        payload = AdminPasswordUpdateRequest(new_password="Another secure passphrase 2026")

        with (
            patch("app.routers.admin.get_pool", return_value=_Pool(conn)),
            patch(
                "app.routers.admin.users_repo.get_user_by_id",
                new=AsyncMock(return_value=existing),
            ),
            patch("app.routers.admin.hash_password", return_value="new-hash") as hash_mock,
            patch(
                "app.routers.admin.users_repo.set_password",
                new=AsyncMock(return_value=updated),
            ) as set_password_mock,
            patch(
                "app.routers.admin.destroy_all_for_user", new=AsyncMock(return_value=2)
            ) as revoke_mock,
            patch("app.routers.admin.auth_audit.record_event", new=AsyncMock()) as audit_mock,
        ):
            response = await update_user_password(9, payload, _request(), "ADMIN")

        hash_mock.assert_called_once_with("Another secure passphrase 2026")
        set_password_mock.assert_awaited_once_with(
            conn, 9, "new-hash", must_change_password=False
        )
        revoke_mock.assert_awaited_once_with(9)
        self.assertEqual(response.user["id"], 9)
        self.assertNotIn("hashed_password", response.user)
        audit_mock.assert_awaited_once()

    async def test_admin_password_update_does_not_change_password_if_revocation_fails(self) -> None:
        conn = _Connection()
        existing = {
            "id": 9,
            "email": "viewer@example.com",
            "role": "VIEWER",
            "display_name": "Viewer",
            "organization": None,
            "is_active": True,
            "must_change_password": False,
            "hashed_password": "old-hash",
        }
        payload = AdminPasswordUpdateRequest(new_password="Another secure passphrase 2026")

        with (
            patch("app.routers.admin.get_pool", return_value=_Pool(conn)),
            patch(
                "app.routers.admin.users_repo.get_user_by_id",
                new=AsyncMock(return_value=existing),
            ),
            patch("app.routers.admin.hash_password", return_value="new-hash"),
            patch(
                "app.routers.admin.users_repo.set_password", new=AsyncMock()
            ) as set_password_mock,
            patch(
                "app.routers.admin.destroy_all_for_user",
                new=AsyncMock(side_effect=RuntimeError("Redis unavailable")),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Redis unavailable"):
                await update_user_password(9, payload, _request(), "ADMIN")

        set_password_mock.assert_not_awaited()
