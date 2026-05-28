-- gridExtractor — esquema completo de la base de datos `loldata`.
-- PostgreSQL 16+. Lo aplica automaticamente el init-script del contenedor
-- (docker-compose monta este fichero en /docker-entrypoint-initdb.d/).
-- Referencia: CLAUDE.md §4.

BEGIN;

-- ----------------------------------------------------------------------
-- teams
-- ----------------------------------------------------------------------
CREATE TABLE teams (
    id       SERIAL PRIMARY KEY,
    tag      VARCHAR(8),                   -- nullable: GRID puede no aportar nameShortened
    name     VARCHAR(50) NOT NULL,
    grid_id  BIGINT UNIQUE                 -- nullable hasta que se descubre
);

-- ----------------------------------------------------------------------
-- players  (la persona, no la cuenta)
-- ----------------------------------------------------------------------
CREATE TABLE players (
    id           SERIAL PRIMARY KEY,
    team_id      INTEGER REFERENCES teams(id),
    name         VARCHAR(30) NOT NULL,
    role         VARCHAR(8),                          -- TOP/JUNGLE/MID/ADC/SUPPORT; NULL al crear desde discovery
    starter      BOOLEAN NOT NULL DEFAULT FALSE,      -- el discovery siempre crea con FALSE; el extractor de oficiales lo asciende
    grid_id      BIGINT UNIQUE,
    last_update  TIMESTAMPTZ,                          -- ultima oficial que reconcilio a este jugador (CLAUDE.md §5.5)
    CHECK (role IS NULL OR role IN ('TOP','JUNGLE','MID','ADC','SUPPORT'))
);

-- ----------------------------------------------------------------------
-- champions  (catalogo de campeones de LoL — cargado desde Data Dragon)
-- ----------------------------------------------------------------------
CREATE TABLE champions (
    id    INTEGER PRIMARY KEY,          -- Riot champion key (numerico, ej. 266)
    name  VARCHAR(50) NOT NULL UNIQUE,  -- display name: "Lee Sin", "Wukong"
    alias VARCHAR(50) NOT NULL UNIQUE   -- internal name: "LeeSin", "MonkeyKing"
);

-- ----------------------------------------------------------------------
-- accounts  (cuentas de Riot — se pueblan en una fase posterior)
-- ----------------------------------------------------------------------
CREATE TABLE accounts (
    id         SERIAL PRIMARY KEY,
    riot_id    VARCHAR(100) NOT NULL,
    player_id  INTEGER NOT NULL REFERENCES players(id),
    region     VARCHAR(8) NOT NULL,
    puuid      CHAR(78) UNIQUE
);

-- ----------------------------------------------------------------------
-- drafts  (1-a-1 con games; estructura rigida a proposito, CLAUDE.md §4.2)
-- ----------------------------------------------------------------------
CREATE TABLE drafts (
    id                  SERIAL PRIMARY KEY,
    first_pick_team_id  INTEGER REFERENCES teams(id),
    ban1   INTEGER, ban2  INTEGER, ban3  INTEGER, ban4  INTEGER, ban5  INTEGER,
    ban6   INTEGER, ban7  INTEGER, ban8  INTEGER, ban9  INTEGER, ban10 INTEGER,
    pick1  INTEGER, pick2 INTEGER, pick3 INTEGER, pick4 INTEGER, pick5 INTEGER,
    pick6  INTEGER, pick7 INTEGER, pick8 INTEGER, pick9 INTEGER, pick10 INTEGER
);

-- ----------------------------------------------------------------------
-- games  (una fila = una partida de LoL)
-- ----------------------------------------------------------------------
CREATE TABLE games (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    version         VARCHAR(10),
    game_type       VARCHAR(20) NOT NULL CHECK (game_type IN ('OFFICIAL','SCRIM','SOLOQ')),
    tournament      VARCHAR(50),
    team1_id        INTEGER REFERENCES teams(id),
    team2_id        INTEGER REFERENCES teams(id),
    result          VARCHAR(5) NOT NULL CHECK (result IN ('BLUE','RED','NONE')),
    draft_id        INTEGER UNIQUE REFERENCES drafts(id),  -- 1-a-1 con drafts
    grid_series_id  BIGINT,
    game_number     SMALLINT,
    riot_api_id     BIGINT,
    stats           JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- claves naturales: GRID por (serie, numero); soloq por riot_api_id.
    -- En Postgres los NULL no chocan en UNIQUE, asi que conviven sin choque.
    UNIQUE (grid_series_id, game_number),
    UNIQUE (riot_api_id)
);

-- ----------------------------------------------------------------------
-- picks  (10 filas por partida — una por jugador)
-- ----------------------------------------------------------------------
CREATE TABLE picks (
    id          BIGSERIAL PRIMARY KEY,
    player_id   INTEGER NOT NULL REFERENCES players(id),
    account_id  INTEGER REFERENCES accounts(id),
    game_id     INTEGER NOT NULL REFERENCES games(id),
    champ_id    INTEGER NOT NULL REFERENCES champions(id),
    side        VARCHAR(5) NOT NULL CHECK (side IN ('BLUE','RED')),
    result      BOOLEAN NOT NULL,
    pick_order  INTEGER,
    stats       JSONB
);

-- ----------------------------------------------------------------------
-- Indices auxiliares (la idempotencia ya tiene los UNIQUE arriba)
-- ----------------------------------------------------------------------
CREATE INDEX idx_players_team_id  ON players(team_id);
CREATE INDEX idx_games_date       ON games(date);
CREATE INDEX idx_games_game_type  ON games(game_type);
CREATE INDEX idx_picks_game_id    ON picks(game_id);
CREATE INDEX idx_picks_player_id  ON picks(player_id);

COMMIT;
