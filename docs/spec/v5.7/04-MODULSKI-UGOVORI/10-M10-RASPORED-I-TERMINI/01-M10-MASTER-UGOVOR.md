---
tip: modulni-implementacioni-ugovor
modul-id: M10
naziv: Raspored, pravila ponavljanja i termini
status: SPEC_CANDIDATE
revizija: "1.3"
datum: 2026-09-08
schema-zavisnosti: [M08, M09]
read-portovi: [M04, M06, M08, M09]
application-guardovi: [M01, M03, M05]
izlazni-portovi-za: [M11, M13, M14, M15, M16, M18, M19, M20, M21, M28]
offline-policy: DENY
---

# M10 — Raspored, pravila ponavljanja i termini

## 1. Cilj, autoritet i granice

M10 je jedini vlasnik poslovne namere ponavljanja, materijalizovanih školskih termina, izuzetaka i konflikata grupe/osoblja. M08 ostaje jedini vlasnik zauzeća lokacije/prostora. M10 orkestrira M08 occupancy port u istoj lokalnoj transakciji modularnog monolita.

M10 poseduje `ScheduleSeries`, `ScheduleSeriesInstructor`, `TermOccurrence`, `TermOccurrenceInstructor`, `OccurrenceRevision`, `ScheduleGenerationRun` i interne conflict claim zapise za Group/Staff.

M10 ne poseduje Program/Location/Space, Group/Enrollment/StaffAssignment, attendance, fee/obligation, event, poruku ili notifikaciju. Ne šalje M14 komandu direktno; emituje outbox. H0 podržava nedeljno ponavljanje po jednom danu u sedmici po seriji. Složenije RRULE obrasce, cross-school konflikt osobe, zamenu termina drugim događajem i marketplace rezervacije ne uvodi potajno.

## 2. Entiteti i polja

### 2.1. Tipovi i vreme

- `InstantUTC`: TIMESTAMPTZ i RFC3339 UTC u API-ju.
- `LocalTime`: `HH:mm:ss`, bez offset-a.
- `LocalDate`: ISO datum.
- `IanaTimeZone`: validan naziv tz baze.
- `Version`: UInt64 CAS.
- Interval occurrence-a je poluotvoren `[starts_at,ends_at)`.

### 2.2. `ScheduleSeries`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id`, `group_id` | UUID | NE | M09 ACTIVE Group iste škole pri aktivaciji. |
| `location_id`, `space_id` | UUID | NE/DA | M08 Location/Space iste škole; null Space znači cela lokacija. |
| `name` | string(1..150) | NE | Plain text; nema child PII. |
| `weekday` | enum | NE | `MONDAY`…`SUNDAY`; jedna serija = jedan weekday. |
| `local_start_time` | LocalTime | NE | Lokalna poslovna namera. |
| `duration_minutes` | UInt32 | NE | `5..1440`. |
| `time_zone` | IanaTimeZone | NE | Snapshot; promena lokacije ne menja seriju tiho. |
| `valid_from`, `valid_until` | LocalDate | NE/DA | Inclusive datumi recurrence-a; valid_until ≥ valid_from. |
| `gap_policy` | enum | NE | H0 tačno `SHIFT_FORWARD_BY_GAP`. |
| `overlap_policy` | enum | NE | H0 tačno `EARLIER_OFFSET`. |
| `generation_horizon_days` | UInt16 | NE | Default 120, dozvoljeno `30..365`. |
| `status` | enum | NE | `DRAFT`, `ACTIVE`, `PAUSED`, `ENDED`. |
| `created_at`, `updated_at` | InstantUTC | NE | Server vreme. |
| `version` | UInt64 | NE | CAS. |

`UNIQUE(school_id,id)` i svi FK-ovi uključuju school_id. Multiple weekdays se modeluju sa više serija, ne nizom/opaque RRULE poljem.

### 2.3. `ScheduleSeriesInstructor`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id`, `series_id` | UUID | NE | Tenant-safe. |
| `staff_profile_id` | UUID | NE | M06 StaffProfile iste škole i važeća M09 Group assignment za period. |
| `role` | enum | NE | `LEAD`, `INSTRUCTOR`, `ASSISTANT`, `SPECIALIST`. |
| `starts_on`, `ends_on` | LocalDate | NE/DA | Effective period u seriji. |
| `version` | UInt64 | NE | CAS. |

Najviše jedan efektivni LEAD po occurrence-u. Izmena stvara/menja buduću nameru; prošli occurrence snapshot se ne prepisuje.

