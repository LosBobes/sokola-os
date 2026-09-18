---
tip: modulni-implementacioni-ugovor
modul-id: M16
naziv: Događaji Light
status: SPEC_CANDIDATE
revizija: "1.4"
datum: 2026-09-15
schema-zavisnosti: [M04, M08, M09]
read-portovi: [M06, M07, M08, M09, M10]
application-orchestration: [neutral-coordinator-M16-plus-M12, processing-authorization-coordinator-M16-plus-M17]
application-guardovi: [M01, M03, M05]
izlazni-portovi-za: [M12, M14, M15, M17, M18, M19, M21, M25, M27, M28, M30]
offline-policy: DENY
---

# M16 — Događaji Light

## 1. Cilj, autoritet i granice

M16 vodi školske i gostujuće/spoljne događaje, audience, lokacije, prijave, frozen participant snapshot i posebnu event evidenciju dolaska. Jedan `Event` model ima diskriminator `origin_type` sa tačno `SCHOOL_ORGANIZED` ili `EXTERNAL_ORGANIZER`; ne postoji drugi GuestEvent ili fake tenant.

M16 ne poseduje cenu/kotizaciju/obavezu/uplatu (M12), redovni raspored/prisustvo (M10/M11), dokument (M15), notifikaciju (M14), komunikaciju (M13), guardian/person/group/location (M06–M09) niti standalone organizer workspace. Events Pro agenda, turnirski bracket, smeštaj, prevoz, marketplace i public ticket commerce nisu H0.

## 2. Entiteti, polja i relacije

Svi aggregate/command tenant zapisi sa surrogate `id` imaju `school_id`, `UNIQUE(school_id,id)` i kompozitne FK-ove. Keyed projection/receipt bez surrogate ID-a mora imati eksplicitni kompozitni PK/UNIQUE koji počinje sa `school_id` i nijedan tenant-less lookup. UTC trenutak + School IANA lokalna namera se čuvaju zajedno.

Precizni tipovi: svi `id`/`*_id` su UUID; `local_start/local_end` su `TIMESTAMP WITHOUT TIME ZONE`, `timezone` je IANA `varchar(64)`, izvedeni `starts_at/ends_at` i svi ostali `*_at` su UTC `TIMESTAMPTZ`; `version` je `BIGINT >= 1`; kapaciteti su `INTEGER >= 0`; ciphertext je `BYTEA`; snapshot hash je lowercase `CHAR(64)`. Kodovi/enumi imaju DB `CHECK`/registry FK. Polje je obavezno osim kada eksplicitno piše nullable; conditional polja imaju DB constraint prema `origin_type`/`location_type`.

`Event`: `id`, `school_id`, `origin_type`, `title` varchar(200), `description_ciphertext BYTEA`, `description_key_version`, `category` (`COMPETITION`,`PERFORMANCE`,`WORKSHOP`,`SEMINAR`,`CAMP`,`TRIP`,`EXAM`,`SHOWCASE`,`FESTIVAL`,`TOURNAMENT`,`CELEBRATION`,`MEETING`,`OTHER`), `status` (`DRAFT`,`PUBLISHED`,`CANCELLED`), `local_start`, `local_end`, `timezone`, `starts_at`, `ends_at`, `responsible_staff_profile_id`, `registration_opens_at`, `registration_closes_at`, `cancellation_deadline_at nullable`, `location_tbd` boolean default false, `capacity_mode nullable` (`NO_LIMIT`,`WARNING`,`HARD_LIMIT`), `capacity_limit nullable`, `school_allocated_capacity nullable`, `interest_flow_enabled nullable`, `external_organizer_name nullable varchar(200)`, `external_reference nullable`, `published_at nullable`, `cancelled_at nullable`, `cancel_reason_code nullable`, `version`, `created_at`, `updated_at`. `external_organizer_name` je samo minimizovan display naziv i ne sme sadržati kontakt, credential ili ličnu belešku; opis se dekriptuje samo za autorizovan prikaz i nikad ne loguje/eventuje. Nema `fee_amount`, `price`, `currency`, `due_date` ili document ID.

