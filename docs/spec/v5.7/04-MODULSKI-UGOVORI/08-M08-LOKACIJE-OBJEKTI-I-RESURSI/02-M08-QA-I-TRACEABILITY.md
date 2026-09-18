---
tip: qa-i-traceability
modul-id: M08
status: SPEC_CANDIDATE
revizija: "1.2"
datum: 2026-09-08
obavezni-scenariji: 52
---

# M08 — QA i traceability

Svaki scenario je automatizovan gde se proverava schema, command, concurrency ili authorization. Seed koristi School A/B, dva Branch-a, dve lokacije i najmanje dva Space-a u istoj lokaciji; nema realnih podataka dece.

| QA ID | Scenario | Očekivani dokaz | Master trag |
|---|---|---|---|
| `M08-QA-001` | School bez Branch kreira Location. | Uspeh; branch null; tenant School. | §2.2, §3 |
| `M08-QA-002` | Dva Branch-a istog code-a u školi. | Drugi 409 `M08_CODE_CONFLICT`. | §2.2, §6 |
| `M08-QA-003` | Isto ime Branch-a, drugi case/Unicode ekvivalent. | 409 name conflict. | §2.2 |
| `M08-QA-004` | Branch A se deaktivira. | Istorija ostaje; nov Location ne može da ga izabere. | §3, §5 |
| `M08-QA-005` | Reactivate non-archived Branch. | ACTIVE + version/audit/outbox. | §5 |
| `M08-QA-006` | Archive Branch sa aktivnom Location. | 409 dependency; bez promene. | §3, §6 |
| `M08-QA-007` | Jedan Program koriste grupe u dva grada. | Jedan Program ID; nema kopije po Branch-u. | §2.3, §3 |
| `M08-QA-008` | Program category ima nepoznat tenant code. | Prihvaćen kao opisni Code64; bez auth/billing efekta. | §2.3 |
| `M08-QA-009` | Archive Program sa aktivnom Group. | 409 dependency. | §3, §5 |
| `M08-QA-010` | M09 koristi Program škole B u školi A. | Safe 404/composite FK odbija. | §2.1, §4 |
| `M08-QA-011` | Fizička Location sa adresom i validnim country code. | ACTIVE. | §2.4 |
| `M08-QA-012` | Fizička Location bez adrese/reason-a. | 422 `M08_PHYSICAL_ADDRESS_REQUIRED`. | §2.4, §6 |
| `M08-QA-013` | ONLINE Location bez access reda koristi se u terminu. | 422 access required. | §2.4–2.5 |
| `M08-QA-014` | Location IANA timezone ne postoji. | 422; nema fallback offseta. | §2.1, §6 |
| `M08-QA-015` | Branch timezone promenjen posle occurrence-a. | Stari UTC ne menja se; novi rule koristi novu zonu. | §3 |
| `M08-QA-016` | Cross-tenant Location detail. | Isti safe 404 kao random UUID. | §4 |
| `M08-QA-017` | Location list actor škole A. | Nema B redova ni count/suggestion hint-a. | §4, §7 |
| `M08-QA-018` | Set online URI sa HTTP. | 422 invalid; nema ciphertext/log-a. | §6, §7 |
| `M08-QA-019` | Rotacija online URI-ja. | Stari REVOKED, novi ACTIVE, jedna transakcija. | §2.5, §5 |
| `M08-QA-020` | Actor ima structure.view bez occurrence access-a. | URI 403/no-store; metadata ostaje dozvoljena. | §4 |
| `M08-QA-021` | Guardian sa validnim child occurrence pristupom. | Dobija samo URI za taj occurrence, bez liste tajni. | §4, §7 |
| `M08-QA-022` | Inspect log/audit/outbox posle URI read-a. | Nema URI/ciphertext/fingerprint/child PII. | §4, §8 |
| `M08-QA-023` | Location bez Space dobija whole-location block. | CONFIRMED. | §2.7 |
| `M08-QA-024` | Dva različita Space-a isto vreme; zatim vreme napreduje 32 dana bez cancel komande. | Oba su CONFIRMED i ostaju takva; nema implicitnog expiry-ja, PENDING claim-a ni cleanup job-a. | §2.7, §3 |
| `M08-QA-025` | Isti Space preklapanje. | Tačno jedan; drugi 409. | §2.7 |
| `M08-QA-026` | Whole-location i Space paralelno. | Location lock; tačno jedan uspeh. | §2.7, §8 |
| `M08-QA-027` | Space block postoji, whole-location dolazi kasnije. | 409 conflict. | §2.7 |
| `M08-QA-028` | Interval A završava kad B počinje. | Nema konflikta. | §3 |
| `M08-QA-029` | starts_at=end ili >end. | 422 range invalid. | §2.7, §6 |
| `M08-QA-030` | Interval duži od 31 dana u H0. | 422 range invalid. | §2.7 |
| `M08-QA-031` | TERM_OCCURRENCE bez source ref. | 422 source invalid. | §2.7 |
| `M08-QA-032` | Isti source pokuša drugi active block. | Idempotent isti zahtev ili 409 za drugi payload. | §2.7, §8 |
| `M08-QA-033` | Cancel block pa rezerviši isti slot. | Novi confirm uspeva. | §5 |
| `M08-QA-034` | Dva cancel-a sa istim request/payload. | Isti rezultat; jedan audit/outbox. | §8 |
| `M08-QA-035` | Cancel sa stale version. | 409 stale; blok ostaje. | §6 |
| `M08-QA-036` | Space capacity null. | Validno; nema pretpostavljenog limita. | §2.6 |
| `M08-QA-037` | Capacity 0 ili 100001. | 422 invalid. | §2.6, §6 |
| `M08-QA-038` | Smanjenje capacity ispod enrollment count-a. | Soft warning; nema M09 mutacije. | §3 |
| `M08-QA-039` | 51 equipment tags. | 422 limit; ništa nije skraćeno. | §2.6, §8 |
| `M08-QA-040` | Equipment tag se koristi kao booking dokaz. | Odbijeno; nema takvog porta. | §1.2, §3 |
| `M08-QA-041` | Archive Space sa budućim block-om. | 409 dependency. | §3, §5 |
| `M08-QA-042` | Inactivate Space sa budućim block-om. | Dozvoljeno; postojeći block ostaje; novi nije dozvoljen. | §3, §5 |
| `M08-QA-043` | Promena Location branch-a uz budući occurrence. | 409 ili ista orkestracija replanira; nema tihog reparent-a. | §3 |
| `M08-QA-044` | Dva update-a istog Space/version-a. | Jedan uspeh, drugi stale. | §8 |
| `M08-QA-045` | Isti idempotency key, drugi payload. | 409 key reused; jedan side effect. | §6, §8 |
| `M08-QA-046` | Identical concurrent request ostaje in-flight. | Bounded wait pa 409 + Retry-After 1; bez duplikata. | §8 |
| `M08-QA-047` | Header/body request UUID mismatch. | 400; nema business upisa. | §6–7 |
| `M08-QA-048` | Permission opozvan pre commit-a update-a. | 409 concurrent authorization; rollback. | §4, §8 |
| `M08-QA-049` | Migracija COALESCE redova ima stvarni konflikt. | Cutover blokiran; exception report; nema proizvoljnog pobednika. | §9 |
| `M08-QA-050` | Drugi migration run. | No-op/reconciliation identičan; nema dual mastera. | §9 |
| `M08-QA-051` | Jedan M16 događaj ima dve `EventLocation` instance u dve slobodne lokacije. | Dva CONFIRMED bloka sa `source_kind=EVENT`, svaki `source_ref_id=EventLocation.id`; retry ne duplira. | §2.7, §7–8 |
| `M08-QA-052` | Druga od dve event lokacije je u konfliktu tokom publish-a. | Oba occupancy upisa i M16 publish rollback-uju; nema polupublikovanog događaja ni prvog bloka. | §2.7, §7–8 |

## Seed

- School A: timezone `Europe/Belgrade`; Branch `BG`, `NS`; Program `FOOTBALL`, `BALLET`.
- Location A1: fizička, dva Space-a; Location A2: ONLINE sa rotiranim secretom.
- School B: isti prikazni nazivi i različiti UUID-evi radi cross-tenant testova.
- Occupancy intervali: dodirni, preklapajući, whole-location i dva različita Space-a.
