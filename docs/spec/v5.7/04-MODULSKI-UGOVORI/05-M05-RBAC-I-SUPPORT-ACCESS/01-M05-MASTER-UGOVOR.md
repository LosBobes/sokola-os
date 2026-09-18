---
tip: modul-specifikacija
modul: M05
modul-id: M05
naziv: RBAC i Support Access
revizija: "2.0"
status: SPEC_CANDIDATE
datum: 2026-09-16
kanonska-verzija-vaulta: v5.7
horizont: H0
schema-zavisnosti: [M06]
read-portovi: [M01, M03, M04, M06, M07]
izlazni-portovi-za: [M02, M14, M17, M19, M21, M28]
---

# M05 — RBAC i Support Access

## 0. Normativni status i jezik ugovora

Ovaj dokument je domenski autoritet za authorization domene, role, permission katalog, dodelu prava i kontrolisani pristup SOKOLA podrške. Važi zajedno sa M00–M04. Jedna globalna uloga „SOKOLA administrator“, trajna Support rola, UI-only provera, owner wildcard i odobrenje podrške bez saglasnosti škole su zabranjeni.

Kanonski M06/M07 ključevi su u `04-M05-PERMISSION-REGISTRY-M06-M07.md`, a M17–M21/M28 ključevi u `03-M05-PERMISSION-REGISTRY-M17-M21-M28.md`. U H0 su efektivni samo `SCHOOL` i `PLATFORM`. `EVENT_ORGANIZER_WORKSPACE` i `VENUE_OPERATOR_WORKSPACE` su rezervisani, fail-closed i ne mogu dobiti role/permission/assignment dok njihov vlasnički modul, resolver, negativni isolation testovi i nova M05 policy revizija nisu aktivni. `Organization` nikada nije authorization domen.

Reči **MORA**, **NE SME**, **TAČNO**, **NAJVIŠE** i **ISKLJUČIVO** su proverljivi zahtevi. Interni identifikatori i statusi se ne lokalizuju. Stack, framework, fizička organizacija koda i konkretan mehanizam zaključavanja ostaju slobodni pod uslovom da sve poslovne garancije i testovi iz ovog paketa važe.

## 1. Cilj i granice

### 1.1. Cilj

M05 mora da:

1. održava jedan verzionisan, fail-closed katalog dozvola i sistemskih uloga;
2. dodeljuje i opoziva school-scoped i platform-scoped uloge bez tenant curenja i privilege escalation-a;
3. izračuna efektivna prava na serveru za svaku zaštićenu komandu, query, download, export, realtime subscribe i background callback u ime korisnika;
4. kombinuje role i eksplicitne grantove, ali dozvoljava M03 tenant i domenskim modulima subject guard da rezultat samo dodatno suze;
5. obezbedi neposredno važenje suspenzije/opoziva, bez stale-cache prozora;
6. omogući standardni Support Access samo nakon eksplicitnog odobrenja škole, za tačnu svrhu, tiket, scope i kratko trajanje;
7. omogući strogo ograničen break-glass samo za stvarnu vanrednu situaciju, sa ratifikacijom, obaveštenjem i pregledom;
8. ostavi potpun, tenant-vidljiv audit trag bez tajnog impersonation-a;
9. izdaje ograničen offline authorization lease samo za operacije koje njihov modul eksplicitno dozvoli.
10. podrži buduće event-only i venue-only radne prostore bez lažne škole i bez njihovog prerano aktivnog pristupa u H0.

### 1.2. Vlasništvo granica

| Tema | Autoritet | M05 ugovor |
|---|---|---|
| Nalog, autentifikacija, sesija, step-up | M01 | M05 troši potvrđen actor/session i poziva AUTH-08 posle relevantne promene. |
| Poziv i prihvatanje pristupa | M02 | M05 validira grant-spec i atomarno prima rezultat prihvatanja. |
| Aktivna škola i tenant execution context | M03 | M05 ne veruje `school_id` iz klijenta; koristi M03 kontekst. |
| School lifecycle, primary owner, entitlements | M04 | `PRIMARY_OWNER` nije M05 uloga; M04 štiti poslednjeg OWNER-a i transfer. |
| Person i SchoolMembership | M06 | `RoleAssignment` ima tenant-safe FK ka membership-u; M05 čita verzionisan `MembershipFacts`. M06 ne poziva M05 nazad. |
| GuardianChildLink i prava po detetu | M07 | M05 daje baznu GUARDIAN ulogu; M07 uvek sužava konkretan subject. |
| Grupe, termini i dodela osoblja | M09/M10/M11 | M05 daje baznu akciju; dodeljeni group/term scope proverava vlasnički modul. |
| Finansijska semantika | M12 | M05 registruje ključeve, ali ne računa saldo niti knjiži. |
| Dokumenti, prihvatanja, privatnost | M15/M17 | M05 ne određuje pravni osnov ni retention sadržaja. |
| Navigacija, Command Bar, PWA | M19 | M05 daje bezbednu projekciju i offline envelope; M19 upravlja UX-om i redom. |

### 1.3. Non-goals

M05 eksplicitno nije:

- identity provider, login, password ili session servis;
- invitation/onboarding lifecycle;
- registar ljudi, starateljskih veza, grupa ili termina;
- vlasnik pravnog statusa škole, pretplate ili capability entitlement-a;
- vlasnik poslovnih pravila finansija, prisustva, dokumenata ili pretrage;
- sistem za kreiranje proizvoljnih tenant uloga u Core MVP-u;
- Organization-wide permission scope ili ugovorni model koji daje pristup školama;
- aktivacija event/venue authorization domena pre M30/M33 ugovora, resolvera i izolacionih testova;
- ACL na nivou reda koji zamenjuje subject guard domenskog modula;
- način da support, platform actor, owner ili frontend zaobiđu server-side proveru;
- trajni impersonation, „login as user“, deljenje sesije ili nevidljiv read access;
- pravni dokaz kvalifikovanog elektronskog potpisa;
- offline autorizacija za kritične administrativne, finansijske ili Support Access promene.

## 2. Entiteti, polja i relacije

### 2.1. Tipovi i zajednička pravila

- `UUID`: nepredvidiv 128-bitni identifikator.
- `Instant`: UTC trenutak sa najmanje milisekundnom preciznošću; baza je autoritet vremena.
- `Version`: pozitivan 64-bitni integer, počinje sa 1 i raste za 1 po promeni agregata.
- `Key`: ASCII lower-case dot-separated ključ, 3–128 karaktera, regex `^[a-z][a-z0-9]*(\.[a-z][a-z0-9_]*)+$`.
- Svi redovi koji imaju `school_id` imaju tenant-safe FK/UNIQUE indekse koji uključuju `school_id` kada referenciraju tenant entitet.
- `reason_note` je 1–500 UTF-8 znakova kada je obavezan; ne sme sadržati lozinku, token, zdravstveni podatak, finansijski detalj, sadržaj dokumenta ili nepotreban podatak deteta.
- M00 `CommandReceipt`, audit i outbox se ponovo koriste; M05 ne pravi paralelne generičke tabele.

### 2.2. AuthorizationPolicyRevision

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id` | UUID | da | PK. |
| `revision_no` | int32 | da | Globalno jedinstven, strogo raste. |
| `status` | enum | da | `DRAFT`, `ACTIVE`, `SUPERSEDED`, `REJECTED`. |
| `canonical_content_hash` | char(64) | da | SHA-256 kanonskog permission/role/binding sadržaja. |
| `created_at`, `created_by_account_id` | Instant, UUID | da | Platform actor. |
| `activated_at`, `activated_by_account_id` | Instant, UUID? | uslovno | Oba obavezna samo za ACTIVE/SUPERSEDED. |
| `change_reason_code`, `change_ticket_ref` | enum, string(1..100) | da | Zatvoren razlog + spoljašnji release/security ref. |
| `version` | Version | da | Optimistic concurrency. |

Tačno jedna revizija je `ACTIVE`. Objavljena revizija je immutable; ispravka je nova revizija.

### 2.2.1. AuthorizationDomainDefinition

`AuthorizationDomainDefinition` je deo kanonskog sadržaja `AuthorizationPolicyRevision`; nije tenant ili korisnički kreiran podatak.

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `policy_revision_id` | UUID | da | FK na AuthorizationPolicyRevision. |
| `authorization_domain_key` | enum/registry key | da | `SCHOOL`, `PLATFORM`, `EVENT_ORGANIZER_WORKSPACE`, `VENUE_OPERATOR_WORKSPACE`. Unique u reviziji. |
| `status` | enum | da | `ACTIVE`, `RESERVED`, `RETIRED`. |
| `owner_module_id` | string(3..8) | da | SCHOOL=M03, PLATFORM=M05, EVENT_ORGANIZER_WORKSPACE=M30, VENUE_OPERATOR_WORKSPACE=M33. |
| `context_resolver_key` | Key | da | Server-side resolver koji proizvodi i proverava domain context. |
| `requires_subject_guard` | boolean | da | `true` za sve business domene; PLATFORM koristi granularne platform permissions i posebne business zabrane. |
| `is_organization_contract_scope` | boolean | da | U ovoj reviziji uvek `false`; Organization nije auth domen. |

H0 policy mora imati `SCHOOL=ACTIVE`, `PLATFORM=ACTIVE`, a oba buduća workspace domena `RESERVED`. `RESERVED`, `RETIRED`, unknown ili domen bez dokazivo svežeg owner resolver-a je deny. Takav domen ne sme imati active `RoleDefinition`, `PermissionDefinition`, binding ili assignment. Aktivacija budućeg domena zahteva novu M05 policy reviziju, aktivan vlasnički modul, tenant-safe context resolver, assignment model u vlasničkom modulu i negativne query/count/search/cache/job/export/realtime isolation testove. M05 evaluator se ponovo koristi; M05 ne preuzima njihove poslovne entitete.

Fizička baza može implementirati registry tabelom ili ekvivalentom, ali ne sme koristiti zatvoren `SCHOOL|PLATFORM` enum koji zahteva prepisivanje postojećih redova da bi se bezbedno dodao novi domen.

### 2.3. PermissionDefinition

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `policy_revision_id` | UUID | da | FK na AuthorizationPolicyRevision. |
| `permission_key` | Key | da | PK u reviziji; stabilan kroz revizije. |
| `authorization_domain_key` | registry key | da | Mora pokazivati na `ACTIVE AuthorizationDomainDefinition` iste policy revizije; permission pripada tačno jednom domenu. |
| `resource_type`, `action` | string(1..80) | da | Neutralan domen i atomska radnja. |
| `risk_level` | enum | da | `LOW`, `ELEVATED`, `HIGH`, `CRITICAL`. |
| `delegation_class` | enum | da | `ROLE_ONLY`, `DIRECT_DELEGABLE`, `INTERNAL_ONLY`, `NON_DELEGABLE`. |
| `step_up_required` | boolean | da | HIGH/CRITICAL je uvek `true`. |
| `offline_policy` | enum | da | `DENY`, `READ_CACHE_ALLOWED`, `QUEUE_ALLOWED`. Default `DENY`. |
| `child_data_class` | enum | da | `NONE`, `IDENTIFIER_ONLY`, `ROSTER_MINIMAL`, `STANDARD_CHILD`, `SPECIAL_CATEGORY`. |
| `subject_guard_key` | Key? | ne | Obavezno kada pravo nije dovoljno bez odnosa/dodele. |
| `target_role_keys` | sorted string[] | da | Prazno znači da direct grant nije dozvoljen. |
| `status` | enum | da | `ACTIVE` ili `RETIRED`. |

Unique: `(policy_revision_id, permission_key)`. Nepoznat, retired ili pogrešno scoped permission je deny.

### 2.4. RoleDefinition i RolePermissionBinding

`RoleDefinition` polja: `policy_revision_id UUID`, `role_key enum/registry key`, `authorization_domain_key registry key`, `workspace_key Code64?`, `localization_key Key`, `administrative_rank int16`, `assignment_policy M04_M02_ONLY|OWNER_MANAGED|OWNER_OR_MANAGER_MANAGED|M07_ONLY|PLATFORM_SECURITY_MANAGED|OWNER_MODULE_MANAGED`, `status ACTIVE|RETIRED`, `display_order int16`. Unique `(revision, authorization_domain_key, role_key)`. H0 mapiranje je fiksno: OWNER=`M04_M02_ONLY`; MANAGER=`OWNER_MANAGED`; LIMITED_ADMIN/INSTRUCTOR/SUBSTITUTE_INSTRUCTOR=`OWNER_OR_MANAGER_MANAGED`; GUARDIAN/PAYER=`M07_ONLY`; sve platform role=`PLATFORM_SECURITY_MANAGED`. School workspace mapiranje je: OWNER/MANAGER/LIMITED_ADMIN→`ADMIN`, INSTRUCTOR/SUBSTITUTE_INSTRUCTOR→`INSTRUCTOR`, GUARDIAN→`GUARDIAN`, PAYER→`PAYER`. Buduća workspace uloga, ako bude odobrena, koristi `OWNER_MODULE_MANAGED` i assignment agregat svog modula; ne koristi `RoleAssignment` sa lažnim `school_id`.

`RolePermissionBinding` polja: `policy_revision_id UUID`, `role_key enum`, `permission_key Key`. PK je sva tri polja. Binding je immutable unutar objavljene revizije.

`SchoolRoleLabelOverride` je isključivo prikazna konfiguracija: `id UUID`, `school_id UUID`, `role_key INSTRUCTOR|SUBSTITUTE_INSTRUCTOR`, `locale string(2..20)` kao validan BCP-47 tag, `singular_label string(1..40)`, `plural_label string(1..40)`, `status ACTIVE|RETIRED`, `created_at Instant`, `updated_at Instant`, `version Version`. Label je plain Unicode bez HTML/control znakova i ne sme biti isti kao za OWNER/MANAGER/GUARDIAN/PAYER na istom locale-u tako da zbunjuje security značenje. Najviše jedan ACTIVE red po `(school_id, role_key, locale)`. Ako override ne postoji, koristi se kanonski localization key.

Kanonski school role ključevi su:

| Role key | Neutralno značenje | Ko je dodeljuje |
|---|---|---|
| `OWNER` | Vlasnik škole | Isključivo M04 owner nomination + M02 acceptance/internal provisioning. |
| `MANAGER` | Školski operativni administrator | OWNER direktno ili M02 poziv koji OWNER odobri. |
| `LIMITED_ADMIN` | Administrator bez implicitnih poslovnih prava | OWNER/MANAGER; konkretna prava preko eksplicitnih grantova. |
| `INSTRUCTOR` | Osoblje koje vodi dodeljene aktivnosti | OWNER/MANAGER; subject scope daje M09/M10. |
| `SUBSTITUTE_INSTRUCTOR` | Vremenski i terminski ograničeno osoblje | OWNER/MANAGER; bez term assignment-a nema pristupa. |
| `GUARDIAN` | Odrasla osoba povezana sa detetom | Isključivo M02/M07 kontrolisani tok. |
| `PAYER` | Odrasla osoba sa verifikovanom finansijskom vezom prema detetu, bez implicitnog guardian prava | Isključivo M02/M07 kontrolisani tok; bazni binding-i su samo finance-related. |

UI može prikazati „trener“, „nastavnik“, „predavač“, „koreograf“ ili drugi tenant naziv. Interni ključ ostaje `INSTRUCTOR`. Legacy `TRAINER` se deterministički migrira u `INSTRUCTOR`, a `SUBSTITUTE_TRAINER` u `SUBSTITUTE_INSTRUCTOR`; paralelni aktivni par nije dozvoljen.

Kanonski platform role ključevi su:

| Role key | Tačna svrha |
|---|---|
| `PLATFORM_OPERATIONS_ADMIN` | M04 provisioning/lifecycle/entitlement radnje, bez child/business pristupa. |
| `PLATFORM_SECURITY_ADMIN` | Account security, policy objava i platform-role kontrola. |
| `PLATFORM_SUPPORT_AGENT` | Može tražiti i koristiti odobren Support Access; sam role ne daje tenant podatke. |
| `PLATFORM_INCIDENT_COMMANDER` | Može pokrenuti dozvoljen break-glass; nema redovan tenant access. |
| `PLATFORM_BILLING_ADMIN` | SaaS subscription administracija, ne školski family ledger. |

Ne postoji `SUPER_ADMIN`, implicitni wildcard niti permission inheritance iz administrativnog ranga. `CommercialAgreement`, `OrganizationSchool`, Organization račun ili payer status ne stvaraju role/binding/assignment ni u jednom domenu.

### 2.5. RoleAssignment

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id`, `school_id`, `person_id`, `school_membership_id` | UUID | da | Membership mora biti ista Person + School. |
| `role_key` | school-role enum | da | Iz §2.4. |
| `status` | enum | da | `SCHEDULED`, `ACTIVE`, `SUSPENDED`, `REVOKED`, `EXPIRED`. |
| `valid_from`, `valid_until` | Instant, Instant? | da/ne | `valid_until > valid_from`; `OWNER` obavezno ima `valid_from<=created_at` i `valid_until=null`, pa se ownership završava samo eksplicitnim M04/M05 tokom. |
| `source_kind` | enum | da | `INVITATION_ACCEPTANCE`, `DIRECT_ASSIGNMENT`, `OWNER_NOMINATION`, `MIGRATION`, `GUARDIAN_LINK`, `PAYER_LINK`. |
| `source_ref` | UUID | da | Opaque ID vlasničkog source zapisa; migracija koristi UUID svog import evidence reda. |
| `created_by_account_id`, `created_at` | UUID, Instant | da | Actor ili service principal. |
| `suspended_by`, `suspended_at`, `suspend_reason_code` | UUID?, Instant?, enum? | uslovno | Sva ili nijedno. |
| `revoked_by`, `revoked_at`, `revoke_reason_code` | UUID?, Instant?, enum? | uslovno | Sva ili nijedno. |
| `version` | Version | da | Expected-version guard. |

