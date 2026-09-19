# Deploying SOKOLA to Hetzner (alongside existing services)

SOKOLA runs at **https://sokola.losbobes.com** on the shared Hetzner server
that already hosts gamgee, iris and flora-find, using the host-Caddy +
loopback-port pattern (the `add-hetzner-service` skill) so nothing existing is
disturbed.

The repo files are ready. The steps below are the ones a human still owns
because they touch DNS, secrets and SSH.

## How it shares the server

```
                       Browser  --HTTPS 443-->  Caddy (host, one instance)
   gamgee         ->  localhost:3000
   iris           ->  localhost:3001
   flora-find     ->  localhost:3002
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
| Caddy block | `sokola.losbobes.com { reverse_proxy localhost:3003 }` | one appended block, every other service's block left as-is |
| Database | SOKOLA's own `db` container, internal network only | not shared with other apps on the box |

## 1. Point DNS at the server

Add an A record for `sokola` in the `losbobes.com` zone pointing at the
server's IP. Owning the domain means the whole zone is yours, so no purchase or
registrar step is involved. Caddy obtains a Let's Encrypt certificate
automatically once the record resolves and ports 80/443 reach the box; no new
firewall rules are needed, since 80/443/22 are already open for the other
services.

> If `losbobes.com` is served through Cloudflare (as gamgee is), either set the
> record to **DNS only** (grey cloud) so Caddy can complete the HTTP-01
> challenge, or keep it proxied and use a Cloudflare Tunnel like gamgee does.
> Proxied-orange plus HTTP-01 will fail to issue.

## 2. Confirm port 3003 is actually free

The port registry lists 3003 for SOKOLA, but the **live Caddyfile on the server
is the source of truth**:

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
nano ops/hetzner/.env
```

Five secrets are mandatory, and the stack refuses to start without any of them,
by design (`compose.prod.yml` uses `${VAR:?...}`, and `app.main` rejects the
insecure defaults whenever `SOKOLA_ENVIRONMENT` is production-like):

| Variable | How to generate |
| --- | --- |
| `SOKOLA_DB_PASSWORD` | `openssl rand -hex 32` |
| `SOKOLA_SESSION_SECRET` | `openssl rand -hex 32` |
| `SOKOLA_PASSWORD_PEPPER` | `openssl rand -hex 32` |
| `SOKOLA_CONTACT_ENCRYPTION_KEYS` | `echo "1:$(openssl rand -base64 32)"` |
| `SOKOLA_CONTACT_FINGERPRINT_KEYS` | `echo "1:$(openssl rand -base64 32)"` |

The two contact keyrings protect school business contacts: one encrypts them,
the other derives the keyed fingerprint used to deduplicate them. They are
separate so either can be rotated without the other. **Rotate by appending a
version** (`1:<old>,2:<new>`), never by replacing one: the version that wrote a
row is stored with it, and dropping that version makes the row unreadable. Keys
are base64 of exactly 32 bytes; a malformed keyring stops the app at boot rather
than at the first contact read.

The pepper is folded into every password hash and is never stored in the
database. **Rotating it invalidates every existing password**, so set it once
and keep it.

SOKOLA sends no email, so no SMTP configuration is needed. Sign-in is
email+password (the default, on in every environment) plus optional Google.
Note the consequence: there is no self-service password reset, so a user who
forgets their password needs an administrator.

Optional:

- **Google OIDC** (`SOKOLA_GOOGLE_CLIENT_ID` / `_SECRET`). The redirect URL
  defaults to `https://sokola.losbobes.com/api/auth/google/callback` and must
  match an Authorized redirect URI on the Google OAuth client exactly. See
  `ops/GOOGLE_OIDC.md`.

## 4. Add the Caddy vhost (append, do not overwrite)

```bash
cat /opt/sokola/ops/hetzner/Caddyfile >> /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

Appending keeps every other service's block untouched, and `reload` is
zero-downtime for them.

## 5. Build and start

```bash
cd /opt/sokola
docker compose -f compose.prod.yml --env-file ops/hetzner/.env up --build -d
docker compose -f compose.prod.yml ps
curl -sS https://sokola.losbobes.com/
```

The `api` container runs `alembic upgrade head` before starting uvicorn, so
migrations apply on every deploy with no separate step.

## 6. (Optional) Automatic deploys

`.github/workflows/deploy.yml` redeploys on every push to `main`, but it
no-ops until the connection secrets exist.

The other three services live in the **LosBobes** GitHub org and inherit
`HETZNER_HOST` / `HETZNER_USER` / `HETZNER_SSH_KEY` from org-level secrets.
This repo is currently `Vbatocanin/sokola-os`, outside the org, so it inherits
nothing. Two options:

- **Transfer the repo into the org** (`gh api repos/Vbatocanin/sokola-os/transfer
  -f new_owner=LosBobes`) and it picks up the shared connection secrets. If the
  org secrets are scoped to "Selected repositories", add this repo to that list
  at `github.com/organizations/LosBobes/settings/secrets/actions`.
- **Or set the three `HETZNER_*` secrets on this repo directly.** GitHub secrets
  are write-only, so the existing values cannot be read back out of the other
  repos, so you would need the SSH key material to hand.

Either way, set `DEPLOY_PATH` at the **repo** level:

```bash
printf '/opt/sokola' | gh secret set DEPLOY_PATH -R <owner>/sokola-os
```

This matters: if the org defines `DEPLOY_PATH` for another service, an
inheriting repo would `git reset --hard` and rebuild inside **that** service's
directory. A repo-level value overrides the inherited one and affects nothing
else. Never run `gh secret set DEPLOY_PATH --org LosBobes` to fix one service.

## Updating

```bash
cd /opt/sokola && git pull && docker compose -f compose.prod.yml --env-file ops/hetzner/.env up --build -d
```

Or `make -f ops/hetzner/Makefile deploy` from your laptop. The `sokola_pg` and
`sokola_documents` named volumes persist across rebuilds.

## Persistence note

Uploaded documents are stored on the filesystem (`SOKOLA_DOCUMENTS_STORAGE_DIR`,
default `/app/var/documents`), not in Postgres and not in object storage. The
`sokola_documents` named volume is what keeps them across deploys. Without it
they would live in the container's writable layer and `up --build` would delete
them. Back it up alongside the database:

```bash
docker run --rm -v sokola_documents:/data -v "$PWD:/backup" alpine \
  tar czf /backup/sokola-documents.tar.gz -C /data .
```
