# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

SOKOLA OS — a multi-tenant SaaS "operating system" for sports clubs, dance schools, and
training organizations. Built as a **fast modular monolith**: one FastAPI process, one React
SPA, one PostgreSQL database. The canonical spec is `BUILD_SOKOLA_OS_FROM_SCRATCH_PROMPT.md`;
this repo is its production implementation, delivered in numbered "increments" (see git log).

Product docs (PRDs) are written in Serbian and live outside the repo (`~/Downloads/SOKOLA`);
error messages and UI copy in the code are in Serbian by design. Code and identifiers are English.

## Commands

npm workspaces at the root orchestrate everything (`packages/contracts`, `apps/api`, `apps/web`).

```bash
# Database (Postgres 16 on host port 55432 — note the non-default port)
docker compose -f compose.m0.yml up -d db

# --- Backend (apps/api) ---
cd apps/api
python3 -m venv .venv && ./.venv/bin/pip install -e '.[dev]'
./.venv/bin/alembic upgrade head
./.venv/bin/uvicorn app.main:app --reload        # http://localhost:8000/docs

# Full backend gate (mirrors CI): ruff + mypy + architecture gate + alembic
# upgrade/check + pytest + OpenAPI parity
scripts/check.sh

# Run one test file / one test (from apps/api, venv active or via ./.venv/bin)
pytest tests/test_billing.py
pytest tests/test_billing.py -k duplicate_charge
# pytest talks to a REAL Postgres — the db container must be up and migrated.

# --- Frontend (apps/web) ---
cd apps/web && npm install && npm run dev        # http://localhost:5173
npm run gen:api        # regenerate src/api/schema.d.ts from openapi/*.openapi.json
npm run build          # tsc + vite; CI also checks gen:api leaves no diff
npx cypress run --e2e  # E2E against a live API+web+Postgres stack

# --- Root-level cross-cutting verifiers (Node) ---
npm run verify         # typecheck + lint + arch + migrations + parity across workspaces
```

There is no separate lint/typecheck step to remember per-language: `scripts/check.sh` is the
backend source of truth, `npm run verify` is the cross-cutting one. Every increment must end
green on these before the next begins.

## The one rule that governs everything: server-derived context

The client may *request* which organization/role it is acting in, but **never grants** one.
This is the core security invariant; violating it is the most serious kind of bug here.

- A request carries a principal (who) and a `x-sokola-role-assignment-id` header (which context).
- `app/security/deps.py::get_context` re-resolves the `RoleAssignment` from the DB, confirms it
  belongs to this principal and is active, and derives `organization_id`, `role_code`, `scope`
  into an immutable `RequestContext` (`app/security/context.py`).
- **There is no global `isAdmin` flag and no client-supplied tenant/role id anywhere.** Every
  domain re-checks each resource against `context.organization_id` on every read and write.
- `require_roles(...)` in a router is the permission half only; feature flags are separate.
- Errors never confirm the existence of a record the caller may not see (e.g. a foreign
  context returns the same "Nedostupan kontekst" as a nonexistent one).

Authentication (`app/security/auth.py`) resolves the principal two ways: the **dev header
adapter** (`x-sokola-person-id`, local/test only) and the **OIDC session** cookie (Google
login, `app/security/oidc.py`). The dev adapter is gated by `allow_insecure_dev_auth`, which
`app/main.py::_guard_dev_auth` refuses to let run in staging/production. When Google client
id+secret are set, OIDC is active; otherwise the app falls back to the dev adapter.

## Backend architecture (apps/api)

Modular monolith. `app/main.py` is the **only** place domains are wired — it imports each
domain's `router` and includes it. CORS/Session/CSRF middleware order is deliberate (see the
comment there).

Each domain in `app/domains/<name>/` follows a fixed layering:

```
router.py      HTTP surface: paths, operation_id, require_roles guards, response_model
service.py     business rules and orchestration (the "verb" layer)
repository.py  DB queries scoped to the organization
models.py      SQLAlchemy ORM
schemas.py     Pydantic request/response DTOs
enums.py       domain states/statuses
```

Domains: identity, organization, people, parent, groups, scheduling, attendance, billing,
payments, events, communications, plus auth, internal (dev-only), health.

**Enforced dependency direction** (`apps/api/scripts/check_architecture.py`, run in the gate):
- A domain must not import another domain's `service`/`repository`/`router`/`policy`. Only
  `models`/`enums`/`schemas` records may cross domains. Cross-domain *behavior* goes through
  the outbox, not a direct call.
- `app/common` must never import a product domain.
- No `service.py` may exceed the size ratchet (600 lines) — split before you exceed it.
- No `password_hash`/`reset_token`/`password_reset` columns may exist: SOKOLA stores no
  passwords (auth is external OIDC). This is asserted structurally.

### Platform spine (`app/platform/`)

Cross-cutting infrastructure every domain leans on:
- **outbox** — transactional outbox. Domains emit events in the same DB transaction as their
  write; the **worker** (`python -m app.worker`, entrypoint `app/worker.py`) delivers them.
  `app/handlers.py` registers all domains' handlers on import — a new async cross-domain effect
  is a handler here, not a direct import.
- **idempotency** — dedupes retried mutations so a repeated request never double-writes.
- **audit** — history of sensitive access/role/finance/privacy changes.

## Contracts & the OpenAPI parity gate

`openapi/*.openapi.json` is a **checked-in, hand-authored** contract and the source of truth
for the client. Two gates keep code and contract honest:
- Backend: `python -m scripts.check_openapi_parity` — the FastAPI app's generated schema must
  match the checked-in document (add `operation_id` to every route; it becomes the client
  method name and the parity key).
- Web: `npm run gen:api` regenerates `apps/web/src/api/schema.d.ts`; CI fails if it leaves a diff.

So a new/changed endpoint means: implement it, update the checked-in OpenAPI doc, regenerate web
types. All three must agree.

## Frontend architecture (apps/web)

React 19 + Vite + React Router. Role-based shells (manager / trainer / parent) under
`src/routes/`. Everything goes through the thin typed client in `src/api/client.ts`, which maps
HTTP outcomes to a fixed set of **canonical UI states** exactly once:
`401/403 -> permission`, `409 -> conflict/review`, `422 -> validation`, missing/5xx on a
mutation -> `manual_recovery` (**never an automatic replay of the primary action** — this
prevents double-submits on network failure). Preserve this mapping when adding calls.

## Conventions worth knowing

- Python 3.12+, `from __future__ import annotations` everywhere, mypy `strict`, ruff line
  length 100 (`E,F,I,UP,B,SIM,C4`). `Depends()` in defaults (B008) is idiomatic and allowed.
- IDs are ULIDs (`python-ulid`); shared column/base/enums helpers live in `app/common/`.
- Migrations live in `apps/api/migrations/versions`; `alembic check` in the gate asserts models
  and migrations are in sync — generate a migration for every model change.
- Money is minor-units integers with an explicit currency (default RSD); see `app/common/money.py`
  and `apps/web/src/lib/money.ts`. Financial records are corrected, never silently overwritten.