### 2.4. `TermOccurrence`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id`, `series_id`, `group_id` | UUID | NE | Tenant-safe snapshot reference. |
| `location_id`, `space_id` | UUID | NE/DA | Snapshot; Space null = cela lokacija. |
| `local_date`, `intended_local_start_time` | LocalDate/LocalTime | NE | Originalna poslovna namera. |
| `time_zone` | IanaTimeZone | NE | Zona korišćena za rezoluciju. |
| `starts_at`, `ends_at` | InstantUTC | NE | Autoritativni trenutci, start < end. |
| `utc_offset_seconds` | Int32 | NE | Primenenjeni offset, radi dokazivosti DST rezolucije. |
| `dst_resolution` | enum | NE | `EXACT`, `SHIFTED_FORWARD_GAP`, `EARLIER_OFFSET_OVERLAP`. |
| `status` | enum | NE | `SCHEDULED`, `CANCELLED`. |
| `cancellation_reason_code` | Code64 | DA | Obavezan za CANCELLED. |
| `source_series_version` | UInt64 | NE | Verzija namere koja ga je proizvela. |
| `created_at`, `updated_at` | InstantUTC | NE | Server vreme. |
| `version` | UInt64 | NE | CAS. |

`UNIQUE(school_id,series_id,local_date)` sprečava duplu materializaciju. `COMPLETED` nije trajni status: izveden je kada je `status=SCHEDULED` i `ends_at<=now`; M11 status ne menja M10 lifecycle.

### 2.5. `TermOccurrenceInstructor`

Snapshot dodele za konkretni occurrence: `id`, `school_id`, `occurrence_id`, `staff_profile_id`, `role`, `source_series_instructor_id`, `version`. Unique `(school_id,occurrence_id,staff_profile_id,role)`. Ne prepisuje se kada se kasnije izmeni serija; future regeneration/edit ga eksplicitno menja.

### 2.6. `OccurrenceRevision`

Append-only dokaz promene: `id`, `school_id`, `occurrence_id`, `revision_no`, `change_kind` (`GENERATED`, `RESCHEDULED`, `INSTRUCTORS_CHANGED`, `CANCELLED`, `REACTIVATED`), `before_hash`, `after_hash`, `reason_code`, `actor_account_id`, `command_id`, `created_at`. Unique occurrence/revision_no i occurrence/command_id. Hash je SHA-256 canonical poslovne projekcije, ne sadrži PII.

### 2.7. `ScheduleGenerationRun`

`id`, `school_id`, `series_id`, `range_start`, `range_end`, `source_series_version`, `status` (`RUNNING`, `SUCCEEDED`, `FAILED`), `attempt UInt16`, `generated_count UInt32`, `skipped_existing_count UInt32`, `failure_code nullable`, `command_id`, `started_at`, `finished_at nullable`, `version`. `range_end>=range_start`; attempt počinje od 1. RUNNING zahteva `finished_at=NULL`, `failure_code=NULL`; SUCCEEDED zahteva non-null `finished_at`, null failure i trajno dokazive count-ove; FAILED zahteva non-null `finished_at` i zatvoren `failure_code`. Jedan uspešan run po `(school_id,series_id,source_series_version,range_start,range_end)`; retry je novi attempt/red i ne menja istorijski terminalni run.

### 2.8. Conflict claims

M10 održava interne potvrđene claims za `GROUP` i `STAFF` resurse: school, resource type/id, occurrence_id, `[starts_at,ends_at)`, status. M08 održava Location/Space occupancy. Potvrda/izmena occurrence-a:

1. zaključava candidate resurse sortirane `GROUP < STAFF po UUID < LOCATION po UUID`;
2. proverava overlap potvrđenih claims iste škole;
3. poziva M08 occupancy potvrdu u istoj DB transakciji;
4. upisuje occurrence, snapshot, revisions, audit, outbox i receipt;
5. rollback jedne stavke vraća sve.

## 3. Poslovna pravila i invarijante

