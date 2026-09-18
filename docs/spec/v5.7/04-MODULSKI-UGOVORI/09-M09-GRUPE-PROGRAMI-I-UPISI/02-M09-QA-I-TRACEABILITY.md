---
tip: qa-traceability
modul-id: M09
status: SPEC_CANDIDATE
revizija: "1.2"
datum: 2026-09-08
obavezni-scenariji: 60
---

# M09 — QA i traceability

Svaki scenario je automatizovan na API/service nivou; `PAR` zahteva dve nezavisne DB transakcije i barijeru pre commit-a. Seed ima škole A/B, programe P-A/P-B, grupe GA/GB, participant/staff profile u obe škole, OWNER/MANAGER/INSTRUCTOR/GUARDIAN/PAYER i fiksno vreme `2026-09-08T10:00:00Z`.

| ID | Scenario | Očekivanje |
|---|---|---|
| M09-QA-001 | Create DRAFT Group sa ACTIVE M08 Program. | 201, version 1, audit/outbox/receipt atomski. |
| M09-QA-002 | Aktivacija sa INACTIVE Program. | 409 REFERENCE_INACTIVE; bez write-a. |
| M09-QA-003 | Cross-tenant Program ID. | 404 safe. |
| M09-QA-004 | Dupli code/name. | 409, deterministički. |
| M09-QA-005 | Group sadrži price/schedule JSON polje. | 422 unknown/forbidden field. |
| M09-QA-006 | Preferred Space nije u Location. | 422/409; bez write-a. |
| M09-QA-007 | DRAFT→ACTIVE→INACTIVE→ACTIVE. | Sve dozvoljeno uz rast version-a. |
| M09-QA-008 | ACTIVE→ARCHIVED direktno. | 409 transition not allowed. |
| M09-QA-009 | Archive bez zavisnosti iz DRAFT/INACTIVE. | Uspeh, terminalno. |
| M09-QA-010 | Archive sa budućim M10 terminom. | 409 dependencies exist. |
| M09-QA-011 | Create Enrollment koristi ParticipantProfile. | 201 DRAFT; nema StudentProfile. |
| M09-QA-012 | Aktivacija eligibility prolazi. | ACTIVE + transition + receipt. |
| M09-QA-013 | Cross-tenant participant. | 404 safe; nema count leak-a. |
| M09-QA-014 | Dva preklapajuća enrollmenta istog participant/group. | Drugi 409. |
| M09-QA-015 | Isti participant u dve grupe. | Dozvoljeno. |
| M09-QA-016 | ACTIVE red ima budući `starts_on`; roster/capacity se čita danas bez worker-a. | Nije u rosteru niti današnjem capacity count-u; pojavljuje se tačno na početku School local date intervala bez status mutacije. |
| M09-QA-017 | `ends_on` je jednak School local datumu as-of instant-a; cleanup/effective-transition worker nije pokrenut. | Nije vraćen i ne zauzima capacity; ekskluzivni kraj važi iz query ugovora bez job-a. |
| M09-QA-018 | Suspend pa resume. | Jedan enrollment, append transitions. |
| M09-QA-019 | Resume TERMINATED reda. | 409; zahteva novi Enrollment. |
| M09-QA-020 | Retroaktivni transition pre poslednjeg. | 409. |
| M09-QA-021 | TERMINATE bez reason. | 422. |
| M09-QA-022 | HARD limit ima jedno mesto. | Prva aktivacija uspeva. |
| M09-QA-023 PAR | Dve paralelne aktivacije za poslednje mesto. | Tačno jedna uspeva; druga 409. |
| M09-QA-024 | SUSPENDED participant i capacity. | I dalje zauzima mesto. |
| M09-QA-025 | WARNING iznad limita bez override. | 409 override required. |
| M09-QA-026 | WARNING override bez permission-a. | 403. |
| M09-QA-027 | WARNING override sa permission+reason. | Uspeh + audit reason. |
| M09-QA-028 | HARD_LIMIT sa override flag-om. | I dalje 409. |
| M09-QA-029 | NO_LIMIT sa capacity vrednošću. | 422. |
| M09-QA-030 | Smanjenje capacity ispod aktivnih. | Group update + warning; nema brisanja. |
| M09-QA-031 | Transfer u slobodnu target grupu. | Source terminated + target active atomski. |
| M09-QA-032 | Transfer u pun target. | Potpun rollback; source active. |
| M09-QA-033 PAR | Dva transfera istog source-a. | Najviše jedan; drugi conflict/idempotent retry. |
| M09-QA-034 | Retry transfera isti key/payload. | Identičan receipt, bez duplikata. |
| M09-QA-035 | Isti key, drugi target. | 409 idempotency reuse. |
| M09-QA-036 | Assign LEAD instructor. | ACTIVE assignment. |
| M09-QA-037 | Preklapajući drugi LEAD. | 409. |
| M09-QA-038 | Dva različita non-lead instruktora. | Dozvoljeno. |
| M09-QA-039 | Assignment actor nema RBAC role. | Assignment ne omogućava API; M05 deny. |
| M09-QA-040 | Instructor sa permission, bez assignment. | Subject guard skriva tuđu grupu. |
| M09-QA-041 | Instructor sa aktivnim assignmentom. | Samo dozvoljena group projekcija. |
| M09-QA-042 | End assignment bez reason pre planiranog kraja. | 422. |
| M09-QA-043 | Guardian traži roster. | 403/404 prema concealment pravilu. |
| M09-QA-044 | Payer traži roster. | Odbijeno; finance veza nije child access. |
| M09-QA-045 | List total sa skrivenim grupama. | Total ne uključuje skrivene. |
| M09-QA-046 | Cursor druge škole. | 404/422 opaque invalid; bez leak-a. |
| M09-QA-047 | Version mismatch update. | 409; bez partial write-a. |
| M09-QA-048 | Missing expected version. | 428. |
| M09-QA-049 | M06 port nedostupan. | 503 fail-closed. |
| M09-QA-050 | Outbox payload pregled. | Nema imena, kontakta, zdravlja, finance ili free texta. |
| M09-QA-051 | Audit rollback simulacija. | Business write takođe rollback. |
| M09-QA-052 | Offline write. | Deny; nema lokalnog konačnog uspeha. |
| M09-QA-053 | Waitlist flag OFF, grupa puna. | 409; nema WaitlistEntry. |
| M09-QA-054 | Deactivate Group. | Postojeći termini/upisi nisu tiho promenjeni. |
| M09-QA-055 | Reaktivacija uz archived Program. | 409. |
| M09-QA-056 | As-of instant je između ACTIVE i kasnije SUSPENDED/TERMINATED tranzicije; zasebno se šalje budući suspend/transfer. | Roster koristi poslednju transition `effective_at<=instant` i poluotvoren interval; buduća statusna komanda/transfer je 422, nema `groups.enrollment_effective_transition` job-a. |
| M09-QA-057 | Unicode display name. | Dozvoljen; runtime code ostaje ASCII. |
| M09-QA-058 | HTML/control/BiDi u name/description. | 422/sanitized po plain-text ugovoru, nikad izvršen. |
| M09-QA-059 | Pretraga aktivnog M09 ugovora. | Nema `StudentProfile`, `base_monthly_price_minor`, `price_minor`, `schedule_hint`. |
| M09-QA-060 | DB FK sa school mismatch-om. | Baza odbija čak i kada app guard izostane u test adapteru. |

## Traceability

| Garancija | Normativno | Testovi |
|---|---|---|
| Neutralni model i vlasništvo | 01 §1–2 | 1–16, 59 |
| Capacity i concurrency | 01 §3, §7 | 22–30, 60 |
| Transfer | 01 §2.5, §3, §7 | 31–35 |
| Staff bez RBAC eskalacije | 01 §2.6, §4 | 36–44 |
| Tenant/privacy | 01 §4 | 3, 13, 43–46, 50, 60 |
| Lifecycle | 01 §5 | 7–10, 17–21, 54–55 |
| Idempotency/transaction | 01 §7 | 1, 23, 31–35, 47–51 |
