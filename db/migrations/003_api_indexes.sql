-- 003 — Indexes to speed up the read-only API queries.
--
-- The API filters/joins on columns that were not indexed:
--   - picks.champ_id  -> /games EXISTS, /picks, /scouting, /matchups filters
--   - games.team1_id / team2_id -> almost every team filter
--   - games.version / tournament -> patch / tournament filters
--
-- Apply:  docker compose exec -T db psql -U "$PGUSER" -d "$PGDATABASE" < db/migrations/003_api_indexes.sql
-- (or from DBeaver). Idempotent: IF NOT EXISTS.

BEGIN;

CREATE INDEX IF NOT EXISTS idx_picks_champ_id  ON picks(champ_id);
CREATE INDEX IF NOT EXISTS idx_games_team1_id  ON games(team1_id);
CREATE INDEX IF NOT EXISTS idx_games_team2_id  ON games(team2_id);
CREATE INDEX IF NOT EXISTS idx_games_version   ON games(version);
CREATE INDEX IF NOT EXISTS idx_games_tournament ON games(tournament);

COMMIT;
