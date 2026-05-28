-- Migracion 001: tabla champions + FK desde picks.champ_id
-- Aplicar a BDs ya existentes:
--   docker compose exec -T db psql -U loldata -d loldata < db/migrations/001_add_champions.sql
-- (Para BDs nuevas este bloque ya esta integrado en db/schema.sql)

BEGIN;

CREATE TABLE IF NOT EXISTS champions (
    id    INTEGER PRIMARY KEY,          -- Riot champion key (numerico, ej. 266)
    name  VARCHAR(50) NOT NULL UNIQUE,  -- display name: "Lee Sin", "Wukong"
    alias VARCHAR(50) NOT NULL UNIQUE   -- internal name: "LeeSin", "MonkeyKing"
);

-- FK desde picks.champ_id → champions.id
-- La columna picks.champ_id es NOT NULL, asi que la integridad referencial
-- es total: ningun pick puede referenciar un campeon desconocido.
ALTER TABLE picks
    ADD CONSTRAINT picks_champ_id_fkey
    FOREIGN KEY (champ_id) REFERENCES champions(id);

COMMIT;
