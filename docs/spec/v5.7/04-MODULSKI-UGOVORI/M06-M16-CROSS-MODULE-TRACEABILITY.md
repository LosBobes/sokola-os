---
tip: cross-module-traceability
obim: M06-M16
status: SPEC_CANDIDATE
datum: 2026-09-15
exclude-from-programmer-candidate-until-complete: false
---

# M06–M16 — Cross-module traceability

Ovo je jedina aktivna putanja za obostranu M06–M16 traceability matricu. Autoritet za dependency smerove je [[00-M00-OBIM-I-ARHITEKTURA/02-M00-ARHITEKTURA-MODULI-I-ZAVISNOSTI#4.1. Aktivni M00–M16 Core registar|M00 registar]], a za zajedničke granice [[../00-DCR-AKTIVNI-v5.7/DCR-20260907-01-Kanonska-Konsolidacija-M00|DCR-20260907-01 revizija 2.3]]. Sve veze ispod su specifikovane; stanje koda ostaje `CODE_REPOSITORY_UNVERIFIED` do repo pregleda.

## M08–M12 zatvorene veze

| Producer → Consumer | Vrsta i ugovor | Tenant/failure garancija | Pozitivan / negativan dokaz |
|---|---|---|---|
| M04 → M08 | SCHEMA: School tenant anchor | composite school FK; cross-school safe 404 | M08 QA 1/6, 26/42 |
| M08 → M09 | SCHEMA/READ: Program, optional Branch/Location/Space defaults | ACTIVE reference pri Group aktivaciji; no cascade | M09 QA 1–6 / 55,60 |
| M06 → M09 | SCHEMA/READ: ParticipantProfile, StaffProfile | isti school; eligibility/as-of, no Person copy | M09 QA 11–16 / 13,39–44 |
| M09 → M10 | SCHEMA/READ: Group, staff assignment | assignment je subject, ne permission; fail-closed outage | M10 QA 4–7,37–41 / 47–50,55 |
| M08 → M10 | TRANSACTIONAL PORT: occupancy confirm/cancel | isti local transaction; Location lock; space conflict rollback | M10 QA 30–35 / 55,61 |
| M09+M10 → M11 | READ: roster-as-of + occurrence | frozen roster, no back-write; outage no partial session | M11 QA 2–7 / 60,68 |
| M05 → M11 client | CAPABILITY: offline lease | actor/school/session bound; sync reauth; purge | M11 QA 40–57 / M05 QA 153,160 |
| M07 → M12 | SCHEMA/READ: Family/Payer basis | finance-only, split shares, no child-data grant | M12 QA 21–30 / 73–78 |
| M08/M09/M16 → M12 | READ: Program/Group/Event fee scope | M12 owns FeeRule/amount; source is immutable ref | M12 QA 5–20 / 91–94 |
| M12 → M14 | OUTBOX: finance event | async minimal payload; no direct call/no push PII | M12 QA 88–89 |
| M10/M11 → M14 | OUTBOX: schedule/attendance events | producer never waits; attendance event ne znači automatsku parent poruku | M10 QA 55–59 / M11 QA 61–62 |
| M13 → M15 | READ: document current version/access | publish preview hash vezan za version; outage/stale version zaustavlja publish | M13 QA 12–18 / M15 QA 13–24 |
| M09/M10/M12/M16 → M14 | OUTBOX: versioned minimal domain event | nema direktnog poziva; unknown schema quarantine; recipient current-basis | M14 QA 1–18, 60 |
| M07/M09/M12/M16 → M15 | READ: typed access/subject scope | isti school; hidden/cross-tenant safe 404; nema reverse write-a | M15 QA 25–43, 66–72 |
| Application coordinator → M16 + M12 | APPLICATION_ORCHESTRATION nad dva owner porta | M12 poseduje fee/obligation; fee registration ili pojedinačno otkazivanje i svi obavezni finance write-ovi su jedna lokalna transakcija; Event→Registration→M12 lock redosled; M16 ne poziva M12 | M16 QA 56–58, 79–84 / M12 QA 99–104 |
| M16 → M12 | OUTBOX/READ BARRIER: `EventCancelledV1` + current Event fact | Event cancel odmah blokira collectible read/instruction/reminder/allocation; M12 job materializuje svaki Assessment idempotentno; nema M12 write-a u M16 niti reverse call-a pod M12 lock-om | M16 QA 49–50, 85–86 / M12 QA 103–107 |
| M16 → M14 | OUTBOX: event lifecycle | M16 commit ne čeka delivery i ne poziva M14 | M16 QA 49–50, 59–60 / M14 QA 1–14 |
| M15 → M16 | READ: EVENT scope validation | M15 čita event tenant/status; M16 ne zavisi od M15 | M15 QA 29–31 / M16 QA 67–68 |

Za ove redove nema reverse domain import-a: M08 ne poziva M10; M09 ne čita cenu/attendance; M10 ne čita M11; M11 ne menja M12; M16 ne poziva M12/M14/M15; M12 ne menja M09/M16 source entitet. Application orchestration nije dozvola za direktan tuđi table write ili poziv M12→M16 tokom već započete M16 komande.

Matrica će se smatrati potpunom tek kada za svaki stvarni par zavisnih modula navede:

- tip veze: `SCHEMA_DEPENDENCY`, `READ_PORT`, `CONSUMES_EVENT` ili `APPLICATION_ORCHESTRATION`;
- vlasnički entitet/port/event i njegovu verziju;
- tačan producer i consumer paragraf;
- tenant, authorization, idempotency i failure semantiku;
- najmanje jedan pozitivan i jedan negativan integration test;
- potvrdu da nema suprotnog domain importa ili direktnog upisa u tuđu tabelu.

Matrica je `SPEC_CANDIDATE`: potvrđuje ugovornu pokrivenost M06–M16, ali ne implementaciju. Ulazi u programmer candidate samo ako finalni overlay i svi validatori prođu.
