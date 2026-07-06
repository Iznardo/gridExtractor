-- gridExtractor — full schema for the `loldata` database.
-- PostgreSQL 16+. Applied automatically by the container init-script
-- (docker-compose mounts this file in /docker-entrypoint-initdb.d/).

BEGIN;

-- ----------------------------------------------------------------------
-- teams
-- ----------------------------------------------------------------------
CREATE TABLE teams (
    id       SERIAL PRIMARY KEY,
    tag      VARCHAR(8),                   -- nullable: GRID may omit nameShortened
    name     VARCHAR(50) NOT NULL,
    grid_id  BIGINT UNIQUE                 -- nullable until discovered
);

-- ----------------------------------------------------------------------
-- players  (the person, not the account)
-- ----------------------------------------------------------------------
CREATE TABLE players (
    id           SERIAL PRIMARY KEY,
    team_id      INTEGER REFERENCES teams(id),
    name         VARCHAR(30) NOT NULL,
    role         VARCHAR(8),                          -- TOP/JUNGLE/MID/ADC/SUPPORT; NULL when created from discovery
    starter      BOOLEAN NOT NULL DEFAULT FALSE,      -- discovery always creates FALSE; the official extractor promotes it
    grid_id      BIGINT UNIQUE,
    last_update  TIMESTAMPTZ,                          -- last official game that reconciled this player
    CHECK (role IS NULL OR role IN ('TOP','JUNGLE','MID','ADC','SUPPORT'))
);

-- ----------------------------------------------------------------------
-- champions  (LoL champion catalog — loaded from Data Dragon)
-- ----------------------------------------------------------------------
CREATE TABLE champions (
    id    INTEGER PRIMARY KEY,          -- Riot champion key (numeric, e.g. 266)
    name  VARCHAR(50) NOT NULL UNIQUE,  -- display name: "Lee Sin", "Wukong"
    alias VARCHAR(50) NOT NULL UNIQUE   -- internal name: "LeeSin", "MonkeyKing"
);

-- ----------------------------------------------------------------------
-- accounts  (each player's Riot accounts — src/riot/accounts_sync.py)
-- The puuid is the only identity: Riot IDs change and are NOT persisted.
-- ----------------------------------------------------------------------
CREATE TABLE accounts (
    id         SERIAL PRIMARY KEY,
    player_id  INTEGER NOT NULL REFERENCES players(id),
    region     VARCHAR(8) NOT NULL,               -- Match-V5 regional cluster (europe/americas/asia/sea)
    puuid      CHAR(78) NOT NULL UNIQUE
);

-- ----------------------------------------------------------------------
-- drafts  (1-to-1 with games; rigid structure on purpose)
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
-- games  (one row = one LoL game)
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
    draft_id        INTEGER UNIQUE REFERENCES drafts(id),  -- 1-to-1 with drafts
    grid_series_id  BIGINT,
    game_number     SMALLINT,
    riot_api_id     VARCHAR(20),   -- full Riot matchId, with platform ("EUW1_7884453182")
    stats           JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Natural keys: GRID by (series, number); soloq by riot_api_id.
    -- In Postgres NULLs do not collide in UNIQUE, so they coexist.
    UNIQUE (grid_series_id, game_number),
    UNIQUE (riot_api_id)
);

-- ----------------------------------------------------------------------
-- picks  (10 rows per game — one per player)
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
    -- Role played IN THIS GAME (players.role = current roster role). Source:
    -- riot_id ordering convention in GRID games, team_position in soloq.
    -- NULL when the source is unreliable (Smite tripwire) or absent.
    role        VARCHAR(8) CHECK (role IN ('TOP','JUNGLE','MID','ADC','SUPPORT')),
    stats       JSONB
);

-- ----------------------------------------------------------------------
-- Auxiliary indexes (idempotency is covered by the UNIQUEs above)
-- ----------------------------------------------------------------------
CREATE INDEX idx_players_team_id  ON players(team_id);
CREATE INDEX idx_games_date       ON games(date);
CREATE INDEX idx_games_game_type  ON games(game_type);
CREATE INDEX idx_picks_game_id    ON picks(game_id);
CREATE INDEX idx_picks_player_id  ON picks(player_id);

-- Indexes for the read-only API (= migration 003; here for fresh installs).
CREATE INDEX idx_picks_champ_id   ON picks(champ_id);
CREATE INDEX idx_games_team1_id   ON games(team1_id);
CREATE INDEX idx_games_team2_id   ON games(team2_id);
CREATE INDEX idx_games_version    ON games(version);
CREATE INDEX idx_games_tournament ON games(tournament);

COMMIT;
