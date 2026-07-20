# PRD ↔ App domain map

The SOKOLA product docs live outside this repo (default:
`~/Downloads/SOKOLA`). Each PRD carries an `oblast:` value in its frontmatter.
This table maps every known `oblast` to where it should land in the app, so an
alignment pass knows *where to look* and *what a gap looks like*.

"Backend domain" = `apps/api/app/domains/<name>`. A blank backend cell means
**no domain exists yet** — that is a structural gap to report, not an error in
this table.

| PRD file | `oblast` | Backend domain(s) | Web route(s) | Notes |
|---|---|---|---|---|
| 00-MVP-SOKOLA-OS | ceo-mvp | (umbrella) | — | Master doc; use to sanity-check scope, not to align 1:1. |
| 01-Prijava-pozivi-i-uloge | prijava-pozivi-i-uloge | auth, identity, internal | routes/Entry.tsx, RoleHome.tsx | Invites live under internal/identity; OIDC under auth. |
| 02-Skola-ogranci-programi-i-prostori | skola-organizacija-i-prostori | organization | — | Branches/programs/spaces may be sub-entities of organization. |
| 03-Osobe-roditelji-i-clanstva | osobe-roditelji-i-clanstva | people, parent | manager/People.tsx | Parent↔child links span people + parent. |
| 04-Grupe-i-upis-clanova | grupe-i-clanstva | groups | — | Enrollment = groups/{id}/members. |
| 05-Raspored-i-termini | raspored | scheduling | manager/Schedule.tsx | |
| 06-Prisustvo-i-napredak | prisustvo | attendance, scheduling | manager/Attendance.tsx | Attendance sheet hangs off a schedule session. |
| 07-Clanarine-uplate-i-dugovanja | finansije | billing, payments | manager/Money.tsx | Charges + billing runs + payments. |
| 08-Obavestenja-i-komunikacija | komunikacija | communications | manager/Communications.tsx | |
| 09-Dokumenti-i-ugovori | dokumenti | **(none)** | — | No `documents` domain — likely a gap. |
| 10-Dogadjaji-za-skole | dogadjaji | events | parent/Events.tsx | |
| 11-Uvoz-postojecih-podataka | uvoz-podataka | **(none)** — maybe internal | — | Import tooling not yet a domain. |
| 12-Privatnost-saglasnosti-i-zahtevi | privatnost-i-saglasnosti | **(none)** — cross-cutting | — | Consents/DSAR; may be woven through people/parent + platform. |
| 13-Izvestaji-i-pregled-poslovanja | izvestaji | **(none)** | — | Reporting reads across billing/attendance/etc. |
| 14-Pocetni-ekrani-i-navigacija | navigacija-i-pocetni-ekrani | — (shell/UX) | routes/RoleHome.tsx, components/shell.tsx | Mostly a web concern. |
| 15-Operativna-pretraga | pretraga | **(none)** | — | Cross-entity search; no dedicated domain yet. |
| 16-Uvodjenje-nove-skole | uvodjenje-skole | organization, identity | routes/Entry.tsx | Onboarding orchestrates several domains. |

## How to use this map

1. Read the PRD's `oblast` from frontmatter and look it up here.
2. If a backend domain is listed, that folder is the primary evidence for
   alignment. Read its `router.py` (endpoints), `models.py` (data),
   `service.py` (business rules), `enums.py` (states/statuses).
3. If the backend cell says **(none)**, the whole PRD is a candidate gap —
   verify by grepping for the concept across the codebase before concluding it
   is unimplemented (it may live inside a neighbouring domain).
4. Cross-check every implemented endpoint against the OpenAPI spec in
   `openapi/` — the spec is the contract, the domain is the implementation.

Keep this table current: when a new domain lands or a PRD is added, update the
row so future alignment passes stay trustworthy.
