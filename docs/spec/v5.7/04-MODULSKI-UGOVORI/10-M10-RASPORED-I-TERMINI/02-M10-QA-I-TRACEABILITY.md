---
tip: qa-traceability
modul-id: M10
status: SPEC_CANDIDATE
revizija: "1.3"
datum: 2026-09-08
obavezni-scenariji: 67
---

# M10 — QA i traceability

Clock i tzdata verzija su fiksirani u testu. DST fixture koristi zonu sa poznatim gap/overlap datumima iz verzije tzdata deklarisane u test manifestu; očekivani UTC instant je zapisan, ne računa se iz lokalne zone test mašine. `PAR` koristi odvojene transakcije i commit barijeru.

| ID | Scenario | Očekivanje |
|---|---|---|
| M10-QA-001 | Create DRAFT weekly series. | 201, bez occurrence-a. |
| M10-QA-002 | weekday/time/duration invalid. | 422. |
| M10-QA-003 | Numeric UTC offset umesto IANA zone. | 422. |
| M10-QA-004 | Aktivacija validne serije. | ACTIVE + horizon + receipt. |
| M10-QA-005 | INACTIVE Group/Location. | 409, rollback. |
| M10-QA-006 | Cross-tenant Space/Staff. | 404 safe. |
| M10-QA-007 | Multiple weekday array payload. | 422; više serija je ugovor. |
| M10-QA-008 | Spring DST gap. | Tačan shifted UTC/offset/resolution. |
| M10-QA-009 | Autumn DST overlap. | Tačan earlier-offset UTC/resolution. |
| M10-QA-010 | Normal local time. | EXACT. |
| M10-QA-011 | Retry generation istog range-a. | Nema duplikata; skipped count/isti receipt. |
| M10-QA-012 PAR | Dva generation run-a. | Jedan authoritative rezultat, unique occurrence-i. |
| M10-QA-013 | Simuliran failure pre commit-a horizon generacije. | Series ostaje DRAFT/prethodno stanje, run/occurrence/claims/audit/outbox/receipt se ne vide; retry pravi tačno jedan kompletan rezultat. |
| M10-QA-014 | Horizon 29/366. | 422; 30..365 samo. |
| M10-QA-015 | Jedna serija preko valid_until. | Ne generiše posle datuma. |
| M10-QA-016 | Pause. | Nema nove generacije; stari future ostaje. |
| M10-QA-017 | Resume. | Dopunjava horizon posle recheck-a. |
| M10-QA-018 | End sa KEEP politikom. | ENDED; future ostaje. |
| M10-QA-019 | End sa CANCEL politikom. | Future cancel; započeti ostaju. |
| M10-QA-020 | End bez politike uz future. | 422. |
| M10-QA-021 | THIS_OCCURRENCE reschedule. | Samo izabrani future termin + revision. |
| M10-QA-022 | THIS_AND_FUTURE. | Stara serija skraćena, nova nasledna; prošlost ista. |
| M10-QA-023 | ENTIRE_SERIES pre prvog termina. | Dozvoljeno. |
| M10-QA-024 | ENTIRE_SERIES posle početog termina. | 409 sa dozvoljenim scope-om. |
| M10-QA-025 | Edit započetog occurrence-a. | 409. |
| M10-QA-026 | Cancel future. | CANCELLED, claims/occupancy oslobođeni. |
| M10-QA-027 | Cancel retry. | Isti receipt, jedan revision/event. |
| M10-QA-028 | Reactivate bez konflikta. | SCHEDULED + novi claims. |
| M10-QA-029 | Reactivate sa konfliktom. | 409, ostaje CANCELLED. |
| M10-QA-030 PAR | Ista Group, preklapajući termini. | Tačno jedan commit. |
| M10-QA-031 PAR | Isti Staff, dve Group. | Tačno jedan commit u istoj školi. |
| M10-QA-032 PAR | Isti Space, različite Group. | M08 dozvoli tačno jedan. |
| M10-QA-033 | Različiti Space iste Location. | Oba mogu uspeti. |
| M10-QA-034 | Whole-location block protiv Space. | 409. |
| M10-QA-035 | Intervals end==start. | Nema konflikta. |
| M10-QA-036 | Isto globalno lice Staff u drugoj školi. | Nema cross-tenant query/leak/block u H0. |
| M10-QA-037 | Nema LEAD, hard tenant policy. | 409. |
| M10-QA-038 | Nema LEAD, warning policy bez ack. | 409 ack required. |
| M10-QA-039 | Nema LEAD uz ack/reason. | Uspeh + audit. |
| M10-QA-040 | Dva efektivna LEAD-a. | 409. |
| M10-QA-041 | Staff assignment istekao pre termina. | 409 reference inactive. |
| M10-QA-042 | Location timezone promenjen posle Series create. | Series snapshot/occurrence ostaje isti. |
| M10-QA-043 | tzdata update posle materializacije. | Postojeći occurrence ne menja UTC. |
| M10-QA-044 | Duplicate local date iste serije. | DB unique odbija. |
| M10-QA-045 | Query range 94 dana. | 422/413 prema ugovoru; ne puni memoriju. |
| M10-QA-046 | Page >500. | Clamp/reject deterministički. |
| M10-QA-047 | Instructor vidi tuđu Group. | 404/403 po concealment, bez detalja. |
| M10-QA-048 | Instructor vidi dodeljenu Group. | Minimalna projekcija. |
| M10-QA-049 | Guardian admin M10 endpoint. | Odbijeno; koristi M28 composition. |
| M10-QA-050 | Payer schedule zahtev. | Odbijeno. |
| M10-QA-051 | List total/cache. | Tenant+subject filter pre total/cache. |
| M10-QA-052 | Missing expected version. | 428. |
| M10-QA-053 | Stale version. | 409; nema partial claims. |
| M10-QA-054 | Isti idempotency key/drugi payload. | 409. |
| M10-QA-055 | Dependency failure posle conflict check. | 503 + potpuni rollback. |
| M10-QA-056 | Audit write failure. | Business write rollback. |
| M10-QA-057 | Outbox payload. | Nema imena/kontakta/online URI-ja. |
| M10-QA-058 | Offline write. | Deny; nema finalnog optimistic statusa. |
| M10-QA-059 | Direct call M10→M14 pretraga. | Nema aktivne runtime zavisnosti. |
| M10-QA-060 | Trajni COMPLETED enum pretraga. | Ne postoji; completed je projekcija. |
| M10-QA-061 | DB school mismatch FK. | Odbijeno na DB nivou. |
| M10-QA-062 | Concurrent authorization revoke pre commit-a. | Precommit recheck odbija i rollback. |
| M10-QA-063 | One-off occurrence. | Ista conflict/security/idempotency pravila. |
| M10-QA-064 | One-off preko 24h. | 422; duration max. |
| M10-QA-065 | ScheduleGenerationRun je RUNNING sa `finished_at` ili `failure_code`. | DB CHECK odbija; nema parcijalno vidljivih occurrence-a/claims-a. |
| M10-QA-066 | SUCCEEDED/FAILED generation run conditional polja. | SUCCEEDED zahteva finished time i null failure; FAILED zahteva finished time i zatvoren failure code. |
| M10-QA-067 | Retry nakon FAILED run-a za isti scope. | Novi attempt/red; istorijski FAILED ostaje nepromenjen, unique occurrence-i sprečavaju duplikate. |

## Traceability

| Garancija | Normativno | QA |
|---|---|---|
| Local intent, UTC i DST | 01 §2–3 | 2–10, 42–43 |
| Generation i idempotency | 01 §2.7, §7 | 4, 11–20, 44, 54–55, 65–67 |
| Edit scopes/lifecycle | 01 §3, §5 | 16–29 |
| Conflict concurrency | 01 §2.8 | 30–36, 53, 61 |
| Tenant/RBAC/privacy | 01 §4 | 6, 36, 47–51, 57, 62 |
| Granice modula | 01 §1, §3 | 57–60 |
