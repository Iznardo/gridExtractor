-- SoloQ fase 2: identidad de partidas Riot y limpieza de accounts.
-- Aplicar sobre BDs creadas antes de 2026-06-12; schema.sql ya lo incorpora.
BEGIN;

-- El matchId de Riot lleva prefijo de plataforma (EUW1_..., KR_...);
-- guardarlo completo evita colisiones entre plataformas en el UNIQUE.
ALTER TABLE games ALTER COLUMN riot_api_id TYPE VARCHAR(20)
    USING riot_api_id::VARCHAR;

-- El puuid es la unica identidad de una cuenta; el Riot ID cambia
-- constantemente y no se persiste (decision 2026-06-12).
ALTER TABLE accounts DROP COLUMN riot_id;
ALTER TABLE accounts ALTER COLUMN puuid SET NOT NULL;

COMMIT;
