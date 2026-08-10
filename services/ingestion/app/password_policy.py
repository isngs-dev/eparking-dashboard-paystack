"""Argon2id hashing + password policy, duplicated (deliberately) from
`services/api/app/core/passwords.py` for use by the bootstrap CLI
(`app/create_admin.py`).

## Why duplicated, not imported

`services/ingestion` and `services/api` are built as separate Docker images
(see both services' Dockerfiles: each `COPY`s only its own `services/<name>`
directory plus `services/common`) -- there is no cross-service import path
today, and this project deliberately doesn't share a package between the two
beyond `eparking_common`. Introducing one just for this CLI would be a much
larger structural change than Phase 1 calls for. This file is kept in exact
parameter/behavior lockstep with `services/api/app/core/passwords.py` --
same argon2id params (`m=19456, t=2, p=1`), same 12-160 char policy, same
NFKC-normalization -- so a password created by this CLI verifies identically
under the API's `passwords.py` at login. If the two ever drift, `passwords.py`
is the source of truth; update this file to match.

This module intentionally does NOT include `DUMMY_HASH` (no login/timing
concern in an offline CLI) or the full common-password blocklist duplication
concern -- it reuses the *same* curated list content, kept in sync manually.
"""

from __future__ import annotations

import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError

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
    return unicodedata.normalize("NFKC", password)


def hash_password(password: str) -> str:
    return _hasher.hash(_normalize(password))


def verify_password(hashed: str, password: str) -> bool:
    try:
        return _hasher.verify(hashed, _normalize(password))
    except (VerifyMismatchError, VerificationError, InvalidHash):
        return False


class PasswordPolicyError(ValueError):
    pass


def validate_password_policy(password: str) -> None:
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
    return _normalize(password).casefold() in _COMMON_PASSWORDS


# Kept in sync with services/api/app/core/passwords.py's
# `_CURATED_COMMON_PASSWORDS_RAW` -- see that module's docstring for the
# "pragmatic v1 stand-in for a full top-~10k list" rationale.
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
