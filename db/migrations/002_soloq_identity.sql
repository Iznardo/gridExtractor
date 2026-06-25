-- SoloQ phase 2: Riot match identity and accounts cleanup.
-- Apply to DBs created before 2026-06-12; schema.sql already includes it.
BEGIN;

-- Riot's matchId carries a platform prefix (EUW1_..., KR_...); storing it whole
-- avoids cross-platform collisions in the UNIQUE.
ALTER TABLE games ALTER COLUMN riot_api_id TYPE VARCHAR(20)
    USING riot_api_id::VARCHAR;

-- The puuid is an account's only identity; the Riot ID changes constantly and
-- is not persisted.
ALTER TABLE accounts DROP COLUMN riot_id;
ALTER TABLE accounts ALTER COLUMN puuid SET NOT NULL;

COMMIT;
