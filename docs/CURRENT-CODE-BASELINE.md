---
tip: kodni-baseline-ugovor
status: REPOSITORY_DISCOVERED
datum: 2026-09-18
popunio: Claude Code (automatsko čitanje repozitorijuma)
---

# Stvarni kodni baseline

Popunjeno čitanjem stvarnog repozitorijuma i izvršavanjem stvarnih komandi, prema
`00-CLAUDE-CODE-IZVRSI.md` §1. Sve vrednosti ispod imaju repo putanju ili izvršenu komandu
kao dokaz. Nijedna vrednost nije pretpostavljena.

> **Granica ovog dokumenta.** Ovaj dokument opisuje *zatečeno* stanje. On ne tvrdi da je
> bilo koji modul `IMPLEMENTED` u smislu v5.7 ugovora. Mapiranje zatečenog koda na ugovore
> nalazi se u `REPO-FIRST-KLASIFIKACIJA.md`.

## 1. Identitet repozitorijuma

| Polje | `resolution_status` | `runtime_value` | Dokaz |
|---|---|---|---|
| Repository | `RESOLVED` | `LosBobes/sokola-os` | `git remote -v` |
| Branch | `RESOLVED` | `claude/development-instructions-nfa7fz` | `git rev-parse --abbrev-ref HEAD` |
| Commit SHA (baseline) | `RESOLVED` | `92ccccc979fb53979081e84ded0c6e7aae56fb11` | `git rev-parse HEAD` |
| Datum provere | `RESOLVED` | `2026-09-18` | izvršavanje ovog koraka |
| Napomena o dostupnosti | `RESOLVED` | Lokalni PostgreSQL 16.13 pokrenut iz sesije; Docker daemon nije dostupan, pa `compose.m0.yml` nije korišćen | `pg_isready`, `docker ps` |

## 2. Stack

| Polje | `resolution_status` | `runtime_value` | Dokaz |
|---|---|---|---|
| Framework/runtime | `RESOLVED` | Python 3.12 + FastAPI 0.141 (modularni monolit), Uvicorn; React 19 + Vite + React Router SPA | `apps/api/pyproject.toml`, `apps/api/app/main.py`, `apps/web/package.json` |
| Baza i ORM | `RESOLVED` | PostgreSQL 16 + SQLAlchemy 2.0.54, Alembic 1.20 | `apps/api/pyproject.toml`, `apps/api/app/db.py`, `apps/api/alembic.ini` |
| Migration head | `RESOLVED` | `a1c4f2d80b37` (jedan head, 21 revizija) | `alembic heads` → `a1c4f2d80b37 (head)`, exit 0 |
| Auth/OIDC | `RESOLVED` | Email+password (scrypt + server-side pepper, hash samo na `AuthAccount`) i Google OIDC; dev header adapter nemoguće uključiti van `local`/`test` | `apps/api/app/security/{password,password_auth,oidc,auth}.py`, `apps/api/app/config.py` |
| Storage | `RESOLVED` | Samo lokalni fajl sistem (`documents_storage_dir`, podrazumevano `var/documents`); `StorageBackend` interfejs postoji za budući S3/GCS | `apps/api/app/domains/documents/storage.py`, `apps/api/app/config.py` |
| Email provider/adapter | `RESOLVED` | **Ne postoji.** Nema SMTP/SendGrid/Resend adaptera u kodu; notifikacije završavaju u `notification` tabeli (in-app inbox), ne u email transportu | `grep -ril 'smtp\|sendgrid\|resend\|send_email' apps/api/app` → bez pogodaka |
| Jobs/queue/cron | `RESOLVED` | Transakcioni outbox (`outbox_message`) + poll worker proces `python -m app.worker`; nema eksternog queue/cron sistema | `apps/api/app/worker.py`, `apps/api/app/platform/outbox/worker.py` |
| Test runner | `RESOLVED` | pytest 9.1.1 (integracioni testovi protiv stvarnog PostgreSQL-a); Cypress za E2E | `apps/api/pyproject.toml` `[tool.pytest.ini_options]`, `apps/web/cypress/e2e/` |
| Build/deploy target | `RESOLVED` | Docker image (`apps/api/Dockerfile`) + `compose.prod.yml`, deploy na Hetzner preko GitHub Actions | `.github/workflows/deploy.yml`, `ops/hetzner/` |
| Staging URL/build ID | `UNRESOLVED` | `null` | Nije dokaziv iz repoa; drži se u deployment secrets |

## 3. Tenant topologija (M03)

