# SOKOLA PRD Sweep vs app @ `3c2d074`

Coverage across all 16 feature PRDs, the structural finding that explains the
app's shape, and the phased plan of attack. Per-PRD detail lives in the
sibling files (see [README](README.md)).

**Legend:** 🟢 solid · 🟡 happy-path only (lifecycle/rules thin) · 🟠 model exists, no endpoints · 🔴 absent

## Coverage matrix

| # | PRD (oblast) | v/status | Coverage | What's real | What's missing |
|---|---|---|---|---|---|
| 01 | prijava-pozivi-i-uloge | 1.0 odobreno | 🟡 | OIDC login, no-password (enforced), one global identity, server-derived context, revocation | Invitations (model-only 🟠), all role-assignment/permission endpoints, protected-owner, support access |
| 02 | skola-organizacija-i-prostori | 1.0 usvojeno | 🔴 | Flat `Organization` + membership; create/current/tenant-lookup | Branches, locations, rooms/spaces, programs, categories, capacity, "u pripremi", guided setup — no models |
| 03 | osobe-roditelji-i-clanstva | 1.0 usvojeno | 🟡 | Person roster CRUD; rich guardian/membership models (🟠) | Membership lifecycle, guardian invites, duplicate review, additional-guardian, directory-with-family |
| 04 | grupe-i-clanstva | 1.0 odobreno | 🟡 | Groups + add/list members, capacity mode | Group pricing + member discount (no data), enrollment lifecycle (suspend/resume/transfer/end), "u pripremi" |
| 05 | raspored | 1.0 odobreno | 🟡 | Sessions + conflict-check (strong), `SessionSeries` model (🟠) | Weekly-rule create, 12-week generation, edit-series, cancel, trainer-swap, room-change |
| 06 | prisustvo | 1.0 odobreno | 🟡 | Attendance sheet get/save 🟢 | "Napredak" (progress) — absent |
| 07 | finansije | 1.0 odobreno | 🟢 | Billing runs + preview, charges, payments (real minor-units money) | Pricing source (from group), charge-cancel/payment-void endpoints (reasons modeled 🟠), debts view |
| 08 | komunikacija | 1.0 odobreno | 🟡 | Announcements publish + preview | Delivery-failure handling, in-app inbox, per-event auto-notifications |
| 09 | dokumenti | 1.0 odobreno | 🔴 | — | Entire documents/contracts domain absent |
| 10 | dogadjaji | 1.0 odobreno | 🟢 | Events + registrations + cancel (most complete domain) | Minor lifecycle edges |
| 11 | uvoz-podataka | — | 🔴 | — | Entire import domain absent |
| 12 | privatnost-i-saglasnosti | — | 🔴 | Tenant-isolation invariants honored | Consents, DSAR/requests, retention — absent |
| 13 | izvestaji | — | 🔴 | — | Entire reporting domain absent |
| 14 | navigacija-i-pocetni-ekrani | — | 🟡 | Role homes + app shell (web) | Full nav/"Više" menu, per-role completeness |
| 15 | pretraga | — | 🔴 | — | Operational search absent |
| 16 | uvodjenje-skole | — | 🔴 | Org create only | Guided onboarding (depends on 01 invites + 02 setup) |

*(00 is the umbrella MVP doc — not scored.)*

## The one finding that explains the whole app

**The data layer is built to v1.0; the endpoint layer is a happy-path slice.**
Nearly every domain has full state-machine enums and future-shaped models but
exposes only create/list/get. The states exist; the transitions have no routes.
Verified examples:

- `Invitation` + 5 statuses + `expires_at` (`apps/api/app/domains/identity/models.py:120`) — referenced **only** in `models.py`/`enums.py`, zero endpoints.
- `SessionSeries` + `SessionSeriesFrequency` (`apps/api/app/domains/scheduling/models.py`) — the only scheduling writes are single-session create + conflict-check (`scheduling/service.py:36`).
- `Charge.cancellation_reason` / `PaymentRecord` void reason exist, but no cancel/void endpoint (`billing/service.py`, `payments/service.py:17`).
- `GroupMembership.end_reason` (`groups/models.py:52`) — no end/suspend/transfer endpoint.

**Consequence for planning:** much of the remaining work is *surfacing lifecycle
mutations over models that already exist* — cheaper and lower-risk than
greenfield. The genuinely-absent work is concentrated in six areas: PRD 02
sub-entities, and PRDs 09, 11, 12, 13, 15.

## Blocking decision (do first)

Authorization is currently by role **name** (`require_roles(...)`,
`apps/api/app/security/deps.py:74`), which contradicts PRD 01 §19.2/§25.5
("role name alone must not grant area access"). PRDs 02/03/04 each define
per-area permission matrices that cannot be built until this is resolved:
**a policy/permission layer over `RoleCode`, or scoped role variants?** The
enums already hint at the intended direction — "New capabilities do not get new
role codes; they get policy rules" (`apps/api/app/domains/identity/enums.py:1`)
— but that policy layer does not exist yet.

## Plan of attack

### Wave 0 — Decide the permission model (½ day; blocks everything below)
Resolve the role-name-vs-permissions conflict. Recommended: a thin policy layer
keyed on `(role_code, area, scope)` so `require_roles` becomes
`require_permission`. Every Wave 1+ endpoint consumes it.

### Wave 1 — Foundational surfaces (unblock onboarding & scoping)
1. **Invitations end-to-end** (PRD 01 §16–24): send / accept-existing /
   accept-new / revoke / reissue / 7-day expiry / wrong-account. Model is ready;
   single highest-leverage gap.
2. **Role administration** (01 §25–26, §14): assign/revoke/suspend,
   protected-last-owner guard, permission changes with audit.
3. **School structure** (PRD 02): branches, locations, rooms/spaces (+capacity),
   programs, categories, "u pripremi" state. New models; referenced by 04/05/16,
   so build before finishing scheduling/groups.

### Wave 2 — Finish the started domains (high ROI, models exist)
4. **Scheduling series** (05): weekly-rule create + 12-week generation +
   edit-series / cancel / trainer-swap / room-change.
5. **Enrollment + pricing** (04): group base price + member discount (data),
   then enroll / suspend / resume / transfer / end.
6. **Membership & guardians** (03): membership lifecycle, additional-guardian
   invites, duplicate review.
7. **Finance edges** (07): charge-cancel, payment-void, debts view, wire pricing
   into billing runs.

### Wave 3 — Absent supporting domains (sequence by data dependency)
8. **Consents/privacy** (12) — gates lawful handling of child data used by
   03/09/13.
9. **Documents** (09) → then **Import** (11).
10. **Reports** (13) and **Search** (15) last — they read across everything, so
    build after the underlying data is complete.

### Wave 4 — Polish
11. Communications delivery + inbox + auto-notifications (08), attendance
    progress (06), navigation completeness (14), parent surface expansion.

**Sequencing rationale:** Wave 0 unblocks authz everywhere; Wave 1 unblocks
onboarding (16) and trainer/parent scoping; Wave 2 is cheap because it is
endpoints over existing models; Wave 3's read-heavy domains (13, 15)
deliberately come after their inputs exist.
