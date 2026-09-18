---
tip: modulni-implementacioni-ugovor
modul-id: M09
naziv: Grupe, upisi i dodele osoblja
status: SPEC_CANDIDATE
revizija: "1.2"
datum: 2026-09-08
schema-zavisnosti: [M06, M08]
read-portovi: [M04, M06, M08]
application-guardovi: [M01, M03, M05]
izlazni-portovi-za: [M10, M11, M12, M13, M14, M15, M16, M18, M19, M20, M21, M28]
offline-policy: DENY
---

# M09 — Grupe, upisi i dodele osoblja

## 1. Cilj, autoritet i granice

### 1.1. Cilj

M09 je jedini vlasnik:

- `Group` — operativne kohorte u okviru M08 programa;
- `GroupEnrollment` — vremenski ograničenog učešća M06 `ParticipantProfile` u grupi;
- `GroupEnrollmentTransition` — neizmenjive istorije statusa upisa;
- `EnrollmentTransfer` — atomske promene grupe;
- `StaffGroupAssignment` — vremenski ograničene poslovne dodele M06 `StaffProfile` grupi.

Jezgro je neutralno prema disciplini: grupa može biti tim, plesna grupa, glumački ansambl, muzička klasa ili edukativna radionica. UI može koristiti tenantov prevod, ali runtime model ostaje `Group`, `ParticipantProfile` i `StaffProfile`.

### 1.2. Non-goals

M09 ne poseduje:

- `Program`, `Branch`, `Location` ili `Space` — M08;
- `Person`, `ParticipantProfile`, `StaffProfile` ili school membership — M06;
- permission i platformsku ulogu — M05;
- recurrence, termin ili konflikt prostora/trenera — M10/M08;
- prisustvo — M11;
- cenu, popust, pro-rata pravilo, članarinu, obavezu ili uplatu — M12;
- listu čekanja u H0. Budući `groups.waitlist` je feature flag podrazumevano `OFF` i ne menja H0 upis;
- registraciju na događaj — M16.

`preferred_location_id` i `preferred_space_id` su podrazumevane vrednosti forme za M10, ne rezervacija niti raspored. Dodela osoblja opisuje poslovni odnos; sama ne dodeljuje RBAC permission.

## 2. Tipovi, entiteti i relacije

### 2.1. Zajednički ugovor

`Identifier` je UUID, `InstantUTC` je TIMESTAMPTZ, `LocalDate` je ISO datum, `Version` je UInt64 CAS, a `Code64` je English ASCII kod. Svaki red ima `school_id`, `UNIQUE(school_id,id)` i kompozitne tenant-safe FK veze. Periodi su poluotvoreni `[starts_on, ends_on)`; null `ends_on` znači otvoren kraj.

### 2.2. `Group`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id` | UUID | NE | PK i M04 School tenant-safe FK. |
| `program_id` | UUID | NE | ACTIVE/INACTIVE M08 Program iste škole; pri aktivaciji mora biti ACTIVE. |
| `branch_id` | UUID | DA | M08 Branch iste škole; null = school-wide. |
| `code` | Code64 | NE | Stabilan; `UNIQUE(school_id,code)`. |
| `name`, `normalized_name` | string(1..150) | NE | Plain text; unique među non-archived grupama škole. |
| `description` | string(0..500) | DA | Bez zdravstvenih, porodičnih i drugih child beleški. |
| `capacity_mode` | enum | NE | `NO_LIMIT`, `WARNING`, `HARD_LIMIT`. |
| `capacity` | UInt32 | DA | Obavezno za WARNING/HARD_LIMIT; `1..100000`; null za NO_LIMIT. |
| `preferred_location_id` | UUID | DA | M08 Location iste škole; samo form default. |
| `preferred_space_id` | UUID | DA | Zahteva preferred Location i Space unutar nje; samo form default. |
| `status` | enum | NE | `DRAFT`, `ACTIVE`, `INACTIVE`, `ARCHIVED`. |
| `created_at`, `updated_at` | InstantUTC | NE | Server vreme. |
| `version` | UInt64 | NE | Početno 1; +1 po mutaciji. |

Group nema price, currency, fee rule, schedule JSON, weekdays niti staff/participant niz. Takva polja su zabranjeni paralelni source of truth.

