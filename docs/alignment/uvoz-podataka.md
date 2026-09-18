# Alignment: Uvoz postojećih podataka

**oblast:** `uvoz-podataka` · status not marked `odobreno` in frontmatter · **app @ `3c2d074`**

## Summary

**0 implemented · entire domain absent.** No import tooling, no staging/preview
model, no mapping or dry-run endpoint. The dev-only `POST /internal/dev/identities`
(`apps/api/app/domains/internal/router.py`) creates a single identity for tests —
it is not a data-import path.

## Missing (all of it)

- Upload a source file (CSV/spreadsheet) of people/members/groups.
- Column mapping to SOKOLA fields.
- Dry-run / preview with per-row validation before commit.
- Duplicate detection on import (ties to PRD 03 §13–15 and PRD 01 §32).
- Partial-result handling and an import audit trail.
- Rollback / re-import semantics.

## Plan

Wave 3, after the target entities are complete (people/membership PRD 03, groups
PRD 04, school structure PRD 02) — you can only import into models that exist.
Reuse the duplicate-review flow from PRD 03/01 rather than inventing a second one.

## Open questions

1. `uvoz-podataka` frontmatter is not `odobreno` — confirm it is a v1.0
   commitment before scheduling, and treat as draft-adjacent per skill scope rules.
2. Import source formats and volume expectations (pilot-school onboarding size)?