Unique je najviše jedan open assignment `(school_id, school_membership_id, role_key)` sa statusom SCHEDULED/ACTIVE/SUSPENDED. Istorijski red se ne oživljava.

`RoleAssignment` izlaže `UNIQUE(school_id,id)` i `UNIQUE(school_id,id,person_id)`. Composite FK `(school_id,school_membership_id,person_id)` mora pokazivati na isti M06 membership. Role-to-membership mapiranje je zatvoreno: OWNER/MANAGER/LIMITED_ADMIN/INSTRUCTOR/SUBSTITUTE_INSTRUCTOR zahtevaju `STAFF`; GUARDIAN zahteva `GUARDIAN`; PAYER zahteva `CONTACT` ili `GUARDIAN`. Drugi par je 422 `RBAC_MEMBERSHIP_REQUIRED`.

### 2.6. PlatformRoleAssignment

Polja: `id UUID`, `user_account_id UUID`, `role_key platform-role enum`, `status SCHEDULED|ACTIVE|SUSPENDED|REVOKED|EXPIRED`, `valid_from Instant`, `valid_until Instant?`, `source_ticket_ref string(1..100)`, `created_by_account_id UUID`, `created_at Instant`, `suspended_by_account_id UUID?`, `suspended_at Instant?`, `suspend_reason_code enum?`, `revoked_by_account_id UUID?`, `revoked_at Instant?`, `revoke_reason_code enum?`, `version Version`. Suspend/revoke trojke su sva polja ili nijedno. Nema `school_id`, Person niti SchoolMembership. Najviše jedan open assignment po `(user_account_id, role_key)`. `PLATFORM_SECURITY_ADMIN` obavezno ima `valid_from<=created_at` i `valid_until=null`; uklanja se samo eksplicitnom, step-up zaštićenom komandom koja čuva najmanje jednog drugog ACTIVE security admina.