### 2.3. `GroupEnrollment`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id`, `group_id` | UUID | NE | Group iste škole. |
| `participant_profile_id` | UUID | NE | M06 ParticipantProfile iste škole. |
| `starts_on` | LocalDate | NE | Poslovni datum početka. |
| `ends_on` | LocalDate | DA | Ekskluzivni kraj; mora biti posle starts_on. |
| `status` | enum | NE | `DRAFT`, `ACTIVE`, `SUSPENDED`, `TERMINATED`. |
| `status_reason_code` | Code64 | DA | Obavezan za suspend/terminate. |
| `created_by_account_id`, `updated_by_account_id` | UUID | NE | Actor audit referenca. |
| `created_at`, `updated_at` | InstantUTC | NE | Server vreme. |
| `version` | UInt64 | NE | CAS. |

Za isti `(school_id,group_id,participant_profile_id)` periodi statusa ACTIVE ili SUSPENDED ne smeju da se preklapaju. DRAFT ne ulazi u roster. TERMINATED red se ne reaktivira; novi povratak kreira novi Enrollment.

### 2.4. `GroupEnrollmentTransition`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id`, `enrollment_id` | UUID | NE | Tenant-safe FK. |
| `from_status` | enum | DA | Null samo za CREATE. |
| `to_status` | enum | NE | Novi status. |
| `effective_at` | InstantUTC | NE | Ne sme biti pre poslednjeg transition effective_at. |
| `reason_code` | Code64 | DA | Obavezan gde lifecycle zahteva. |
| `actor_account_id`, `command_id` | UUID | NE | Actor i idempotentna komanda. |
| `created_at` | InstantUTC | NE | Server vreme upisa. |

Red je append-only. `UNIQUE(school_id,enrollment_id,command_id)` sprečava duplu tranziciju.

### 2.5. `EnrollmentTransfer`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id` | UUID | NE | Tenant-safe. |
| `source_enrollment_id`, `target_enrollment_id` | UUID | NE | Različite grupe iste škole i isti participant. |
| `effective_on` | LocalDate | NE | Source završava, target počinje ovog datuma. |
| `reason_code` | Code64 | NE | Obavezan. |
| `actor_account_id`, `command_id`, `created_at` | UUID/InstantUTC | NE | Audit/idempotency. |

`UNIQUE(school_id,source_enrollment_id)` sprečava drugi transfer istog izvora. Source terminate, target create/activate, oba transition reda, transfer, audit i outbox nastaju u jednoj transakciji.

### 2.6. `StaffGroupAssignment`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `school_id`, `group_id` | UUID | NE | Tenant-safe. |
| `staff_profile_id` | UUID | NE | M06 StaffProfile iste škole. |
| `assignment_role` | enum | NE | `LEAD_INSTRUCTOR`, `INSTRUCTOR`, `ASSISTANT`, `SPECIALIST`. |
| `starts_on`, `ends_on` | LocalDate | NE/DA | Poluotvoren period. |
| `status` | enum | NE | `ACTIVE`, `ENDED`. |
| `reason_code` | Code64 | DA | Obavezan za prevremeni End. |
| `created_by_account_id`, `ended_by_account_id` | UUID | NE/DA | Audit reference. |
| `created_at`, `ended_at` | InstantUTC | NE/DA | Uslovno. |
| `version` | UInt64 | NE | CAS. |

Za isti staff/group/role ACTIVE periodi se ne preklapaju. Najviše jedan aktivan `LEAD_INSTRUCTOR` u istom poslovnom trenutku. Dodela ne kreira M05 grant; M05 subject guard samo može da koristi aktivnu dodelu kao dodatno suženje već postojeće dozvole.

## 3. Poslovna pravila i invarijante

