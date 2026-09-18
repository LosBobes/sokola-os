# Alignment: Uvođenje nove škole

**oblast:** `uvodjenje-skole` · status not marked `odobreno` · **app @ `3c2d074`**

## Summary

**~1 implemented · orchestration absent.** The atomic first step exists — a
SOKOLA admin/creator can create an organization and become its owner — but the
*guided onboarding* this PRD describes (structured setup of school → locations →
rooms → programs → first invite, with progress and a "u pripremi" state) does not
exist. It is a composition over PRD 01 (invites) and PRD 02 (structure), both of
which are themselves incomplete.

## Implemented (verified)

- **I1 — Create school + first owner (atomic).** `POST /organizations` →
  `create_organization` (`apps/api/app/domains/organization/service.py:34`):
  org + membership + OWNER + audit + outbox event in one transaction. Test
  `tests/test_organization.py:10`. Dev bootstrap of a first identity exists via
  `POST /internal/dev/identities` (`apps/api/app/domains/internal/router.py`).

## Missing (in-scope, not built)

- **M1 — Guided setup flow / vođeno pokretanje (PRD 02 §24, §25).** No
  step-through onboarding; no per-step progress model.
- **M2 — "U pripremi" school state.** Not modeled (PRD 02 M5) — an onboarding
  school should not yet accept normal invites (PRD 01 §31).
- **M3 — First-owner invite path.** The controlled first-owner invite (PRD 01 §13)
  has no endpoint — depends on the invitation system (PRD 01 M1).
- **M4 — Structure setup during onboarding.** Locations/rooms/programs don't exist
  as entities (PRD 02 M1–M3).
- **M5 — Onboarding screens (PRD 02 §27 O02/O03/O04).** No web onboarding routes.

## Plan

This is the **integration milestone for Wave 1**: once invitations (01) and
school structure (02) land, onboarding is mostly orchestration + a progress
state + screens. Do not start it before those; sequence it as the capstone that
proves Wave 1 end-to-end (create school → set it up → invite first staff →
activate).

## Open questions

1. Frontmatter not `odobreno` — confirm v1.0 scope.
2. Should onboarding be admin-driven (SOKOLA admin creates + invites) only, per
   PRD 01 §13's "no public registration" rule? That constrains the UI surface.
