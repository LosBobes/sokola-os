---
tip: integration-map
modul-id: M17
status: SPEC_CANDIDATE
datum: 2026-09-09
---

# M17 — mapa integracije

| Veza | Vrsta | Garancija |
|---|---|---|
| M01→M17 | guard/read | Session/account/step-up; M17 ne poseduje identitet. |
| M03/M04→M17 | guard/schema | School tenant/context/status; compliance intake ostaje minimalno dostupan. |
| M05→M17 | guard | Permission/support/break-glass; UI nije authorization. |
| M06→M17 | schema/read | Person/participant subject; nema kopije profila. |
| M07→M17 | read | Trenutni guardian/payer basis; recheck pre commit/download-a. |
| M17→M15 | schema/reference | M17 referencira M15 immutable document/version/hash/evidence; M15 ne importuje M17 schema i ne poziva M17 direktno. |
| Owner moduli→M17 | read guard | `AuthorizeProcessing` pre policy-controlled obrade. |
| Neutralni application coordinator→M17+owner modul | orchestration | Coordinator lease-uje M17 PrivacyTask, poziva tačno jedan verzionisani owner port i vraća durable receipt M17-u; M17 i owner modul nemaju međusobni orchestration import/poziv. |
| M17→M21 | outbox/audit | Minimalni opaque događaji; M21 infrastruktura, M17 semantika. |
| M17→M28 | read/command | Parent-first notice/consent/DSAR površine, child subject guard. |

Schema edges: M17→M04/M06/M15. M17 može FK ka immutable M15 document/evidence identifikatoru u istoj modularnoj bazi. M15 ne schema-zavisi od M17: njegove legal-policy vrednosti su immutable opaque/versioned snapshot reference koje neutralni coordinator proverava pre M15 commit-a. Time ne postoji povratna M15→M17 schema ili direct-call grana.

Obavezni integracioni redosled: M04/M06 schema → M15 document/evidence foundation → M17 policy/consent/request schema → owner-module privacy portovi → M28 UI. M21 audit/job infrastruktura može biti tehnički uvedena ranije, ali ne poseduje M17 poslovna stanja.

M17 ne uvodi marketing consent kao dozvolu za M13 operativnu komunikaciju; svaki purpose je zaseban. M14 push payload nema child/consent/request detalj. M18 agregat/izveštaj mora imati purpose i suppression prag. M20 import ne sme izmišljati grant.
