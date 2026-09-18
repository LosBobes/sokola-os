---
tip: modulni-implementacioni-ugovor
modul-id: M08
naziv: Ogranci, programi, lokacije i prostori
status: SPEC_CANDIDATE
revizija: "1.2"
datum: 2026-09-08
schema-zavisnosti: [M04]
read-portovi: [M04]
application-guardovi: [M01, M03, M05]
izlazni-portovi-za: [M09, M10, M12, M15, M16, M18, M19, M20, M21, M27, M28]
offline-policy: DENY
---

# M08 — Ogranci, programi, lokacije i prostori

## 1. Cilj, autoritet i granice

### 1.1. Cilj

M08 je jedini vlasnik tenant-scoped strukture u kojoj škola organizuje različite delatnosti i mesta rada:

- `Branch` — opciona organizaciona jedinica škole, npr. grad ili poslovni ogranak;
- `Program` — neutralna disciplina ili ponuda, npr. fudbal, balet, gluma, klavir ili matematika;
- `Location` — fizičko ili online mesto održavanja aktivnosti;
- `LocationOnlineAccess` — odvojena, zaštićena pristupna tajna online lokacije;
- `Space` — konkretna sala, teren, učionica, studio ili scena unutar lokacije;
- `SpaceOccupancyBlock` — jedini H0 autoritet za hard-conflict zauzeće lokacije/prostora.

Jedna M04 `School` ostaje jedina bezbednosna tenant granica i kada radi u više gradova, vrtića, hala ili sopstvenih objekata. `Branch` nikada nije podtenant i ne daje pristup.

### 1.2. Non-goals

M08 ne poseduje:

- `School`, `Organization`, subscription ili komercijalni entitlement — M04;
- role, permission ili Support Access — M05;
- osobe, članstva, zaposlene ili polaznike — M06;
- grupe, upise i dodele osoblja — M09;
- recurrence i termine — M10;
- attendance — M11;
- cenovnik, zakup prostora, fakturu, uplatu ili prihod — M12;
- događaj — M16;
- rezervabilnu opremu, održavanje, kvarove i marketplace prostora — Operations/H3.

`ownership_kind` opisuje poslovni odnos škole prema mestu; ne kreira ugovor, dug, pravo pristupa ili marketplace zapis. `equipment_tags` su opis, ne stanje inventara. H0 nema cross-school booking niti zajednički `Venue` tenant.

## 2. Tipovi, entiteti i relacije

### 2.1. Zajednički tipovi

| Tip | Ugovor |
|---|---|
| `Identifier` | UUID; generiše server; nepredvidiv. |
| `InstantUTC` | UTC/TIMESTAMPTZ. |
| `LocalDate` | ISO `YYYY-MM-DD`. |
| `Code64` | English ASCII `[A-Z0-9][A-Z0-9_-]{0,63}`. |
| `DisplayName` | Unicode plain text 1–150, trimovan, bez HTML/control/BiDi/zero-width znakova. |
| `IanaTimeZone` | Važeći IANA naziv iz runtime tz baze; offset poput `+01:00` nije dovoljan. |
| `Version` | Pozitivan UInt64, početno 1, raste tačno za 1 po mutaciji. |

Svaki tenant entitet ima `school_id`, `UNIQUE(school_id,id)` i sve cross-tenant FK-ove kao kompozitne `(school_id,ref_id)` veze.

### 2.2. `Branch`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id` | Identifier | NE | PK + M04 School tenant-safe FK. |
| `code` | Code64 | NE | Stabilna interna šifra; ne menja se posle create-a. |
| `name` | DisplayName | NE | Prikazni naziv. |
| `normalized_name` | string | NE | Server-side Unicode normalize + casefold za unique proveru. |
| `time_zone_override` | IanaTimeZone | DA | Null znači M04 `School.timezone`; utiče samo na buduće M10 kreiranje. |
| `status` | enum | NE | `ACTIVE`, `INACTIVE`, `ARCHIVED`. |
| `created_at`, `updated_at` | InstantUTC | NE | Server vreme. |
| `version` | Version | NE | CAS. |

