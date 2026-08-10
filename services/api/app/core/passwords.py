"""Password hashing, policy validation, and the common-password blocklist.

Sprint 09 (Authentication & Session Security), Phase 1. Argon2id per the
sprint doc's §3 -- chosen over bcrypt (72-byte input cap, not memory-hard)
and over the sibling platform's legacy PBKDF2 choice (the KB's own recorded
forward-looking recommendation is "Argon2id over PBKDF2", cited in §2 of the
sprint doc). Parameters: OWASP baseline `m=19456` (19 MiB), `t=2`, `p=1`. The
full PHC-format string (embeds params + salt) is stored, so parameters can be
raised later and rehashed transparently on next login via
`needs_rehash`/`check_needs_rehash`.

## Enumeration-safety: `DUMMY_HASH`

Per the sprint doc's §5 login flow: on an unknown-email, inactive, or locked
login attempt, the caller must still run a verify() against *something* so
the response timing matches the "real user, wrong password" path -- otherwise
a timing side-channel reveals which emails exist. `DUMMY_HASH` is computed
ONCE at import time (a real argon2id hash of a random string, same params as
live hashes) specifically so nothing is hashed on the fly per request, which
would itself reintroduce a timing tell (hashing is the expensive part).

## Password policy -- NIST SP 800-63B (length over complexity)

12-160 characters (the sprint's task brief specifies this range; the sprint
doc's own §6 prose says "12 to 128" as a DoS bound -- 160 is used here as the
authoritative upper bound per this phase's explicit instructions, still a
comfortably tight DoS bound on argon2id's fixed-cost input hashing). No
composition rules (no forced uppercase/digit/symbol), no forced rotation, all
printable Unicode allowed. Input is NFKC-normalized before hashing, so
visually-identical Unicode sequences hash identically and a password typed on
different keyboards/IMEs still verifies.

## Common-password blocklist

Offline, no outbound network dependency in the login path (a live HIBP
k-anonymity check is explicitly deferred to a later version per the sprint
doc's "out of scope" table). This module ships a curated list of a few
hundred of the most common real-world passwords as a pragmatic v1
stand-in for a full top-~10k list -- swap `_COMMON_PASSWORDDS_PATH` /
`_CURATED_COMMON_PASSWORDS` for a larger offline corpus later without
changing the call site.
"""

from __future__ import annotations

import secrets
import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError

# OWASP baseline parameters (see module docstring). `hash_len`/`salt_len` use
# the library defaults (32 / 16 bytes) -- only the memory/time/parallelism
# cost knobs are pinned explicitly so a future argon2-cffi version can't
# silently change them under us.
_ARGON2_MEMORY_COST_KIB = 19456  # 19 MiB
_ARGON2_TIME_COST = 2
_ARGON2_PARALLELISM = 1

_hasher = PasswordHasher(
    memory_cost=_ARGON2_MEMORY_COST_KIB,
    time_cost=_ARGON2_TIME_COST,
    parallelism=_ARGON2_PARALLELISM,
)

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 160


def _normalize(password: str) -> str:
    """NFKC-normalize before hashing/verifying, per §6."""
    return unicodedata.normalize("NFKC", password)


def hash_password(password: str) -> str:
    """Return a PHC-format argon2id hash string. Caller is responsible for
    running `validate_password_policy` first if this is a user-supplied
    password (this function itself does not enforce the policy, so it can
    also hash the module's own random `DUMMY_HASH` seed)."""
    return _hasher.hash(_normalize(password))


def verify_password(hashed: str, password: str) -> bool:
    """True on match, False on mismatch or malformed hash. Never raises for
    ordinary mismatch/invalid-hash cases -- callers (including the
    enumeration-safe login path verifying against `DUMMY_HASH`) must be able
    to call this unconditionally without a try/except at every call site."""
    try:
        return _hasher.verify(hashed, _normalize(password))
    except (VerifyMismatchError, VerificationError, InvalidHash):
        return False


def needs_rehash(hashed: str) -> bool:
    """True if `hashed` was produced with weaker-than-current parameters
    (e.g. after `_ARGON2_*` constants above are raised in a future release).
    Login success path: call this, and if True, hash_password + store the
    new hash -- transparent rehash-on-login, no forced reset."""
    try:
        return _hasher.check_needs_rehash(hashed)
    except InvalidHash:
        # Malformed/foreign hash -- treat as needing a rehash rather than
        # raising out of a login success path.
        return True


# --------------------------------------------------------------------------
# DUMMY_HASH -- timing-equalization constant, computed once at import.
# --------------------------------------------------------------------------
# A real argon2id hash of a random (never logged, never reused, discarded
# immediately) string, using the exact same PasswordHasher/params as live
# credentials, so `verify_password(DUMMY_HASH, attempted_password)` costs the
# same CPU time as a genuine wrong-password check against a real user.
DUMMY_HASH: str = hash_password(secrets.token_urlsafe(48))


# --------------------------------------------------------------------------
# Password policy
# --------------------------------------------------------------------------


class PasswordPolicyError(ValueError):
    """Raised by `validate_password_policy` with a human-readable reason."""


def validate_password_policy(password: str) -> None:
    """Raises `PasswordPolicyError` if `password` fails the length bound or
    the common-password blocklist. No composition rules per NIST SP
    800-63B -- do not add uppercase/digit/symbol requirements here."""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at least {PASSWORD_MIN_LENGTH} characters long."
        )
    if len(password) > PASSWORD_MAX_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at most {PASSWORD_MAX_LENGTH} characters long."
        )
    if is_common_password(password):
        raise PasswordPolicyError(
            "This password is too common and easily guessed. Please choose a different one."
        )