1. Aktivna serija čuva lokalnu nameru + IANA zonu; ne čuva samo ponavljajuće UTC vreme.
2. Aktivacija odmah materijalizuje od `max(valid_from, tenant_local_today)` do horizon-a. Dnevni idempotentni job održava najmanje 120 dana ili konfigurisan horizon.
3. Za nepostojeće lokalno vreme DST gap-a pomera se unapred tačno za dužinu gap-a i čuva `SHIFTED_FORWARD_GAP`. Za dvostruko vreme bira se raniji UTC offset i čuva `EARLIER_OFFSET_OVERLAP`.
4. `THIS_OCCURRENCE` menja samo izabrani budući occurrence i kreira revision.
5. `THIS_AND_FUTURE` završava staru seriju dan pre boundary lokalnog datuma i kreira naslednu seriju sa novim pravilom; prošlost ostaje.
6. `ENTIRE_SERIES` je dozvoljen samo kada nema započetog/prošlog occurrence-a. Inače 409 i UI mora ponuditi THIS_AND_FUTURE.
7. Započet ili završen occurrence ne može biti replaniran/cancelovan običnom komandom. Administrativna istorijska korekcija nije H0.
8. Cancel oslobađa Group/Staff claims i M08 occupancy u istoj transakciji; reactivation ponovo radi sve conflict provere.
9. Pause zaustavlja novu generaciju; već materijalizovani budući termini ostaju dok se eksplicitno ne otkažu. End je terminalan za generaciju.
10. Promena timezone, lokacije, trajanja ili instructor-a ne prepisuje prošlost.
11. Staff conflict se proverava unutar iste škole. M10 ne otkriva niti inferira dodelu iste osobe u drugoj školi; cross-school coordination nije H0.
12. Term može imati nula instructor snapshot-a, ali aktivacija serije bez LEAD zahteva warning acknowledgment + reason; tenant može konfigurisati LEAD_REQUIRED koji tada hard-failuje.
13. M10 ne koristi attendance za completed status i ne naplaćuje po održanom terminu.
14. Offline mutacija nije dozvoljena; optimistic UI nije konačan do server receipt-a.
15. Direct M10→M14 call je zabranjen; outbox consumer odlučuje o obaveštenju.
16. Notification-relevant integration event tipovi su tačno `OccurrenceRescheduledV1` i `OccurrenceCancelledV1`. Emituju se u owner commit-u sa minimalnim occurrence/group opaque ID-jem, old/new time range-om ili cancellation statusom/version-om; nemaju ime/kontakt/online URI. Drugi M10 događaj nije runtime alias jednog od ova dva tipa.

### 3.1. Edge cases

| # | Scenario | Ishod |
|---:|---|---|
| 1 | DST spring gap u 02:30. | Čuva intended 02:30, pomera instant za gap, resolution marker. |
| 2 | DST autumn overlap u 02:30. | Raniji offset; isti rezultat na retry-u/tz verziji dok persisted occurrence postoji. |
| 3 | Dva termina iste grupe paralelno. | Tačno jedan commit; drugi 409. |
| 4 | Različite grupe, isti Space. | M08 occupancy odbija drugi. |
| 5 | Različiti Space iste Location. | Dozvoljeno bez whole-location block-a. |
| 6 | THIS_AND_FUTURE boundary je danas, današnji termin je počeo. | Boundary se pomera na prvi nezapočeti lokalni occurrence ili 409 sa tim datumom; početi se ne menja. |
| 7 | Cancel retry posle timeout-a. | Isti receipt; claims su jednom oslobođeni. |
| 8 | Reactivate dok je prostor zauzet. | 409; ostaje CANCELLED. |
| 9 | Generation job duplo pokrenut. | Unique run/occurrence sprečava duplikate. |
| 10 | Location archived između forme i commit-a. | 409 reference inactive; potpuni rollback. |
| 11 | Cross-tenant instructor ID. | 404 safe. |
| 12 | tz baza se ažurira nakon materializacije. | Postojeći UTC/offset ostaje; nematerijalizovana budućnost koristi novu bazu i audit run. |

## 4. Tenant & Security Guard

Svaki request prolazi M01 session → M03 school/version → M05 permission → M10 resource/Group/Staff subject guard → precommit authorization version recheck. M09 StaffAssignment je uslov subject guard-a, ali nije permission grant. Cross-tenant/hidden occurrence ili participant context je safe 404.

M05 registruje:

| Permission | Opseg |
|---|---|
| `school.schedule.view` | Dozvoljen raspored; instructor samo dodeljene grupe, guardian/participant projection samo povezano dete preko M28. |
| `school.schedule.manage` | Series/occurrence create, edit, pause/end/cancel/reactivate. |
| `school.schedule.conflict_override` | Rezervisano; H0 ne može override hard Group/Staff/Space konflikt. |

Owner/Manager upravljaju; LimitedAdmin samo uz eksplicitni grant; Instructor/Substitute view samo dodeljeno; Guardian ne dobija administrativni M10 resource, već minimalni child projection; Payer nema schedule pravo samim payer odnosom.

List/calendar/count/cache/search tenant i subject filtriraju pre rezultata. Outbox/audit sadrži school, occurrence/series/group/resource opaque ID, time range, status/version/reason/correlation; nema imena dece, staff kontakta, online access URI-ja. Online URI se dobija naknadno iz M08 samo uz konkretan occurrence guard.

## 5. Lifecycle & transitions

### 5.1. ScheduleSeries

| From | Komanda | To | Efekat |
|---|---|---|---|
| — | CreateSeries | DRAFT | Nema occurrence-a. |
| DRAFT | ActivateSeries | ACTIVE | Validacija + puna početna horizon generacija u jednoj lokalnoj transakciji; neuspeh ostavlja DRAFT i nula occurrence-a. |
| ACTIVE | PauseSeries | PAUSED | Zaustavlja narednu generaciju. |
| PAUSED | ResumeSeries | ACTIVE | Recheck i dopuna horizon-a. |
| DRAFT/ACTIVE/PAUSED | EndSeries | ENDED | Zaustavlja generaciju; budući postojeći termini se eksplicitno rešavaju payload politikom `KEEP` ili `CANCEL`, obavezno. |
| ENDED | bilo šta | — | Terminalno. |

