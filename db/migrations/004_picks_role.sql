-- 004_picks_role.sql — role played IN THAT GAME (per-game).
-- players.role stays the CURRENT roster role; not touched here.
-- Apply: docker compose exec -T db psql -U "$PGUSER" -d "$PGDATABASE" < db/migrations/004_picks_role.sql
BEGIN;

ALTER TABLE picks ADD COLUMN IF NOT EXISTS role VARCHAR(8)
    CHECK (role IN ('TOP','JUNGLE','MID','ADC','SUPPORT'));

-- Backfill SOLOQ: stats->>'team_position' already persists the per-game truth.
UPDATE picks pk
SET role = CASE pk.stats->>'team_position'
             WHEN 'TOP'     THEN 'TOP'
             WHEN 'JUNGLE'  THEN 'JUNGLE'
             WHEN 'MIDDLE'  THEN 'MID'
             WHEN 'BOTTOM'  THEN 'ADC'
             WHEN 'UTILITY' THEN 'SUPPORT'
           END
FROM games g
WHERE g.id = pk.game_id AND g.game_type = 'SOLOQ' AND pk.role IS NULL;

-- Backfill OFFICIAL/SCRIM: picks were inserted in riot_id order 1..10
-- (_gather_participants), so within (game_id, side) the order of picks.id
-- is TOP/JUNGLE/MID/ADC/SUPPORT. Only sides with exactly 5 picks.
WITH ordered AS (
  SELECT pk.id,
         ROW_NUMBER() OVER (PARTITION BY pk.game_id, pk.side ORDER BY pk.id) AS slot,
         COUNT(*)     OVER (PARTITION BY pk.game_id, pk.side)               AS n
  FROM picks pk
  JOIN games g ON g.id = pk.game_id
  WHERE g.game_type != 'SOLOQ'
)
UPDATE picks
SET role = (ARRAY['TOP','JUNGLE','MID','ADC','SUPPORT'])[o.slot]
FROM ordered o
WHERE picks.id = o.id AND o.n = 5 AND picks.role IS NULL;

COMMIT;
