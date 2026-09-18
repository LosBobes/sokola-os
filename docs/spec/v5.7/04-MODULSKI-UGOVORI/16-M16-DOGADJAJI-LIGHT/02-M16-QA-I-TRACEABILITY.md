---
tip: qa-traceability
modul-id: M16
status: SPEC_CANDIDATE
revizija: "1.4"
datum: 2026-09-15
obavezni-scenariji: 89
---

# M16 — QA i traceability

| QA ID | Scenario | Očekivano |
|---|---|---|
| M16-QA-001 | Create SCHOOL_ORGANIZED validan. | DRAFT. |
| M16-QA-002 | Create EXTERNAL_ORGANIZER validan. | DRAFT. |
| M16-QA-003 | `school_role` payload. | 422 unknown field. |
| M16-QA-004 | `SCHOOL_PARTICIPANT_EXTERNAL`. | 422 unknown enum. |
| M16-QA-005 | EXTERNAL bez organizer name. | 422. |
| M16-QA-006 | SCHOOL sa external-only poljem. | 422. |
| M16-QA-007 | SCHOOL sa allocated capacity. | 422. |
| M16-QA-008 | EXTERNAL sa capacity_mode. | 422. |
| M16-QA-009 | End≤start. | 422. |
| M16-QA-010 | Trajanje >31 dan. | 422/Events Pro. |
| M16-QA-011 | Invalid IANA/DST nonexistent time. | Deterministička validation odluka. |
| M16-QA-012 | Ambiguous DST bez resolver izbora. | 422. |
| M16-QA-013 | Registration close posle start-a. | 422. |
| M16-QA-014 | Audience scope druge škole. | Safe 404. |
| M16-QA-015 | Location druge škole. | Safe 404. |
| M16-QA-016 | Publish bez audience. | 422. |
| M16-QA-017 | Publish bez location, start≤72h. | 422. |
| M16-QA-018 | Lokacija još nije određena (`location_tbd=true`), a početak je za više od 72h. | Dozvoljeno uz eksplicitni flag; objava je odbijena na 72h ili manje bez validne lokacije. |
| M16-QA-019 | Responsible staff inactive. | 422. |
| M16-QA-020 | M08/M10 resource conflict. | 409, bez publish-a/claim-a. |
| M16-QA-021 | Valid publish. | Event+claims+audit+outbox jedan commit. |
| M16-QA-022 | DB fail posle claim-a. | Potpun rollback. |
| M16-QA-023 | Parallel publish. | Jedan commit. |
| M16-QA-024 | Same idempotency key/payload. | Isti result. |
| M16-QA-025 | Same key/drugi payload. | 409. |
| M16-QA-026 | Guardian ACTIVE child in audience. | Register uspeva. |
| M16-QA-027 | Guardian drugo dete. | Safe 404/deny. |
| M16-QA-028 | PAYER register. | 403. |
| M16-QA-029 | Registration pre open/posle close. | 409. |
| M16-QA-030 | Dva zahteva isti participant. | Jedan neterminalan red. |
| M16-QA-031 | Dva guardian-a isti child. | Jedna registracija; retry/conflict determinističan. |
| M16-QA-032 | Dva child-a poslednje HARD mesto. | Tačno jedan uspe. |
| M16-QA-033 | NO_LIMIT sa limitom. | 422. |
| M16-QA-034 | WARNING preko limita guardian. | 409. |
| M16-QA-035 | WARNING staff bez reason/permission. | 403/422. |
| M16-QA-036 | WARNING staff validan override. | Uspeh + audit. |
| M16-QA-037 | HARD staff override. | 409, bez izuzetka. |
| M16-QA-038 | EXTERNAL interest. | INTERESTED, ne troši allocation. |
| M16-QA-039 | Confirm poslednje allocation mesto paralelno. | Jedan uspe. |
| M16-QA-040 | interest_flow OFF Register. | Direktno CONFIRMED. |
| M16-QA-041 | INTERESTED u participant snapshot-u. | Nije uključen. |
| M16-QA-042 | Cancel registration. | Stari red CANCELLED. |
| M16-QA-043 | Guardian reactivate. | 403. |
| M16-QA-044 | Staff reactivate bez reason. | 422. |
| M16-QA-045 | Staff reactivate validno. | Novi red sa reference; stari immutable. |
| M16-QA-046 | Reactivate kad neterminalan red već postoji. | 409. |
| M16-QA-047 | Guardian revoke pre registration commit-a. | Fail closed. |
| M16-QA-048 | Event cancel čeka isti lock kao register. | Nema registration posle cancel commit-a. |
| M16-QA-049 | Cancel event. | CANCELLED, future claims release, outbox. |
| M16-QA-050 | Cancel retry. | Isti receipt, bez drugog event-a. |
| M16-QA-051 | Material time change validan. | Conflict recheck + outbox. |
| M16-QA-052 | Material change stale version. | 409. |
| M16-QA-053 | Title typo change. | Bez lažne material notification klase. |
| M16-QA-054 | Event payload sadrži fee_amount/currency/due. | 422/static schema 0 polja. |
| M16-QA-055 | M12 EVENT FeeRule postoji. | UI composition vidi cenu iz M12. |
| M16-QA-056 | Neutralni coordinator: M16+M12 paid registration uspe. | Registration+Assessment/Obligation atomski; oba owner porta. |
| M16-QA-057 | Coordinator-ov M12 write fail. | Ni registration ni finance red; jedan rollback. |
| M16-QA-058 | M16 pokušava direktan M12 handler/table write ili M12 callback u M16. | Architecture/static test pada. |
| M16-QA-059 | Source event za M14. | Minimalni outbox u commit-u; nema direct call-a. |
| M16-QA-060 | M14 outage. | M16 write uspeva. |
| M16-QA-061 | M15 EVENT validation. | Samo M15→M16 read port. |
| M16-QA-062 | M16 document query/call. | Ne postoji. |
| M16-QA-063 | Start snapshot job prvi put. | Samo eligible neterminalni učesnici. |
| M16-QA-064 | Snapshot job retry. | Bez duplikata. |
| M16-QA-065 | Location snapshot. | Minimalan, hashovan, tenant-safe. |
| M16-QA-066 | Late add staff validan. | Append-only participant snapshot pre attendance. |
| M16-QA-067 | Event attendance za snapshot participant-a. | UNRECORDED→ARRIVED/NO_SHOW. |
| M16-QA-068 | Attendance za INTERESTED/nonparticipant. | 422/safe 404. |
| M16-QA-069 | M11 offline queue za EventAttendance. | Odbijeno; M16 offline DENY. |
| M16-QA-070 | EventAttendance utiče na billing. | Nema takvog read/input-a. |
| M16-QA-071 | Support čita participant/attendance. | Odbijeno; samo masked health. |
| M16-QA-072 | Negative dependency/schema scan. | Nema school_role, price/fee fields, direct M14/M15, GuestEvent ili M11 linka. |
| M16-QA-073 | Dve school EventLocation instance istog događaja. | Dva M08 bloka sa različitim EventLocation source ref-ovima; jedan Event; retry bez duplikata. |
| M16-QA-074 | Druga EventLocation ulazi u occupancy konflikt paralelno sa publish-om. | Ceo publish, svi location upisi, audit/outbox/receipt rollback-uju. |
| M16-QA-075 | Kreiranje DRAFT Event-a bez publish/cancel polja. | Uspeva; sva tri lifecycle polja su NULL. DRAFT sa izmišljenim `published_at` ili cancellation poljem pada na DB CHECK-u. |
| M16-QA-076 | Materializacija UNRECORDED EventAttendance reda. | Uspeva bez actor/time/reason; bilo koje popunjeno polje pada na DB CHECK-u. |
| M16-QA-077 | SCHOOL/EXTERNAL conditional polja se ukrste. | Svaka nedozvoljena kombinacija capacity/interest/external-organizer polja pada na DB CHECK-u; validne kombinacije prolaze. |
| M16-QA-078 | CANCELLED registracija je bila ili nije bila potvrđena. | `cancelled_at`+reason su obavezni; `confirmed_at` se zadržava samo za ranije CONFIRMED_PARTICIPANT, a ne izmišlja za INTERESTED/SCHOOL red. |
| M16-QA-079 | Guardian cancellation request dobije Event lock tačno na cutoff-u. | `database_now == cutoff` je dozvoljen; registracija se otkazuje prema free/fee coordinator ugovoru. |
| M16-QA-080 | Guardian otvori ekran pre cutoff-a, ali command lock dobije 1 ms posle. | 409 `M16_CANCELLATION_DEADLINE_PASSED`; nema M16/M12 promene. |
| M16-QA-081 | Staff otkazuje pre starta, posle guardian deadline-a, sa permission/reason. | Dozvoljeno; fee-backed cancellation koristi isti M16+M12 atomski coordinator. |
| M16-QA-082 | Staff pokušava registration cancellation od `database_now >= starts_at`. | 409; koristi se EventAttendance, registracija i finansije se ne menjaju. |
| M16-QA-083 | Guardian otkazuje fee-backed registraciju sa split obligations. | M16 status, svi M12 obligations, compensating credit/ledger, audit/outbox/receipts commit-uju zajedno. |
| M16-QA-084 | M12 cancellation korak failuje posle simuliranog parcijalnog write-a. | Cela lokalna transakcija rollback; M16 registracija ostaje neterminalna i nema efektivnog M12 reda. |
| M16-QA-085 PAR | `CancelEvent` i poslednja registracija se trkaju. | Event lock daje potpuni poredak; nema registracije commit-ovane posle cancellation commit-a, a svaka ranije commit-ovana ulazi u M12 event cancellation obradu. |
| M16-QA-086 | Event sa 5.000 fee registracija se otkaže. | M16 request bounded: status+claims+jedan event commit; M12 barrier važi odmah, paginirani idempotent consumer završava bez duplog credit-a. |
| M16-QA-087 PAR | Dva zahteva dodaju isti `ALL_ACTIVE_PARTICIPANTS` audience sa null scope ID-em. | Nenull izvedeni `scope_key` i unique daju tačno jedan selector; nema SQL NULL duplikata. |
| M16-QA-088 | Svaki EventLocation tip se proba sa dozvoljenim i ukrštenim school/external/online poljima, pogrešnim space/location parom i vremenom van Event intervala. | Samo tačna conditional matrica prolazi; svi cross-tenant/ukršteni/van-interval redovi su safe 404 ili 422/DB-rejected bez occupancy side effect-a. |
| M16-QA-089 | Event description, external address i participant emergency snapshot se traže kroz log, outbox, list bez prava i index. | Nula plaintext/PII curenja; samo autorizovan detail dekriptuje dozvoljeno polje. Kompletna regresija zahteva 89/89, 0 failed/skipped/flaky. |

Suite: conditional-schema property test, DST fixtures, stvarno paralelni publish/capacity/cancel, cross-module create/cancel rollback, event cancellation barrier, snapshot restart, two-tenant API/DB, authorization revoke, offline i outbox/redaction. Kompletna M16 regresija ima 89 scenarija; prolaz zahteva 89/89, 0 skipped/flaky.