`EventAudience`: `id`, `school_id`, `event_id`, `audience_type` (`ALL_ACTIVE_PARTICIPANTS`,`PROGRAM`,`GROUP`,`PARTICIPANT`), `scope_id nullable`, `scope_key varchar(128)`, `created_at`. ALL zahteva `scope_id=NULL` i literal `scope_key=ALL_ACTIVE_PARTICIPANTS`; ostali tipovi zahtevaju scope ID i tačan `scope_key=PROGRAM|GROUP|PARTICIPANT:<lower-uuid>`. DB CHECK vezuje tip, ID i ključ; unique `(school_id,event_id,audience_type,scope_key)` sprečava duplikate i za ALL selector bez SQL NULL rupe.

`EventLocation`: `id`, `school_id`, `event_id`, `location_type` (`SCHOOL_LOCATION`,`EXTERNAL_LOCATION`,`ONLINE`), `location_id nullable`, `space_id nullable`, `external_location_name nullable`, `address_ciphertext nullable`, `online_access_id nullable` M08 encrypted access, `sequence_no UInt16`, `starts_at`, `ends_at`, `version`; unique `(school_id,event_id,sequence_no)`. SCHOOL_LOCATION zahteva `location_id`, dozvoljava `space_id` samo iz iste lokacije i zabranjuje sva external/online polja. EXTERNAL_LOCATION zahteva non-empty `external_location_name+address_ciphertext` i sva school/online polja null. ONLINE zahteva `online_access_id` i sva school/external polja null. `ends_at>starts_at` i blok je unutar Event intervala. Za svaku SCHOOL_LOCATION instancu M08 occupancy koristi `source_kind=EVENT` i `source_ref_id=EventLocation.id`. Svi blokovi kompletnog location skupa nastaju ili se menjaju u istoj lokalnoj transakciji sa publish/material location izmenom; `Event.id` se ne koristi kao jedinstveni occupancy source.

`EventLocationSnapshot`: immutable `id`, `school_id`, `event_id`, `event_location_id`, `display_label_ciphertext`, `address_or_online_reference_ciphertext nullable`, `captured_at`, `snapshot_hash`; unique `(school_id,event_id,event_location_id)`. Kreira se pri početku; ne sadrži više od operativno potrebnog i nema update/delete u redovnom lifecycle-u.

`EventRegistration`: `id`, `school_id`, `event_id`, `participant_profile_id`, `requested_by_person_id`, `authorization_basis_type`, `authorization_basis_id`, `status`, `status_reason_code nullable`, `registered_at`, `cancelled_at nullable`, `confirmed_at nullable`, `reactivated_from_registration_id nullable`, `version`, `created_at`, `updated_at`. Status zavisi od origin-a: SCHOOL=`REGISTERED|CANCELLED`; EXTERNAL=`INTERESTED|CONFIRMED_PARTICIPANT|CANCELLED`. Jedan neterminalan zapis po event/participant; istorijski otkazani se ne prepisuje.

`EventParticipantSnapshot`: immutable `id`, `school_id`, `event_id`, `participant_profile_id`, `source_registration_id`, `display_label_ciphertext`, `emergency_operational_ciphertext nullable` samo kada neutralni application coordinator uz M17 `AuthorizeProcessing` dokaz preda važeći purpose/version/retention snapshot, `captured_at`, `snapshot_hash`; unique `(school_id,event_id,participant_profile_id)`. M16 čuva samo odobreni minimalni snapshot i ne poziva M17 direktno. SCHOOL uzima REGISTERED; EXTERNAL samo CONFIRMED_PARTICIPANT. INTERESTED nikad nije učesnik. Nema update/delete u redovnom lifecycle-u; kasni staff add je novi red.

`EventAttendance`: `id`, `school_id`, `event_id`, `participant_profile_id`, `status` (`UNRECORDED`,`ARRIVED`,`NO_SHOW`), `recorded_by_account_id nullable`, `recorded_at nullable`, `corrected_at nullable`, `reason_code nullable`, `version`, `created_at`, `updated_at`. Unique event/participant. Nije M11 AttendanceRecord i ne utiče na M12 billing.

### 2.1 Conditional-null i origin CHECK matrica

