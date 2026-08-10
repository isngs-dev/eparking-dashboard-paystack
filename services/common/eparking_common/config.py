"""Application settings.

Frozen `Settings` object loaded once from environment variables (+ optional
`.env` file), following the sibling platform's convention documented in
references/knowledge-base/01_SYSTEM_DESIGN.md and 02_BACKEND_PHILOSOPHY.md:

- Dev-safe defaults so the app runs locally with zero configuration.
- A fail-fast production validation pass that rejects dev-default secrets,
  short JWT keys, identical JWT/encryption secrets, etc. before the app
  serves traffic.

This project is single-tenant: unlike the sibling platform, there is no
tenant_id/multi-tenancy machinery here by design (see project CLAUDE.md).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel dev-default values. Production startup must reject these verbatim,
# not just "anything short" -- someone could paste a 40-char string that is
# still a well-known placeholder.
_DEV_DEFAULT_JWT_SECRET = "dev-only-jwt-secret-do-not-use-in-production"
_DEV_DEFAULT_ENCRYPTION_KEY = "dev-only-encryption-key-do-not-use-in-prod"
_DEV_DEFAULT_PAYSTACK_KEY = "sk_test_placeholder_replace_me"

_MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Immutable app configuration. Construct once via `get_settings()`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- Environment -----------------------------------------------------
    app_env: Literal["development", "staging", "production"] = "development"

    # --- Postgres ----------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "eparking"
    postgres_user: str = "eparking"
    postgres_password: str = "eparking_dev_password"

    # --- Redis ---------------------------------------------------------------
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    # --- Paystack ------------------------------------------------------------
    paystack_secret_key: str = _DEV_DEFAULT_PAYSTACK_KEY

    # --- Security --------------------------------------------------------
    jwt_secret: str = _DEV_DEFAULT_JWT_SECRET
    secret_encryption_key: str = _DEV_DEFAULT_ENCRYPTION_KEY
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60

    # --- Auth (Sprint 7: two static per-role API keys, see
    # services/api/app/core/auth.py for the "why static keys, not JWT"
    # reasoning) -- dev-safe defaults so local curl testing needs no setup;
    # production should override both with distinct, random, >=32-char
    # values (see the production validation gate below).
    admin_api_key: str = "dev-admin-key-do-not-use-in-production"
    viewer_api_key: str = "dev-viewer-key-do-not-use-in-production"

    # --- Sessions & login rate limiting (Sprint 9: session auth) -------------
    # Opaque server-side sessions in Redis, not JWT -- see
    # `services/api/app/core/sessions.py`. Dev-safe defaults below;
    # `session_cookie_secure` is production-gated (must be True) below.
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    session_cookie_name: str = "eparking_session"
    session_cookie_secure: bool = False
    login_rate_limit_per_minute: int = 10
    login_max_failed_attempts: int = 5
    login_lockout_minutes: int = 15

    # --- API -----------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    # --- Celery ----------------------------------------------------------
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def asyncpg_dsn(self) -> str:
        # Same shape as database_url; kept separate because asyncpg and
        # SQLAlchemy-style URLs have historically diverged on scheme. We use
        # asyncpg directly (no ORM) per 02_BACKEND_PHILOSOPHY.md.
        return self.database_url

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def resolved_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def resolved_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @field_validator("jwt_secret", "secret_encryption_key")
    @classmethod
    def _no_blank_secrets(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("secret values must not be blank")
        return value

    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        """Fail-fast production gate.

        Not exercised locally (app_env defaults to "development"), but
        scaffolded now per the Sprint 1 spec so it isn't bolted on later.
        Mirrors 02_BACKEND_PHILOSOPHY.md: reject dev-default JWT_SECRET /
        SECRET_ENCRYPTION_KEY, reject secrets shorter than 32 chars, reject
        identical JWT/encryption secrets, reject a dev-default Paystack key.
        """
        if self.app_env != "production":
            return self

        errors: list[str] = []

        if self.jwt_secret == _DEV_DEFAULT_JWT_SECRET:
            errors.append("JWT_SECRET is still set to its development default")
        if len(self.jwt_secret) < _MIN_SECRET_LENGTH:
            errors.append(
                f"JWT_SECRET must be at least {_MIN_SECRET_LENGTH} characters in production"
            )

        if self.secret_encryption_key == _DEV_DEFAULT_ENCRYPTION_KEY:
            errors.append(
                "SECRET_ENCRYPTION_KEY is still set to its development default"
            )
        if len(self.secret_encryption_key) < _MIN_SECRET_LENGTH:
            errors.append(
                f"SECRET_ENCRYPTION_KEY must be at least {_MIN_SECRET_LENGTH} "
                "characters in production"
            )

        if self.jwt_secret == self.secret_encryption_key:
            errors.append(
                "JWT_SECRET and SECRET_ENCRYPTION_KEY must not be identical"
            )

        if self.paystack_secret_key == _DEV_DEFAULT_PAYSTACK_KEY:
            errors.append(
                "PAYSTACK_SECRET_KEY is still set to its placeholder default"
            )
        if not self.paystack_secret_key.startswith("sk_"):
            errors.append(
                "PAYSTACK_SECRET_KEY does not look like a Paystack secret key "
                "(expected it to start with 'sk_')"
            )

        if self.postgres_password == "eparking_dev_password":
            errors.append("POSTGRES_PASSWORD is still set to its development default")

        if self.admin_api_key == "dev-admin-key-do-not-use-in-production":
            errors.append("ADMIN_API_KEY is still set to its development default")
        if self.viewer_api_key == "dev-viewer-key-do-not-use-in-production":
            errors.append("VIEWER_API_KEY is still set to its development default")
        if self.admin_api_key == self.viewer_api_key:
            errors.append("ADMIN_API_KEY and VIEWER_API_KEY must not be identical")

        if not self.session_cookie_secure:
            errors.append(
                "SESSION_COOKIE_SECURE must be true in production "
                "(the session cookie must be Secure-flagged over HTTPS)"
            )

        cors_origins_lower = self.cors_origins.lower()
        if "localhost" in cors_origins_lower:
            errors.append("CORS_ORIGINS must not contain 'localhost' in production")
        if "*" in self.cors_origins:
            errors.append("CORS_ORIGINS must not contain '*' in production")

        if errors:
            joined = "; ".join(errors)
            raise ValueError(f"Refusing to start in production: {joined}")

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once and cache. Settings itself is frozen/immutable."""
    return Settings()
