-- 003 — Indices para acelerar las queries de la API read-only (api_audit A2).
--
-- La API filtra/joinea por columnas que hoy no estan indexadas:
--   · picks.champ_id  → EXISTS de /games, filtros de /picks, /scouting, /matchups
--   · games.team1_id / team2_id → casi todos los filtros por equipo
--   · games.version / tournament → filtros de parche / torneo
--
-- Aplicar:  docker compose exec -T db psql -U "$PGUSER" -d "$PGDATABASE" < db/migrations/003_api_indexes.sql
-- (o desde DBeaver). Idempotente: IF NOT EXISTS.

BEGIN;

CREATE INDEX IF NOT EXISTS idx_picks_champ_id  ON picks(champ_id);
CREATE INDEX IF NOT EXISTS idx_games_team1_id  ON games(team1_id);
CREATE INDEX IF NOT EXISTS idx_games_team2_id  ON games(team2_id);
CREATE INDEX IF NOT EXISTS idx_games_version   ON games(version);
CREATE INDEX IF NOT EXISTS idx_games_tournament ON games(tournament);

COMMIT;