- `Event.status=DRAFT` zahteva `published_at`, `cancelled_at` i `cancel_reason_code` sva `NULL`; `PUBLISHED` zahteva non-null `published_at` i null cancellation polja; `CANCELLED` zahteva non-null `cancelled_at` i `cancel_reason_code`, dok `published_at` ostaje non-null samo ako je događaj prethodno bio objavljen.
- `origin_type=SCHOOL_ORGANIZED` zahteva non-null `capacity_mode` i `interest_flow_enabled=NULL`, `school_allocated_capacity=NULL`, `external_organizer_name=NULL`; `capacity_limit` je non-null tačno za `WARNING|HARD_LIMIT`, a null za `NO_LIMIT`.
- `origin_type=EXTERNAL_ORGANIZER` zahteva `capacity_mode=NULL`, non-null `interest_flow_enabled` i `external_organizer_name`; `school_allocated_capacity` je non-null i `>=0` kada je confirmation omogućen, a `capacity_limit` je uvek null. `external_reference` ostaje opcion.
- SCHOOL `REGISTERED` ima `confirmed_at=NULL`, `cancelled_at=NULL`, `status_reason_code=NULL`; SCHOOL `CANCELLED` zahteva `cancelled_at` i zatvoren `status_reason_code`. EXTERNAL `INTERESTED` ima oba lifecycle vremena null; `CONFIRMED_PARTICIPANT` zahteva `confirmed_at` i null `cancelled_at`; EXTERNAL `CANCELLED` zahteva `cancelled_at` i reason, a zadržava `confirmed_at` samo ako je ranije bio potvrđen.
- Nova reaktivirana registracija zahteva `reactivated_from_registration_id` ka CANCELLED registraciji istog `(school_id,event_id,participant_profile_id)`; originalna registracija ima ovo polje null. Ciklus ili lanac koji preskače neposredni prethodni otkazani red nije dozvoljen.
- `EventAttendance.status=UNRECORDED` zahteva sva actor/time/reason polja null. `ARRIVED|NO_SHOW` zahtevaju `recorded_by_account_id` i `recorded_at`; prvi unos ima `corrected_at=NULL` i `reason_code=NULL`, a promena već evidentiranog statusa zahteva non-null `corrected_at` i zatvoren correction `reason_code`. Korekcija koja ostavlja isti status je idempotentni no-op, ne lažna korekcija.

## 3. Poslovna pravila i invarijante