Ograničenja: `UNIQUE(school_id,code)` i `UNIQUE(school_id,normalized_name) WHERE status!='ARCHIVED'`. Škola sme imati nula ogranaka; tada su lokacije school-wide. Isti program može biti ponuđen kroz više ogranaka preko grupa, bez kopiranja programa.

### 2.3. `Program`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id` | Identifier | NE | Tenant-safe. |
| `code` | Code64 | NE | Stabilna interna šifra. |
| `name` | DisplayName | NE | Npr. Fudbal, Balet, Gluma, Klavir. |
| `normalized_name` | string | NE | Za unique proveru. |
| `category_code` | Code64 | DA | Tenant-defined neutralna analitička kategorija; nema auth/billing ponašanje. |
| `description` | string(0..500) | DA | Plain text; bez child podataka. |
| `status` | enum | NE | `ACTIVE`, `INACTIVE`, `ARCHIVED`. |
| `created_at`, `updated_at` | InstantUTC | NE | Server vreme. |
| `version` | Version | NE | CAS. |

Ograničenja: `UNIQUE(school_id,code)` i `UNIQUE(school_id,normalized_name) WHERE status!='ARCHIVED'`. Program pripada školi, ne ogranku. M09 `Group.program_id` referencira ovaj entitet.

### 2.4. `Location`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id` | Identifier | NE | Tenant-safe. |
| `branch_id` | Identifier | DA | Ako postoji, ACTIVE/INACTIVE Branch iste škole; null = school-wide. |
| `code` | Code64 | NE | Stabilna šifra. |
| `name`, `normalized_name` | DisplayName, string | NE | Unique među non-archived lokacijama škole. |
| `location_type` | enum | NE | `SPORTS_HALL`, `STUDIO`, `FIELD`, `AIR_DOME`, `KINDERGARTEN`, `SCHOOL_BUILDING`, `THEATER`, `SPORTS_CENTER`, `ACCOMMODATION`, `CLASSROOM_SITE`, `OPEN_SPACE`, `ONLINE`, `OTHER`. |
| `ownership_kind` | enum | NE | `OWN`, `EXTERNAL_RENTED`, `PARTNER_SHARED`, `PUBLIC_USE`, `ONLINE_ONLY`. |
| `time_zone` | IanaTimeZone | NE | Eksplicitni resolved snapshot iz branch/school zone pri create-u. |
| `address_line`, `city`, `postal_code` | string | DA | Zabranjeno za ONLINE-only kada nema fizičke adrese. |
| `country_code` | char(2) | DA | ISO 3166-1 alpha-2; obavezno za fizičku adresu. |
| `access_note` | string(0..300) | DA | Plain text bez šifre, ključa, zdravstvenih ili child podataka. |
| `status` | enum | NE | `ACTIVE`, `INACTIVE`, `ARCHIVED`. |
| `created_at`, `updated_at` | InstantUTC | NE | Server vreme. |
| `version` | Version | NE | CAS. |

`ONLINE` zahteva ACTIVE `LocationOnlineAccess` pre upotrebe u novom terminu. Fizička lokacija može postojati bez adrese samo uz `location_type=OTHER` i reason `ADDRESS_NOT_AVAILABLE`; UI to jasno označava.

### 2.5. `LocationOnlineAccess`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id`, `location_id` | Identifier | NE | Lokacija iste škole i `location_type=ONLINE`. |
| `access_uri_ciphertext` | encrypted bytes/ref | NE | KMS/envelope enkripcija; nikad log, event ili list projection. |
| `access_uri_fingerprint` | HMAC char(64) | NE | Dedupe/rotation, odvojen ključ od enkripcionog. |
| `key_version` | UInt32 | NE | Verzija ključa. |
| `status` | enum | NE | `ACTIVE`, `REVOKED`. |
| `rotated_from_id` | Identifier | DA | Prethodni red iste lokacije. |
| `created_at`, `revoked_at` | InstantUTC | NE/DA | Uslovno. |
| `version` | Version | NE | CAS. |

Najviše jedan ACTIVE red po lokaciji. Rotacija kreira nov red i opoziva stari u jednoj transakciji; ciphertext se ne prepisuje.

