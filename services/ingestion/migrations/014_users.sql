-- 014_users.sql
-- Sprint 09 (Authentication & Session Security), Phase 1 -- user identity
-- storage. Supersedes the Sprint 7 static-API-key model as the *browser*
-- auth mechanism (the API keys themselves stay, repositioned as service
-- credentials -- see auth.py's Phase 2 rewrite, not touched by this file).
--
-- `role` is TEXT + CHECK, deliberately not a Postgres enum: adding a role
-- value later (e.g. a future AUDITOR role) needs only a one-line ALTER on
-- the CHECK, matching the `011_unmapped_enum_value.sql` precedent of
-- avoiding enum-alteration migrations where a CHECK does the same job more
-- cheaply.
--
-- No seed credentials in this migration -- bootstrap is a CLI command
-- (`services/ingestion/app/create_admin.py`), not a migration-embedded
-- password, per the sprint doc's explicit instruction.

CREATE TABLE IF NOT EXISTS eparking.users (
    id                   BIGSERIAL PRIMARY KEY,
    email                TEXT NOT NULL,               -- normalize to lowercase at write path
    hashed_password      TEXT NOT NULL,                -- argon2id PHC string
    role                 TEXT NOT NULL,                 -- 'ADMIN' | 'VIEWER'
    display_name         TEXT NOT NULL,
    organization         TEXT,                          -- 'AICL' | 'GSDS' -- display/audit only
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
    failed_login_count   INT NOT NULL DEFAULT 0,
    locked_until         TIMESTAMPTZ,
    last_login_at        TIMESTAMPTZ,
    password_changed_at  TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_role_valid CHECK (role IN ('ADMIN', 'VIEWER')),
    CONSTRAINT users_org_valid  CHECK (organization IS NULL OR organization IN ('AICL', 'GSDS'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON eparking.users (lower(email));
CREATE INDEX IF NOT EXISTS ix_users_email_active ON eparking.users (email) WHERE is_active;

CREATE TABLE IF NOT EXISTS eparking.password_reset_tokens (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES eparking.users(id) ON DELETE CASCADE,
    token_hash    TEXT NOT NULL,
    expires_at    TIMESTAMPTZ NOT NULL,
    consumed_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_reset_tokens_user ON eparking.password_reset_tokens (user_id);