1. Group može postati ACTIVE samo uz ACTIVE Program i, ako su navedeni, ACTIVE Branch/Location/Space iste škole.
2. Participant može u isto vreme biti u više grupa; zabrana važi samo za dupli preklapajući upis u istu grupu.
3. Aktivacija upisa zaključava Group red, proverava participant eligibility preko M06 i kapacitet u istoj transakciji.
4. HARD_LIMIT: ako bi broj efektivno ACTIVE upisa prešao capacity, komanda se odbija 409. SUSPENDED se računa u zauzeće mesta, jer čuva mesto.
5. WARNING: aktivacija iznad capacity zahteva `capacity_override=true`, permission `school.groups.capacity.override` i razlog; bez toga 409. NO_LIMIT ne računa limit.
6. Capacity se računa za `effective_on` iz komande, ne samo za trenutno vreme.
7. Smanjenje capacity ispod postojećeg broja ne ukida upise; vraća warning i blokira narednu aktivaciju za HARD_LIMIT.
8. Upis se ne briše. Greška pre aktivacije može otkazati DRAFT kroz TERMINATED sa reason; aktivna istorija ostaje.
9. Retroaktivna tranzicija pre poslednje evidentirane tranzicije nije dozvoljena. Ispravka istorijskog podatka je posebno auditarno administrativno pravilo, van H0.
10. Transfer je jedina atomska cross-group promena. Target capacity/eligibility se proverava pre source terminate; neuspeh target-a ne menja source.
11. Deaktivacija Group ne menja postojeće enrollment/staff redove, ali zabranjuje nove upise, dodele i M10 schedule rules.
12. Archive Group je terminalan i moguć samo bez ACTIVE/SUSPENDED enrollmenta, ACTIVE staff dodele, budućeg M10 termina i otvorene finansijske zavisnosti koju vlasnički modul prijavi.
13. Brisanje/promena Program/Branch preference ne propagira se tiho u istorijske grupe.
14. M09 write je online-only. UI može optimistično prikazati spinner/pending request, ali nikad konačan upis pre server receipt-a.
15. Waitlist nije implicitni fallback: `M09_GROUP_CAPACITY_EXCEEDED` ne kreira nijedan drugi entitet kada je flag OFF.
16. `GetRosterAsOf(group_id, instant)` i capacity proveru ne određuje worker niti današnja denormalizovana vrednost sama. Efektivnost je deterministički presek: `starts_on <= SchoolLocalDate(instant) < ends_on` kada kraj postoji, plus poslednja append-only `GroupEnrollmentTransition` sa `effective_at<=instant`; samo stanje ACTIVE ulazi u attendance roster, dok ACTIVE i SUSPENDED rezervišu capacity. DRAFT/TERMINATED i transition nastao posle preseka ne ulaze. Ako nema transition-a do preseka, red nije efektivan.
17. H0 lifecycle komande Activate/Suspend/Resume/Terminate primenjuju se odmah: `effective_at=database_now` i ne prihvataju budući statusni transition. Prirodni budući početak/kraj se modeluje isključivo `starts_on/ends_on`; budući transfer/suspend/resume/terminate nije H0 i vraća `M09_VALIDATION_FAILED`. `EnrollmentTransfer.effective_on` mora biti School local date u trenutku commit-a. Zato ne postoji `groups.enrollment_effective_transition`; prolazak vremena menja rezultat intervalskog read-a bez mutacije reda ili worker-a.

### 3.1. Edge cases

| # | Scenario | Ishod |
|---:|---|---|
| 1 | Dva poslednja mesta se paralelno aktiviraju. | Group lock serijalizuje; najviše zahtevan broj do limita uspe. |
| 2 | Target transfer je pun. | Ceo transfer rollback; source ostaje ACTIVE. |
| 3 | Isti participant je ranije TERMINATED pa se vraća. | Novi Enrollment; istorijski red se ne reaktivira. |
| 4 | Cross-tenant participant UUID postoji. | Safe 404; ne odaje postojanje profila. |
| 5 | Program postane INACTIVE između forme i commita. | Precommit recheck vraća 409; Group se ne aktivira. |
| 6 | WARNING limit je prekoračen bez override permission-a. | 409; nije dovoljan UI checkbox. |
| 7 | Instruktor dobije assignment bez RBAC role. | Assignment postoji, ali ne može otvoriti podatke; M05 deny. |
| 8 | Upis počinje sutra, roster se traži danas. | Ne pojavljuje se u današnjem as-of rosteru. |
| 9 | Group se deaktivira posle generisanih termina. | Termini se ne otkazuju automatski; M10 eksplicitna odluka. |
| 10 | Identičan transfer retry posle timeout-a. | Isti target/source/receipt; bez duplikata. |
| 11 | Feature flag waitlist OFF i grupa puna. | Samo deterministička greška; nema skrivenog reda čekanja. |
| 12 | ACTIVE i SUSPENDED period istog upisa se preklapaju. | Jedan Enrollment menja status; drugi preklapajući red je DB-invalid. |

## 4. Tenant & Security Guard

Redosled je M01 session → M03 school context/version → M05 permission → M09 resource/subject guard → precommit recheck. Organization, Branch, Group code, ruta i staff assignment nisu tenant dokaz ili permission.

M05 registruje:

| Permission | Svrha |
|---|---|
| `school.groups.view` | Grupe i agregatni kapacitet bez child detalja. |
| `school.groups.manage` | Group create/update/lifecycle. |
| `school.groups.capacity.override` | WARNING prekoračenje uz razlog; nije HARD_LIMIT bypass. |
| `school.groups.enrollments.view` | Roster samo za dozvoljeni Group/subject scope. |
| `school.groups.enrollments.manage` | Create/activate/suspend/terminate/transfer. |
| `school.groups.staff_assignments.manage` | Assign/end staff. |

Owner/Manager dobijaju sve ove ključeve. LimitedAdmin ih nema osim eksplicitnog school-scoped grant-a. Instructor/Substitute dobija view samo za aktivno dodeljene grupe; assignment ne može proširiti permission. Guardian i Payer ne dobijaju M09 roster; njihovi mySOKOLA prikazi dolaze kroz child-scoped read composition iz M28. Cross-tenant ili hidden subject je safe 404; poznat group uz nedostatak akcije je 403.

List/count/search/export prvo primenjuje tenant + permission + assignment/subject scope, pa tek onda paginaciju i total. Nema health/contact/guardian/finance podatka u M09. Audit/outbox sadrži opaque aggregate/participant/staff ID, status/version/reason/correlation, bez imena ili slobodnog teksta.

## 5. Lifecycle & transitions

### 5.1. Group

| From | Komanda | To | Guard |
|---|---|---|---|
| — | CreateGroup | DRAFT | Validan M08 scope. |
| DRAFT | ActivateGroup | ACTIVE | ACTIVE Program/references. |
| ACTIVE | DeactivateGroup | INACTIVE | Expected version. |
| INACTIVE | ReactivateGroup | ACTIVE | Reference recheck. |
| DRAFT/INACTIVE | ArchiveGroup | ARCHIVED | Nema aktivnih/budućih zavisnosti. |
| ACTIVE | ArchiveGroup | — | Zabranjeno; prvo explicit deactivate + resolve dependencies. |
| ARCHIVED | bilo šta | — | Terminalno. |

### 5.2. GroupEnrollment

| From | Komanda | To |
|---|---|---|
| — | CreateEnrollment | DRAFT |
| DRAFT | ActivateEnrollment | ACTIVE |
| ACTIVE | SuspendEnrollment | SUSPENDED |
| SUSPENDED | ResumeEnrollment | ACTIVE |
| DRAFT/ACTIVE/SUSPENDED | TerminateEnrollment | TERMINATED |
| TERMINATED | bilo šta | — terminalno |

Transfer je atomska izvedba `source ACTIVE/SUSPENDED → TERMINATED` i `target — → ACTIVE`; nema međustanja vidljivog drugim transakcijama.

### 5.3. StaffGroupAssignment

| From | Komanda | To |
|---|---|---|
| — | AssignStaff | ACTIVE |
| ACTIVE | EndStaffAssignment | ENDED |
| ENDED | bilo šta | — terminalno |

## 6. Error catalog

| Kod | HTTP | Značenje |
|---|---:|---|
| `M09_VALIDATION_FAILED` | 422 | Neispravno polje/period/enum. |
| `M09_NOT_FOUND_SAFE` | 404 | Resurs nije vidljiv u aktivnoj školi. |
| `M09_PERMISSION_DENIED` | 403 | Poznat resurs, akcija nije dozvoljena. |
| `M09_VERSION_CONFLICT` | 409 | Expected version nije aktuelan. |
| `M09_GROUP_CODE_CONFLICT` | 409 | Duplikat code/name u školi. |
| `M09_REFERENCE_INACTIVE` | 409 | Program/Branch/Location/Space/Profile nije važeći za akciju. |
| `M09_ENROLLMENT_OVERLAP` | 409 | Preklapajući upis istog učesnika u istoj grupi. |
| `M09_GROUP_CAPACITY_EXCEEDED` | 409 | HARD/WARNING limit nije dozvolio aktivaciju. |
| `M09_CAPACITY_OVERRIDE_REQUIRED` | 409 | WARNING limit traži permission i razlog. |
| `M09_LEAD_INSTRUCTOR_CONFLICT` | 409 | Preklapajuća lead dodela. |
| `M09_TRANSITION_NOT_ALLOWED` | 409 | Nedozvoljena lifecycle promena. |
| `M09_RETROACTIVE_TRANSITION_DENIED` | 409 | Effective_at je pre poslednje tranzicije. |
| `M09_ARCHIVE_DEPENDENCIES_EXIST` | 409 | Aktivne/buduće zavisnosti sprečavaju archive. |
| `M09_TRANSFER_TARGET_UNAVAILABLE` | 409 | Target eligibility/capacity nije prošao. |
| `M09_IDEMPOTENCY_KEY_REUSED` | 409 | Isti ključ, drugačiji payload/scope. |
| `M09_PRECONDITION_REQUIRED` | 428 | Nedostaje expected version za update. |
| `M09_RATE_LIMITED` | 429 | Prekoračen tenant/actor limit. |
| `M09_DEPENDENCY_UNAVAILABLE` | 503 | Autoritativni M06/M08 port nije dostupan. |