1. `origin_type` je immutable posle create-a. `school_role`/`SCHOOL_PARTICIPANT_EXTERNAL` su zabranjeni runtime aliasi.
2. Vreme: end>start, trajanje H0 ≤31 dan; registration open<close≤start; opcion `cancellation_deadline_at` mora biti posle registration open i pre ili tačno na startu; timezone validan IANA; UTC se izvodi deterministički uz isti M10 DST resolver ugovor.
3. Publish zahteva ≥1 audience, ≥1 validnu location ili eksplicitno `location_tbd=true` samo ako start>72h; responsible ACTIVE staff; fresh M08/M09/M10 facts; nema resource conflict-a. Za više school lokacija coordinator sortira sve `EventLocation.id` i M08 `Location.id`, zaključava ih deterministički i potvrđuje ceo skup occupancy blokova all-or-nothing.
4. SCHOOL capacity: NO_LIMIT bez limit-a; WARNING dozvoljava samo staff override uz permission+reason+audit; HARD_LIMIT nikad override. Aktivni REGISTERED se broje pod Event row lock-om.
5. EXTERNAL capacity koristi samo `school_allocated_capacity`; CONFIRMED count ga ne prelazi. INTERESTED ne zauzima mesto. Ako interest OFF, validan zahtev ide direktno CONFIRMED.
6. Guardian registruje samo dete sa ACTIVE M07 basis-om i participant u audience-u. Staff registracija zahteva poseban permission/subject. PAYER nema pravo.
7. Cancellation je terminalna za konkretan registration red. Guardian može otkazati samo pre `cancellation_deadline_at`; kada deadline nije zadat, cutoff je `starts_at`. Poređenje je `database_now <= cutoff`; zahtev koji dobije Event lock tek posle cutoff-a pada iako je UI ranije bio otvoren. Staff sa `school.events.registration_manage` može otkazati pre starta uz zatvoreni reason; od starta nadalje status se ne menja u CANCELLED nego se koristi EventAttendance. „Ponovo prijavi” kreira novi red koji referencira otkazani; samo staff, reason, current eligibility/capacity, step-up za događaj u toku 24h. Guardian nikad reaktivira.
8. Publish/register/cancel/material change upisuju minimalni outbox event. M16 ne poziva M14/M13/M15. Delivery ne utiče na uspeh M16 transakcije.
9. Ako događaj ima cenu, M12 FeeRule scope=EVENT i neutralni application coordinator poziva M16 registration port i M12 Assessment/Obligation port u jednoj lokalnoj transakciji kada je naplata uslov registracije. Isti princip važi za pojedinačno otkazivanje: coordinator zaključava Event→EventRegistration, pa M12 account/obligation redove, i commit-uje registration CANCELLED + `CancelAssessmentObligations` ili ništa. M16 ne čuva novac i ne poziva M12; M12 failure rollback-uje celu orkestraciju bez M16 upisa u M12 tabelu. M12 EVENT scope validacija pre zaključavanja dobija isti tenant-bound Event fact/version; ne poziva nazad M16 tokom započete M16 komande.
10. M15 može read-only validirati EVENT scope. M16 ne zna za dokumente niti proverava njihovu listu.
11. Snapshot nastaje jednom na event start job-u, idempotentno. Kasnija prijava zahteva kontrolisan staff late-add pre attendance; istorijski snapshot se dopunjuje append-only, ne menja prethodne redove.
12. EventAttendance je online-only, koristi samo snapshot učesnike i eksplicitni confirm; nema default PRESENT/ARRIVED bulk pretpostavke i nema M11 offline queue.
13. Material change posle publish-a (vreme, lokacija, cancellation policy) zahteva reason, expected version, conflict recheck i outbox; title typo pre start-a je minor change prema zatvorenom field registry-ju.
14. `CancelEvent` atomarno sprečava nove prijave, otpušta sve buduće M08 occupancy blokove čiji su `source_ref_id` vrednosti EventLocation redovi tog događaja i emituje `EventCancelledV1`. M12 ga obrađuje idempotentno preko svog consumer/job ugovora, bez direktnog M16 finansijskog upisa. Sam M16 commit je trenutna autoritativna naplatna barijera: M12 mora blokirati naplatu/reminder/instrukciju i pre materijalizacije cancellation-a. M16 cancellation ne čeka neograničen fan-out svih finansijskih redova i ne tvrdi da je spoljni refund izvršen.
15. Notification-relevant integration event tipovi su tačno `EventPublishedV1`, `EventMateriallyChangedV1`, `EventCancelledV1` i `EventRegistrationChangedV1`. Payload je minimalan school/event/registration/participant opaque ref + status/version/reason category; nema naslova, imena, kontakta, fee/amount-a ili external free text-a. M14 sam resolve-uje current recipient/subject.

### 3.1. Edge cases

| # | Slučaj | Rezultat |
|---:|---|---|
| 1 | Dva guardian-a uzmu poslednje HARD mesto | Event lock: jedan uspe, drugi 409. |
| 2 | EXTERNAL INTERESTED count iznad allocation-a | Dozvoljeno; confirm je zaključan capacity-jem. |
| 3 | Guardian pokuša reactivate | 403; novi red ne nastaje. |
| 4 | Lokacija promenjena između validation-a i publish-a | M08 version/conflict 409; potpuni rollback. |
| 5 | Coordinator-ov M12 fee korak padne | Registration i obligation oba ne nastaju; M16 nije zvao M12 direktno. |
| 6 | Guardian link opozvan pre commit-a | Precommit guard odbija. |
| 7 | Event cancelled dok register zahtev čeka lock | Cancel pobedi; register 409. |
| 8 | Cross-tenant group/location/participant | Safe 404. |
| 9 | Start job ponovljen | Jedan snapshot po participant-u/location-u. |
| 10 | Attendance za INTERESTED osobu | 422/not found; nije snapshot participant. |
| 11 | Guardian šalje cancel pre cutoff-a, ali Event lock dobije posle cutoff-a. | 409 deadline passed; registracija i finansije ostaju nepromenjene. |
| 12 | Plaćena registracija se otkazuje, M12 korak pada. | Potpuni rollback; ni M16 CANCELLED ni M12 partial credit. |
| 13 | Event cancel i nova registracija se trkaju. | Isti Event lock dozvoljava ili kompletnu raniju registraciju koja zatim ulazi u cancellation obradu, ili odbijanje registracije; nikad aktivna registracija nastala posle cancel commit-a. |
| 14 | Event ima 5.000 naplativih registracija. | M16 cancel ostaje bounded; `EventCancelledV1` pokreće paginiranu M12 obradu, uz trenutni finance barrier. |