### 2.6. `Space`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id`, `location_id` | Identifier | NE | Location iste škole. |
| `code` | Code64 | NE | Stabilno u lokaciji. |
| `name`, `normalized_name` | DisplayName, string | NE | Unique u non-archived prostoru lokacije. |
| `space_type` | enum | NE | `HALL`, `CLASSROOM`, `FIELD`, `POOL`, `STUDIO`, `STAGE`, `ROOM`, `WHOLE_LOCATION`, `OTHER`. |
| `capacity` | UInt32 | DA | `1..100000`; soft upozorenje, nije enrollment hard limit. |
| `equipment_tags` | sorted unique Code64[] | NE | Default `[]`, maksimum 50. |
| `accessibility_tags` | sorted unique Code64[] | NE | Default `[]`, maksimum 30. |
| `access_note` | string(0..300) | DA | Bez tajni/PII. |
| `status` | enum | NE | `ACTIVE`, `INACTIVE`, `ARCHIVED`. |
| `created_at`, `updated_at` | InstantUTC | NE | Server vreme. |
| `version` | Version | NE | CAS. |

Ograničenja: `UNIQUE(school_id,location_id,code)` i unique normalized name među non-archived redovima. `WHOLE_LOCATION` je prikazna oznaka; booking cele lokacije se i dalje modeluje occupancy redom sa `space_id=null`.

### 2.7. `SpaceOccupancyBlock`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id`, `location_id` | Identifier | NE | Location tenant-safe FK. |
| `space_id` | Identifier | DA | Ako postoji, Space mora pripadati istom `(school_id,location_id)`. Null znači zauzeće cele lokacije. |
| `starts_at`, `ends_at` | InstantUTC | NE | Poluotvoren interval `[start,end)`, `start<end`, maksimum 31 dan u H0. |
| `source_kind` | enum | NE | `TERM_OCCURRENCE`, `EVENT`, `MANUAL_HOLD`, `OPERATIONS_BLOCK`. |
| `source_ref_id` | Identifier | DA | Obavezan osim za `MANUAL_HOLD`; identitet jedne rezervacione instance vlasničkog modula. Za `TERM_OCCURRENCE` je M10 `Occurrence.id`; za `EVENT` je M16 `EventLocation.id`, a ne `Event.id`. |
| `status` | enum | NE | `CONFIRMED`, `CANCELLED`. |
| `reason_code` | Code64 | DA | Obavezan za MANUAL_HOLD i cancel. |
| `created_by_account_id`, `cancelled_by_account_id` | Identifier | NE/DA | Audit reference, ne child ID. |
| `created_at`, `cancelled_at` | InstantUTC | NE/DA | Uslovno. |
| `version` | Version | NE | CAS. |

Jedna rezervaciona instanca izvora ima najviše jedan aktivan blok: partial `UNIQUE(school_id,source_kind,source_ref_id) WHERE status='CONFIRMED' AND source_ref_id IS NOT NULL`. Jedan događaj sme imati više `EventLocation` redova i zato više occupancy blokova, ali svaki konkretan `EventLocation.id` najviše jedan. M08 ne koristi `Event.id` kao `source_ref_id` i ne uvodi paralelno polje `event_location_id`.

Konflikt postoji kada se intervali preklapaju u istoj lokaciji i važi bar jedno:

1. postojeći ili novi blok ima `space_id=null` — zauzeta je cela lokacija;
2. oba imaju isti non-null `space_id`.

Potvrda zaključava M08 `Location` red za `(school_id,location_id)`, zatim u istoj transakciji proverava sve CONFIRMED preklapajuće blokove i upisuje novi red. Time su i location-wide i space-level zahtevi serijalizovani i race-safe. Vendor-specifičan exclusion/lock može biti drugačiji samo ako dokazuje istu garanciju pod stvarno paralelnim transakcijama.

### 2.8. Relacije

| Od | Relacija | Do |
|---|---|---|
| M04 School | 1:N | Branch, Program, Location |
| Branch | 0:N | Location |
| Program | 1:N | M09 Group |
| Location | 1:N | Space, LocationOnlineAccess, SpaceOccupancyBlock |
| Space | 0:N | SpaceOccupancyBlock |

## 3. Poslovna pravila i invarijante

