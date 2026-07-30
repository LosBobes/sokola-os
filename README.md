# SOKOLA OS

The daily operating system for sports clubs, dance schools, and training organizations.
Multi-tenant SaaS built as a **fast modular monolith**: one API, one web app, one PostgreSQL database.

> Built from `BUILD_SOKOLA_OS_FROM_SCRATCH_PROMPT.md`. This repository is the production
> implementation of that specification.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2 |
| Database | PostgreSQL 16 |
| Frontend | React 19 + Vite + React Router (typed client generated from OpenAPI) |
| Async | Transactional outbox + worker |
| E2E | Cypress |
| CI | ruff · mypy · pytest · alembic check · OpenAPI parity · web build · Cypress |

## Layout

```
apps/
  api/        FastAPI modular monolith (one router package per domain)
  web/        React SPA (role-based shells: manager / trainer / parent)
packages/
  contracts/  OpenAPI doc + generated TypeScript client
openapi/      Checked-in OpenAPI 3 document (source of the parity gate)
ops/          Infra / deployment assets
scripts/      Local verification harness
```

## Quick start

```bash
# 1. Start PostgreSQL
docker compose -f compose.m0.yml up -d db

# 2. API
cd apps/api
python3 -m venv .venv && ./.venv/bin/pip install -e '.[dev]'
cp .env.example .env
./.venv/bin/alembic upgrade head
./.venv/bin/uvicorn app.main:app --reload   # http://localhost:8000/docs

# 3. Web (once scaffolded)
cd ../web && npm install && npm run dev       # http://localhost:5173
```

## Verification

```bash
scripts/check.sh        # ruff + mypy + alembic check + pytest (backend)
```

Every increment must end green on the harness before the next begins. See
`BUILD_SOKOLA_OS_FROM_SCRATCH_PROMPT.md` §10 and §11 for the full gate list.

## Security & multi-tenancy

Context is **server-derived**: the client may request a role/organization but never grants one.
Every resource is re-checked against the active organization on every read and write.
Auth is external OIDC in production; a header adapter exists for local dev only and is
impossible to enable in staging/production.