## 4. Tenant i Security Guard

Request: M01→M03→M04→M05→M16 resource→M06/M07/M08/M09/M10 subject/scope; high-risk precommit recheck. Permission ključevi: `school.events.view`, `school.events.manage`, `school.events.publish`, `school.events.register_child`, `school.events.registration_manage`, `school.events.capacity_override`, `school.events.attendance_record`, `school.events.attendance_correct`. Owner/Manager sve; Limited explicit; Instructor view/attendance/registration samo assigned scope uz binding; Guardian view/register/cancel samo svoje dete; Payer none. Support nema participant snapshot, registration ili attendance read/write; samo masked aggregate operational health ako grant izričito dozvoli.

External organizer opis/adresa enkriptovani su i minimizovani, a display naziv je strogo ograničen na naziv organizatora bez kontaktnih ili tajnih podataka; nema automatskog Person/account/tenant-a. Public visibility ne postoji u H0 M16; M27 kasnije koristi odobrenu public projekciju, nikad privatni model.

## 5. Lifecycle

| Entitet | Iz | Akcija | U |
|---|---|---|---|
| Event | — | Create | DRAFT |
| Event | DRAFT | Publish | PUBLISHED |
| Event | DRAFT/PUBLISHED | Cancel | CANCELLED |
| SCHOOL Registration | — | Register | REGISTERED |
| SCHOOL Registration | REGISTERED | Cancel | CANCELLED |
| EXTERNAL Registration | — | ExpressInterest | INTERESTED |
| EXTERNAL Registration | —/INTERESTED | ConfirmParticipant | CONFIRMED_PARTICIPANT |
| EXTERNAL Registration | INTERESTED/CONFIRMED_PARTICIPANT | Cancel | CANCELLED |
| bilo koji cancelled registration | CANCELLED | StaffReactivate | novi red u validnom početnom statusu |
| EventAttendance | — | snapshot materialization | UNRECORDED |
| EventAttendance | UNRECORDED | Record | ARRIVED/NO_SHOW |
| EventAttendance | ARRIVED/NO_SHOW | Correct | ARRIVED/NO_SHOW |

CANCELLED Event/Registration su terminalni; reactivation nikad ne menja stari red.

## 6. Error katalog

| Kod | HTTP | Opis |
|---|---:|---|
| `M16_NOT_FOUND_SAFE` | 404 | Hidden/cross-tenant/missing. |
| `M16_PERMISSION_DENIED` | 403 | Nedozvoljena akcija. |
| `M16_VALIDATION_FAILED` | 422 | Polje/origin/time/audience/location. |
| `M16_INVALID_TRANSITION` | 409 | Lifecycle. |
| `M16_REGISTRATION_CLOSED` | 409 | Van prozora. |
| `M16_CANCELLATION_DEADLINE_PASSED` | 409 | Guardian deadline je prošao ili je za staff događaj već počeo; nema statusne ili finansijske promene. |
| `M16_NOT_IN_AUDIENCE` | 422 | Nije eligible, bez tuđih detalja. |
| `M16_CAPACITY_LIMIT_REACHED` | 409 | HARD/allocation. |
| `M16_OVERRIDE_REASON_REQUIRED` | 422 | WARNING override. |
| `M16_RESOURCE_CONFLICT` | 409 | M08/M10 conflict. |
| `M16_STALE_VERSION` | 409 | CAS/dependency version. |
| `M16_ALREADY_REGISTERED` | 409 | Neterminalan red postoji. |
| `M16_REACTIVATION_FORBIDDEN` | 403 | Guardian/invalid old row. |
| `M16_BILLING_ATOMICITY_FAILED` | 503 | Coordinator nije mogao da commit-uje obavezni M12 write; nema M16 registration commit-a. |
| `M16_IDEMPOTENCY_KEY_REUSED` | 409 | Isti key, drugi payload. |
| `M16_RATE_LIMITED` | 429 | Limit. |
| `M16_DEPENDENCY_UNAVAILABLE` | 503 | Autoritativni port; fail closed. |