### 2.7. PermissionGrant

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id`, `school_id`, `role_assignment_id` | UUID | da | RoleAssignment mora biti ista škola. |
| `permission_key` | Key | da | Aktivna `SCHOOL` definicija sa `DIRECT_DELEGABLE`. |
| `scope_kind` | enum | da | `SCHOOL`, `CHILD`, `GROUP`, `PROGRAM`, `LOCATION`, `TERM`; mora odgovarati permission-u. |
| `scope_ref` | UUID? | uslovno | Null samo za SCHOOL; za ostale ga type-specific owner resolver potvrđuje unutar iste škole. Polimorfni lažni FK nije dozvoljen. |
| `scope_version_at_grant` | Version? | uslovno | Obavezan za non-SCHOOL scope; snapshot nije trajni allow i owner resolver se ponavlja pri svakoj radnji. |
| `subject_basis_kind` | enum | da | `NONE`, `GUARDIAN_CHILD_LINK`, `PAYER_CHILD_LINK`; za CHILD scope mora odgovarati semantici permission-a. |
| `subject_basis_ref` | UUID? | uslovno | Obavezan za guardian/payer CHILD scope; M07 resolver potvrđuje isti school i child. |
| `status` | enum | da | `ACTIVE`, `REVOKED`, `EXPIRED`. |
| `valid_from`, `valid_until` | Instant, Instant? | da/ne | Ne sme nadživeti parent RoleAssignment. |
| `granted_by`, `granted_at`, `grant_reason_code` | UUID, Instant, enum | da | Actor mora i sam imati pravo + delegabilnost. |
| `revoked_by`, `revoked_at`, `revoke_reason_code` | UUID?, Instant?, enum? | uslovno | Sva ili nijedno. |
| `version` | Version | da | Concurrency. |

Najviše jedan aktivan grant za `(school, role_assignment, permission_key, scope_kind, scope_ref)`. Grant se ne prenosi sa jednog role assignment-a na drugi.

### 2.8. Support entiteti

#### SupportAccessRequest

`id UUID`, `school_id UUID`, `requested_by_account_id UUID`, `support_account_id UUID`, `support_ticket_ref string(1..100)`, `ticket_verified_at Instant`, `ticket_verification_receipt_id UUID`, `purpose_code enum`, `purpose_note string(1..500)`, `requested_scope_hash char(64)`, `requested_duration_minutes int16` (15–120), `status PENDING|APPROVED|REJECTED|CANCELLED|EXPIRED`, `created_at Instant`, `expires_at Instant=created_at+24h`, `decided_by_account_id UUID?`, `decided_by_person_id UUID?`, `decided_at Instant?`, `decision_reason_code enum?`, `decision_reason_note string(1..500)?`, `version Version`. Decision polja su obavezna za APPROVED/REJECTED; cancel koristi requester kao decision actor; EXPIRED nema izmišljeni actor. Za standardni tok `requested_by_account_id = support_account_id`, account ima active PLATFORM_SUPPORT_AGENT i ticket sistem potvrđuje da je isti account assignee. `ticket_verification_receipt_id` je nepredvidiv opaque ID autoritativnog verifier receipt-a; M05 ne čuva hash niskoentropijskog ticket sadržaja kao dokaz verifikacije.

#### SupportAccessRequestScopeItem

Svaki zahtev ima 1–100 normalizovanih stavki: `id UUID`, `request_id UUID`, `school_id UUID`, `capability enum`, `resource_type string(1..80)?`, `resource_id UUID?`, `command_code Code64?`, `data_mask_profile enum`, `read_write READ_ONLY|CONTROLLED_MUTATION`, `canonical_position int16`. `(school_id, request_id)` ima tenant-safe FK ka zahtevu; svaki `resource_id` owner-resolver mora pripadati istoj školi pre upisa. `CONTROLLED_MUTATION` zahteva `capability=CONTROLLED_REPAIR_EXECUTE`, non-null `resource_type`, `resource_id` i `command_code`; ostale stavke moraju imati `command_code=null`. Wildcard, prefix, regex i prazna stavka su zabranjeni. Unique je `(request_id, capability, canonical_resource_type, canonical_resource_id, canonical_command_code, data_mask_profile, read_write)`, gde baza koristi determinističke sentinel vrednosti za null samo u unique izrazu, ne u domenskim kolonama. `requested_scope_hash` je SHA-256 canonical JSON-a svih stavki sortiranih istim totalnim poretkom i ponovo se računa pri svakom approve/read-u.

Purpose codes: `CONFIGURATION_DIAGNOSIS`, `ACCESS_DIAGNOSIS`, `INCIDENT_DIAGNOSIS`, `CUSTOMER_REPORTED_DATA_REPAIR`, `MIGRATION_ASSISTANCE`. Slobodan purpose bez koda se odbija.

#### SupportAccessGrant

`id UUID`, `grant_mode STANDARD|BREAK_GLASS`, `request_id UUID?`, `break_glass_ref UUID?`, `school_id UUID`, `support_account_id UUID`, `status SCHEDULED|ACTIVE|REVOKED|EXPIRED`, `approved_scope_hash char(64)`, `starts_at Instant`, `expires_at Instant`, `approved_by_person_id UUID?`, `approved_by_account_id UUID`, `approved_at Instant`, `approval_step_up_at Instant`, `approved_duration_minutes int16`, `revoked_by_account_id UUID?`, `revoked_at Instant?`, `revoke_reason_code enum?`, `revoke_reason_note string(1..500)?`, `created_at Instant`, `version Version`. Tačno jedno od `request_id` i `break_glass_ref` je popunjeno. STANDARD zahteva request i school approver Person; BREAK_GLASS zahteva ratification zapis i nema lažni school approver. Za STANDARD `expires_at <= approved_at+120min` i ne može biti posle traženog kraja; za BREAK_GLASS `expires_at <= activated_at+30min`. Parent ne čuva paralelne capability/resource nizove; jedini scope autoritet su `SupportScopeItem` redovi, a `approved_scope_hash` je njihov verifikacioni digest.

#### SupportScopeItem

`id UUID`, `grant_id UUID`, `school_id UUID`, `capability enum`, `resource_type string(1..80)?`, `resource_id UUID?`, `command_code Code64?`, `data_mask_profile enum`, `read_write READ_ONLY|CONTROLLED_MUTATION`, `canonical_position int16`. `data_mask_profile` je tačno `TENANT_METADATA`, `ACCESS_DIAGNOSTIC`, `RECORD_STRICT` ili `INCIDENT_STRICT`; nijedan profil ne otkriva M05-zabranjene kategorije. Za `CONTROLLED_MUTATION` su `resource_id` i `command_code` obavezni; wildcard nije dozvoljen. Unique i canonicalization pravila ista su kao kod request stavke, sa `grant_id` umesto `request_id`.

Za STANDARD grant svaka odobrena stavka mora biti identična jednoj request stavci osim što approver sme izabrati stroži `data_mask_profile`, promeniti `CONTROLLED_MUTATION` u `READ_ONLY` kada capability to dozvoljava ili izostaviti stavku. Ne sme dodati capability/resource/command, ublažiti masku niti proširiti write pravo. Ova subset provera, tenant owner-resolve, upis svih grant stavki, računanje `approved_scope_hash`, prelaz request-a i kreiranje granta izvršavaju se u istoj transakciji pod lock-om request-a. BREAK_GLASS stavke se porede sa zatvorenim incident-scope katalogom umesto sa request-om.

Dozvoljene capabilities su:

- `TENANT_METADATA_READ`;
- `CONFIGURATION_READ`;
- `ACCESS_DIAGNOSTICS_READ`;
- `MODULE_RECORD_READ_MASKED`;
- `CONTROLLED_REPAIR_EXECUTE`.

#### SupportAccessSession

`id UUID`, `grant_id UUID`, `school_id UUID`, `support_account_id UUID`, `status ACTIVE|ENDED|REVOKED|EXPIRED`, `started_at Instant`, `last_activity_at Instant`, `ended_at Instant?`, `end_reason_code enum?`, `end_reason_note string(1..500)?`, `support_session_nonce_hash char(64)`, `version Version`. Najviše jedna ACTIVE sesija po `(grant_id, support_account_id)`; idle maksimum 15 min i apsolutni kraj je grant expiry.

`SupportTenantExecutionContext` je request-scoped value object, ne trajni tenant izbor i ne novi master entitet. Sadrži tačno: `school_id`, `support_grant_id`, `support_session_id`, `support_account_id`, `approved_capabilities`, `approved_scope_hash`, `grant_version`, `session_version`, `policy_revision_no`, `expires_at`, `correlation_id`, `mode=SUPPORT`. M05 ga gradi server-side posle svih grant/session guardova; M03 tenant resolver potvrđuje samo School granicu. Ne ulazi u korisnikov `AvailableTenantContext`, ne menja regularni active school/workspace i ne zahteva M06 SchoolMembership — named, school-approved grant zamenjuje membership isključivo za navedeni Support scope. To nije implicitni bypass.

#### SupportActivityEvent

Append-only polja: `id UUID`, `school_id UUID`, `grant_id UUID`, `support_session_id UUID`, `sequence_no UInt64`, `occurred_at Instant`, `actor_account_id UUID`, `action_code Code64`, `resource_type string(1..80)`, `resource_ref_hmac char(64)`, `resource_ref_hmac_key_version UInt32`, `result ATTEMPTED|ALLOWED|DENIED|ERROR`, `http_status int16?`, `correlation_id UUID`, `ticket_ref string(1..100)`, `mask_profile enum`, `reason_code enum?`, `prev_event_hash char(64)?`, `event_hash char(64)`. Unique su `(support_session_id, sequence_no)` i `(support_session_id, event_hash)`. Prvi događaj ima `sequence_no=1` i `prev_event_hash=null`; svaki sledeći ima `sequence_no=prethodni+1` i tačan prethodni hash. Alokacija broja i prethodnog hash-a zaključava session chain head, pa paralelni zahtevi ne mogu napraviti dve grane. `resource_ref_hmac` je tenant-keyed/domain-separated HMAC sa zabeleženom key verzijom. `event_hash=lowercase_hex(SHA-256(UTF8("SOKOLA-SUPPORT-ACTIVITY-V1") || 0x0A || RFC8785-JCS(celog allow-listed event objekta bez event_hash)))`; UUID je lowercase, Instant je UTC RFC3339 sa tačno šest decimalnih cifara, a dozvoljeni null je eksplicitan. Hash uključuje `prev_event_hash` i HMAC key verziju. Nema request/response tela, imena deteta, kontakta, finansijskog iznosa, tokena ili sadržaja dokumenta.

Pre svakog support read-a trajno se upisuje `ATTEMPTED`; tek tada se resource razrešava i eventualno materijalizuje response. Terminalni `ALLOWED|DENIED|ERROR` zapis nastaje posle odluke. Ako ATTEMPTED upis nije moguć, radnja je fail-closed bez čitanja; ako terminalni zapis zakaže, response se ne šalje, ATTEMPTED ostaje vidljiv i podiže security alert. Za `CONTROLLED_MUTATION`, business promena, receipt, standardni business audit/outbox i terminalni SupportActivityEvent moraju biti u istoj lokalnoj DB transakciji; ako moduli nemaju zajedničku lokalnu transakciju, ta repair komanda nije dozvoljena u H0. Time nema poslovnog uspeha bez potpunog support traga.

#### BreakGlassRatification i BreakGlassReview

`BreakGlassRatification`: `id UUID`, `grant_id UUID`, `activated_by_account_id UUID`, `ratified_by_account_id UUID?`, `incident_ref string(1..100)`, `reason_code enum`, `justification string(1..500)`, `activated_at Instant`, `ratification_deadline Instant=activated_at+10min`, `ratified_at Instant?`, `status PENDING|RATIFIED|MISSED|REVOKED`, `notification_delay_reason_code enum?`, `notification_due_at Instant?`, `notification_sent_at Instant?`, `version Version`. Delay polja su dozvoljena samo uz dokumentovan security containment, a due nikad nije posle `activated_at+60min`.

`BreakGlassReview`: `id UUID`, `grant_id UUID`, `status DUE|COMPLETED|OVERDUE`, `due_at Instant=grant_end+24h`, `reviewer_account_id UUID?`, `completed_at Instant?`, `findings_code enum?`, `findings_note string(1..1000)?`, `follow_up_ticket_ref string(1..100)?`, `version Version`. Findings code/note su obavezni za COMPLETED.

### 2.9. OfflineAuthorizationLease

Polja: `id UUID`, `school_id UUID`, `user_account_id UUID`, `device_installation_id UUID`, `permission_key Key`, `resource_type string(1..80)`, `resource_id UUID`, `purpose_code enum`, `issued_at Instant`, `expires_at Instant`, `authorization_version Version`, `tenant_access_version Version`, `policy_revision_no int32`, `status ACTIVE|REVOKED|EXPIRED|CONSUMED`, `max_operations int16` (1–500), `consumed_operations int16` (0–max), `lease_nonce_hash char(64)`, `revoked_at Instant?`, `revoke_reason_code enum?`, `version Version`. Lease ne nosi dodatnu dozvolu: samo ograničava kada već dozvoljena `QUEUE_ALLOWED` operacija može biti lokalno snimljena i kasnije ponovo autorizovana.

### 2.10. Zatvoreni reason registri

Svaka policy, role, direct-grant, revoke, support decision/end i offline-revoke bezbednosna mutacija zahteva kod iz odgovarajuće liste; Support request koristi svoj obavezni `purpose_code`. Label create/update/retire i support session start nemaju slobodan reason input. Unknown vrednost je 422 `RBAC_REASON_INVALID` ili `SUPPORT_DECISION_REASON_INVALID`. `reason_note` je obavezan za kodove označene sa `*` i uvek za policy publish, platform role change, support revoke, break-glass i review.

| Radnja | Dozvoljeni reason codes |
|---|---|
| Policy publish/reject | `NEW_MODULE_PERMISSIONS`, `SECURITY_CORRECTION*`, `ROLE_BINDING_CORRECTION*`, `PERMISSION_RETIREMENT*`, `DRAFT_REJECTED*` |
| School role suspend | `SECURITY_REVIEW*`, `TEMPORARY_LEAVE`, `ACCESS_PAUSE*`, `MEMBERSHIP_SUSPENDED` |
| School role reactivate | `SECURITY_CLEARED*`, `RETURNED_TO_DUTY`, `ACCESS_RESTORED*` |
| School role revoke | `MEMBERSHIP_ENDED`, `RESPONSIBILITY_ENDED`, `ROLE_REPLACED`, `SECURITY_REVOKE*`, `OWNER_TRANSFER` |
| Direct permission grant | `DUTY_REQUIRED*`, `TEMPORARY_COVERAGE*`, `GUARDIAN_SCOPE_APPROVED*`, `PAYER_SCOPE_APPROVED*`, `MIGRATION` |
| Direct permission revoke | `DUTY_ENDED`, `SCOPE_CHANGED*`, `SECURITY_REVOKE*`, `PARENT_ROLE_REVOKED`, `PERMISSION_RETIRED`, `RELATION_ENDED` |
| Platform role assign/revoke | `DUTY_ASSIGNED*`, `DUTY_ENDED*`, `SECURITY_REVOKE*`, `ACCOUNT_INACTIVE*` |
| Support reject | `INSUFFICIENT_SCOPE*`, `INVALID_TICKET*`, `NOT_REQUIRED`, `SECURITY_CONCERN*` |
| Support request cancel | `ISSUE_RESOLVED`, `REQUEST_REPLACED`, `ENTERED_IN_ERROR*` |
| Support grant revoke | `SCHOOL_REQUEST*`, `ISSUE_RESOLVED`, `SCOPE_VIOLATION*`, `SECURITY_INCIDENT*`, `GRANT_REPLACED*` |
| Support session end | `COMPLETED`, `USER_ENDED`, `IDLE_TIMEOUT`, `GRANT_REVOKED`, `GRANT_EXPIRED`, `SECURITY_TERMINATED*` |
| Offline lease revoke | `USER_LOGOUT`, `SESSION_EXPIRED`, `SCHOOL_SWITCHED`, `ACCESS_REVOKED`, `DEVICE_RESET` |
| Break-glass review finding | `JUSTIFIED_NO_ISSUE`, `JUSTIFIED_FOLLOW_UP_REQUIRED*`, `POLICY_VIOLATION*`, `SECURITY_INCIDENT_CONFIRMED*` |

## 3. Poslovna pravila i invarijante

### 3.1. Efektivna autorizacija

Redovni school korisnik prolazi ovim redosledom:

1. M01 potvrđuje session/account, revocation i `authorization_version`;
2. M03 razrešava jednu aktivnu školu, stanje škole, mode i `tenant_access_version`;
3. M06 potvrđuje aktivan SchoolMembership iste Person i School;
4. M05 učitava tačno jednu ACTIVE policy reviziju i sve vremenski važeće ACTIVE school role assignment-e;
5. M05 pravi uniju permission binding-a i važećih direct grantova; izabrani workspace je ne filtrira;
6. M04 entitlement/feature flag može samo dodatno ugasiti funkciju, nikad dati permission;
7. resource se tenant-safe razrešava unutar aktivne škole;
8. vlasnički modul primenjuje subject guard (dete, grupa, termin, lokacija ili drugi odnos);
9. HIGH/CRITICAL radnja proverava step-up i ponavlja verzije neposredno pre commit-a.

Odluka je `ALLOW` samo ako je svih devet slojeva pozitivno. Nedostupan policy/membership/authorization store, nepoznat ključ ili nedokazana svežina daje fail-closed. JWT, frontend store, ruta, sakriveno dugme, provider claim ili cache nisu permission autoritet.

Pre navedenog pipeline-a M05 mora dokazati da traženi `authorization_domain_key` postoji i da je `ACTIVE` u istoj policy reviziji. `RESERVED`, `RETIRED`, unknown ili domen bez dostupnog/svežeg context resolver-a vraća deny/fail-closed pre učitavanja business resursa. U H0 nijedan request ne sme konstruisati event/venue workspace context niti pretvoriti Organization/agreement/scope ref u School context.

Platform komanda koja ne čita school business sadržaj prolazi M01, aktivnu platform RoleAssignment, platform permission, step-up/risk i command-specific M04/M17 guardove; nema lažni M06 membership. Ako joj je potreban `school_id` za provisioning/lifecycle, M03 ga koristi kao tenant boundary, a platform permission ne otvara podatke dece, attendance, dokumente ili school finance.

Support request ima zaseban, stroži pipeline: M01 active support account → active PLATFORM_SUPPORT_AGENT ili incident role → ACTIVE named SupportAccessGrant → ACTIVE SupportAccessSession → request-time grant/session expiry/version → M03 potvrda tačne School granice u `SupportTenantExecutionContext` → exact capability/resource/command scope → masking/prohibited-action guard → vlasnički business/tenant/version guard za kontrolisanu repair komandu → durable SupportActivityEvent. Support actor ne mora imati M06 membership; odobreni grant je jedini ograničeni dokaz pristupa i nikad se ne prevodi u regularnu school role ili workspace.

### 3.2. Uloge, grantovi i delegacija

1. Efektivni permissions su unija svih aktivnih uloga osobe u aktivnoj školi i njihovih aktivnih grantova. M05 MVP nema person-level `DENY`; subject guard može suziti.
2. Role rank služi samo za administriranje dodela; ne nasleđuje permissions.
3. Novi permission je default deny za svaku ulogu dok nova policy revizija eksplicitno ne sadrži binding.
4. OWNER nije wildcard i nema platform dozvole. `PRIMARY_OWNER` je M04 designation, ne dodatna uloga.
5. OWNER sme direktno upravljati `MANAGER`, `LIMITED_ADMIN`, `INSTRUCTOR`, `SUBSTITUTE_INSTRUCTOR`; drugi OWNER ide samo kroz M04/M02. OWNER ne dodeljuje GUARDIAN ili PAYER bez M07 toka.
6. MANAGER sme upravljati samo `LIMITED_ADMIN`, `INSTRUCTOR`, `SUBSTITUTE_INSTRUCTOR`; ne sme OWNER, MANAGER, GUARDIAN ni PAYER.
7. LIMITED_ADMIN, INSTRUCTOR, SUBSTITUTE_INSTRUCTOR, GUARDIAN i PAYER ne dodeljuju role.
8. Direct grant može dodeliti OWNER; MANAGER samo ako ima `school.rbac.permissions.delegate` i sam poseduje ciljni permission. Nijedan actor ne može delegirati permission koji nema, `ROLE_ONLY`, `INTERNAL_ONLY`, `NON_DELEGABLE`, platform permission ili širi scope od sopstvenog.
9. PermissionGrant za GUARDIAN mora nositi `CHILD` scope, `subject_basis_kind=GUARDIAN_CHILD_LINK` i važeći M07 `GuardianChildLink`; bez veze grant ne daje pristup. `PAYER` ima samo eksplicitne finance-related binding-e/grantove sa `subject_basis_kind=PAYER_CHILD_LINK` i važećim M07 `PayerChildLink`; taj basis nikad ne daje attendance/document/health/profile/guardian pravo. Ista osoba može imati GUARDIAN i PAYER role, ali se svaki permission i subject basis proverava zasebno.
10. Membership `SUSPENDED` i account `SUSPENDED` čine sve uloge neefektivnim bez brisanja istorije. Membership `TERMINATED` u istoj transakciji opoziva sve otvorene `RoleAssignment` i `PermissionGrant` zapise te epizode. Nova epizoda članstva zahteva nove dodele.
11. Revoke parent role assignment-a atomarno opoziva sve njegove open PermissionGrant-e.
12. Škola `DEACTIVATED` gasi tenant kontekst; uloge ostaju istorijski zapisi. Reaktivacija ne vraća staru M03 sesiju/kontekst i ne oživljava expired/revoked dodele.
13. Platform role nema `school_id` i nikad sam po sebi ne otvara tenant resurs. Support grant nije RoleAssignment.
14. M21 `rbac.temporal_access_transition` je jedini published posao za regularne vremenske M05 dodele/grantove/lease-e. Svakog minuta platform coordinator obrađuje PLATFORM shard ili jednu po jednu School u izolovanim tenant transakcijama, zaključava parent pre child grantova i koristi `(aggregate_id,valid_from|valid_until,source_version)` kao child business identity. Materijalizuje SCHEDULED→ACTIVE i dospele →EXPIRED, zatvara child grantove gde je potrebno i atomarno upisuje access-version invalidation, receipt, audit i outbox. Request-time `database_now` provera ostaje authorization autoritet i bez job-a. OWNER i PLATFORM_SECURITY_ADMIN su po gornjem ugovoru netemporalni i nikada nisu kandidat ovog posla.

### 3.3. M05 permission registry revizije 1.3

M05 mora fizički registrovati najmanje sledeće ključeve sa tačnim scope-om. Permission-i drugih modula dodaju se isključivo objavom nove policy revizije nakon što njihov kanonski modul definiše semantiku; programer ih ne izmišlja.

| Permission | Authorization domain | Risk | Default role binding | Tačno pravo |
|---|---|---|---|---|
| `school.rbac.assignments.view` | SCHOOL | ELEVATED | OWNER, MANAGER | Lista dodela samo svoje škole; maskiran identitet. |
| `school.rbac.roles.assign` | SCHOOL | HIGH | OWNER, MANAGER | Dodela samo prema §3.2; step-up. |
| `school.rbac.roles.suspend` | SCHOOL | HIGH | OWNER, MANAGER | Suspenzija nižih dodela; step-up. |
| `school.rbac.roles.revoke` | SCHOOL | HIGH | OWNER, MANAGER | Opoziv nižih dodela; step-up. |
| `school.rbac.permissions.delegate` | SCHOOL | CRITICAL | OWNER | Direct grant uz anti-escalation; step-up. |
| `school.rbac.permissions.revoke` | SCHOOL | CRITICAL | OWNER | Opoziv grant-a; MANAGER samo eksplicitnim grantom i u sopstvenom dometu. |
| `school.rbac.labels.manage` | SCHOOL | LOW | OWNER, MANAGER | Menja samo INSTRUCTOR prikaznu etiketu; ne menja role key/binding. |
| `school.support.requests.approve` | SCHOOL | CRITICAL | OWNER | Approve/reject; step-up ≤5 min. |
| `school.support.grants.revoke` | SCHOOL | CRITICAL | OWNER | Trenutan revoke; step-up ≤5 min. |
| `school.support.activity.view` | SCHOOL | HIGH | OWNER | Pregled maskirane aktivnosti. |
| `platform.authorization.catalog.publish` | PLATFORM | CRITICAL | PLATFORM_SECURITY_ADMIN | Objavi novu policy reviziju. |
| `platform.notification.policy.publish` | PLATFORM | CRITICAL | PLATFORM_SECURITY_ADMIN | Aktivira immutable M14 notification policy reviziju; step-up i audit. |
| `platform.roles.manage` | PLATFORM | CRITICAL | PLATFORM_SECURITY_ADMIN | Dodela/suspenzija/opoziv platform role uz kontrolu poslednjeg security admina. |
| `platform.accounts.suspend` | PLATFORM | CRITICAL | PLATFORM_SECURITY_ADMIN | M01 AUTH-09. |
| `platform.accounts.reactivate` | PLATFORM | CRITICAL | PLATFORM_SECURITY_ADMIN | M01 AUTH-10. |
| `platform.accounts.disable` | PLATFORM | CRITICAL | PLATFORM_SECURITY_ADMIN | M01 AUTH-11 + M17 legal/security guard. |
| `platform.organizations.manage` | PLATFORM | CRITICAL | PLATFORM_OPERATIONS_ADMIN | M04 ORG-01..03; ne daje school business pristup. |
| `platform.schools.create` | PLATFORM | CRITICAL | PLATFORM_OPERATIONS_ADMIN | M04 SCH-01; step-up i initial-owner nomination guard. |
| `platform.schools.lifecycle.manage` | PLATFORM | CRITICAL | PLATFORM_OPERATIONS_ADMIN | M04 SCH-04 on-behalf-of i SCH-05/06. |
| `platform.schools.ownership.manage` | PLATFORM | CRITICAL | PLATFORM_OPERATIONS_ADMIN | M04 ORG-04 pravno-komercijalni transfer škole. |
| `platform.school_ownership.override` | PLATFORM | CRITICAL | PLATFORM_OPERATIONS_ADMIN | M04 OWN-04; obavezni legal case, reason i step-up. |
| `platform.product_entitlements.manage` | PLATFORM | CRITICAL | PLATFORM_OPERATIONS_ADMIN | M04 ENT-01/02; entitlement nije authorization. |
| `platform.billing_administration` | PLATFORM | CRITICAL | PLATFORM_BILLING_ADMIN | M04 SUB-02 i platform subscription query; nije M12 family finance. |
| `school.profile.manage` | SCHOOL | HIGH | OWNER, MANAGER | M04 SCH-02/03 u aktivnoj školi; timezone migracioni guard važi. |
| `school.lifecycle.activate` | SCHOOL | CRITICAL | OWNER | M04 SCH-04 uz primary-owner i readiness guard; ROLE_ONLY. |
| `school.owners.manage` | SCHOOL | CRITICAL | OWNER | M04 OWN-01..03 uz primary-owner/last-owner guard; ROLE_ONLY. |
| `school.subscription_usage.view` | SCHOOL | ELEVATED | OWNER, MANAGER | M04 usage snapshot samo sopstvene škole; bez roster/child liste. |
| `platform.support.requests.create` | PLATFORM | ELEVATED | PLATFORM_SUPPORT_AGENT | Predlog support zahteva, bez tenant pristupa. |
| `platform.support.sessions.start` | PLATFORM | HIGH | PLATFORM_SUPPORT_AGENT | Start samo već odobrenog granta za isti account. |
| `platform.support.break_glass.activate` | PLATFORM | CRITICAL | PLATFORM_INCIDENT_COMMANDER | Emergency activation iz §3.5. |
| `platform.support.break_glass.ratify` | PLATFORM | CRITICAL | PLATFORM_SECURITY_ADMIN | Ratifikacija drugog account-a. |
| `platform.support.reviews.complete` | PLATFORM | HIGH | PLATFORM_SECURITY_ADMIN | Post-incident review. |
| `platform.commercial.catalog.manage` | PLATFORM | CRITICAL | PLATFORM_BILLING_ADMIN | M04 COM-01..06. |
| `platform.commercial.plans.manage` | PLATFORM | CRITICAL | PLATFORM_BILLING_ADMIN | M04 COM-07..10. |
| `platform.commercial.agreements.manage` | PLATFORM | CRITICAL | PLATFORM_BILLING_ADMIN | M04 COM-11, 12, 14..18. |
| `platform.commercial.agreements.acceptance.record` | PLATFORM | CRITICAL | PLATFORM_BILLING_ADMIN | M04 COM-13 isključivo. |
| `platform.commercial.adjustments.manage` | PLATFORM | CRITICAL | PLATFORM_BILLING_ADMIN | M04 COM-19..20. |
| `platform.commercial.read` | PLATFORM | ELEVATED | PLATFORM_BILLING_ADMIN | M04 commercial query-ji. |

Delegation i direct-grant target za M05 ključeve su zatvoreni:

| Permission skup | `delegation_class` | Dozvoljeni direct target role |
|---|---|---|
| `school.rbac.assignments.view` | `DIRECT_DELEGABLE` | `LIMITED_ADMIN` |
| `school.rbac.roles.assign`, `.suspend`, `.revoke` | `ROLE_ONLY` | nijedan |
| `school.rbac.permissions.delegate`, `.revoke` | `DIRECT_DELEGABLE` | samo `MANAGER`; direct-granted pravo ne može dalje delegirati samo sebe niti permission koji actor nema iz sopstvenog role binding-a |
| `school.rbac.labels.manage` | `DIRECT_DELEGABLE` | `LIMITED_ADMIN` |
| `school.support.requests.approve`, `school.support.grants.revoke` | `ROLE_ONLY` | nijedan |
| `school.support.activity.view` | `DIRECT_DELEGABLE` | `MANAGER`, `LIMITED_ADMIN` |
| svi `platform.*` ključevi iz M05 | `ROLE_ONLY` | nijedan; samo PlatformRoleAssignment binding |
| svih šest `platform.commercial.*` ključeva | `ROLE_ONLY` | nijedan; isključivo PLATFORM_BILLING_ADMIN PlatformRoleAssignment binding — nema direct-grant, nema School/MANAGER delegate putanje |

Za M04 school ključeve default binding je: OWNER dobija sva četiri; MANAGER dobija samo `school.profile.manage` i `school.subscription_usage.view`. `school.profile.manage` je direct-delegable samo ka LIMITED_ADMIN, a `school.subscription_usage.view` ka LIMITED_ADMIN; `school.lifecycle.activate` i `school.owners.manage` su ROLE_ONLY i ostaju pod M04 primary-owner guardom. Svi M04 platform ključevi su ROLE_ONLY. M05 ne menja command semantiku M04.

M04 permission ključevi i default binding-i su u tabeli iznad. Svih šest commercial ključeva imaju default binding isključivo `PLATFORM_BILLING_ADMIN`: nijedna School rola, Organization veza, payer status, CommercialAgreement, Support grant ili entitlement ih ne dodeljuje. Nijedan permission ne implicira drugi.

Finansijski i Operations ključevi ulaze u jednu policy reviziju bez preimenovanja ili dupliranja. M12 koristi granularne ključeve `finance.fee_rules.manage`, `finance.billing.preview`, `finance.obligations.manage`, `finance.credit.apply`, `finance.credit.correct`, `finance.view`, `finance.billing.confirm`, `finance.payments.record_cash`, `finance.payments.record_bank`, `finance.financial_profile.manage`, `finance.payments.reverse`, `finance.payment_allocations.correct`, `finance.refund_reviews.decide` i `finance.refunds.confirm_external`; njihov business/subject scope ostaje M12. Tačno 26 aktivnih Operations permission ID-eva iz F-O01 ostaju odvojeni i ne aktiviraju reserved workspace domen.

#### 3.3.1. Matrica uloga, resursa i M05 akcija

`A` znači dozvoljeno uz permission i sve guardove; `C` znači uslovno prema navedenom ograničenju; `—` znači server-side deny. Platform role kolone važe samo za platform resurse ili unutar posebno odobrenog Support grant-a; nikad kao implicitna school dozvola.

| Resurs / akcija | OWNER | MANAGER | LIMITED_ADMIN | INSTRUCTOR | SUBSTITUTE_INSTRUCTOR | GUARDIAN | PAYER | PLAT. OPS | PLAT. SECURITY | PLAT. SUPPORT | INCIDENT CMD | PLAT. BILLING |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| School RoleAssignment / view | A | A | — | — | — | — | — | — | — | — | — | — |
| School RoleAssignment / assign-suspend-reactivate-revoke | C: samo niže staff role | C: LIMITED/INSTRUCTOR/SUBSTITUTE | — | — | — | — | — | — | — | — | — | — |
| PermissionGrant / grant | A: delegable school pravo | C: ima oba prava i ne širi scope | — | — | — | — | — | — | — | — | — | — |
| PermissionGrant / revoke | A | C: sopstveni dozvoljeni domet | — | — | — | — | — | — | — | — | — | — |
| SchoolRoleLabelOverride / set-retire | A | A | — | — | — | — | — | — | — | — | — | — |
| SupportAccessRequest / approve-reject | A: step-up, drugi account | — | — | — | — | — | — | — | — | — | — | — |
| SupportAccessGrant / revoke | A: svoja škola | — | — | — | — | — | — | — | C: security incident | — | — | — |
| SupportActivity / view | A | C: samo explicit grant | C: samo explicit grant | — | — | — | — | — | C: incident/audit duty | C: samo sopstveni grant | C: sopstveni incident | — |
| PolicyRevision / publish | — | — | — | — | — | — | — | — | A | — | — | — |
| PlatformRoleAssignment / manage | — | — | — | — | — | — | — | — | A: step-up, ticket, bez self-assign | — | — | — |
| Account / suspend-reactivate-disable | — | — | — | — | — | — | — | — | A: tačan `platform.accounts.*` | — | — | — |
| SupportAccessRequest / create | — | — | — | — | — | — | — | — | — | A: samo sebi i ticket-assignee match | — | — |
| SupportAccessSession / start-end | — | — | — | — | — | — | — | — | C: emergency revoke/end | A: named odobren grant | C: break-glass grant | — |
| BreakGlass / activate | — | — | — | — | — | — | — | — | — | — | A | — |
| BreakGlass / ratify-review | — | — | — | — | — | — | — | — | A | — | — | — |
| M04 provisioning/lifecycle/entitlement | — | — | — | — | — | — | — | A: samo tačni M04 bindings | C: samo security override koji M04 navodi | — | — | C: samo billing key |
| M04 commercial catalog/plan/agreement/adjustment (COM-01..20) | — | — | — | — | — | — | — | — | — | — | — | A: isključivo tačan granularni `platform.commercial.*` ključ, step-up ≤5min, ticket_ref |

Za svaki poslovni resurs vlasnički modul definiše semantiku, a M05 registruje stabilan permission key, role binding, scope, delegaciju i offline policy. M06–M07 su jedino u `04-M05-PERMISSION-REGISTRY-M06-M07.md`, M08–M12 binding-i su §3.3.2, M13–M16 §3.3.3, a M17–M21 i M28 jedino u `03-M05-PERMISSION-REGISTRY-M17-M21-M28.md`. Dok vlasnički i M05 ugovor nisu oba prisutna i saglasna, rezultat je deny.

#### 3.3.2. M08–M12 permission policy i default bindings

`A` je default role binding; `S` zahteva i vlasnički subject/resource guard; `—` nema binding. Direct grant je dozvoljen samo gde kolona `Delegacija` to kaže i nikad ne uklanja subject guard. `LIMITED_ADMIN` bez direct grant-a ostaje deny.

| Permission | Risk | Offline | OWNER | MANAGER | LIMITED_ADMIN | INSTRUCTOR | SUBSTITUTE | GUARDIAN | PAYER | Delegacija |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `school.structure.view` | LOW | DENY | A | A | — | — | — | — | — | ka LIMITED_ADMIN |
| `school.structure.manage` | ELEVATED | DENY | A | A | — | — | — | — | — | ka LIMITED_ADMIN |
| `school.occupancy.manage` | HIGH | DENY | A | A | — | — | — | — | — | ka LIMITED_ADMIN za MANUAL_HOLD samo |
| `school.online_access.view` | HIGH | DENY | S | S | — | S | S | S | — | bez direct grant-a; occurrence/event/child scope obavezan |
| `school.online_access.manage` | CRITICAL | DENY | A | A | — | — | — | — | — | ROLE_ONLY; step-up |
| `school.groups.view` | LOW | DENY | A | A | — | S | S | — | — | ka LIMITED_ADMIN |
| `school.groups.manage` | ELEVATED | DENY | A | A | — | — | — | — | — | ka LIMITED_ADMIN |
| `school.groups.capacity.override` | HIGH | DENY | A | A | — | — | — | — | — | ka LIMITED_ADMIN uz reason; nikad HARD_LIMIT bypass |
| `school.groups.enrollments.view` | HIGH | DENY | A | A | — | S | S | — | — | ka LIMITED_ADMIN; roster subject guard |
| `school.groups.enrollments.manage` | HIGH | DENY | A | A | — | — | — | — | — | ka LIMITED_ADMIN |
| `school.groups.staff_assignments.manage` | HIGH | DENY | A | A | — | — | — | — | — | ka LIMITED_ADMIN |
| `school.schedule.view` | LOW | DENY | A | A | — | S | S | S | — | ka LIMITED_ADMIN; Guardian linked-child projection |
| `school.schedule.manage` | HIGH | DENY | A | A | — | — | — | — | — | ka LIMITED_ADMIN |
| `school.schedule.conflict_override` | CRITICAL | DENY | — | — | — | — | — | — | — | RESERVED u H0; evaluator uvek deny |
| `school.attendance.view` | HIGH | DENY | A | A | — | S | S | S | — | ka LIMITED_ADMIN; Guardian linked-child projection |
| `school.attendance.record` | HIGH | QUEUE_ALLOWED | A | A | — | S | S | — | — | ka LIMITED_ADMIN; jedini H0 queue permission |
| `school.attendance.lock` | HIGH | DENY | A | A | — | — | — | — | — | ka LIMITED_ADMIN |
| `school.attendance.correct_after_lock` | CRITICAL | DENY | A | A | — | — | — | — | — | ROLE_ONLY; step-up+reason |
| `school.attendance.roster_correct` | CRITICAL | DENY | A | A | — | — | — | — | — | ROLE_ONLY; step-up+reason |
| `finance.view` | HIGH | DENY | A | A | — | — | — | — | S | ka LIMITED_ADMIN; PAYER samo ACTIVE payer subject |
| `finance.fee_rules.manage` | HIGH | DENY | A | A | — | — | — | — | — | ka LIMITED_ADMIN |
| `finance.billing.preview` | ELEVATED | DENY | A | A | — | — | — | — | — | ka LIMITED_ADMIN |
| `finance.billing.confirm` | CRITICAL | DENY | A | A | — | — | — | — | — | ROLE_ONLY; fresh step-up za svaki confirm |
| `finance.obligations.manage` | HIGH | DENY | A | A | — | — | — | — | — | ka LIMITED_ADMIN |
| `finance.payments.record_cash` | HIGH | DENY | A | A | — | — | — | — | — | ka LIMITED_ADMIN |
| `finance.payments.record_bank` | HIGH | DENY | A | A | — | — | — | — | — | ka LIMITED_ADMIN |
| `finance.payment_allocations.correct` | CRITICAL | DENY | A | A | — | — | — | — | — | ROLE_ONLY; reason |
| `finance.payments.reverse` | CRITICAL | DENY | A | A | — | — | — | — | — | ROLE_ONLY; step-up+reason |
| `finance.credit.apply` | HIGH | DENY | A | A | — | — | — | — | S | PAYER samo sopstveni FamilyBillingAccount; bez direct grant-a |
| `finance.credit.correct` | CRITICAL | DENY | A | A | — | — | — | — | — | ROLE_ONLY; fresh step-up + drugi različit ovlašćeni actor za svaku korekciju |
| `finance.refund_reviews.decide` | CRITICAL | DENY | A | A | — | — | — | — | — | ROLE_ONLY |
| `finance.refunds.confirm_external` | CRITICAL | DENY | A | A | — | — | — | — | — | ROLE_ONLY; step-up |
| `finance.financial_profile.manage` | CRITICAL | DENY | A | A | — | — | — | — | — | ROLE_ONLY; step-up |

GUARDIAN nema default finance binding. Isti account može dobiti finance samo kroz zaseban PAYER assignment sa ACTIVE M07 payer basis-om ili school admin ulogu. PAYER nema attendance, group roster, schedule ni online-access binding. H1 Guardian schedule/attendance prikaz dodatno zahteva aktivan M28 entitlement; postojanje binding-a samo po sebi ne aktivira H1 površinu. Staff assignment je subject filter, nikad izvor permission-a.

#### 3.3.3. M13–M16 permission policy i default bindings

Sve operacije su offline `DENY`. `S` zahteva aktuelni resource/subject basis; snapshot nije grant.

| Permission | Risk | OWNER | MANAGER | LIMITED_ADMIN | INSTRUCTOR/SUBSTITUTE | GUARDIAN | PAYER | Delegacija/guard |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `school.communications.view` | HIGH | A | A | — | S | S | — | Limited direct; current recipient/group basis |
| `school.communications.compose` | HIGH | A | A | — | S | — | — | Limited direct; assigned group |
| `school.communications.publish` | HIGH | A | A | — | — | — | — | Explicit scoped grant ka Limited/Instructor |
| `school.communications.withdraw` | CRITICAL | A | A | — | — | — | — | ROLE_ONLY; step-up/reason |
| `school.communications.delivery_view` | HIGH | A | A | — | — | — | — | Limited direct; agregat bez PII |
| `school.notifications.view_own` | HIGH | S | S | S | S | S | S | Own authorized subject only |
| `school.notifications.mark_read_own` | LOW | S | S | S | S | S | S | Own only |
| `school.attention.view` | HIGH | A | A | — | S | — | — | Limited direct; staff scope |
| `school.attention.resolve` | HIGH | A | A | — | — | — | — | Limited direct po item scope-u |
| `school.notification_delivery.view` | HIGH | A | A | — | — | — | — | Limited direct; agregat |
| `school.documents.view` | HIGH | A | A | — | S | S | S | Limited direct; owner subject port |
| `school.documents.manage` | HIGH | A | A | — | — | — | — | Limited direct |
| `school.documents.publish` | CRITICAL | A | A | — | — | — | — | ROLE_ONLY |
| `school.documents.download` | CRITICAL | S | S | — | S | S | S | Ticket+current subject; no direct grant |
| `school.documents.accept` | HIGH | S | S | S | S | S | S | Isključivo sopstveni zahtev; guardian samo povezano dete; nikad u tuđe ime |
| `school.documents.record_assisted_acceptance` | CRITICAL | A | A | — | — | — | — | ROLE_ONLY; step-up+giver+reason |
| `school.documents.access_log_view` | CRITICAL | A | A | — | — | — | — | ROLE_ONLY |
| `school.events.view` | HIGH | A | A | — | S | S | — | Limited direct; audience/assignment/child |
| `school.events.manage` | HIGH | A | A | — | — | — | — | Limited direct |
| `school.events.publish` | CRITICAL | A | A | — | — | — | — | ROLE_ONLY |
| `school.events.register_child` | HIGH | — | — | — | — | S | — | Guardian child+audience |
| `school.events.registration_manage` | HIGH | A | A | — | S | — | — | Limited direct; assigned scope |
| `school.events.capacity_override` | CRITICAL | A | A | — | — | — | — | ROLE_ONLY; WARNING only+reason |
| `school.events.attendance_record` | HIGH | A | A | — | S | — | — | Limited direct; online assigned scope |
| `school.events.attendance_correct` | CRITICAL | A | A | — | — | — | — | ROLE_ONLY; step-up+reason |

PAYER document binding važi samo za M12-autorizovan `PAYMENT_PROOF`; notification binding samo za njegov finance subject. Nijedno ne daje child profile, event ili komunikacioni pristup. Support scope ne može uključiti document content/download/acceptance, communication body/recipient list, event participant/attendance ili notification params.

### 3.4. Standardni Support Access

1. Support agent sa `platform.support.requests.create` može tražiti pristup samo sebi, za jednu školu, tiket na kojem je evidentiran kao assignee, zatvoren purpose code, precizan capability/resource scope i 15–120 minuta. School actor otvara/komunicira support ticket drugim ugovorom; ne može unapred proizvesti tenant grant bez named support request-a.
2. Zahtev ističe za 24 sata. Istek se proverava pri read/command vremenu; M21 `rbac.support_access_expiry` samo materijalizuje request/grant/session/break-glass status i ne daje grace period.
3. Odobriti/reject može aktivni OWNER iste škole sa `school.support.requests.approve`, aktivnom M03 sesijom i step-up dokazom ne starijim od 5 minuta.
4. Requester/support account ne može odobriti sopstveni zahtev čak ni ako je ista osoba OWNER. Approver i support account moraju biti različiti UserAccount-i.
5. Approver sme suziti capability, resurse i trajanje; ne sme proširiti zahtev.
6. Grant je vezan za imenovan support account i nikad se ne deli. Access session koristi poseban support credential/context sa vidljivim bannerom: support actor, škola, tiket, preostalo vreme.
7. Support nema impersonation, „view as owner“, tuđu sesiju, uvid u auth identity/provider claim ili nevidljiv pristup.
8. Standardni prikaz koristi masking. Dete: dozvoljen je samo minimalni tehnički identifikator/HMAC i podatak potreban za dokazanu grešku; ime, datum rođenja, kontakt, zdravlje, beleške, dokument sadržaj, fotografija/video i porodične finansije su denied. `SPECIAL_CATEGORY` je standardnom support-u uvek denied.
9. `CONTROLLED_REPAIR_EXECUTE` mora navesti tačan command key i resource ID; validira se ista business, tenant, expected-version i audit pravila kao redovna komanda. Support grant ne može dati permission koji ciljna repair komanda nije eksplicitno označila kao support-repair dozvoljen.
10. Standardni support nikad ne sme: bulk export/download; menjati owner, role/permission, account identity/status, payment/refund/ledger, consent/legal proof, retention/legal hold ili audit; brisati podatke; gasiti masking.
11. OWNER može odmah opozvati grant. Platform security može ga opozvati samo zbog security incidenta, uz reason i obaveštenje školi. Revoke/expiry prekida active session/realtime, povećava tenant access version i blokira sledeći request bez čekanja outbox-a.
12. Svi aktivni OWNER account-i škole dobijaju deduplikovanu notifikaciju bez PII za request created, approved/rejected, session started/ended i revoked/expired; M04 PRIMARY_OWNER je obavezni fallback primalac čak i ako su lične opcione notifikacije drugih owner-a ugašene. OWNER vidi activity listu; ovlašćeni drugi administrator je vidi samo uz eksplicitni `school.support.activity.view` grant.

`SupportTicketVerificationPort.verify(ticket_ref, support_account_id, school_id)` mora vratiti autoritativan rezultat `ACTIVE_ASSIGNED` sa nepredvidivim opaque `ticket_verification_receipt_id UUID` ili `NOT_ALLOWED`; adapter ne vraća ticket sadržaj M05-u. Receipt je kratkoživeći/verzionisan dokaz verifier-a, tenant/account/ticket-purpose bound i ponovo se proverava pri odobrenju ako je stariji od 15 minuta ili je ticket promenio version. `NOT_ALLOWED` vraća tačno 422 `SUPPORT_TICKET_INVALID_OR_NOT_ASSIGNED`, a nedostupan verifier 503 `SUPPORT_TICKET_VERIFICATION_UNAVAILABLE`. Bez konfigurisanog i dostupnog verifier-a standardni Support Access je fail-closed. `IncidentVerificationPort.verify(incident_ref, reason_code, school_id)` isto mora potvrditi `ACTIVE`; nedostupnost blokira break-glass sa 503, ne pretvara se u podrazumevani allow.

### 3.5. Break-glass

1. Dozvoljeni razlozi su samo `ACTIVE_SECURITY_INCIDENT`, `CRITICAL_DATA_INTEGRITY`, `SERVICE_RECOVERY` i zahtevaju postojeći incident/ticket ref.
2. Aktivator mora imati `platform.support.break_glass.activate` i step-up ≤5 minuta. Unosi tačnu školu, scope, maksimalno 30 minuta i minimizovano obrazloženje.
3. Aktivacija odmah kreira najograničeniji grant. Drugi, različit `PLATFORM_SECURITY_ADMIN` mora ratifikovati u roku 10 minuta. Bez ratifikacije grant se automatski opoziva u trenutku deadline-a; request-time guard je autoritet.
4. Škola se obaveštava odmah. Samo ako bi obaveštenje aktivno pogoršalo security containment, može se odložiti najviše 60 minuta uz `notification_delay_reason`; istekom se šalje obavezno.
5. Break-glass ne dozvoljava impersonation, export, owner/RBAC/account identity/payment/ledger/consent/audit promene niti brisanje. Dozvoljava samo dijagnostiku i containment/repair komande unapred označene `break_glass_allowed=true` u vlasničkom modulu.
6. Svaki pokušaj, uključujući odbijen, ulazi u tamper-evident SupportActivityEvent. Post-incident review je obavezan u roku 24 sata od završetka granta.
7. Ne postoji retroaktivno „odobrenje škole“ koje briše break-glass prirodu. Škola vidi incident, actor, reason, scope, vreme, aktivnosti i rezultat pregleda u dozvoljeno maskiranom obliku.

### 3.6. Privatnost, retention i observability

- Role/permission audit istorija čuva se 5 godina od prestanka tenant ugovora; support request/grant/session/activity 24 meseca od zatvaranja; break-glass ratification/review 5 godina. M17 legal hold može produžiti, a formalna pravna odluka/DCR promeniti rok; implementacija ga ne bira.
- Telemetry/logs sadrže `correlation_id`, pseudonimizovan actor/tenant, command key, decision ALLOW/DENY/ERROR, latency bucket, policy revision i error code. Ne sadrže ime, email, telefon, datum rođenja, child ID u čistom obliku, reason note, ticket sadržaj, token ili payload.
- Metrike najmanje: authorization decision latency p50/p95/p99; deny po bezbednom reason bucket-u; stale version; policy unavailable; support active grants; break-glass activations/ratification misses; audit write failures. Tenant naziv nije label.
- Alert: bilo koji audit write failure, break-glass bez ratifikacije, pokušaj zabranjene support akcije ili >5 cross-tenant deny pokušaja istog actor pseudonima/5 min.
- Limiti: najviše šest open school role assignment-a po membership-u (po jedan kanonski key), 200 open direct grantova po role assignment-u, 100 resource scope items i 20 controlled-repair items po support grant-u. Prekoračenje je 422 `RBAC_LIMIT_EXCEEDED`; nikad se tiho ne odbacuju stavke.
- Performance budžet na reprezentativnom seedu do 1.000 aktivnih permission definicija, 6 role assignment-a i 200 grantova po actoru: authorization odluka bez mrežnog vremena p95 ≤25 ms kada je cache dokazano svež, p95 ≤120 ms pri autoritativnom read-u i p99 ≤250 ms; support activity page od 20 redova p95 ≤500 ms. Revocation/revoke komanda p95 ≤500 ms do durable commit-a, a zahtev započet posle commit-a ima nula dozvoljenog stale prozora; realtime disconnect p95 ≤5 s, ali u tom intervalu nijedna nova radnja/event delivery ne prolazi authorization recheck.

### 3.7. Offline i optimistic UI

1. Role, permission, policy, support request/approval/grant/revoke i break-glass operacije zahtevaju aktivnu vezu i server commit; nema offline ni optimistic-final prikaza.
2. Lease se izdaje samo za permission sa `QUEUE_ALLOWED` koji vlasnički modul eksplicitno odobri. M05 r1.0 unapred ne proglašava buduću poslovnu operaciju offline-capable.
3. Lease važi do minimuma `issued_at+12h`, `term_end+4h`, M11 correction deadline-a i M01 absolute session expiry-a.
4. Offline snimak sme sadržati samo opaque operation/idempotency, school/session/participant-roster/group/term reference, display ime potrebno za aktivni attendance ekran, predloženi status/minutes-late, roster digest, base record version, lease vreme i client sync status/error code. Ne sme DOB, kontakt, health/safety, guardian, finansije, dokument, consent, avatar/fotografiju, auth token u payload-u ili slobodnu medicinsku/administrativnu belešku.
5. Logout, session expiry, account/membership/role revoke, school switch i promena korisnika naređuju trenutno brisanje tenant PWA cache-a i lease-a sa uređaja. Server revoke ne može garantovati fizičko brisanje nedostupnog uređaja, pa enkripcija po session-bound ključu mora učiniti podatke nečitljivim posle lokalnog isteka.
6. Sync ponovo proverava current account, tenant, membership, permission, subject i business invariant. Lease je dokaz vremena capture-a, ne pravo da server prihvati zastarelu operaciju. Neuspeh autorizacije daje finalni `SYNC_FAILED` bez automatskog prebacivanja na drugog korisnika/tenant.

### 3.8. Edge cases — obavezni ishodi

| # | Scenario | Deterministički ishod |
|---:|---|---|
| 1 | Korisnik ima MANAGER i INSTRUCTOR u istoj školi, a UI je u Instructor workspace-u. | Efektivna prava su unija obe aktivne uloge; workspace ne sužava. Subject guard i dalje važi. |
| 2 | Isti account je OWNER škole A i GUARDIAN škole B. | A prava nikada ne ulaze u B; svaki tenant se zasebno razrešava. |
| 3 | Dva OWNER-a istovremeno pokušaju da opozovu jedan drugog, a ostao bi nula owner-a. | M04 last-owner lock/constraint dozvoli najviše jednu bezbednu promenu; pokušaj koji bi ostavio nulu vraća 409. |
| 4 | MANAGER pokušava sebi dodeliti finance permission koji nema. | 403; nema granta, audit dozvoljenog uspeha ni outbox-a. Security deny telemetry bez PII. |
| 5 | Direct grant važi, ali parent role je suspendovan u drugom tabu. | Sledeći zahtev fail-closed; grant je neefektivan i stale cache se ne koristi. |
| 6 | Role revoke commit-ovan dok je visokorizična finansijska komanda već počela. | Komanda ponovo proverava versions pre commit-a i vraća 409 `RBAC_CONCURRENT_CHANGE`; nema finansijskog side effect-a. |
| 7 | Resource ID pripada drugoj školi. | Safe 404 bez imena, count-a ili permission indikatora; support activity/log ne otkriva podatak. |
| 8 | OWNER odobri support zahtev posle njegovog 24h deadline-a, pre nego što JOB status promeni. | 410; lazy expiry je autoritet, grant ne nastaje. |
| 9 | Support agent ručno promeni URL na resource druge škole. | Tačno 404 `RBAC_NOT_FOUND_SAFE`; pokušaj se auditira bez target payload-a. |
| 10 | Grant istekne usred aktivne support sesije. | Prvi request nakon isteka je 410 `SUPPORT_GRANT_EXPIRED`, sesija se efektivno završava i realtime se gasi; job nije potreban za bezbednost. |
| 11 | Break-glass nije ratifikovan za 10 minuta. | Automatski efektivno REVOKED/MISSED; nijedna kasna radnja ne prolazi. Naknadna ratifikacija vraća 410. |
| 12 | Isti account je aktivator i ratifikator break-glass-a. | 409; ratifikacija se ne računa. |
| 13 | Policy objava sadrži unknown binding ili dva ACTIVE kataloga. | Cela transakcija se odbija; prethodna ACTIVE revizija ostaje jedini autoritet. |
| 14 | Permission je retired novom revizijom dok postoji direct grant. | Pre aktivacije nove revizije grant postaje neefektivan i atomarno se revokuje/materializuje; nema stale allow prozora. |
| 15 | Legacy Person ima TRAINER i INSTRUCTOR zbog parcijalne migracije. | Migracija deduplikuje u jedan INSTRUCTOR assignment uz history mapping; runtime u međuvremenu fail-closed ne sabira duplikat. |
| 16 | Guardian dobije bazni permission ali GuardianChildLink je opozvan. | M07 subject guard odbija odmah; M07/M05 invalidation prekida cache/realtime/offline lease. |
| 17 | Identical retry AssignRole posle prvog uspeha. | Vraća isti resource/result sa `replay=true`, bez drugog assignment/audit/outbox zapisa. |
| 18 | Isti idempotency ključ sa drugim target role-om. | 409 `RBAC_IDEMPOTENCY_KEY_REUSED`; ništa se ne menja. |
| 19 | Klijent ili seed pošalje `EVENT_ORGANIZER_WORKSPACE` dok je domen RESERVED. | 422 `RBAC_AUTHORIZATION_DOMAIN_UNKNOWN`; ne nastaju context, role, grant ili existence hint. |
| 20 | Organization sa School A/B ili hibridnim agreement-om pokuša Organization-wide autorizaciju. | Tačno 422 `RBAC_AUTHORIZATION_DOMAIN_UNKNOWN`; agreement nije grant, A prava ne ulaze u B, ne kreira se lažni School/workspace assignment. |

## 4. Tenant & Security Guard

### 4.1. School-scoped skladište

- Svaki tenant agregat nosi `school_id NOT NULL`.
- FK ka tenant entitetu koristi composite `(school_id, referenced_id)` ili ekvivalentnu baznu garanciju; application check nije jedina zaštita.
- Query počinje od autorizovanog `TenantExecutionContext.school_id`, nikad od klijentskog school parametra. Paginacija, brojanje, fuzzy search, export, cache key, object-storage key, job payload, realtime channel i audit projection su school-scoped pre filtera/sortiranja.
- Jedan DB poziv/batch ne vraća business podatke više škola. Platform administrative lista vraća samo provisioning metadata koju M04 dopušta, ne M05 business podatke.

Budući business authorization domen mora imati sopstveni immutable domain ID u svakom svom agregatu, composite FK/unique zaštitu, context resolver i iste negativne kontrole za query/list/count/search/cursor/cache/job/storage/export/realtime. Njegov vlasnički modul poseduje assignment entitet; M05 poseduje policy/evaluator. Ne koristi nullable `school_id`, polymorphic Organization grant ili sintetički School. Dok to nije dokazano, domen ostaje `RESERVED` i svaki pristup je deny.

### 4.2. Odgovori bez enumeration-a

- Nepostojeći ID i postojeći ID druge škole daju isti safe 404 oblik, približno isti put obrade i bez indikatora postojanja.
- Postojeće dete/subject za koje guardian ili payer nema pravo da zna da postoji takođe daje isti safe 404 oblik; ne koristi se `RBAC_SUBJECT_SCOPE_FORBIDDEN` za takav slučaj.
- `RBAC_FORBIDDEN` ili `RBAC_SUBJECT_SCOPE_FORBIDDEN` 403 dozvoljeni su samo kada actor već ima nezavisno pravo da zna identitet resursa, ali nema konkretnu akciju ili uži dozvoljeni scope.
- Lista/search sugeriše samo već dozvoljene entitete; nema `total_count`, highlight, faceta ili autocomplete-a računatog nad skrivenim redovima.

### 4.3. Podaci dece

- Bazni role/permission nikad nije dovoljan bez child subject guarda kada `child_data_class != NONE`.
- INSTRUCTOR vidi minimalni roster samo dodeljene grupe/termina; SUBSTITUTE_INSTRUCTOR samo eksplicitno dodeljen termin; GUARDIAN samo dete iz aktivnog M07 linka i dozvoljene kategorije.
- Standardni support ne vidi special-category/health podatke, dokument content, consent evidence, kontakt ili fotografiju/video deteta.
- Export/download i signed URL proveravaju authorization pri kreiranju i pri preuzimanju; URL je kratak, jednokratno/ograničeno važeći i tenant-bound.

### 4.4. Revocation i cache

U transakciji uspešne role/grant/policy/support promene upisuju se agregat, audit, outbox i bezbednosna invalidacija: M03 `tenant_access_version` za pogođeni regularni account/school, `SupportAccessGrant.version`/`SupportAccessSession.version` uz sinhroni write-through revocation dokaz za support account/school i, kada M01 account security to zahteva, `authorization_version`. Server ne vraća uspeh pre durable commit-a. Zahtev započet posle commit-a ne sme proći kroz stale cache. Kada cache freshness nije dokazana, autoritativni store se čita fail-closed. Outbox služi brzini projekcija/realtime-a, ne autorizaciji.

## 5. Lifecycle & transitions

### 5.1. AuthorizationPolicyRevision

| Iz | Komanda/događaj | U | Guard |
|---|---|---|---|
| — | Create draft | DRAFT | Revision number i hash jedinstveni. |
| DRAFT | Publish valid revision | ACTIVE | CRITICAL permission, step-up, validan zatvoren katalog; prethodni ACTIVE u istoj transakciji → SUPERSEDED. |
| DRAFT | Reject | REJECTED | Reason/ticket; terminalno. |
| ACTIVE | Publish next revision | SUPERSEDED | Atomski sa novim ACTIVE; terminalno. |
| ACTIVE/SUPERSEDED/REJECTED | Bilo koji povratak | — | Zabranjeno. |

### 5.2. RoleAssignment i PlatformRoleAssignment

| Iz | Događaj | U | Dozvoljeno |
|---|---|---|---|
| — | Create, `valid_from>now` | SCHEDULED | Da, validni actor/target/scope. |
| — | Create, `valid_from<=now<valid_until/null` | ACTIVE | Da. |
| SCHEDULED | Time reached / `rbac.temporal_access_transition` | ACTIVE | Lazy/request guard je autoritet; job materijalizuje. |
| SCHEDULED | Revoke | REVOKED | Da. |
| SCHEDULED | `valid_until<=now` | EXPIRED | Da. |
| ACTIVE | Suspend | SUSPENDED | Da; ne za poslednjeg OWNER/security admina. |
| SUSPENDED | Reactivate | ACTIVE | Samo isti membership/account validan i rok nije istekao. |
| ACTIVE/SUSPENDED | Revoke | REVOKED | Da uz guards. |
| ACTIVE/SUSPENDED | Time elapsed / `rbac.temporal_access_transition` | EXPIRED | Request-time autoritet; child grant/invalidation atomarnost. |
| REVOKED/EXPIRED | Bilo šta | — | Terminalno; nova dodela je nov ID. |

### 5.3. PermissionGrant

| Iz | Događaj | U | Dozvoljeno |
|---|---|---|---|
| — | Grant | ACTIVE | Samo active parent role, delegable permission/scope. |
| ACTIVE | Revoke/parent revoke/permission retire | REVOKED | Da; parent/retire atomarno. |
| ACTIVE | Time elapsed | EXPIRED | Request-time autoritet. |
| REVOKED/EXPIRED | Reactivate | — | Ne; novi grant. |

`SchoolRoleLabelOverride`: nema reda → RBAC-12 kreira ACTIVE; ACTIVE → RBAC-12 menja label uz expected version; ACTIVE → RBAC-13 RETIRED; RETIRED je terminalan, a novo postavljanje pravi novi ACTIVE red. Nijedan prelaz ne invalidira permission uniju, ali invalidira tenant UI/navigation projection.

### 5.4. SupportAccessRequest

| Iz | Radnja | U | Guard |
|---|---|---|---|
| — | SUP-01 | PENDING | Valid ticket/purpose/scope/duration. |
| PENDING | SUP-02 | APPROVED | Owner, step-up, no self-approval; grant u istoj transakciji. |
| PENDING | SUP-03 | REJECTED | Owner + reason. |
| PENDING | SUP-04 | CANCELLED | Requester pre odluke. |
| PENDING | 24h elapsed | EXPIRED | Lazy autoritet. |
| APPROVED/REJECTED/CANCELLED/EXPIRED | Bilo koja odluka | — | Terminalno. |

### 5.5. SupportAccessGrant i Session

| Entitet/iz | Događaj | U | Guard |
|---|---|---|---|
| Grant — | Approved now/future | ACTIVE/SCHEDULED | Exact account/scope/end. |
| Grant SCHEDULED | Start reached | ACTIVE | Lazy. |
| Grant ACTIVE/SCHEDULED | SUP-07 | REVOKED | School owner ili platform security incident. |
| Grant ACTIVE/SCHEDULED | End reached | EXPIRED | Lazy; terminalno. |
| Session — | SUP-05 | ACTIVE | Grant ACTIVE, actor match, no other active session. |
| Session ACTIVE | SUP-06/idle 15m | ENDED | Voluntary/idle. |
| Session ACTIVE | Grant revoked | REVOKED | Atomski/efektivno odmah. |
| Session ACTIVE | Grant expired | EXPIRED | Request-time. |
| Session terminal | Restart | — | Nova session samo dok grant i dalje ACTIVE. |

### 5.6. Break-glass

| Iz | Radnja/vreme | U | Posledica |
|---|---|---|---|
| — | SUP-08 | PENDING ratification + ACTIVE grant | Max 30 min; notification. |
| PENDING | SUP-09 pre 10m, distinct approver | RATIFIED | Grant ostaje do svog kraja. |
| PENDING | 10m elapsed | MISSED | Grant odmah REVOKED. |
| PENDING/RATIFIED | Security revoke | REVOKED | Grant/session revoked. |
| Grant ended | Review created | DUE | Due +24h. |
| DUE | SUP-10 pre due | COMPLETED | Findings/ticket zapisani. |
| DUE | Due elapsed | OVERDUE | Alert; review i dalje mora biti completed. |
| OVERDUE | SUP-10 | COMPLETED | Kasni completion ostaje auditovan. |

### 5.7. OfflineAuthorizationLease

| Iz | Događaj | U | Pravilo |
|---|---|---|---|
| — | RBAC-10 | ACTIVE | `QUEUE_ALLOWED`, ≤12h, exact device/resource. |
| ACTIVE | RBAC-11 ili auth/access revoke | REVOKED | Sledeći sync denied. |
| ACTIVE | Time elapsed | EXPIRED | Lazy. |
| ACTIVE | `consumed_operations=max_operations` | CONSUMED | Ne prihvata novi capture. |
| Terminal | Reuse | — | Zabranjeno. |

## 6. Error catalog

Odgovor sadrži stabilan `code`, lokalizabilan neutralan `message_key`, `correlation_id` i opcioni bezbedan `retryable`; nikad interni policy sadržaj ili podatke druge škole.

| Kod | HTTP | Kada |
|---|---:|---|
| `RBAC_AUTHENTICATION_REQUIRED` | 401 | Nema važeće M01 sesije. |
| `RBAC_STEP_UP_REQUIRED` | 401 | Step-up nedostaje/prestar. |
| `RBAC_CONTEXT_REQUIRED` | 409 | Nema validnog M03 school context-a. |
| `RBAC_NOT_FOUND_SAFE` | 404 | Nepostojeći ili cross-tenant target. |
| `RBAC_FORBIDDEN` | 403 | Nedostaje permission u poznatom tenantu. |
| `RBAC_SUBJECT_SCOPE_FORBIDDEN` | 403 | Permission postoji i actor već sme da zna resurs, ali uži subject/action guard ne prolazi. Skriven child/subject koristi `RBAC_NOT_FOUND_SAFE`. |
| `RBAC_POLICY_UNAVAILABLE` | 503 | Nije dokaziva jedna sveža ACTIVE revizija. |
| `RBAC_AUTHORIZATION_DOMAIN_UNKNOWN` | 422 | Domen je unknown, RESERVED, RETIRED, nema aktivan owner resolver ili Organization pokušava da glumi auth domen. |
| `RBAC_PERMISSION_NOT_REGISTERED` | 503 | Kod traži unknown/retired permission. |
| `RBAC_POLICY_REVISION_INVALID` | 422 | Draft ima duplicate/unknown/cikličnu/nevalidnu vezu. |
| `RBAC_POLICY_REVISION_CONFLICT` | 409 | Stale revision ili konkurentna objava. |
| `RBAC_REASON_INVALID` | 422 | Reason code/note ne odgovara zatvorenom registru. |
| `RBAC_ROLE_DEFINITION_NOT_FOUND` | 422 | Role key nije kanonski/aktivan. |
| `RBAC_ROLE_ASSIGNMENT_EXISTS` | 409 | Open prirodni ključ već postoji. |
| `RBAC_ROLE_ASSIGNMENT_NOT_FOUND` | 404 | Assignment nije nađen u current scope-u. |
| `RBAC_ROLE_INVALID_TRANSITION` | 409 | Lifecycle prelaz nije dozvoljen. |
| `RBAC_ROLE_STALE_VERSION` | 409 | `expected_version` nije aktuelan. |
| `RBAC_MEMBERSHIP_REQUIRED` | 422 | Target nema odgovarajući M06 membership. |
| `RBAC_TARGET_ACCOUNT_INACTIVE` | 403 | Account nije ACTIVE. |
| `RBAC_ROLE_ASSIGNMENT_NOT_ALLOWED` | 403 | Actor/role pair nije dozvoljen. |
| `RBAC_ROLE_VALIDITY_INVALID` | 422 | Nevalidan vremenski opseg. |
| `RBAC_LAST_OWNER_PROTECTED` | 409 | Ostavio bi školu bez OWNER-a. |
| `RBAC_PRIMARY_OWNER_TRANSFER_REQUIRED` | 409 | Target je M04 primary owner. |
| `RBAC_LAST_SECURITY_ADMIN_PROTECTED` | 409 | Ostavio bi platformu bez aktivnog security admina. |
| `RBAC_GUARDIAN_RELATION_REQUIRED` | 422 | GUARDIAN tok nema M07 vezu/dokaz. |
| `RBAC_PERMISSION_GRANT_EXISTS` | 409 | Isti aktivni grant već postoji. |
| `RBAC_PERMISSION_NOT_DELEGABLE` | 403 | Permission nije direct-delegable. |
| `RBAC_PERMISSION_SCOPE_INVALID` | 422 | Scope kind/ref ne odgovara definiciji. |
| `RBAC_PERMISSION_TARGET_ROLE_INCOMPATIBLE` | 422 | Target role nije dozvoljen. |
| `RBAC_PERMISSION_ACTOR_LACKS_PERMISSION` | 403 | Actor pokušava preneti pravo koje nema. |
| `RBAC_PERMISSION_DELEGATION_DEPTH_FORBIDDEN` | 403 | Grant iz delegiranog prava pokušava dalje delegiranje. |
| `RBAC_PERMISSION_INVALID_TRANSITION` | 409 | Grant lifecycle nije dozvoljen. |
| `RBAC_PERMISSION_STALE_VERSION` | 409 | Stale grant version. |
| `RBAC_ROLE_LABEL_INVALID` | 422 | Role/locale/label nije dozvoljen ili zbunjuje security ulogu. |
| `RBAC_IDEMPOTENCY_KEY_REUSED` | 409 | Isti ključ, drugi canonical payload. |
| `RBAC_CONCURRENT_CHANGE` | 409 | Security/version stanje promenjeno pre commit-a. |
| `RBAC_LIMIT_EXCEEDED` | 422 | Role/grant/support scope prelazi zatvoren limit. |
| `RBAC_CURSOR_INVALID` | 422 | Cursor je sintaksno nevalidan, istekao ili ne odgovara istom query obliku unutar poznatog tenanta; cursor drugog tenanta koristi `RBAC_NOT_FOUND_SAFE`. |
| `SUPPORT_TICKET_REQUIRED` | 422 | Ticket/incident ref nedostaje/nevalidan. |
| `SUPPORT_TICKET_VERIFICATION_UNAVAILABLE` | 503 | Autoritativni ticket verifier nije dostupan ili konfigurisan. |
| `SUPPORT_PURPOSE_INVALID` | 422 | Purpose code/note ne prolazi. |
| `SUPPORT_DURATION_INVALID` | 422 | Van 15–120 min ili proširenje zahteva. |
| `SUPPORT_SCOPE_INVALID` | 422 | Unknown capability, wildcard ili nevažeća capability/resource kombinacija unutar poznatog tenanta; cross-tenant ref koristi `RBAC_NOT_FOUND_SAFE`. |
| `SUPPORT_REQUEST_NOT_PENDING` | 409 | Odluka/cancel nad terminalnim zahtevom. |
| `SUPPORT_TICKET_INVALID_OR_NOT_ASSIGNED` | 422 | Ticket nije aktivan, ne pripada requester-u ili ne odgovara školi; odgovor ne otkriva ticket sadržaj. |
| `SUPPORT_APPROVER_NOT_ALLOWED` | 403 | Nije aktivni ovlašćeni OWNER. |
| `SUPPORT_SELF_APPROVAL_FORBIDDEN` | 403 | Request/support account = approver. |
| `SUPPORT_REQUEST_EXPIRED` | 410 | Prošao request deadline. |
| `SUPPORT_DECISION_REASON_INVALID` | 422 | Reject/cancel/revoke/end reason nije dozvoljen ili mu nedostaje obavezna beleška. |
| `SUPPORT_GRANT_NOT_ACTIVE` | 403 | Grant nije efektivno ACTIVE. |
| `SUPPORT_GRANT_EXPIRED` | 410 | Prošao grant expiry. |
| `SUPPORT_SESSION_CONFLICT` | 409 | Već postoji active session. |
| `SUPPORT_ACTION_OUT_OF_SCOPE` | 403 | Capability/resource/command van granta. |
| `SUPPORT_IMPERSONATION_FORBIDDEN` | 403 | Pokušaj view/login-as. |
| `SUPPORT_EXPORT_FORBIDDEN` | 403 | Export/bulk/download nije dozvoljen. |
| `SUPPORT_MUTATION_NOT_APPROVED` | 403 | Mutation nema exact controlled-repair scope. |
| `SUPPORT_AUDIT_UNAVAILABLE` | 503 | Durable activity audit se ne može upisati. |
| `BREAK_GLASS_REASON_INVALID` | 422 | Reason nije dozvoljen. |
| `BREAK_GLASS_INCIDENT_REQUIRED` | 422 | Nema aktivnog incidenta/ref-a. |
| `BREAK_GLASS_INCIDENT_VERIFICATION_UNAVAILABLE` | 503 | Incident verifier ne može fail-closed potvrditi aktivan incident. |
| `BREAK_GLASS_SCOPE_FORBIDDEN` | 403 | Scope/action nije break-glass allowed. |
| `BREAK_GLASS_RATIFIER_DISTINCT_REQUIRED` | 409 | Isti aktivator i ratifikator. |
| `BREAK_GLASS_RATIFICATION_EXPIRED` | 410 | Ratification posle 10 min. |
| `BREAK_GLASS_NOTIFICATION_DELAY_INVALID` | 422 | Odlaganje bez razloga ili >60 min. |
| `BREAK_GLASS_REVIEW_REQUIRED` | 409 | Obavezni review nije završen; ne blokira bezbednosni revoke, ali blokira zatvaranje incidenta. |
| `OFFLINE_OPERATION_NOT_ALLOWED` | 409 | Permission nije QUEUE_ALLOWED. |
| `OFFLINE_LEASE_EXPIRED` | 410 | Lease deadline prošao. |
| `OFFLINE_LEASE_REVOKED` | 403 | Lease/access opozvan. |
| `OFFLINE_LEASE_SCOPE_MISMATCH` | 403 | Device/tenant/resource/purpose ne odgovara. |
| `OFFLINE_SYNC_AUTHORIZATION_CHANGED` | 409 | Current authorization/subject više ne dozvoljava sync. |

## 7. API ugovori, idempotency i concurrency

### 7.1. Zajednički command envelope

Svaka mutacija prima stabilan `request_id UUID` u command envelope-u, `correlation_id UUID`, `expected_version` za menjani agregat, canonical payload, M01 credential van body-ja i M03 context gde je SCHOOL scope. REST adapter zahteva HTTP `Idempotency-Key` sa UUID vrednošću jednakom `request_id`; drugi transport mora preneti isti semantički ključ tačno jednom. Server čuva `(actor/account-or-service, command_name, request_id, canonical_payload_hash, result_ref, safe_result, committed_at)` u M00 receipt-u.

- identičan retry vraća prvi committed rezultat sa `replay=true` i bez novog side effect-a;
- isti ključ + drugi hash vraća `RBAC_IDEMPOTENCY_KEY_REUSED`;
- dva različita ključa koja ciljaju isti otvoren prirodni ključ: jedan uspeva, drugi dobija semantički 409; ne vraća se tuđi/skriveni objekat kao uspeh;
- redovi agregata se zaključavaju ili CAS ažuriraju; partial unique constraint je poslednja zaštita;
- transaction obuhvata business zapis, receipt, audit, outbox i access-version invalidaciju;
- mrežni timeout posle commit-a rešava se retry-em istog ključa;
- HIGH/CRITICAL komanda ponovo proverava account/tenant/policy/role/grant versions neposredno pre commit-a.

### 7.2. RBAC komande

| ID | Komanda | Permission/actor | Ključni input | Atomski rezultat |
|---|---|---|---|---|
| `RBAC-01` | `AssignSchoolRole` | `school.rbac.roles.assign` ili M02/M04 internal port | target membership, role, validity, source, expected membership version | Novi SCHEDULED/ACTIVE assignment + invalidation. |
| `RBAC-02` | `SuspendSchoolRole` | `school.rbac.roles.suspend` | assignment, expected version, reason | SUSPENDED + child grants neefektivni. |
| `RBAC-03` | `ReactivateSchoolRole` | isto | assignment, expected version, reason | ACTIVE ako svi guardovi i rok važe. |
| `RBAC-04` | `RevokeSchoolRole` | `school.rbac.roles.revoke` ili domain internal | assignment, expected version, reason | REVOKED + svi open grants REVOKED. |
| `RBAC-05` | `GrantDirectPermission` | `school.rbac.permissions.delegate` | assignment, permission, scope, validity, reason | Jedan ACTIVE grant. |
| `RBAC-06` | `RevokeDirectPermission` | `school.rbac.permissions.revoke` | grant, expected version, reason | REVOKED. |
| `RBAC-07` | `PublishAuthorizationPolicyRevision` | `platform.authorization.catalog.publish` | draft revision/version/hash, ticket, reason | Novi ACTIVE; stari SUPERSEDED; retired grant cleanup. |
| `RBAC-08` | `AssignPlatformRole` | `platform.roles.manage` + step-up ≤5m | drugi account, role, validity, ticket, reason, expected account security version | Platform assignment; self-assign je zabranjen. |
| `RBAC-09` | `RevokePlatformRole` | `platform.roles.manage` | assignment/version/reason/ticket | Revoke uz last-security-admin guard. |
| `RBAC-10` | `IssueOfflineAuthorizationLease` | Internal za authenticated client + QUEUE_ALLOWED permission | device, resource, purpose, requested end/max ops | Minimalni ACTIVE lease. |
| `RBAC-11` | `RevokeOfflineAuthorizationLease` | User logout/security/domain internal | lease/version/reason | REVOKED. |
| `RBAC-12` | `SetSchoolRoleLabel` | `school.rbac.labels.manage` | INSTRUCTOR role, locale, singular/plural, `expected_version=0` za create ili tačna verzija active reda, request | ACTIVE override; samo UI projection invalidation. |
| `RBAC-13` | `RetireSchoolRoleLabel` | `school.rbac.labels.manage` | label ID, expected version, request | RETIRED; UI koristi default. |

RBAC-08 ne uvodi procesnu komisiju: jedan postojeći PLATFORM_SECURITY_ADMIN sa svežim step-up dokazom, reason-om i ticket-om može dodeliti rolu drugom aktivnom account-u. Ne može je dodeliti sebi. Poslednji security admin je zaštićen, a svaki grant/revoke odmah auditovan i alertovan.

### 7.3. Support komande

| ID | Komanda | Autoritet | Ključni input | Atomski rezultat |
|---|---|---|---|---|
| `SUP-01` | `RequestSupportAccess` | `platform.support.requests.create`; requester mora biti named support account i ticket assignee | school, purpose/ticket, scope, 15–120 min | PENDING request + school notice; nema access-a. |
| `SUP-02` | `ApproveSupportAccess` | active OWNER, step-up ≤5m | request/version, narrowed scope/duration | Request APPROVED + grant ACTIVE/SCHEDULED + audit/outbox. |
| `SUP-03` | `RejectSupportAccess` | active OWNER, step-up | request/version, reason | REJECTED. |
| `SUP-04` | `CancelSupportAccessRequest` | original requester | request/version, reason | CANCELLED. |
| `SUP-05` | `StartSupportSession` | named account; STANDARD traži active PLATFORM_SUPPORT_AGENT, BREAK_GLASS active PLATFORM_INCIDENT_COMMANDER | grant/version | ACTIVE session + school notice/banner context. |
| `SUP-06` | `EndSupportSession` | session actor/platform security | session/version, reason | ENDED + notice. |
| `SUP-07` | `RevokeSupportAccess` | school owner ili platform security incident | grant/version, reason | Grant/session revoke + immediate invalidation. |
| `SUP-08` | `ActivateBreakGlass` | incident commander + step-up | incident, school, scope, ≤30m, justification, notification state | Grant + pending ratification + notice. |
| `SUP-09` | `RatifyBreakGlass` | distinct platform security admin + step-up | grant/ratification version | RATIFIED ili 410. |
| `SUP-10` | `CompleteBreakGlassReview` | platform security reviewer | review/version, findings, follow-up ticket | COMPLETED + school-visible summary. |
| `SUP-I01` | `RecordSupportActivityAttempt` | Internal middleware only | session/action/resource/correlation | Durable ATTEMPTED red pre resource read-a; failure blokira radnju. |
| `SUP-I02` | `RecordSupportActivityOutcome` | Internal middleware ili ista DB transakcija repair komande | attempt/result/status/reason | Sledeći hash-linked terminalni red; controlled mutation commit nije dozvoljen bez njega. |

### 7.4. Query ugovori

| ID | Query | Guard | Minimalni rezultat |
|---|---|---|---|
| `RBAC-Q01` | `GetMyEffectiveAccess` | M01 + M03 + M06 | policy revision, role refs, UI capability booleans; permission projekcija je hint, ne authorization token. |
| `RBAC-Q02` | `ListSchoolRoleAssignments` | `school.rbac.assignments.view` | Tenant lista; identity minimum, status/validity/source; page 20/max100. |
| `RBAC-Q03` | `GetAuthorizationCatalog` | platform security; school admin samo public school subset | Key/resource/action/risk/delegability; bez skrivenih platform bindings school actoru. |
| `RBAC-Q04` | `ExplainAuthorizationDecision` | same actor/resource ili platform security | Safe reason bucket (`NO_ROLE`, `NO_PERMISSION`, `SUBJECT_SCOPE`, `TENANT_CONTEXT`, `STALE_AUTH`); ne otkriva tuđi resource. |
| `SUP-Q01` | `ListSupportRequests` | owner/requester prema scope-u | Svoji tenant zahtevi; ticket ref, purpose, status, maskiran agent, vreme. |
| `SUP-Q02` | `ListSupportGrants` | `school.support.activity.view` ili named support actor | Scope/status/remaining time; bez child payload-a. |
| `SUP-Q03` | `ListSupportActivity` | `school.support.activity.view`/platform security | Hash-verifikovan tenant log; action/resource type, pseudoref, result, time. |
| `SUP-Q04` | `GetSupportSessionContext` | active named support session | school branding minimum, grant scope, ticket, expiry, mandatory banner; nikad regular user identity. |

Svi query-ji tenant-filteriraju pre count/sort/page. Default sort je `created_at desc, id`; cursor je potpisan, tenant/query-bound i ističe. Cache key uključuje tenant, actor, policy revision, authorization version, tenant access version i subject version gde postoji.

### 7.5. Audit i outbox događaji

Obavezni audit događaji: `authorization_policy_published`, `school_role_assigned`, `school_role_suspended`, `school_role_reactivated`, `school_role_revoked`, `permission_granted`, `permission_revoked`, `platform_role_assigned`, `platform_role_revoked`, `offline_lease_issued`, `offline_lease_revoked`, `support_access_requested`, `support_access_approved`, `support_access_rejected`, `support_access_cancelled`, `support_session_started`, `support_session_ended`, `support_access_revoked`, `support_access_expired`, `break_glass_activated`, `break_glass_ratified`, `break_glass_ratification_missed`, `break_glass_review_completed`.

Outbox događaj nosi samo opaque IDs, versions, reason code i correlation/ticket ref; bez reason note-a i PII. Notification-consumer ugovor koristi tačne tipove `RoleAssignmentChangedV1` i `SupportAccessChangedV1`; ostali M05 audit event nazivi nisu njihovi runtime aliasi. Consumer deduplikuje po event ID-u. Duplicate delivery ne pravi novu notifikaciju ili promenu.

### 7.6. Transport-neutralni response ugovor

Create komanda prvi put vraća HTTP 201, transition/update HTTP 200, query HTTP 200. Uspešna mutacija ima zatvoren oblik `{data:{id,status,version}, replay:boolean, committed_at:Instant, correlation_id:UUID}`; komande koje stvaraju request+grant vraćaju oba ID/status/version objekta u `data`. Identical idempotent replay vraća HTTP 200 i `replay=true`. Nijedna mutacija nije 202/„primljeno“ ako njen poslovni commit nije završen. Error oblik je `{error:{code,message_key,retryable},correlation_id}` bez stack trace-a, policy sadržaja ili tuđih identifikatora. Transport može biti REST/RPC/GraphQL adapter, ali command ID, input obaveznost, status code i atomarnost se ne menjaju.

### 7.7. Brownfield migracioni ugovor

Migracija je idempotentna i radi u kontrolisanom maintenance/deploy koraku, bez perioda sa dva authorization autoriteta:

1. Kreirati nove M05 tabele/constraints i jednu DRAFT policy reviziju; validirati hash i sve postojeće stabilne permission ključeve.
2. Legacy `TRAINER` mapirati u `INSTRUCTOR`, `SUBSTITUTE_TRAINER` u `SUBSTITUTE_INSTRUCTOR`; kada neutralni open red već postoji, zadržati ranije `valid_from`, najnoviju version istoriju i jedan open red, a duplikat označiti migraciono REVOKED sa source cross-ref-om. Ponovljen run je no-op.
3. Existing school OWNER/MANAGER/LIMITED_ADMIN/GUARDIAN role mapirati samo ako SchoolMembership, School i Person veza prolaze tenant-safe dokaz. Ambiguous/orphan red ostaje istorijski neefektivan i ulazi u exception report; ne bira se target nasumično.
4. Legacy monolitni `SOKOLA_ADMIN` ne ostaje aktivan. Svaki njegov active account dobija `PLATFORM_OPERATIONS_ADMIN` i `PLATFORM_SECURITY_ADMIN` radi očuvanja dokumentovanih lifecycle/security obaveza, bez school business pristupa. `PLATFORM_BILLING_ADMIN`, `PLATFORM_SUPPORT_AGENT` i `PLATFORM_INCIDENT_COMMANDER` se ne dodaju bez postojeće eksplicitne permission/ticket evidencije; takav dokaz daje samo odgovarajuću pojedinačnu rolu.
5. Existing PermissionGrant se mapira samo kada permission key postoji u policy reviziji, school/scope FK je dokaziv i grantor nije širio pravo. Ambiguous/unknown/orphan grant postaje neefektivan `REVOKED` sa `MIGRATION` razlogom i exception redom; nikad allow.
6. Existing SupportAccessGrant bez named support account-a, ticket verification-a, school owner approval-a, exact scope-a, masking-a i validnog neisteklog roka ne može postati ACTIVE M05 grant. Čuva se kao istorijski `REVOKED`/`EXPIRED` import i zahteva novi SUP-01/SUP-02 tok za budući pristup.
7. Objaviti policy reviziju i u istoj deployment tački prebaciti sve authorization read-ove na M05; stari role/permission kolone postaju read-only istorija, zatim se uklanjaju tek kada reference scan potvrdi nula potrošača. Nema dual-write perioda kao trajnog rešenja.
8. Povećati authorization/tenant versions za pogođene account-e, ugasiti stare support/context/realtime projekcije i obrisati permission cache. Migracija ne loguje PII.
9. Generisati machine-readable exception report sa opaque legacy ID-em, reason code-om i predloženom bezbednom akcijom; dok je red unresolved, pristup je deny. Drugo pokretanje ne pravi nove assignment-e, grantove, audit ili exception duplikate.

## 8. Acceptance kriterijumi, QA i seed

M05 je prihvatljiv samo ako svih 180 determinističkih scenarija iz `02-M05-QA-I-TRACEABILITY.md` prolaze na server/API nivou. Minimalne obavezne garancije:

1. nepoznat permission/policy outage fail-closed;
2. nijedan cross-tenant test ne vraća podatak, count, sugestiju ili dokaz postojanja;
3. workspace promena ne menja permission uniju;
4. svaki role/grant/support lifecycle odbija nedozvoljen prelaz;
5. owner/manager ne mogu dodeliti sebi ili drugom više nego što pravila dozvoljavaju;
6. last OWNER, primary owner i last security admin zaštite rade pod konkurentnim zahtevima;
7. revoke commit blokira svaki kasnije započet zahtev i prekida realtime/support session;
8. standardni support zahteva školskog owner-a, ticket/purpose/scope/time, masking i potpun activity audit;
9. break-glass traži realan incident, drugu ratifikaciju ≤10 min, max 30 min, notice i review ≤24h;
10. finansijski, auth, owner/RBAC, consent, export i audit delete ostaju zabranjeni support-u;
11. idempotent replay ne duplira resource, audit, outbox ili notice;
12. offline lease nikad ne pretvara capture u finalnu serversku autorizaciju i lokalni child podaci su minimalni/purgeable;
13. log/metrics/traces prolaze automated PII deny-list proveru;
14. legacy TRAINER migracija daje samo neutralni INSTRUCTOR model bez paralelnih role ključeva;
15. source scanning nalazi jedan aktivan permission/role/support source of truth, bez `SUPER_ADMIN`, trajne `SOKOLA_SUPPORT` uloge ili owner wildcard-a.

Seed skup `M05-SEED-01` mora imati najmanje:

- škole A i B u različitim Organization-ima i školu C u istoj Organization kao A;
- po dva OWNER-a u A (jedan PRIMARY_OWNER), jednog OWNER-a u B/C;
- account X: OWNER A + GUARDIAN B; account Y: MANAGER A + INSTRUCTOR A; LIMITED_ADMIN A; INSTRUCTOR A; SUBSTITUTE_INSTRUCTOR sa jednim terminom; GUARDIAN sa dvoje dece od kojih je veza ka jednom opozvana;
- active/suspended/ended membership-e, active/scheduled/suspended/expired/revoked roles i grantove;
- dva platform security admina, operations admina, support agenta i incident commandera;
- pending/approved/expired/revoked support zahteve/grantove, jedan ratifikovan i jedan propušten break-glass;
- dve device instalacije i active/expired/revoked offline lease;
- opaque, sintetičke podatke; bez stvarne dece, kontakata, tiketa ili finansijskih podataka.

## 9. Definition of Done

M05 je spreman za implementacionu predaju tek kada: schema constraints/migracija postoje; policy seed hash je reproducibilan; svi command/query/error ugovori postoje; svih 213 QA testova prolazi; negativni tenant/subject/domain testovi se izvršavaju za svaku površinu; audit/outbox/receipt/invalidation su transakcijski; PII observability scan je čist; support masking i forbidden-action testovi prolaze; legacy role migracija je dokazano idempotentna; RESERVED/unknown authorization domen je fail-closed; Organization nije auth scope; M06–M21 i M28 policy binding-i su tačno seed-ovani; aktivni M00–M21/M28 dokumenti nemaju kontradikciju ili paralelan source of truth. To je specifikacioni DoD; `IMPLEMENTED` zahteva repo/migration/test dokaz.