def is_common_password(password: str) -> bool:
    """Case-insensitive check against the offline common-password blocklist."""
    return _normalize(password).casefold() in _COMMON_PASSWORDS


# --------------------------------------------------------------------------
# Common-password blocklist -- pragmatic v1 stand-in.
# --------------------------------------------------------------------------
# NOT a full top-~10k corpus (e.g. SecLists' 10k-most-common.txt) -- this is
# a curated few hundred of the most common real-world passwords (annual
# "worst passwords" lists, keyboard-walk patterns, and this project's own
# domain terms) as a pragmatic first pass. Swap in a larger offline list file
# later (e.g. load from a packaged .txt at import time) without changing
# `is_common_password`'s signature or any call site.
_CURATED_COMMON_PASSWORDS_RAW = [
    "123456", "123456789", "12345678", "12345", "1234567", "1234567890",
    "qwerty", "qwerty123", "qwertyuiop", "password", "password1",
    "password123", "passw0rd", "letmein", "welcome", "welcome1",
    "monkey", "dragon", "master", "login", "admin", "administrator",
    "abc123", "abcd1234", "iloveyou", "trustno1", "sunshine", "princess",
    "football", "baseball", "basketball", "soccer", "shadow", "michael",
    "jennifer", "jordan", "superman", "batman", "starwars", "hello",
    "hello123", "freedom", "whatever", "qazwsx", "zaq12wsx", "1q2w3e4r",
    "1qaz2wsx", "asdfghjkl", "asdf1234", "zxcvbnm", "654321", "111111",
    "121212", "000000", "1111111", "11111111", "222222", "333333",
    "444444", "555555", "666666", "777777", "888888", "999999",
    "target123", "changeme", "changeme123", "letmein123", "access",
    "access123", "flower", "flower1", "summer", "summer2024", "winter",
    "spring", "autumn", "hunter", "hunter2", "buster", "soccer1",
    "hockey", "killer", "george", "harley", "ranger", "cookie",
    "mustang", "shadow1", "michelle", "charlie", "andrew", "matthew",
    "abigail", "daniel", "computer", "internet", "yankees", "dallas",
    "cowboys", "jackson", "tigger", "purple", "orange", "banana",
    "chicken", "yellow", "phoenix", "diamond", "silver", "gold",
    "eagle1", "maggie", "peanut", "nicole", "chelsea", "biteme",
    "matrix", "corvette", "firebird", "blahblah", "3rjs1la7qe",
    "test123", "guest", "guest123", "root", "toor", "user",
    "user123", "temp123", "temporary", "default", "public",
    "letmein1", "trustno1!", "password!", "P@ssw0rd", "Password1",
    "Password123", "Passw0rd!", "Qwerty123!", "abcdefgh", "abcdefg",
    "abcabc123", "asdasd123", "121314", "159357", "753951",
    "246810", "192837465", "159753", "987654321", "123123123",
    "aaaaaa", "aaaaaaaa", "bbbbbb", "cccccc", "zzzzzz", "asdf",
    "asdfasdf", "qweasd", "qweasdzxc", "poiuyt", "mnbvcxz",
    "lkjhgfdsa", "iloveyou1", "iloveyou2", "loveyou", "sweetheart",
    "beautiful", "angel", "angel1", "princess1", "sunshine1",
    "baseball1", "football1", "basketball1", "hockey1", "soccer123",
    "welcome123", "letmein12", "opensesame", "sesame", "letmeinnow",
    "newpassword", "newuser", "changeme1", "changepassword",
    "temppass", "temppassword", "12341234", "1234554321",
    "qwerty12345", "1qazxsw2", "zaq1zaq1", "q1w2e3r4",
    "q1w2e3r4t5", "1a2b3c4d", "a1b2c3d4", "p@ssword", "p@ssw0rd",
    "p@$$w0rd", "letmein!", "iloveyou!", "monkey123", "dragon123",
    "master123", "shadow123", "superman1", "batman123", "spiderman",
    "ironman", "thunder", "lightning", "phantom", "warrior",
    "trooper", "cowboy", "cowboy1", "rockstar", "rocket", "rocket1",
    "tennis", "cricket", "cricket1", "swimming", "running",
    "parking", "parking123", "eparking", "paystack", "dashboard",
    "revenue", "occupancy", "traffic123", "vehicle123", "carpark",
    "carpark1", "ticket123", "admin123", "admin1234", "adminadmin",
    "viewer123", "viewer1234", "operator", "operator1", "manager",
    "manager1", "manager123", "supervisor", "director", "employee",
    "employee1", "staff123", "office123", "company123", "business1",
    "welcome2024", "welcome2025", "welcome2026", "spring2024",
    "summer2025", "autumn2024", "winter2025", "january123",
    "february1", "march2024", "april2024", "may2024", "june2024",
    "july2024", "august2024", "september1", "october123",
    "november1", "december1", "monday123", "tuesday1", "wednesday",
    "thursday1", "friday123", "saturday1", "sunday123",
    "nigeria123", "lagos1234", "abuja1234", "naija123", "westafrica",
    "gsds1234", "aicl1234", "shopkeeper", "cabdriver", "dispatch1",
    "trailer123", "porter123",
]
_COMMON_PASSWORDS: frozenset[str] = frozenset(
    unicodedata.normalize("NFKC", p).casefold() for p in _CURATED_COMMON_PASSWORDS_RAW
)