## 7. API, idempotency, concurrency i NFR

Komande: `CreateEvent`, `UpdateDraftEvent`, `SetEventAudience`, `SetEventLocations`, `PublishEvent`, `ChangePublishedEvent`, `CancelEvent`, `RegisterChild`, `ExpressInterest`, `ConfirmParticipant`, `CancelRegistration`, `StaffReactivateRegistration`, `MaterializeEventSnapshot`, `RecordEventAttendance`, `CorrectEventAttendance`. Write ima idempotency/request/correlation; mutacije expected version; override/cancel/reactivate/correct reason.

| API ugovor | Obavezni poslovni input | Uspešan rezultat |
|---|---|---|
| `Create/UpdateDraftEvent` | origin, title/category/time; expected version za update | DRAFT event/version |
| `SetEventAudience/Locations` | event/version, kompletan typed set | novi event version + all-or-nothing occupancy plan, svaki M08 source ref je EventLocation ID |
| `Publish/ChangePublishedEvent` | event/version, fresh dependency versions | PUBLISHED/version + outbox |
| `CancelEvent` | event/version, reason | CANCELLED + occupancy release + `EventCancelledV1`; M12 read/write barrier važi odmah, materialization je M12 owner posao |
| `RegisterChild` | SCHOOL event, participant, guardian basis | REGISTERED ili capacity error |
| `ExpressInterest/ConfirmParticipant` | EXTERNAL event, participant; staff permission za confirm | INTERESTED/CONFIRMED_PARTICIPANT |
| `CancelRegistration` | registration/version, actor basis, reason, Event/version i database-time cutoff recheck | free registration: stari red CANCELLED; fee-backed: M16 CANCELLED + svi M12 assessment obligations/credit efekti u jednom coordinator commit-u |
| `StaffReactivateRegistration` | cancelled ID/version, reason | novi registration ID; stari neizmenjen |
| `MaterializeEventSnapshot` | event/version neposredno pre starta | immutable participant/location snapshot |
| `Record/CorrectEventAttendance` | event/participant/status/version; correction reason | ARRIVED/NO_SHOW/version |
| `List/GetEvent` | cursor/date/filter ili ID | tenant/subject-scoped event projekcija; M12 price samo composition |

Lock order za koordinisanu naplativu prijavu ili pojedinačno otkazivanje: Event→registration participant key→M12 family account/obligation po M12 redosledu. Neutralni coordinator koristi owner portove u jednoj lokalnoj transakciji; M16 ne importuje M12 command handler i nema direktan table write. Receipt/audit/outbox svih uspešnih owner promena su u istom commit-u. `CancelEvent` ne radi sinhroni finansijski fan-out; emitovani event, M12 barrier i M21-katalogizovan M12 consumer čine zaseban pouzdan tok. Event query cursor default30/max100, date range≤366 dana; registration batch max200; p95 list≤300ms, single write≤700ms bez provider/outbox delivery čekanja.

Obavezni indeksi: event calendar `(school_id,status,starts_at,id)`; audience unique `(school_id,event_id,audience_type,scope_key)`; location unique `(school_id,event_id,sequence_no)`; aktivna registration unique partial `(school_id,event_id,participant_profile_id)` za neterminalne statuse; registration list `(school_id,event_id,status,id)`; attendance unique `(school_id,event_id,participant_profile_id)`; M08 occupancy partial unique `(school_id,source_kind,source_ref_id)` gde je za događaj `source_kind=EVENT` i `source_ref_id=EventLocation.id`. Nema indeksa nad event opisom, eksternom adresom ili participant snapshot sadržajem.

## 8. Acceptance kriterijumi

M16 prolazi samo uz QA matricu: oba origin toka, conditional schema, parallel capacity, staff-only reactivation, M08 conflict atomicity, M12 fee create/cancel atomicity i event cancellation barrier, M15/M14 no reverse/direct call, snapshot retry, event attendance separation, current guardian guard, two-tenant safe 404, offline deny, audit/outbox i negative scan `school_role|fee_amount|price_minor`.
