# Alignment: Škola, ogranci, programi i prostori

**oblast:** `skola-organizacija-i-prostori` · **v1.0**, status `usvojeno` · **app @ `3c2d074`**

## Summary

**~2 implemented · 1 partial · ~9 missing.** The organization exists only as a
**flat tenant record**. None of this PRD's structural sub-entities — branches,
locations, rooms/spaces, programs, program categories — exist as models, so the
bulk of the doc (§12–19, §24 guided setup, §27 screens) is unbuilt. What is real:
tenant creation with the creator as owner, current-org read, and public
slug lookup. The organization also lacks the three-state lifecycle (§11: "u
pripremi / aktivna / neaktivna") — it only carries the generic
active/archived `RecordStatus`.

## Missing (in-scope, not built)

- **M1 — Locations / branches (§12, §13).** No `Location`/`Branch` model exists
  anywhere (confirmed: no such class in `apps/api/app/domains/`). `Organization`
  has only `name/slug/type/timezone` + membership (`apps/api/app/domains/organization/models.py`).
- **M2 — Rooms / spaces + capacity (§15, §16).** No `Room`/`Space` model. Note:
  scheduling references rooms conceptually (conflict-check) but there is no room
  entity to conflict on.
- **M3 — Programs (§17) and program categories (§18).** No `Program`/`Category`
  model. Groups (`groups/models.py`) have no `program_id` link.
- **M4 — Internal codes for programs/spaces (§19).** No code fields.
- **M5 — School lifecycle "u pripremi" (§11).** Enum absence confirmed —
  organization membership has only ACTIVE/ENDED and the record has only
  active/archived; no PREPARING/DRAFT school state.
- **M6 — Safe deactivation of location/space/program (§20, §21).** No entities, so
  no guarded deactivation.
- **M7 — Deletion rules (§22) and duplicate detection (§23).** Absent.
- **M8 — Guided school setup / vođeno pokretanje (§24, §25).** No onboarding
  orchestration; only `POST /organizations` exists. (See also PRD 16.)
- **M9 — Screens O02/O03/O04 + school profile (§27).** No backend to render;
  web has no organization-settings routes (`apps/web/src/routes/` has none).
- **M10 — Logo / school profile fields (§10).** `Organization` has no logo/profile
  columns.

## Partial

- **P1 — School profile & state at read time (§10, §11).** `Organization` exists
  with `RecordStatusMixin`, and an archived org is refused downstream
  (`apps/api/app/security/deps.py:57`). But the PRD's richer profile and the
  three-state lifecycle are not modeled.
- **P2 — Access matrix (§26).** Role checks exist via `require_roles`, but per-area
  permissions this PRD assumes are not implemented — same root cause as PRD 01 C1.

## Implemented (verified)

- **I1 — Create school; creator becomes owner (§6).** `POST /organizations`
  (`apps/api/app/domains/organization/router.py`,
  `service.py:34` `create_organization`) — creates org + membership + OWNER
  assignment in one transaction, with audit + outbox event. Test
  `tests/test_organization.py:10`.
- **I2 — Organization types (§7).** `OrganizationType` enum covers SCHOOL /
  SPORTS_CLUB / DANCE_SCHOOL / COURSE_PROVIDER / EVENT_ORGANIZER / BUSINESS /
  OTHER (`apps/api/app/domains/organization/enums.py`). Current-org read
  (`GET /organizations/current`) and public slug lookup (`GET /tenants/{slug}`,
  test `test_organization.py:39`) exist.

## Out of scope (§32 — not gaps)

Per §32 "Ne ulazi u MVP" — verify against the doc before building; do not score
these as gaps.

## Open questions

1. This is **Wave 1 greenfield.** Recommended entity order: Location/Branch →
   Room/Space (+capacity) → Program → Category, since scheduling (05) and groups
   (04) will link to Program and Room. Confirm the intended parent/child shape
   (does a Group belong to a Program? does a Session book a Room?).
2. "U pripremi" school state (§11) interacts with onboarding (PRD 16) and
   invitations (PRD 01) — a school in preparation should not yet accept normal
   invites. Sequence 02 with 16.
3. §26 access matrix depends on the Wave 0 permission-model decision.
