-- 003_locations_terminals.sql
-- Sprint 2: locations and pos_terminals. Terminal->location mapping is
-- resolved (dropped, not needed) per Sprint 0 overview -- location_id stays
-- nullable/unused indefinitely, no location-mapping admin UI is built
-- around it. Kept cheap because it's trivial to retain.

CREATE TABLE IF NOT EXISTS eparking.locations (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    code        TEXT UNIQUE,
    is_active   BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS eparking.pos_terminals (
    id              BIGSERIAL PRIMARY KEY,
    serial          TEXT NOT NULL UNIQUE,
    label           TEXT,
    location_id     BIGINT REFERENCES eparking.locations (id),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