| Polje | `resolution_status` | `runtime_value` | Dokaz |
|---|---|---|---|
| Tenant topologija — fizička šema (M03 §4) | `RESOLVED` | Jedna baza, jedna `public` šema, 42 tabele; tenant diskriminator je kolona `organization_id VARCHAR(64)` | `\dt` (42 tabele), `\d billing_run` |
| Tenant context store/resolver (M03 §5.3/§12 TEN-PORT-01) | `RESOLVED` | `RequestContext` izveden na serveru iz sesije; klijent sme tražiti organizaciju, ali je nikad ne dodeljuje | `apps/api/app/security/context.py`, `apps/api/app/security/deps.py` |
| DB FK/UNIQUE/RLS/BYPASSRLS stanje (M03 §7) | `RESOLVED` | **Nema RLS politika.** FK ka tenantu su jednokolonski (`organization_id → organization.id`), **nisu composite tenant FK**; `UNIQUE` je mestimično tenant-scoped (`uq_org_membership(organization_id, person_id)`), mestimično globalan (`uq_auth_identifier(type, value)`) | `grep -rl 'ROW LEVEL SECURITY\|POLICY' migrations/versions/` → prazno; `\d billing_run`; `apps/api/app/domains/*/models.py` |
| Cache tenant izolacija (M03 §11) | `RESOLVED` | **N/P — ne postoji cache sloj.** Nema Redis/memcache adaptera; nema keširanih autorizacionih odluka | `grep -ril 'redis' apps/api/app` → bez pogodaka |
| Jobs/outbox tenant izolacija (M03 §11) | `VERIFY_IN_REPO` | Outbox poruke se upisuju u istoj transakciji kao business upis; nošenje `organization_id` u payload-u po tipu poruke nije dokazano statički | `apps/api/app/platform/outbox/service.py`, `apps/api/app/handlers.py` |
| Object-storage tenant izolacija (M03 §11) | `VERIFY_IN_REPO` | Lokalni fajl sistem; particionisanje po tenantu i kratkoživeći signed URL nisu dokazani | `apps/api/app/domains/documents/storage.py` |
| Realtime tenant izolacija (M03 §11) | `RESOLVED` | **N/P — ne postoji realtime sloj** (nema WebSocket/SSE kanala) | `apps/api/app/main.py` |
| Export/report tenant izolacija (M03 §11) | `VERIFY_IN_REPO` | `reports` domen čita kroz `RequestContext`; da li svaki izvor metrike nosi tenant filter zahteva izvršni test | `apps/api/app/domains/reports/service.py` |
| Lokacije tenant testova (M03 §20/22) | `RESOLVED` | Cross-tenant negativni testovi postoje i prolaze (npr. `test_tenant_isolation`, `test_security.py`), ali ne pokrivaju svaku M03 §11 površinu | `apps/api/tests/test_security.py`, `apps/api/tests/test_scheduling_series.py::test_tenant_isolation` |

## 4. Izvršene komande i stvarni rezultati

Izvršeno na commit-u `92ccccc` **pre bilo kakve izmene koda** (baseline snimak):

| Komanda | Exit code | Rezultat |
|---|---:|---|
| `ruff check app tests` | 0 | All checks passed |
| `mypy app` | 0 | no issues found in 176 source files |
| `python -m scripts.check_architecture` | 0 | Architecture gate OK |
| `alembic heads` | 0 | `a1c4f2d80b37 (head)` — tačno jedan head |
| `alembic upgrade head` | 0 | 21 revizija primenjeno na praznu bazu |
| `alembic check` | 0 | No new upgrade operations detected |
| `pytest` | **1** | **1 failed, 285 passed** — `tests/test_scheduling_series.py::test_edit_scope_all_future` |
| `python -m scripts.check_openapi_parity` | 0 | OpenAPI parity OK |

Zatečeni pad **nije posledica ove izmene** (`00-CLAUDE-CODE-IZVRSI.md` §1.3). Uzrok i
otklanjanje opisani su u `REPO-FIRST-KLASIFIKACIJA.md` §4 (F-01).

Posle Talas-1 clock port izmene, na istom okruženju:

| Komanda | Exit code | Rezultat |
|---|---:|---|
| `ruff check app tests` | 0 | All checks passed |
| `mypy app` | 0 | no issues found in 177 source files |
| `python -m scripts.check_architecture` | 0 | Architecture gate OK |
| `alembic check` | 0 | No new upgrade operations detected |
| `pytest` | 0 | **293 passed, 0 failed, 0 skipped** |
| `python -m scripts.check_openapi_parity` | 0 | OpenAPI parity OK |
| `scripts/verify-spec-manifest.sh` | 0 | 72/72 fajla odgovaraju manifestu |

Okruženje izvršavanja: Python 3.12, PostgreSQL 16.13, `SOKOLA_ENVIRONMENT=test`,
`SOKOLA_ALLOW_INSECURE_DEV_AUTH=true`, baza `postgresql+psycopg://sokola@127.0.0.1:5432/sokola`.
Nijedan test nije preskočen i nijedan nije označen `xfail`.

**Nije izvršeno u ovoj sesiji:** web `npm run build` / `npm run typecheck` i Cypress E2E
(zahtevaju pun `npm ci` i pokrenut stack), pa za njih nema izvršnog dokaza.

## 5. Komande koje čine verifikacioni harness

| Namena | Komanda | Napomena |
|---|---|---|
| Ceo backend | `scripts/check.sh` | Ogledalo CI backend job-a |
| Spec integritet | `scripts/verify-spec-manifest.sh` | Dodato uz ovaj baseline |
| Web tipovi/build | `npm run typecheck` / `npm run build` (u `apps/web`) | |
| E2E | `npx cypress run --e2e` (u `apps/web`) | Zahteva pokrenut API + web |
| Root `npm run verify` | **neispravan** | Vidi F-02 u klasifikaciji |

## Pravilo aktuelnosti

Baseline važi za commit `92ccccc`. Svaka naredna izmena koja menja migration head, stack ili
rezultate harness-a mora ažurirati ovaj dokument u istom commit-u.
