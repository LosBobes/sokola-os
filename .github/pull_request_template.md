<!-- Keep PRs small and scope-locked. One increment or one fix per PR. -->

## What & why

<!-- What does this change do, and which user workflow or gate does it serve? -->

## Scope check

- [ ] Stays within the P0 domain list (no red-list features, see BUILD_SOKOLA_OS_FROM_SCRATCH_PROMPT.md §12)
- [ ] No new runtime dependency without a purpose/security/removal note
- [ ] No `domain → domain` service import; `common` imports no domain
- [ ] User-facing strings are Serbian (Latin) product vocabulary

## Verification

- [ ] `ruff` + `mypy` clean
- [ ] `alembic upgrade head` and `alembic check` pass (migrations reversible)
- [ ] `pytest` green against real PostgreSQL
- [ ] OpenAPI regenerated & committed if the API surface changed (`python -m scripts.export_openapi`)
- [ ] Cross-tenant / permission negative tests added or still cover the change
- [ ] Cypress E2E updated if a journey changed

## Security & tenancy

- [ ] Every new resource access re-checks the active organization (server-derived context)
- [ ] Idempotency keys on financial/registration/import/notification mutations
- [ ] No secrets, tokens, or provider names committed or leaked in error envelopes

## Screenshots / notes

<!-- UI changes: before/after. Data model changes: migration summary. -->