1. Nijedan M08 ID iz request-a nije tenant dokaz; server prvo razrešava školu pa composite FK/resource guard.
2. Branch i Program se ne kopiraju po gradu, grupi ili proizvodu; isti Program može imati grupe u više Branch-eva.
3. Deaktiviran Branch/Program/Location/Space ostaje čitljiv u istoriji, ali se ne bira za novi Group/Schedule/Event.
4. Archive je terminalan i dozvoljen tek kada nema ACTIVE zavisnog reda niti budućeg CONFIRMED occupancy-ja. Za privremeni prestanak koristi se INACTIVE.
5. Promena `Location.time_zone` ne menja postojeće M10 occurrence trenutke; važi samo za novo pravilo ili eksplicitno replaniranje budućnosti.
6. Location bez Space je validan; novi termin tada zauzima celu lokaciju (`space_id=null`).
7. Zauzeće cele lokacije konfliktuje sa svakim prostorom u njoj. Dva različita prostora iste lokacije mogu biti istovremeno zauzeta ako nema whole-location bloka.
8. Intervali koji se samo dodiruju (`end==start`) nisu konflikt.
9. Capacity je informativan. M09 hard capacity je zaseban enrollment invariant.
10. Online pristup se dekriptuje samo za konkretan dozvoljeni termin/događaj i nikad ne ulazi u list/search/export/cache key/outbox/telemetry.
11. `ownership_kind` ne menja tenant, RBAC, cenu ili obavezu.
12. Promena branch veze lokacije ne menja istorijske termine; dozvoljena je samo uz expected version i bez budućih potvrđenih termina ili kroz eksplicitno M10 replaniranje u istoj orkestraciji.
13. Program category i UI terminologija ne menjaju Group/Schedule/Attendance pravila; jezgro ostaje neutralno.
14. M08 write operacije su online-only i ne koriste optimistic-final uspeh.
15. H0 nema privremeni occupancy claim, `PENDING` blok niti implicitni TTL. `CheckOccupancyAvailability` je neobavezujući read. `ConfirmOccupancy` u jednoj transakciji ili upisuje trajni `CONFIRMED` blok i receipt ili ne upisuje ništa; potvrđeni blok ostaje autoritet dok ga vlasnički source/manual actor eksplicitno ne otkaže. Ne postoji runtime job `structure.occupancy_claim_expiry`, a kašnjenje bilo kog worker-a ne sme osloboditi zauzet termin.

### 3.1. Obavezni edge cases

| # | Scenario | Deterministički ishod |
|---:|---|---|
| 1 | Škola nema Branch. | School-wide Location/Program/Group tok radi; ne kreira se lažni ogranak. |
| 2 | Dva grada koriste isti Program. | Jedan Program, različite M09 Group/Branch reference. |
| 3 | Whole-location i Space zahtev stižu paralelno. | Location lock dozvoli tačno jedan; drugi 409. |
| 4 | Dva različita Space-a iste Location u istom vremenu. | Oba uspevaju ako nema whole-location bloka. |
| 5 | Stari online link je rotiran dok je ekran otvoren. | Stari red REVOKED; sledeći read dobija novi samo posle ponovne authorization provere. |
| 6 | Cross-tenant space UUID je validan. | Safe 404, bez location/name indikatora. |
| 7 | Archive Location sa budućim occurrence-om. | 409 dependency conflict; ništa se ne otkazuje tiho. |
| 8 | Capacity se smanji ispod broja upisanih. | Update uspe uz warning; M09 upisi se ne menjaju. |
| 9 | Branch timezone se promeni. | Postojeći occurrence UTC ostaje; novi M10 rule koristi novu resolved zonu. |
| 10 | Isti source retry potvrde occupancy-ja. | Vraća isti receipt/blok; ne pravi drugi red. |

## 4. Tenant, security i zaštita dece

Svaka zaštićena operacija prolazi: M01 session → M03 active School/tenant versions → M05 permission → M08 resource guard → precommit version recheck za write. `Branch`, Organization, `ownership_kind`, slug, ruta i UI izbor nikad nisu access grant.

Permission ključevi koje M05 mora registrovati:

| Ključ | Akcija | Subject guard |
|---|---|---|
| `school.structure.view` | list/detail Branch/Program/Location/Space bez tajne | Active school membership i dozvoljeni scope. |
| `school.structure.manage` | create/update/lifecycle | School admin permission. |
| `school.occupancy.manage` | manual hold/cancel i vlasnički M10/M16 port | Source ownership + tenant guard. |
| `school.online_access.view` | dekriptovanje URI-ja | Konkretan M10/M16 access na occurrence/event; nije dovoljan structure view. |
| `school.online_access.manage` | set/rotate/revoke | OWNER/MANAGER ili eksplicitni grant; step-up ≤10 min. |

Liste, count, search, cursor i cache tenant-filteriraju pre računanja. Cross-tenant ili skriven resurs vraća `M08_NOT_FOUND_SAFE` 404. `403` se koristi samo kada actor već sme da zna resurs, ali nema akciju.

M08 ne čuva podatke dece. Event/audit/outbox sadrži school ID, aggregate ID, status/version, reason code i correlation ID; nema naziv lokacije, adresu, online URI, osobu ili dete. Telemetry koristi pseudonimizovan tenant/actor i nema PII.

## 5. Lifecycle i tranzicije

### 5.1. Branch, Program, Location i Space

| From | Komanda | To | Guard |
|---|---|---|---|
| — | Create | `ACTIVE` | Validan unique code/name i tenant. |
| `ACTIVE` | Deactivate | `INACTIVE` | Ne briše istoriju/buduće veze. |
| `INACTIVE` | Reactivate | `ACTIVE` | Parent aktor i reference važe. |
| `ACTIVE`/`INACTIVE` | Archive | `ARCHIVED` | Nema aktivnih/budućih zavisnosti. |
| `ARCHIVED` | bilo šta | — | Terminalno. |

### 5.2. LocationOnlineAccess

| From | Komanda | To |
|---|---|---|
| — | Set/Rotate | `ACTIVE` |
| `ACTIVE` | Rotate | stari `REVOKED`, novi `ACTIVE` atomski |
| `ACTIVE` | Revoke | `REVOKED` |
| `REVOKED` | bilo šta | — terminalno |

### 5.3. SpaceOccupancyBlock

| From | Komanda | To |
|---|---|---|
| — | Confirm, atomski conflict check + insert | `CONFIRMED` bez privremenog međustanja ili TTL-a |
| `CONFIRMED` | Cancel | `CANCELLED` |
| `CANCELLED` | bilo šta | — terminalno |

## 6. Error catalog

| Kod | HTTP | Značenje |
|---|---:|---|
| `M08_AUTHENTICATION_REQUIRED` | 401 | M01 sesija ne važi. |
| `M08_NOT_FOUND_SAFE` | 404 | Nepostojeći, cross-tenant ili skriven target. |
| `M08_FORBIDDEN` | 403 | Poznat resurs, nedostaje akcija. |
| `M08_CODE_CONFLICT` | 409 | Code unique sudar. |
| `M08_NAME_CONFLICT` | 409 | Aktivni/non-archived normalized name sudar. |
| `M08_PARENT_INACTIVE` | 409 | Parent Branch/Location/Program nije ACTIVE za novu vezu. |
| `M08_INVALID_TIME_ZONE` | 422 | Nije važeći IANA naziv. |
| `M08_INVALID_LOCATION_TYPE` | 422 | Enum nije dozvoljen. |
| `M08_PHYSICAL_ADDRESS_REQUIRED` | 422 | Fizičko mesto nema adresu ni dozvoljeni reason. |
| `M08_ONLINE_ACCESS_REQUIRED` | 422 | ONLINE lokacija nema ACTIVE access red. |
| `M08_ONLINE_ACCESS_FORBIDDEN` | 403 | Nema konkretnog occurrence/event access-a. |
| `M08_ONLINE_ACCESS_INVALID` | 422 | URI nije HTTPS/odobrena online šema. |
| `M08_SPACE_CAPACITY_INVALID` | 422 | Capacity van `1..100000`. |
| `M08_OCCUPANCY_RANGE_INVALID` | 422 | Interval nije validan ili je duži od 31 dana. |
| `M08_OCCUPANCY_CONFLICT` | 409 | Location/space interval konflikt. |
| `M08_OCCUPANCY_SOURCE_INVALID` | 422 | Source kind/ref kombinacija nije validna. |
| `M08_ALREADY_CANCELLED` | 409 | Blok je već CANCELLED sa drugim zahtevom. |
| `M08_DEPENDENCY_EXISTS` | 409 | Archive nije dozvoljen zbog aktivne/buduće reference. |
| `M08_INVALID_TRANSITION` | 409 | Lifecycle prelaz nije dozvoljen. |
| `M08_STALE_VERSION` | 409 | expected version nije aktuelan. |
| `M08_IDEMPOTENCY_KEY_INVALID` | 400 | Header/body UUID nedostaje ili se ne poklapa. |
| `M08_IDEMPOTENCY_KEY_REUSED` | 409 | Isti ključ, drugi canonical payload. |
| `M08_IDEMPOTENCY_IN_PROGRESS` | 409 | Isti zahtev je još u toku; `Retry-After: 1`. |
| `M08_LIMIT_EXCEEDED` | 422 | Tag/batch/page limit prekoračen. |
| `M08_CONCURRENT_AUTHORIZATION_CHANGE` | 409 | Guard/version promenjen pre commit-a. |

