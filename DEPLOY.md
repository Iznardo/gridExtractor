# Deploying gridExtractor on a home/local server (with Tailscale)

Deploy architecture: **a single `docker compose up`** brings up three services.

| Service | What it is | Binding | Reach |
|---|---|---|---|
| `db`  | Postgres 16 | `127.0.0.1:5432` | host only |
| `api` | FastAPI (read-only) | `127.0.0.1:8000` | host only (+ `web` over the internal network) |
| `web` | nginx: React bundle + `/api` proxy | `${WEB_HOST}:${WEB_PORT}` (default `0.0.0.0:8080`) | **the single entry point** |

The **extractors** (discovery/officials/scrims/soloq) do NOT run in Docker:
they run on the host with the venv and are automated with cron (see §5).

---

## 1. Server requirements

- Docker Engine + Docker Compose v2.
- Python 3.12 + venv (for the extractors on the host).
- [Tailscale](https://tailscale.com) installed and the machine joined to your
  tailnet (`tailscale up`) — recommended if you want access from outside the
  host without opening a port on the router. Not required if you only ever
  access the front from the same machine.
- git.

With Tailscale you don't need to open any port on the router: access goes
through the tailnet.

---

## 2. Step-by-step deployment

```bash
# 1. Clone
git clone <repo-url> gridExtractor
cd gridExtractor

# 2. Secrets (not versioned; create it by hand on the server)
cp .env.example .env
#    Fill in: GRID_API_KEY, RIOT_API_KEY, PGPASSWORD
#    (PGUSER/PGDATABASE/ports already have sane defaults)

# 3. Bring up db + api + web
docker compose up -d --build
```

The first time, with `./postgres_data` empty, Postgres applies
`db/schema.sql` on its own. **Migrations are NOT applied automatically** —
run them once:

```bash
for f in db/migrations/*.sql; do
  docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$f"
done
```

Check that everything is healthy:

```bash
docker compose ps                       # all 3 services "running"/"healthy"
curl -s http://127.0.0.1:8000/health    # the API responds
```

### Initial data population (on the host, with the venv)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.lock        # pinned, reproducible environment

python -m src.discovery.run                       # teams/players from GRID
python -m src.common.champions                    # Data Dragon catalog
python -m src.extraction.run --since 2026-01-01   # first official-games load
# (scrims/soloq: see README §"Automating extractions")
```

---

## 3. How to reach it (and how to change the address)

After `docker compose up`, the front listens on `WEB_PORT` (default `8080`).
There are several ways to reach it, from simplest to cleanest.

### 3.1 By Tailscale IP (works right away, nothing to change)

Every machine in the tailnet has a stable `100.x.y.z` IP. Find it with:

```bash
tailscale ip -4
```

From any device on your tailnet:

```
http://100.x.y.z:8080
```

### 3.2 By MagicDNS name (recommended for everyday use)

If you have **MagicDNS** enabled (Tailscale admin console → DNS → *Enable
MagicDNS*), the machine is reachable by name, no need to remember the IP:

```
http://<machine-name>:8080
http://<machine-name>.<your-tailnet>.ts.net:8080
```

**Renaming** the machine is done in the Tailscale *admin console* (*Machines*
→ the machine → *Edit machine name*). The new MagicDNS name becomes
`new-name.<your-tailnet>.ts.net`. Nothing to change on the server.

### 3.3 Changing the port

Edit `.env`:

```ini
WEB_PORT=9000
```

and recreate the service:

```bash
docker compose up -d web
```

The address is now `http://<machine>:9000`.

### 3.4 HTTPS with no port, tailnet-only (the cleanest + safest option)

`tailscale serve` publishes the front **inside your tailnet** with automatic
HTTPS and no port number: `https://<machine>.<tailnet>.ts.net`.

1. Enable HTTPS in the admin console (*DNS → Enable HTTPS*), once.
2. Close the front to every other interface (LAN/public), leaving it on
   loopback only, so **only** `tailscale serve` can reach it. In `.env`:

   ```ini
   WEB_HOST=127.0.0.1
   ```

   ```bash
   docker compose up -d web
   ```

3. Publish it on the tailnet:

   ```bash
   sudo tailscale serve --bg 8080      # use your WEB_PORT if you changed it
   tailscale serve status              # see the active config
   ```

Final access, padlocked and with no port:

```
https://<machine>.<your-tailnet>.ts.net
```

To undo it: `sudo tailscale serve reset`.

> **`serve` vs `funnel`:** `tailscale serve` = private, your tailnet only
> (what you want here). `tailscale funnel` = opens it to **the whole
> internet**. Don't use funnel for this: the API is read-only but would
> expose all your scouting data with no auth.

---

## 4. Operations

```bash
docker compose ps                  # status
docker compose logs -f api         # API logs
docker compose logs -f web         # nginx logs
docker compose restart api         # restart one service
docker compose down                # stop everything (data persists in ./postgres_data)
```

**Updating after a `git pull`:**

```bash
git pull
docker compose up -d --build       # rebuilds api and web if they changed
# If the frontend changed, rebuilding `web` regenerates the bundle automatically.
# If there are new migrations under db/migrations/, rerun the loop from §2.
```

---

## 5. Automated extractors (cron, on the host)

The extraction scripts run with the host's venv (the `db` container must be
up when they fire). `crontab -e` template (see the README's "Automating
extractions (cron)" section for details and `%` escaping):

```cron
PROJECT=/path/to/gridExtractor
PYTHON=$PROJECT/.venv/bin/python
LOGDIR=$PROJECT/logs

# Officials (daily): last 7 days
0 4 * * *  cd "$PROJECT" && $PYTHON -m src.extraction.run --since "$(date -u -d '7 days ago' +\%Y-\%m-\%d)" >> "$LOGDIR/official.log" 2>&1
# Scrims (daily)
15 4 * * *  cd "$PROJECT" && $PYTHON -m src.extraction.scrims_run --since "$(date -u -d '7 days ago' +\%Y-\%m-\%d)" >> "$LOGDIR/scrims.log" 2>&1
# Discovery (weekly)
30 3 * * 0  cd "$PROJECT" && $PYTHON -m src.discovery.run >> "$LOGDIR/discovery.log" 2>&1
```

---

## 6. "Nothing exposed" checklist

- [ ] `.env` with the real secrets — **gitignored**, created by hand on the server, never committed.
- [ ] `db` and `api` bound to `127.0.0.1` (already the case in the compose file).
- [ ] Access via Tailscale, not via a port opened on the router.
- [ ] For maximum lockdown: `WEB_HOST=127.0.0.1` + `tailscale serve` (§3.4), so the front isn't on the LAN either.
- [ ] Never `tailscale funnel` for this service.
