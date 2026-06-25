-- Migration 001: champions table + FK from picks.champ_id.
-- Apply to existing DBs:
--   docker compose exec -T db psql -U loldata -d loldata < db/migrations/001_add_champions.sql
-- (For new DBs this is already part of db/schema.sql.)

BEGIN;

CREATE TABLE IF NOT EXISTS champions (
    id    INTEGER PRIMARY KEY,          -- Riot champion key (numeric, e.g. 266)
    name  VARCHAR(50) NOT NULL UNIQUE,  -- display name: "Lee Sin", "Wukong"
    alias VARCHAR(50) NOT NULL UNIQUE   -- internal name: "LeeSin", "MonkeyKing"
);

-- FK from picks.champ_id -> champions.id.
-- picks.champ_id is NOT NULL, so referential integrity is total: no pick can
-- reference an unknown champion.
ALTER TABLE picks
    ADD CONSTRAINT picks_champ_id_fkey
    FOREIGN KEY (champ_id) REFERENCES champions(id);

COMMIT;
