# gridExtractor

A workflow for extracting League of Legends competitive match data from the
[GRID.gg](https://grid.gg) API into a queryable PostgreSQL database.

It is built on top of [`grid-minion`](https://pypi.org/project/grid-minion/),
an unofficial Python client for GRID. `grid-minion` solves the heavy lifting
(downloading raw events, reconstructing drafts and stats from livestats
streams, handling remakes, etc.). This project is everything around it:
the orchestration scripts, the database schema, and the glue that wires them
together so the whole pipeline runs as a single piece.

The end goal is to keep a clean, incrementally-fed, queryable repository of
LoL match data — drafts, picks, results, objectives, wards, post-game stats
— that you can plug into analysis, dashboards, or models.

## Table of contents

- [Project status](#project-status)
- [How it works](#how-it-works)
- [Database schema](#database-schema)
- [Requirements](#requirements)
- [Setup](#setup)
- [Usage](#usage)
- [Querying the data](#querying-the-data)
- [Automating extractions (cron)](#automating-extractions-cron)
- [Idempotency and reprocessing](#idempotency-and-reprocessing)
- [Known limitations](#known-limitations)
- [Project layout](#project-layout)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Project status

| Stage | Status |
|---|---|
| Database schema (`loldata`, PostgreSQL 16) | Implemented |
| Player/team discovery from GRID tournaments | Implemented |
| Official match extraction (with roster reconciliation) | Implemented |
| Scrim extraction (with auto-discovery + warnings) | Implemented |
| SoloQ extraction (via Riot API, not via GRID) | Implemented |
| Riot `accounts` table population | Implemented (`accounts_sync`) |
| Per-player builds for officials/scrims (runes, items, skills) | Implemented (grid-minion v0.2.0) |
| Read-only query API (FastAPI) | Implemented (`src/api/`) |

The pipeline has been validated against real data from the LCK, LEC and LES.
All four data sources (discovery, officials, scrims, SoloQ) are in place, and a
read-only API over the same database is up (see §6). The next milestone is the
front-end on top of that API.

There is one known data shape that the scrim extractor cannot currently
recover (matches played but with no draft events emitted by GRID). See
[Known limitations](#known-limitations).

## How it works

The project is structured around three sources of match data that share the
same `games` table, differentiated by the `game_type` column:

| Source | `game_type` | Pipeline |
|---|---|---|
| Official tournament matches | `OFFICIAL` | `grid-minion`, filtered by tournaments listed in `config/tournaments.yaml`. Reconciles the players' current team/role/starter status. |
| Scrims | `SCRIM` | `grid-minion`, no tournament filter — every `PUBLISHED` scrim visible to your GRID account. Does **not** reconcile roster (scrim data is too noisy). |
| SoloQ | `SOLOQ` | Riot API directly (queue 420). PUUID is the account identity; one row per tracked account present in the game. |

The end-to-end flow for a GRID-sourced run is:

```
config/tournaments.yaml       (only for officials)
        │
        ▼
GRID GraphQL: allSeries  ──► nodes (series metadata)
        │
        ▼
For each series not yet fully in DB:
    GRID REST: download raw events bundle
    grid-minion.split_grid_series()  ──► one event list per game
        │
        ▼  per game
    Observers: TeamsObserver, DraftObserver,
               PostGameObserver, ObjectiveKilledObserver, WardsObserver
        │
        ▼
    Auto-discovery: ensure_team / ensure_player by grid_id
    Officials only: reconcile_player_roster (team/role/starter)
        │
        ▼
    INSERT drafts → INSERT games → INSERT picks  (idempotent)
```

Three rules are enforced everywhere:

1. **Idempotency.** Re-running an extractor never reprocesses a match that's
   already in the database; the `ON CONFLICT (grid_series_id, game_number)`
   key (or `riot_api_id` for SoloQ) absorbs duplicates. Series already
   complete in the DB are skipped *before* downloading their events.
2. **Cosmetic vs. positional data.** Names, tags, etc. are written **once**
   on discovery and never overwritten. Positional facts (team, role,
   starter) are only updated from **official** matches, in chronological
   order, protected against out-of-order runs by `players.last_update`.
3. **Match-level granularity.** A GRID *series* is a Bo1/Bo3/Bo5; a *game* is
   one match within a series. The schema and the extractors both work at
   the game level.

## Database schema

The database is called `loldata`. The complete schema is in
[`db/schema.sql`](db/schema.sql) and is automatically applied the first time
the Postgres container boots (via `docker-entrypoint-initdb.d`).

### Tables

- **`teams`** — one row per team. `grid_id` is the join key with GRID.
- **`players`** — one row per *person* (not per Riot account). `team_id`,
  `role` and `starter` are reconciled from official matches.
- **`accounts`** — one row per Riot account belonging to a player. Populated
  from `config/soloq_accounts.yaml` via `src/riot/accounts_sync.py`. The
  `puuid` is the account's only identity (Riot IDs change and are not stored).
- **`champions`** — Riot Data Dragon catalog (id, name, alias). Bootstrapped
  automatically on the first extractor run.
- **`games`** — one row per game. The `stats` JSONB column holds the post-game
  meta, objectives and wards exactly as `grid-minion` returns them.
- **`drafts`** — flat layout of the 20 bans+picks of a game (10 bans, 10
  picks), in draft order. Linked 1-to-1 with `games`.
- **`picks`** — one row per (player, game). 10 per game. Per-player stats
  (KDA, gold, CS, damage, etc.) live in the JSONB `stats` column.

### Natural keys

- `games (grid_series_id, game_number)` — identity for any GRID-sourced
  game (officials or scrims). One series produces 1–5 games.
- `games (riot_api_id)` — identity for SoloQ games. Postgres treats `NULL`s
  as distinct in `UNIQUE` constraints, so the two keys coexist without
  conflict.

### `stats` JSONB shape

The `games.stats` column contains:

```json
{
  "meta":       { "winner": "BLUE", "version": "14.23", ... },
  "objectives": { ... ObjectiveKilledObserver output ... },
  "wards":      [ ... WardsObserver output ... ]
}
```

The `picks.stats` column contains per-player aggregates plus the build. For
GRID-sourced games (officials/scrims), `runes`/`final_items` come from the Riot
summary and `skill_order`/`build_path` from the Riot livestats (grid-minion
v0.2.0); any of them may be `null` when the source feed is missing/partial:

```json
{ "kills": 4, "deaths": 2, "assists": 8, "gold": 13420,
  "cs": 256, "damage_dealt": 18900, "kda_str": "4/2/8",
  "runes": { "primary_style": 8200, "primary": [8229, 8275],
             "sub_style": 8400, "sub": [8473, 8242],
             "stat_perks": [5008, 5008, 5011] },
  "final_items": [3047, 3157, 6653, 4645, 3363],
  "skill_order": "QWEQQRQEQEREEWWRWW",
  "build_path": [{ "ts_s": 3, "action": "BUY", "item_id": 1056 }, ...] }
```

SoloQ rows share these build keys (same contract) and add a few that only the
Riot API exposes: `champ_level`, `vision_score`, `team_position`,
`summoner_spells`. The GRID and SoloQ shapes mirror what `grid-minion` and the
Riot API produce respectively; refer to their docs when consuming them.

## Requirements

- **Docker** and **Docker Compose** (for running the PostgreSQL container).
  PostgreSQL 16 is used.
- **Python 3.10+** with `pip` and the ability to create a virtualenv.
- **A GRID.gg API key** with access to the tournaments and/or scrims you
  want to ingest.
- Outbound HTTPS to `api.grid.gg` and `ddragon.leagueoflegends.com`.

## Setup

```bash
# 1. Clone and enter the project
git clone <repo-url> gridExtractor
cd gridExtractor

# 2. Create a virtualenv and install Python dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Or, for a reproducible install with the exact versions used to validate
# the pipeline: `pip install -r requirements.lock`

# 3. Configure credentials
cp .env.example .env
# Edit .env and fill in:
#   GRID_API_KEY  (your GRID.gg key)
#   PGPASSWORD    (any password — used by both the container and Python)
# The other PG* variables have safe defaults.

# 4. Start the containers (PostgreSQL + the read-only API)
docker compose up -d
# The first run also builds the API image. The DB's first boot reads
# db/schema.sql automatically (via the /docker-entrypoint-initdb.d mount);
# after that, the volume in ./postgres_data/ persists the data. The API is
# then reachable at http://localhost:${API_PORT:-8000} (see §6).

# 5. Configure the tournaments to track (officials only)
$EDITOR config/tournaments.yaml
# Add the tournament names exactly as they appear in GRID, one per line.
# Names are resolved by `contains` and then matched exactly client-side;
# 0 or >1 matches are skipped with a warning.
```

That's all. The `champions` table is populated automatically the first
time you run an extractor.

### Verifying the setup

```bash
# Should print "loldata=#" prompt and exit cleanly
docker compose exec -T db psql -U "$PGUSER" -d "$PGDATABASE" -c '\dt'
```

You should see the seven tables listed (`teams`, `players`, `accounts`,
`champions`, `games`, `drafts`, `picks`).

## Usage

All scripts are runnable as Python modules from the project root. They each
load `.env` themselves; you don't need to `source` it.

### 1. Discovery — seed teams and players

```bash
python -m src.discovery.run
```

For every tournament listed in `config/tournaments.yaml`, this:

1. Resolves the tournament ID via GRID GraphQL.
2. Paginates `allSeries` (filtered to `SeriesType = ESPORTS`) to collect
   participating teams.
3. For each unique team, fetches its full roster (titulares + suplentes)
   via the `players(filter: { teamIdFilter })` query.
4. Inserts new rows into `teams` and `players` only — never updates
   existing rows.

Run it before the first official extraction, before a new split, or any
time you suspect new teams/players appeared. It is cheap and idempotent.

**Recommendation:** if a scrim run starts creating teams/players you don't
recognise (it logs WARNING on each creation), run discovery for the
relevant tournament first — that way the scrim auto-discovery picks up
the proper metadata instead of creating placeholders.

### 2. Official extraction

```bash
# Full historical pass for the tournaments in tournaments.yaml
python -m src.extraction.run

# Or only series scheduled from a given date onward
python -m src.extraction.run --since 2026-01-01
```

What it does, per series in chronological order:

- Skips series whose games are all already in the DB (without downloading
  events).
- Downloads the raw event bundle from GRID REST.
- For each game in the series, runs the `grid-minion` observers and:
  - Auto-discovers any team or player missing from the catalog.
  - **Reconciles** the player's roster fields (team, role, starter,
    last_update) from this match, but only if the match is newer than
    what's already recorded.
  - Inserts the draft, the game, and the 10 picks atomically.

### 3. Scrim extraction

```bash
python -m src.extraction.scrims_run [--since 2026-01-01]
```

What's different from officials:

- No tournament filter. The script pulls **every** `PUBLISHED` series of
  type `SCRIM` visible to your GRID account, in chronological order.
- `tournament` is set to the literal string `'SCRIM'` for every row.
- Auto-discovery still creates missing teams and players, but emits a
  `WARNING` log line on every creation. Use those warnings to audit the
  resulting rows manually (scrim data is noisy — typos in names, masked
  team names, fill players, etc. are common).
- **No roster reconciliation.** A player playing fill in a scrim should
  not retroactively be marked as that team's starter in the database.
- Mid-game feed invalidations (technical reconnections, not real remakes)
  no longer drop the draft: grid-minion v0.2.0 ignores any
  `grid-invalidated-series` that arrives after the game has started, and
  rescues side-swaps internally. The old `_rescue_from_history` workaround
  was removed.

### 4. Manually refreshing the champions table

The catalog is bootstrapped automatically when empty, but you can force
a refresh if a new patch lands:

```bash
python -m src.common.champions
```

It re-fetches the latest version from Riot Data Dragon and inserts any
new champion IDs. Existing rows are not touched.

### 5. SoloQ extraction (Riot API)

SoloQ does not use GRID. First, list the accounts to track in
`config/soloq_accounts.yaml` (each entry binds a Riot ID to an existing
`players` row by exact name) and sync them into the `accounts` table:

```bash
python -m src.riot.accounts_sync
```

Only the `puuid` is stored as the account identity (Riot IDs change and are
not persisted). To resolve a Riot ID to its PUUID/region ad hoc:

```bash
python -m src.riot.resolve_run "Name#TAG"
```

Then extract ranked solo games (queue 420) and persist them:

```bash
python -m src.extraction.soloq_run --since 2026-06-01 [--limit 50]
```

It filters match IDs against the DB before downloading (idempotency by
`riot_api_id`), skips remakes, and writes one `picks` row per tracked account
present. `drafts` stays empty for SoloQ (Riot exposes no pick sequence; bans
are simultaneous and kept in `games.stats`). Requires a `RIOT_API_KEY` in
`.env`.

## Querying the data

Connect with `psql`, [DBeaver](https://dbeaver.io), or any Postgres client
using the credentials in `.env`.

```bash
docker compose exec -it db psql -U loldata -d loldata
```

A few example queries:

```sql
-- Total games per source
SELECT game_type, count(*) FROM games GROUP BY game_type ORDER BY 1;

-- Win rate of a team in officials this split
SELECT
  t.name,
  count(*) FILTER (WHERE
    (g.team1_id = t.id AND g.result = 'BLUE') OR
    (g.team2_id = t.id AND g.result = 'RED')
  ) AS wins,
  count(*) AS games
FROM games g
JOIN teams t ON t.id IN (g.team1_id, g.team2_id)
WHERE g.game_type = 'OFFICIAL'
  AND g.tournament = 'LEC - Spring 2026'
GROUP BY t.name
ORDER BY wins DESC;

-- Most-banned champion in officials, last 30 days
SELECT c.name, count(*) AS bans
FROM games g
JOIN drafts d  ON d.id = g.draft_id
JOIN champions c ON c.id IN
     (d.ban1,d.ban2,d.ban3,d.ban4,d.ban5,
      d.ban6,d.ban7,d.ban8,d.ban9,d.ban10)
WHERE g.game_type = 'OFFICIAL'
  AND g.date >= current_date - INTERVAL '30 days'
GROUP BY c.name
ORDER BY bans DESC
LIMIT 20;

-- Current starting roster of a team
SELECT role, name
FROM players
WHERE team_id = (SELECT id FROM teams WHERE name = 'G2 Esports')
  AND starter = TRUE
ORDER BY array_position(
  ARRAY['TOP','JUNGLE','MID','ADC','SUPPORT']::text[], role
);
```

## The query API (FastAPI)

A read-only HTTP API over the same `loldata` database lives in `src/api/`. It is
SQL-only (no ORM), reuses the DB layer, and is meant for a front-end (and ad-hoc
use).

The recommended way to run it is via Docker Compose: the `api` service starts
alongside the `db` service (it waits for the DB healthcheck), so a single
command brings both up — no need to launch `uvicorn` by hand:

```bash
docker compose up -d        # starts db + api
docker compose up -d --build api   # rebuild after changing dependencies
```

`src/` is mounted into the container with `--reload`, so editing API code
reloads it live without rebuilding. The API is published on `API_PORT` (default
`8000`). To run it outside Docker instead (e.g. quick local debugging):

```bash
uvicorn src.api.main:app --reload
```

Interactive docs at `http://localhost:8000/docs`. All query filters are
**id-based** (resolve champion/team names to ids via the catalog endpoints
first); responses include both the id and the resolved name.

| Endpoint | Purpose |
|---|---|
| `GET /champions`, `/teams`, `/players?team_id=&role=` | Catalog (populate filters, resolve name→id). |
| `GET /drafts` | Drafts (officials/scrims). Filters: `team_id, rival_id, patch, pick_phase(first\|second), champ_id, game_type`. Exposes both axes: `team1`=BLUE/`team2`=RED **and** `first_pick_team` (decoupled since 2026). |
| `GET /scouting/champion-pool?team_id=` | Per-player champion pool split by medium (`by_medium`: official/scrim/soloq). Attribution via `players.team_id`. |
| `GET /games` | Game search: `team_id, patch, game_type, champ_id, champ_id2+opposing` (matchup on opposite sides), `date_from/date_to`. Returns side compositions (`blue_champions`/`red_champions`). |
| `GET /picks` | Raw per-player picks (drill-down); `stats` JSONB as stored. |

CORS is open to `localhost` and there is no auth (local use). Read-only: give it
a Postgres user with `SELECT` only if you expose it.

## Automating extractions (cron)

The recommended cadence depends on how fast you need fresh data:

- **Officials:** once a day after the typical match window in your region
  works well — match data usually lands in GRID within a few hours of the
  game ending.
- **Scrims:** once a day too; scrims are reported with delay and there's
  rarely a reason to poll more often.

A reasonable `crontab` (run `crontab -e`):

```cron
# Common: project paths and PATH
PROJECT=/home/youruser/gridExtractor
PYTHON=/home/youruser/gridExtractor/.venv/bin/python
LOGDIR=/home/youruser/gridExtractor/logs
PATH=/usr/local/bin:/usr/bin:/bin

# 04:00 every day — official matches, only the last 7 days of series
0 4 * * *  cd "$PROJECT" && $PYTHON -m src.extraction.run --since "$(date -u -d '7 days ago' +\%Y-\%m-\%d)" >> "$LOGDIR/official.log" 2>&1

# 04:15 every day — scrims, only the last 7 days
15 4 * * *  cd "$PROJECT" && $PYTHON -m src.extraction.scrims_run --since "$(date -u -d '7 days ago' +\%Y-\%m-\%d)" >> "$LOGDIR/scrims.log" 2>&1

# Sundays 03:30 — refresh discovery (catches new players/subs)
30 3 * * 0  cd "$PROJECT" && $PYTHON -m src.discovery.run >> "$LOGDIR/discovery.log" 2>&1
```

Notes:

- The `--since` window is a defensive filter, not a correctness
  requirement: idempotency means re-running without `--since` is also
  safe, just slower because more series get inspected.
- The `%` character is special in cron and must be escaped as `\%`.
- Create `$LOGDIR` ahead of time (`mkdir -p`).
- The Postgres container must be running when cron fires. If you reboot
  the host, make sure `docker compose up -d` is run on startup (the
  `restart: unless-stopped` policy in `docker-compose.yml` already
  handles that once you've started it once).
- If you want notifications on failure, wrap the command in something
  like [`heartbeat`](https://healthchecks.io) or pipe the log through a
  filter that pings you on `ERROR`. The extractors log every error and
  exit 0 even on partial failure, so checking the log tail is the
  recommended monitoring approach.

## Idempotency and reprocessing

- Re-running any extractor never produces duplicate rows. Series and
  games already in the DB are skipped before downloading.
- If a row is wrong (a scrim came in incomplete, a typo'd player name was
  auto-created), **delete it manually** and re-run the extractor. There
  is no `--force` flag on purpose: silent updates of historical data are
  unsafe and the project keeps these edits deliberate.
- Roster reconciliation (officials only) is protected by
  `players.last_update`. An older match can never overwrite roster data
  derived from a newer one, even if you run things out of order.

## Known limitations

- **Pattern A (scrims):** some scrim series are played but GRID never
  emits `team-picked-character` / `team-banned-character` events. The
  Riot summary still reports a winner and the picked champions per
  player, but the draft itself (bans + pick order) is lost. These series
  are currently skipped with a `WARNING` log. Open question: whether GRID
  exposes the draft in a different event type for these series, or
  whether the data is simply not there. To investigate.
- **LPL has no Riot summary.** GRID returns 404 on the Riot summary
  endpoint for LPL series at this API tier, so `TeamsObserver` cannot
  resolve participants and those series are skipped. Not a code bug — a
  data-access limit; deferred until a future grid-minion exposes an
  alternative source. Keep LPL commented out in `tournaments.yaml`.
- **Build backfill.** Per-player builds were added with grid-minion
  v0.2.0; games ingested before that don't have them, and idempotency
  skips already-stored games. Backfilling them needs an explicit
  re-extraction path (not built yet).
- **`tournaments.yaml` is project-specific.** The repository ships with a
  sample value — customise it before running the official extractor.

## Project layout

```
.
├── README.md                  this file
├── requirements.txt           direct Python dependencies (loose pins)
├── requirements.lock          fully-pinned environment for reproducible deploys
├── LICENSE                    MIT
├── docker-compose.yml         PostgreSQL 16 + read-only API services
├── Dockerfile.api             image for the FastAPI service
├── .env.example               credentials template (copy to .env)
├── config/
│   └── tournaments.yaml       tournament names for the official extractor
├── db/
│   ├── schema.sql             full schema, auto-applied on first boot
│   └── migrations/            incremental migrations for existing DBs
└── src/
    ├── common/                shared helpers (GraphQL pagination,
    │                          champion lookup, role normalisation)
    ├── db/                    connection + ensure_team/ensure_player +
    │                          roster reconciliation
    ├── discovery/             bulk team/player discovery from tournaments
    ├── extraction/            official + scrim + soloq extractors
    │   ├── official.py        per-series logic for officials
    │   ├── scrims.py          per-series logic for scrims
    │   ├── soloq.py           soloq persistence (games + picks)
    │   ├── _persistence.py    shared INSERT helpers
    │   ├── run.py             entry point: python -m src.extraction.run
    │   ├── scrims_run.py      entry point: python -m src.extraction.scrims_run
    │   └── soloq_run.py       entry point: python -m src.extraction.soloq_run
    ├── riot/                  Riot API layer (client, endpoints, extract)
    └── api/                   read-only FastAPI app (§6)
        ├── main.py            app factory + lifespan (caches champ map)
        ├── deps.py            shared deps (DB conn, champ map)
        └── routers/           catalog, drafts, scouting, games, picks
```

## Troubleshooting

- **`Falta GRID_API_KEY en el entorno`** — your `.env` is missing or
  hasn't been picked up. Make sure it lives at the project root and that
  you ran the command from the project root.
- **`psycopg.OperationalError: connection refused`** — the Postgres
  container isn't running. `docker compose up -d` and retry.
- **`Torneo 'X': sin coincidencia exacta`** — the name in
  `tournaments.yaml` doesn't match any GRID tournament exactly. The log
  prints the candidates returned by the `contains` filter — copy the
  exact name from there.
- **Discovery returns 0 teams** — verify your API key has access to that
  tournament. GRID accounts have scoped permissions; some tournaments
  require a higher tier.
- **Scrim extractor logs `WARNING ... creado PLAYER nuevo`** — this is
  expected when a scrim brings in someone not yet in the catalog. Review
  the warnings; if they're real players, leave them; if they're typos or
  one-off fills, delete the row and (optionally) re-run discovery to
  pull the canonical name from GRID.
- **`draft vacio sin historial recuperable`** — Pattern A above. The
  series is skipped. There is nothing to do at the moment beyond
  recording the series ID for the future investigation.

## License

MIT — see [`LICENSE`](LICENSE).
