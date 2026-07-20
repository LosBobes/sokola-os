# Alignment: Osobe, roditelji i članstva

**oblast:** `osobe-roditelji-i-clanstva` · **v1.0**, status `usvojeno` · **app @ `3c2d074`**

## Summary

**~4 implemented · 3 partial · ~8 missing.** The roster's *read* surface and the
*data model* are genuinely strong — Person vs membership is cleanly separated,
and guardian relationships are fully modeled — but the write surface is a thin
happy path: create a provisional person, list, get. Everything about the
membership lifecycle, guardians, and duplicate handling exists as models/enums
without endpoints.

## Implemented (verified)

- **I1 — Person ≠ membership separation (§5).** `Person` is global
  (`apps/api/app/domains/identity/models.py:23`); org membership is separate
  (`apps/api/app/domains/organization/models.py` `OrganizationMembership`).
- **I2 — Add provisional person (§11, §12).** `POST /people` →
  `create_provisional_person` (`apps/api/app/domains/people/service.py:22`,
  `router.py:20`), staff-gated. Tests `tests/test_people.py` (4).
- **I3 — Directory / roster read (§31), person profile read (§32).**
  `GET /people`, `GET /people/{id}` (`people/service.py:82,88`), org-scoped.
- **I4 — Guardian relationship model (§23, §24).** `GuardianRelationship`,
  `GuardianOrganizationAccess`, `GuardianRelationshipType`, `GuardianAccessStatus`
  (`apps/api/app/domains/people/models.py`, `enums.py`).

## Partial

- **P1 — Membership lifecycle states (§16–18).** `MembershipStatus` (ACTIVE/ENDED)
  exists (`organization/enums.py`) but there are only ACTIVE/ENDED — no
  "u pripremi / privremeno obustavljeno" states, and no end/suspend/resume endpoint.
- **P2 — Duplicate detection (§13–15).** `ExternalPersonReference` +
  `PersonMergeRecord` (`identity/models.py:139`) exist, but no duplicate-check
  endpoint or review flow (see PRD 01 M11).
- **P3 — Access matrix (§34).** Role-gated reads exist; per-area permissions the
  PRD assumes are not modeled (PRD 01 C1).

## Missing (in-scope, not built)

- **M1 — End / suspend / resume membership (§16, §19, §20, §21).** Endpoints absent.
- **M2 — Protected last owner on membership end (§22).** No guard (see PRD 01 M4).
- **M3 — Guardian invite / additional-guardian flow (§26–29).** No endpoint; model
  ready. Ties to PRD 01 M7.
- **M4 — Revoke parental access (§30).** No endpoint.
- **M5 — Primary contact designation (§25).** No endpoint/field surfaced.
- **M6 — School-local member data / local code / admin note (§8, §9, §10).** Not
  surfaced in schemas.
- **M7 — Screens M02/duplicate/profile/guardians/end/reactivate (§33).** Web has
  `manager/People.tsx` (roster) only.
- **M8 — Person profile family/roles/groups/history composite (§32).** Read returns
  basic person, not the composite the PRD describes.

## Open questions

1. Wave 2 priority: the guardian **model is ready** — surfacing guardian invite +
   membership end/suspend endpoints is high-ROI low-risk.
2. §38 (deca i privatnost) overlaps PRD 12 (consents) — sequence together.