Greška nikad ne vraća cross-tenant detalj, child/staff ime, SQL ili stack trace.

## 7. API, idempotency, concurrency i događaji

### 7.1. Komande

Sve komande zahtevaju `active_school_id`, `Idempotency-Key`, `correlation_id`; update/lifecycle i `expected_version`. Payload hash obuhvata canonical payload + school + actor + command type. Receipt se čuva najmanje 30 dana.

| Komanda | Ključni ulaz | Rezultat |
|---|---|---|
| `Create/Update/Activate/Deactivate/Reactivate/ArchiveGroup` | Group polja/version/reason | Group + version + receipt. |
| `Create/Activate/Suspend/Resume/TerminateEnrollment` | group, participant, effective datum, reason | Enrollment + transition receipt. |
| `TransferEnrollment` | source, target group, effective_on, reason | Transfer + oba enrollment ID-a. |
| `Assign/EndStaffAssignment` | group, staff, role, period/version | Assignment receipt. |

Retry sa istim ključem i hash-om vraća originalni HTTP status/body i ne ponavlja audit/outbox. Drugi hash je 409. Server generiše ID; client-supplied business ID se ne prihvata kao tenant dokaz.

Aktivacija/transfer zaključavaju Group red(ove) deterministički po UUID redosledu, zatim proveravaju reference, overlap i capacity. Transfer zaključava source/target Group i source Enrollment. Staff dodela zaključava Group + postojeće kandidat redove. Mutacija, transition, audit, outbox i receipt su jedna DB transakcija. Deadlock/serialization retry je ograničen i nikada ne ponavlja spoljni side effect.

Outbox događaji: `GroupActivatedV1`, `GroupDeactivatedV1`, `EnrollmentActivatedV1`, `EnrollmentSuspendedV1`, `EnrollmentTerminatedV1`, `EnrollmentTransferredV1`, `StaffGroupAssignedV1`, `StaffGroupAssignmentEndedV1`. Payload je minimalan: school_id, aggregate/reference opaque ID, effective date, version, correlation_id; nema PII.

### 7.2. Query ugovor

- `ListGroups`: cursor pagination, default 25, max 100; filteri program/branch/status; stable sort `(normalized_name,id)`.
- `GetGroup`: safe 404.
- `GetRosterAsOf(group_id, instant)`: M09 autoritativni port; primenjuje tačan interval+transition presek iz §3 i vraća samo efektivno ACTIVE enrollment/participant opaque ID, enrollment version i period/status. Consumer dodatne podatke dobija od M06 uz sopstveni guard. Job lag ne može promeniti rezultat.
- `ListStaffAssignmentsAsOf`: isto vremensko pravilo.
- Max range istorije bez export job-a je 366 dana.

Performance cilj: p95 list/read ≤300 ms, write bez spoljnog outage-a ≤500 ms pri podržanom tenant volumenu. Minimalni indeksi: `(school_id,status,normalized_name,id)`, `(school_id,program_id,status)`, enrollment `(school_id,group_id,status,starts_on,ends_on)`, participant history i staff-as-of indeksi. Query plan/load dokaz je deo implementacionog DoD-a.

## 8. Acceptance sažetak

M09 je prihvatljiv samo ako automatizovani testovi iz `02-M09-QA-I-TRACEABILITY.md` prolaze, uključujući dve stvarno paralelne capacity aktivacije, atomski transfer rollback, cross-tenant safe 404, dodelu bez permission eskalacije, as-of roster i negativnu pretragu zabranjenih polja `StudentProfile`, `base_monthly_price`, `price_minor`, `schedule_hint` u aktivnom M09 runtime ugovoru.