Error body je `{code,message_key,correlation_id,retryable,details?}`. `details` nikad ne otkriva cross-tenant ID, online URI ili naziv skrivenog resursa.

## 7. Komande, query-ji i portovi

Svaka write komanda ima `request_id UUID`, HTTP `Idempotency-Key` sa istom vrednošću, `correlation_id UUID`; update/lifecycle komande imaju `expected_version`. Svi write-ovi su server-confirmed i online-only.

| ID | Komanda | Obavezni specifični input | Atomski rezultat |
|---|---|---|---|
| `M08-BR-01` | `CreateBranch` | school, code, name, timezone? | ACTIVE Branch. |
| `M08-BR-02` | `UpdateBranch` | branch, patch, expected version | Dozvoljena polja + version. |
| `M08-BR-03` | `SetBranchStatus` | branch, target ACTIVE/INACTIVE/ARCHIVED, reason | Dozvoljena tranzicija. |
| `M08-PR-01` | `CreateProgram` | school, code, name, category? | ACTIVE Program. |
| `M08-PR-02` | `UpdateProgram` | program, patch, expected version | Dozvoljena polja. |
| `M08-PR-03` | `SetProgramStatus` | program, target, reason | Dozvoljena tranzicija. |
| `M08-LOC-01` | `CreateLocation` | school, branch?, code/name/type/ownership/timezone/address | ACTIVE Location. |
| `M08-LOC-02` | `UpdateLocation` | location, patch, expected version | Validan update; istorija ne menja occurrence. |
| `M08-LOC-03` | `SetLocationStatus` | location, target, reason | Dozvoljena tranzicija. |
| `M08-LOC-04` | `SetOrRotateOnlineAccess` | online location, HTTPS URI, expected version | Novi ACTIVE secret; stari REVOKED. |
| `M08-LOC-05` | `RevokeOnlineAccess` | access row, expected version, reason | REVOKED. |
| `M08-SP-01` | `CreateSpace` | location, code/name/type/capacity/tags | ACTIVE Space. |
| `M08-SP-02` | `UpdateSpace` | space, patch, expected version | Validan update. |
| `M08-SP-03` | `SetSpaceStatus` | space, target, reason | Dozvoljena tranzicija. |
| `M08-OCC-01` | `ConfirmOccupancy` | location, space?, interval, source kind/ref, reason? | Jedan CONFIRMED blok ili conflict; receipt/audit/outbox. |
| `M08-OCC-02` | `CancelOccupancy` | block, expected version, reason | CANCELLED; slot oslobođen. |

Query-ji:

- `M08-Q01 ListStructure`: filter `branch_id`, `program_status`, `location_status`, `cursor`, `page_size` default 25/max 100; sort normalized name + ID; bez online URI-ja.
- `M08-Q02 GetLocationDetail`: dozvoljeni metadata snapshot; tajna odvojena.
- `M08-Q03 ResolveOnlineAccessForActivity`: occurrence/event ref; ponavlja M01/M03/M05 i source subject guard pre dekripcije; response `Cache-Control: no-store`.
- `M08-Q04 CheckOccupancyAvailability`: preview bez rezervacije; rezultat nije garancija i nosi `checked_at`; jedina potvrda je `M08-OCC-01`.
- `M08-Q05 ResolveProgram`: active/status/version metadata za M09/M12.

