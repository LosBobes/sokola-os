# Alignment: Operativna pretraga

**oblast:** `pretraga` · status not marked `odobreno` · **app @ `3c2d074`**

## Summary

**0 implemented · absent.** No cross-entity search endpoint. Each domain has its
own scoped list (`GET /people`, `GET /groups`, `GET /events`, `GET /schedule/sessions`)
with pagination (`app/common/pagination.py`), but there is no unified operational
search across people/groups/sessions/charges.

## Missing (all of it)

- Single search endpoint spanning people, groups, sessions, events, charges.
- Result ranking + type-labelled results.
- Strict tenant scoping (search must never leak across organizations — the same
  `context.organization_id` re-check that the list endpoints use).
- Post-context-switch reset of prior search results (PRD 01 §28 references this).

## Plan

Wave 3, **last** — search reads across everything, so its value scales with how
complete the underlying data is. Cheapest correct v1: fan-out over the existing
per-domain repositories with a shared org filter, rather than a separate search
index.

## Open questions

1. Frontmatter not `odobreno` — confirm v1.0 scope.
2. Postgres full-text/`ILIKE` fan-out vs a dedicated index — fan-out is almost
   certainly enough at pilot scale and avoids new infrastructure.
