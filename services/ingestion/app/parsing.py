"""Isolated, unit-testable parsing helpers.

Scope note (see .claude/skills/paystack-ingestion/SKILL.md "Verified Paystack
API facts"): the ordinal-date format below (`"Jul 1st, 2026 06:37:34 AM"`) is
CSV-export-only. Paystack's live Transaction API returns proper ISO 8601
timestamps -- `parse_ordinal_csv_datetime` must never be called on API
response data, only on rows read from the CSV-backfill path.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

# Matches "Jul 1st, 2026 06:37:34 AM" / "Jul 21st, 2026 ..." / "Jul 22nd, 2026 ..."
# etc. The ordinal suffix (st/nd/rd/th) is stripped before delegating to
# strptime, since Python's stdlib has no directive for ordinal suffixes.
_ORDINAL_SUFFIX_RE = re.compile(r"(\d{1,2})(st|nd|rd|th)\b")

# Format after suffix-stripping: "Jul 1, 2026 06:37:34 AM"
_STRIPPED_FORMAT = "%b %d, %Y %I:%M:%S %p"


def strip_ordinal_suffix(value: str) -> str:
    """Remove day-ordinal suffixes (1st/2nd/3rd/4th...21st/22nd/23rd/31st).

    Deliberately does not validate that the suffix is the *correct* one for
    the given day (e.g. "2st" would still be stripped) -- Paystack's export
    is trusted to produce correct suffixes; this function's only job is
    making the string strptime-parseable.
    """
    return _ORDINAL_SUFFIX_RE.sub(r"\1", value)


def parse_ordinal_csv_datetime(value: str) -> datetime:
    """Parse a Paystack CSV-export timestamp like "Jul 1st, 2026 06:37:34 AM".

    CSV-backfill path ONLY -- never call this on live API responses (those
    are ISO 8601; use `datetime.fromisoformat` after normalizing a trailing
    "Z" instead).

    Returns a timezone-aware UTC datetime. The CSV export does not carry
    explicit timezone information; per project convention (confirmed against
    the sample data alongside the accounts-team Excel report, which uses the
    same wall-clock convention) these timestamps are treated as already
    representing the operational timezone and are stored as UTC without
    shifting the clock value -- i.e. this is a label, not a conversion. If a
    real timezone offset is later confirmed, adjust here in one place.

    Raises ValueError on unparseable input (propagated, not swallowed --
    callers decide whether a single bad row should fail the whole run).
    """
    stripped = strip_ordinal_suffix(value.strip())
    parsed = datetime.strptime(stripped, _STRIPPED_FORMAT)
    return parsed.replace(tzinfo=timezone.utc)


def compute_raw_hash(*parts: object) -> str:
    """Stable hash over the fields that matter for idempotent re-ingestion.

    Scope: only the data columns we'd actually rewrite on a no-op re-poll
    (amount, status, gateway_response, channel, source fields, card fields,
    paid_at, fees) -- NOT bookkeeping columns like ingest_run_id/ingested_at,
    which are expected to change on every run regardless of whether the
    underlying transaction data changed. Comparing this hash against the
    stored `raw_hash` lets the upsert skip rewriting data columns for
    unchanged rows while still keeping bookkeeping current.

    `None` values are normalized to the literal string "\x00NULL\x00" (an
    otherwise-unreachable sentinel) so that None and the empty string never
    collide -- both would otherwise stringify differently but adjacent
    fields could still coincidentally produce the same joined string.
    """
    normalized = [
        "\x00NULL\x00" if part is None else str(part) for part in parts
    ]
    joined = "\x1f".join(normalized)  # unit separator -- avoids field-boundary collisions
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
