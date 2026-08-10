-- 015_auth_audit_log.sql
-- Sprint 09 (Authentication & Session Security), Phase 1 -- dedicated audit
-- table for login/session/user-management events.
--
-- `run_logs` (pipeline sync bookkeeping: window_from, rows_fetched, etc.) is
-- deliberately NOT reused here -- its schema is shaped for "did we sync
-- Paystack" queries Sprint 8 depends on, and has no columns an auth event
-- needs (actor, outcome, ip, user agent). A new table avoids corrupting that
-- existing query.
--
-- Every row is written by `app/repositories/auth_audit.py`'s `record_event`,
-- which wraps the INSERT in try/except so an audit-table outage can never
-- itself become a denial-of-service against login (see that module).
--
-- `detail` is JSONB holding reason codes / old-new role diffs etc. -- NEVER
-- passwords, session tokens, or reset tokens.

CREATE TABLE IF NOT EXISTS eparking.auth_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    event_type      TEXT NOT NULL,
    actor_user_id   BIGINT REFERENCES eparking.users(id) ON DELETE SET NULL,
    actor_email     TEXT,           -- denormalized; also the only record for unknown-email failures
    target_user_id  BIGINT REFERENCES eparking.users(id) ON DELETE SET NULL,
    ip_address      INET,
    user_agent      TEXT,
    outcome         TEXT NOT NULL,  -- 'SUCCESS' | 'FAILURE'
    detail          JSONB,          -- reason codes, old/new role. NEVER passwords/tokens.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_auth_audit_created_at ON eparking.auth_audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_auth_audit_actor      ON eparking.auth_audit_log (actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_auth_audit_type       ON eparking.auth_audit_log (event_type, created_at DESC);
