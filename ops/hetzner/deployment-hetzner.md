# Deploying SOKOLA to Hetzner (alongside existing services)

This is PREP ONLY: reviewable files for a human to wire up by hand. Nothing
here has been run against the real server — no SSH, no DNS changes, no live
Caddy edits. See the "Manual steps still required" checklist in the PR body
for the ordered list of what a human still owns.

SOKOLA deploys onto the shared Hetzner server that already runs other apps,
using the host-Caddy + loopback-port pattern (the `add-hetzner-service` skill)
so nothing existing is disturbed.

## How it shares the server

```
                       Browser  --HTTPS 443-->  Caddy (host, one instance)
   existing apps  ->  localhost:3000, 3001, 3002, ...
   sokola         ->  localhost:3003        ->   /opt/sokola stack (web -> api -> db)
```

One Caddy instance serves every domain on the box. SOKOLA is its own Compose
project in `/opt/sokola`, publishing only `127.0.0.1:3003` (the `web`
container; it proxies `/api/` internally to the `api` container over the
Compose network, so Caddy only ever needs to know about one upstream port).

| Concern | SOKOLA value | Why it is safe |
| --- | --- | --- |
| Loopback port | `127.0.0.1:3003` | unique per service (see the skill's `PORT_REGISTRY.md`); re-verify against the live Caddyfile before use |
| Deploy dir / project | `/opt/sokola` | own containers (`sokola-*`) + volumes (`sokola_*`) |
| Caddy block | `sokola.example.com { reverse_proxy localhost:3003 }` | one appended block, every other service's block left as-is |
| Database | SOKOLA's own `db` container, internal network only | not shared with other apps on the box |

## 1. Point DNS at the server

Add an A record for the real SOKOLA domain (placeholder `sokola.example.com`
is used throughout this PR — replace it everywhere before going live) to the
existing server's IP. No new firewall rules are needed; 80/443/22 are already
open for the other services.

## 2. Confirm port 3003 is actually free

The port registry in the `add-hetzner-service` skill lists 3003 as the next
free slot as of this PR, but the **live Caddyfile on the server is the source
of truth** — re-check before appending anything:

```bash
ssh <user>@<host> "grep -oE 'localhost:[0-9]+' /etc/caddy/Caddyfile | sort -u"
```

If 3003 is taken, pick the next free port and update it in three places:
`compose.prod.yml` (the `web.ports` mapping), `ops/hetzner/Caddyfile`, and this
doc.

## 3. Clone and configure

```bash
ssh root@YOUR_SERVER_IP
git clone <repo-url> /opt/sokola
cd /opt/sokola
cp ops/hetzner/.env.prod.example ops/hetzner/.env
nano ops/hetzner/.env      # set SOKOLA_DB_PASSWORD, SOKOLA_SESSION_SECRET
                            # (openssl rand -hex 32 each), and Google OIDC
                            # values if using Google login (see ops/GOOGLE_OIDC.md)
```

## 4. Add the Caddy vhost (append, do not overwrite)

```bash
cat /opt/sokola/ops/hetzner/Caddyfile >> /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

## 5. Build and start

```bash
cd /opt/sokola
docker compose -f compose.prod.yml --env-file ops/hetzner/.env up --build -d
docker compose -f compose.prod.yml ps
curl -sS https://sokola.example.com/
```

The `api` container runs `alembic upgrade head` before starting uvicorn, same
as the local `compose.m0.yml` convention.

## 6. (Optional) Automatic deploys

Set repo secrets under GitHub -> Settings -> Secrets and variables -> Actions:
`HETZNER_HOST`, `HETZNER_USER`, `HETZNER_SSH_KEY`, `HETZNER_PORT` (optional),
`DEPLOY_PATH=/opt/sokola`. Then every push to `main` redeploys via
`.github/workflows/deploy.yml`. If the other services on this box live in a
GitHub org and share `HETZNER_*` secrets at the org level, see the
`add-hetzner-service` skill's note on reusing org secrets — but always set
`DEPLOY_PATH` at the repo level so this service can't deploy into another
app's directory.

## Updating

```bash
cd /opt/sokola && git pull && docker compose -f compose.prod.yml --env-file ops/hetzner/.env up --build -d
```

Or `make -f ops/hetzner/Makefile deploy` from your laptop. The `sokola_pg`
named volume persists across rebuilds.