### 5.2. TermOccurrence

| From | Komanda | To |
|---|---|---|
| — | Generate/CreateOneOff | SCHEDULED |
| SCHEDULED, nezapočet | Reschedule | SCHEDULED + revision |
| SCHEDULED, nezapočet | CancelOccurrence | CANCELLED |
| CANCELLED, nezapočet | ReactivateOccurrence | SCHEDULED posle conflict provere |
| SCHEDULED, započet/završen | Reschedule/Cancel | Zabranjeno u H0 |

## 6. Error catalog

| Kod | HTTP | Opis |
|---|---:|---|
| `M10_VALIDATION_FAILED` | 422 | Polje, datum, zona ili interval nije validan. |
| `M10_NOT_FOUND_SAFE` | 404 | Resurs nije vidljiv. |
| `M10_PERMISSION_DENIED` | 403 | Akcija nije dozvoljena na poznatom resursu. |
| `M10_VERSION_CONFLICT` | 409 | CAS konflikt. |
| `M10_REFERENCE_INACTIVE` | 409 | Group/Location/Space/Staff više nije validan. |
| `M10_RECURRENCE_CONFLICT` | 409 | Duplicate series/local occurrence. |
| `M10_GROUP_TIME_CONFLICT` | 409 | Group overlap. |
| `M10_STAFF_TIME_CONFLICT` | 409 | Staff overlap iste škole. |
| `M10_SPACE_TIME_CONFLICT` | 409 | M08 occupancy conflict. |
| `M10_OCCURRENCE_ALREADY_STARTED` | 409 | H0 istorijska promena odbijena. |
| `M10_EDIT_SCOPE_NOT_ALLOWED` | 409 | ENTIRE_SERIES ili boundary nije dozvoljen. |
| `M10_LEAD_ACK_REQUIRED` | 409 | Nedostaje lead/reason acknowledgment. |
| `M10_TRANSITION_NOT_ALLOWED` | 409 | Lifecycle greška. |
| `M10_IDEMPOTENCY_KEY_REUSED` | 409 | Isti ključ, drugi payload/scope. |
| `M10_PRECONDITION_REQUIRED` | 428 | Nedostaje expected_version. |
| `M10_GENERATION_IN_PROGRESS` | 409 | Drugi aktivni run istog scope-a. |
| `M10_DEPENDENCY_UNAVAILABLE` | 503 | M08/M09 autoritativni port nije dostupan. |
| `M10_RATE_LIMITED` | 429 | Limit. |

## 7. API, idempotency, concurrency i NFR

Komande: `CreateSeries`, `ActivateSeries`, `PauseSeries`, `ResumeSeries`, `EndSeries`, `EditSchedule(scope)`, `CreateOneOffOccurrence`, `CancelOccurrence`, `ReactivateOccurrence`, `GenerateHorizon`. Svaka write komanda ima active school, Idempotency-Key, correlation_id; mutacija expected_version; reason gde je propisan. Receipt 30 dana. Isti key/hash vraća isti rezultat; različit hash 409.

Jedna serija ima jedan weekday i horizon najviše 365 dana, zato jedna aktivacija/generation komanda stvara najviše 53 occurrence-a. Cela komanda je jedna lokalna transakcija: Series status, svi novi occurrence-i/claims/occupancy/revisions, run, receipt, audit i outbox commit-uju zajedno ili ništa. Dnevni scheduler obrađuje svaku seriju kao zasebnu idempotentnu komandu i pravi novi run samo za nedostajući nastavak horizonta. Retry koristi unique series/local-date i vraća isti receipt, bez partial-visible stanja.

Minimalni indeksi: occurrence `(school_id,starts_at,id)`, `(school_id,group_id,starts_at)`, `(school_id,series_id,local_date)`, instructor `(school_id,staff_profile_id,occurrence_id)`, conflict range indeks prema izabranom DB-u, generation unique. Calendar query zahteva range ≤93 dana, cursor/page default 100 max 500. p95 read ≤300 ms i single occurrence write ≤600 ms bez outage-a; scheduler ima tenant-fair red serija i nikad jednu cross-tenant transakciju. Query plan i stvarni parallel conflict test su DoD.

## 8. Acceptance sažetak

M10 prolazi samo uz QA iz `02-M10-QA-I-TRACEABILITY.md`: poznate DST fixture zone/datume, tri edit scope-a, započeti termin, paralelni Group/Staff/Space konflikt, restart generation job-a, tenant concealment, minimalni outbox i negativnu pretragu M10→M14 direct call-a i trajnog `COMPLETED` statusa.
