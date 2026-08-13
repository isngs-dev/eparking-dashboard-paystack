"""Paystack Transaction API client.

Built to the documented request/response shape from Paystack's OpenAPI spec
(see .claude/skills/paystack-ingestion/SKILL.md "Verified Paystack API
facts"). No live secret key is available as of Sprint 3 -- this client is
exercised by the CSV-backfill acceptance test only, not end-to-end against
the real API. Swapping in a real key later requires no code change, only
`PAYSTACK_SECRET_KEY` being populated in the environment.

Key verified facts baked in here (do not "fix" without re-checking the spec):
- Pagination param is `per_page` (snake_case), NOT `perPage`. Paystack
  silently accepts the wrong name and falls back to its default page size --
  a real and easy-to-miss bug, not a hypothetical one.
- Page until `page >= meta.pageCount`.
- Window/filter off `created_at` via `from`/`to` query params -- `paid_at` is
  null for abandoned/failed transactions and must not be used as the window
  anchor.
- Rate limits are undocumented. Retry/backoff and 429 handling here are
  deliberately defensive/generic rather than tuned to an assumed limit.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from eparking_common.config import get_settings

PAYSTACK_BASE_URL = "https://api.paystack.co"

_DEFAULT_PER_PAGE = 100
_MAX_RETRIES = 5
_BASE_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 30.0

# Statuses Paystack's OpenAPI spec documents as valid transaction statuses.
# `reversed` has not been observed in sample data but must not be assumed
# impossible (see the paystack-ingestion skill's non-negotiables).
KNOWN_TRANSACTION_STATUSES = frozenset({"success", "failed", "abandoned", "reversed"})


class PaystackAPIError(RuntimeError):
    """Raised when the Paystack API returns a non-retryable error."""


@dataclass(frozen=True)
class PaystackPage:
    """One page of the `GET /transaction` response."""

    data: list[dict[str, Any]]
    total: int
    total_volume: int | None
    skipped: int | None
    per_page: int
    page: int
    page_count: int


@dataclass
class PaystackClient:
    """Thin async wrapper around Paystack's Transaction API.

    Not a context manager by requirement -- `aclose()` is explicit so the
    Celery task controls the client's lifetime across a possibly multi-page
    poll.
    """

    secret_key: str = field(default_factory=lambda: get_settings().paystack_secret_key)
    base_url: str = PAYSTACK_BASE_URL
    timeout_seconds: float = 30.0
    _client: httpx.AsyncClient = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.secret_key}",
                "Accept": "application/json",
            },
            timeout=self.timeout_seconds,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "PaystackClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def _request_with_retry(self, params: dict[str, Any]) -> dict[str, Any]:
        """GET /transaction with exponential backoff + defensive 429 handling.

        Rate limits are undocumented (per the skill's verified facts) so we
        don't hardcode an assumed quota -- we just back off exponentially
        with jitter on 429/5xx and honor a `Retry-After` header if Paystack
        sends one.
        """
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = await self._client.get("/transaction", params=params)
            except httpx.TransportError as exc:
                last_exc = exc
                await self._sleep_backoff(attempt)
                continue

            if response.status_code == 429:
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                await self._sleep_backoff(attempt, floor_seconds=retry_after)
                continue

            if response.status_code >= 500:
                last_exc = PaystackAPIError(
                    f"Paystack returned {response.status_code}: {response.text[:500]}"
                )
                await self._sleep_backoff(attempt)
                continue

            if response.status_code >= 400:
                # Non-retryable client error (bad key, bad params, etc).
                raise PaystackAPIError(
                    f"Paystack returned {response.status_code}: {response.text[:500]}"
                )

            return response.json()

        raise PaystackAPIError(
            f"Paystack request failed after {_MAX_RETRIES} attempts"
        ) from last_exc

    @staticmethod
    async def _sleep_backoff(attempt: int, *, floor_seconds: float | None = None) -> None:
        backoff = min(_BASE_BACKOFF_SECONDS * (2**attempt), _MAX_BACKOFF_SECONDS)
        backoff += random.uniform(0, backoff * 0.1)  # jitter
        if floor_seconds is not None:
            backoff = max(backoff, floor_seconds)
        await asyncio.sleep(backoff)

    async def fetch_transactions_page(
        self,
        *,
        window_from: datetime,
        window_to: datetime,
        page: int = 1,
        per_page: int = _DEFAULT_PER_PAGE,
        status: str | None = None,
    ) -> PaystackPage:
        """Fetch one page of `GET /transaction`, windowed off `created_at`.

        NOTE: uses `per_page` (snake_case) deliberately -- see module
        docstring. Using `perPage` is silently accepted by Paystack and
        falls back to the default page size, which would quietly under-page
        large windows.
        """
        params = {
            "per_page": per_page,
            "page": page,
            "from": window_from.isoformat(),
            "to": window_to.isoformat(),
        }
        if status is not None:
            params["status"] = status
        payload = await self._request_with_retry(params)

        if not payload.get("status", False):
            raise PaystackAPIError(f"Paystack API returned status=false: {payload.get('message')}")

        meta = payload.get("meta") or {}
        return PaystackPage(
            data=payload.get("data") or [],
            total=meta.get("total", 0),
            total_volume=meta.get("total_volume"),
            skipped=meta.get("skipped"),
            per_page=meta.get("perPage", per_page),
            page=meta.get("page", page),
            page_count=meta.get("pageCount", page),
        )

    async def iter_all_transactions(
        self,
        *,
        window_from: datetime,
        window_to: datetime,
        per_page: int = _DEFAULT_PER_PAGE,
        status: str | None = None,
    ):
        """Async generator yielding every transaction dict in the window.

        Pages until `page >= pageCount`, per the verified pagination
        contract -- not until an empty page is returned (Paystack's
        `pageCount` is authoritative).
        """
        page = 1
        while True:
            result = await self.fetch_transactions_page(
                window_from=window_from,
                window_to=window_to,
                page=page,
                per_page=per_page,
                status=status,
            )
            for row in result.data:
                yield row

            if result.page >= result.page_count or not result.data:
                break
            page += 1


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