Portovi vraćaju opaque ID/status/version/timezone/capacity, ne direktan DB model. M10/M16 occupancy potvrdu pozivaju unutar iste lokalne transakcije modularnog monolita; source modul ne piše M08 tabelu direktno. M16 za skup lokacija sortira `EventLocation.id`, zaključava sve pogođene M08 Location redove deterministički i potvrđuje sve blokove ili nijedan.

## 8. Idempotency, concurrency, audit i NFR

1. Receipt scope je `(school_id,command_id,request_id)` + SHA-256 canonical payload. Isti payload vraća originalni rezultat bez novog audit/outbox-a; drugi payload je 409.
2. Identical in-flight retry čeka do command timeout-a; zatim rezultat ili `M08_IDEMPOTENCY_IN_PROGRESS`.
3. Lock redosled: School/Branch parent → Program/Location → Space → Occupancy, UUID rastuće unutar grupe.
4. Occupancy potvrda uvek zaključava Location pre conflict query-ja; nema check-then-insert van transakcije.
5. State change, receipt, audit marker i outbox su jedna lokalna DB transakcija.
6. Outbox događaji: `structure.branch_changed`, `structure.program_changed`, `structure.location_changed`, `structure.space_changed`, `structure.occupancy_changed`; minimalni payload bez naziva/adrese/URI-ja.
7. Limiti po školi: 500 Branch, 2.000 Program, 10.000 Location, 50.000 Space; batch occupancy maksimum 500; prekoračenje fail-closed.
8. Query p95 cilj na seedu 10.000 lokacija: list ≤300 ms, detail ≤200 ms, occupancy confirm bez contention-a ≤500 ms; online secret read ≤500 ms. Ovo su server ciljevi bez spoljne mreže.
9. Indeksi najmanje: svi tenant composite FK-ovi; `(school_id,status,normalized_name,id)` za liste; `(school_id,location_id,status,starts_at,ends_at)` za occupancy; source partial unique; active online-access partial unique.
10. Retention prati M17; archive ne briše istorijske reference. Tajne se kripto-brišu po odobrenom retention/legal-hold toku.

## 9. Migracija i brownfield pravila

1. Postojeći `Branch` iz M04 i `Program` iz M09 mapiraju se u M08 bez promene stabilnog ID-a; nema duple tabele posle cutover-a.
2. Svaki legacy red dobija `school_id` i composite tenant FK pre uključivanja write saobraćaja; neusklađeni red ide u exception report, ne u drugi tenant.
3. `Location.time_zone` se backfill-uje iz Branch override-a ili M04 School timezone-a i ostaje snapshot.
4. Legacy online URI se enkriptuje u `LocationOnlineAccess`; plaintext se briše tek posle byte/referential reconciliation-a i backup/forward-recovery provere.
5. Stari occupancy XOR/COALESCE model migrira na obavezni `location_id`; `space_id` je opcioni child. Preklapajući aktivni redovi ne dobijaju proizvoljnog pobednika: blokiraju cutover i ulaze u exception report.
6. Migracija je idempotentna, merljiva po count/hash zbirovima i nema period dual-write-a.

## 10. Acceptance kriterijumi

M08 je spreman tek kada:

1. schema dokazuje owner model i sve tenant-safe FK/unique/check uslove;
2. Branch/Program ne postoje kao aktivni master u M04/M09;
3. hierarchical occupancy race testovi dokazuju whole-location/space pravila;
4. online tajna prolazi encryption, no-store, log-redaction i unauthorized-read testove;
5. archive/reactivate i dependency guardovi prate state machine;
6. svaka komanda ima receipt/audit/outbox i negativni authorization test;
7. svi scenariji iz [[02-M08-QA-I-TRACEABILITY]] prolaze;
8. nema offline write-a ili optimistic-final uspeha;
9. repo mapiranje klasifikuje `PRESERVE|ADAPT|IMPLEMENT|REMOVE_CONFLICT|VERIFY_IN_REPO` bez izmišljanja implementacije.
