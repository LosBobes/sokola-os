# Alignment: Privatnost, saglasnosti i zahtevi

**oblast:** `privatnost-i-saglasnosti` · status not marked `odobreno` · **app @ `3c2d074`**

## Summary

**Domain features absent; several invariants honored structurally.** There is no
consent model, no data-subject-request (DSAR) flow, and no retention engine. But
the *cross-cutting privacy invariants* this PRD depends on are genuinely enforced
elsewhere, which matters for sequencing.

## Honored invariants (verified, cross-cutting)

- **Tenant isolation — school A never sees school B.** Every read/write re-checks
  `context.organization_id` (`apps/api/app/security/context.py`,
  `deps.py:42`). Tests `tests/test_security.py:54,74`.
- **A global person is invisible until an org-scoped relationship exists**
  (`apps/api/app/domains/identity/models.py:23` docstring + enforcement).
- **Child has identity but no login** (`StudentLoginAuthorization.login_enabled`
  default False, `identity/models.py:105`).
- **Audit spine** for sensitive changes exists (`app/platform/audit`,
  `AuditDataClass` including PRIVACY-adjacent classes).

## Missing (domain features)

- **Consent records** (saglasnosti): what was consented, by whom, when, scope,
  withdrawal. No model.
- **Data-subject requests** (zahtevi): access/export/erasure request intake +
  workflow + fulfilment. Absent.
- **Retention periods** and automated expiry/erasure. Absent.
- **Consent gating** of features (e.g. a child's data/documents blocked until
  parental consent). No enforcement hook exists for other domains to call.

## Plan

Wave 3, **first** among the absent domains — consents gate documents (09),
reports over child data (13), and lawful import (11). The audit spine and the
`AuditDataClass.PRIVACY` category are the natural foundation to build on.

## Open questions

1. Frontmatter not `odobreno` — confirm v1.0 scope.
2. Which consents are mandatory before which actions? This defines the gating
   hooks other domains must call.
