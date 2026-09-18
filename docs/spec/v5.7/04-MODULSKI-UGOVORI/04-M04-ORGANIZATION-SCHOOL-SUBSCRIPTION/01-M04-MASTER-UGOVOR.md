---
tip: modulni-implementacioni-ugovor
modul-id: M04
naziv: Organization, School i Subscription foundation
status: SPEC_CANDIDATE
datum: 2026-09-16
revizija: 1.4
schema-zavisnosti: []
odlozeni-schema-constraints: [M02, M05, M06]
read-portovi: []
application-read-composition: [M06, M09]
application-orchestration: [M01, M02, M03, M05, M06, M20, M21]
blokira: [M05, M08, M20, M21, M28]
izlazni-portovi-za: [M05, M08, M09, M10, M11, M12, M18, M19, M20, M21, M28]
---

# M04 — Organization, School i Subscription foundation

## 0. Autoritet i normativni rezultat

Ovaj dokument je kanonski poslovni i implementacioni ugovor za `Organization`, `School`, njihovu vremenski praćenu vezu, primarnog vlasnika škole, product entitlement i mesečni subscription usage snapshot. Aktivni M00 i uključeni DCR-ovi određuju zajednički kanon; ovaj dokument poseduje navedeni domen.

Zaključani rezultat je:

- `Organization` je globalni pravno-komercijalni nosilac SaaS odnosa; nije tenant, login, uloga niti dozvola;
- `School` je jedini H0 operativni bezbednosni tenant i zaseban usage/entitlement scope; nije nužno zaseban platiša niti zaseban račun, pa jedna Organization može dobiti konsolidovani komercijalni obračun bez ikakvog cross-school pristupa;
- jedna škola u svakom trenutku pripada tačno jednoj aktivnoj `Organization`, uz neizbrisivu istoriju promene;
- škola nastaje isključivo kontrolisanom platformskom komandom u statusu `IN_PREPARATION`; nema javnog self-service otvaranja;
- škola može imati više M05 `OWNER` dodela, ali tačno jednog aktivnog `PRIMARY_OWNER`; primarnost je M04 pravna/komercijalna oznaka, a ne nova uloga;
- prvi owner dobija pristup isključivo kroz M02 `INITIAL_OWNER` poziv; M04 ne kreira nalog, identity, membership ili role mimo tog atomskog toka;
- `SchoolProductEntitlement` određuje da li je proizvod/capability komercijalno dostupan školi; nikad ne zamenjuje M03 tenant, M05 permission ili M07 subject guard;
- mesečni `SubscriptionBillingSnapshot` broji jedinstvene aktivno upisane polaznike po školi na preciznom lokalnom preseku i zauvek ostaje immutable;
- korekcija je append-only apsolutna vrednost, isključivo platformska radnja;
- M04 nikad ne knjiži roditeljske obaveze/uplate, ne pravi fakturu i ne naplaćuje SOKOLA pretplatu.

Fizički stack, framework, ORM, API stil, struktura paketa i strategija baze ostaju tehnička odluka repoa samo ako su sve sledeće garancije dokazive.

## 1. CILJ I GRANICE

### 1.1. Šta M04 radi

M04 poseduje:

1. globalni `Organization` master i njegov lifecycle;
2. tenant master `School`, njegove osnovne poslovne podatke i lifecycle;
3. istorijsku vezu `OrganizationSchool` bez promene `School.id`;
4. javne/navigacione `SchoolLocator` vrednosti koje nisu security credential;
5. nepromenljiv redosled promena statusa škole;
6. `SchoolOwnerNomination` za M02 owner poziv i `SchoolPrimaryOwnerTerm` za tačno jednog primarnog vlasnika;
7. product entitlement po školi, sa aktivnim `CORE_MVP` i podrazumevano odsutnim `MYSOKOLA_BASIC`/`OPERATIONS` capability-jima;
8. deterministični mesečni usage snapshot i append-only korekciju;
9. komande, query-je, audit/outbox događaje, greške, idempotency, concurrency i QA ugovor za navedene podatke.

### 1.2. Non-Goals — šta eksplicitno nije posao M04

M04 ne radi sledeće:

- ne autentifikuje korisnika, ne čuva OIDC subject, email kao login ključ, sesiju ili lozinku — M01;
- ne vodi invitation token, delivery ili acceptance state — M02;
- ne bira aktivnu školu/workspace i ne sprovodi opšti tenant resolver — M03;
- ne definiše role, permission, delegabilnost ili Support Access — M05;
- ne kreira/merge-uje `Person`, `SchoolMembership` ili `SchoolPersonProfile` — M06;
- ne vodi guardian/child prava — M07;
- ne kreira ogranak, program, lokaciju, prostor ili „podrazumevanu lokaciju” — M08;
- ne kreira grupu niti `GroupEnrollment`; neutralni subscription-usage application coordinator čita M09/M06 istoriju kroz imenovane read portove i M04 upisuje samo agregat; M04 domen ne poziva M09/M06 reentrantno;
- ne vodi šest onboarding celina, readiness za prvi termin ili import — M20;
- ne vodi roditeljske članarine, `Obligation`, `PaymentRecord`, alokacije, refund ili IPS QR — M12;
- ne definiše cenovnik, poreski tretman, fakturu, kartično/bankarsko terećenje, opomenu, automatsku suspenziju zbog duga, računovodstvo ili fiskalizaciju;
- ne daje Organization administratoru implicitni pregled podataka svih škola;
- ne uvodi javnu registraciju škole, besplatni trial ili school-code registraciju;
- ne briše, merge-uje ili reciklira `Organization.id`/`School.id`;
- ne uvodi hale, marketplace, booking ili izdavanje prostora; to ostaje `DESIGNED_FUTURE_REFERENCE / NOT_PART_OF_CURRENT_IMPLEMENTATION`;
- ne dodaje novu glavnu UI oblast „Podešavanja” niti novu MVP površinu. Postojeći A01–A03/O01–O07 tokovi samo koriste ovaj ugovor.

Automatska naplata SOKOLA pretplate ostaje future. Njen izostanak ne odlaže implementaciju Organization/School, entitlement, snapshot i correction osnove.

## 2. ENTITETI I POLJA

### 2.0. Logički tipovi

Tipovi `Identifier`, `UInt64`, `InstantUTC`, `Code64`, `DisplayString120`, `Nullable<T>` i `Boolean` koriste M03 značenje. Dodatni tipovi:

| Tip | Tačno značenje |
|---|---|
| `LocalMonth` | ISO datum prvog dana meseca, `YYYY-MM-01`; druge vrednosti su nevalidne. |
| `IanaTimeZone` | Aktivni IANA zone ID; Windows naziv, offset poput `+01:00` i lokalizovani label nisu dozvoljene skladišne vrednosti. |
| `CurrencyCode` | ISO 4217 kod. U aktuelnom MVP-u jedina dozvoljena vrednost je `RSD`. |
| `LanguageTag` | BCP 47 tag; default i obavezni MVP fallback je `sr-Latn-RS`. |
| `CountryCode` | ISO 3166-1 alpha-2 uppercase; aktuelni MVP dozvoljava `RS`. |
| `NonNegativeInt` | Ceo broj `0..2_147_483_647`. |
| `ReasonCode` | `Code64` iz zatvorenog registra; slobodan tekst ga ne zamenjuje. |
| `EncryptedContact` | AEAD ciphertext sa key version i autentifikovanim context-om; plaintext ne ulazi u log/audit/telemetry. |
| `Fingerprint256` | Keyed HMAC-SHA-256; nije običan hash i ne koristi se kao identity ključ. |
| `NormalizedSlug` | ASCII lowercase `a-z0-9-`, 3–63 znaka; počinje/završava alfanumerikom, nema uzastopne crtice. |
| `SchoolCode` | Tačno 8 uppercase Base32 znakova bez `0/O/1/I/L`; globalno unique; locator, ne tajna/dozvola. |
| `PayloadHash` | SHA-256 nad verzionisanim kanonskim payload-om; uključuje sve poslovno relevantne inpute. |

Sva vremena nastaju server-side. Intervali su poluotvoreni `[valid_from, valid_to)`. `valid_to=null` znači trenutno važeće.

**Komercijalni tipovi:**

| Tip | Tačno značenje |
|---|---|
| `MoneyAmount` | Exact decimal vrednost. Baza koristi `NUMERIC(18,2)` ili strogo ekvivalentan decimalni tip; API/import/export/event koristi kanonski decimalni string. Nikad binary float niti integer minor-unit. |
| `BasisPoints` | Integer `0..10000`; 100 = 1%. |
| `ContentHash` | Lowercase SHA-256, 64 hex znaka nad verzionisanim kanonskim dokumentom/payload-om. |
| `ProductKey` | `SCHOOL_OS`, `EVENTS`, `VENUE`, `SPONSORS`, `COMMERCE`. |
| `CommercialScopeKind` | `ORGANIZATION`, `SCHOOL`, `EVENT_ORGANIZER_WORKSPACE`, `VENUE_OPERATOR_WORKSPACE`, `EVENT`, `VENUE`, `TRANSACTION`. `ORGANIZATION` je ugovorno/bundle polje, nikad authorization domain. |
| `BillingPeriod` | `MONTHLY`, `ANNUAL`, `PER_EVENT`, `PER_BOOKING`, `PER_TRANSACTION`, `NONE`. |
| `ChargeKind` | `FIXED_RECURRING`, `FIXED_ONE_TIME`, `TIERED_USAGE`, `PER_UNIT_USAGE`, `PERCENTAGE`, `PERCENTAGE_WITH_CAP`, `FIXED_DISCOUNT`, `PERCENTAGE_DISCOUNT`, `FREE_PERIOD`, `ZERO_RATED_INCLUDED`. |
| `ThresholdBehavior` | `BLOCK`, `REQUIRE_ACCEPTANCE`, `CONTRACTED_OVERAGE`; nikad null. |
| `TierMode` | `VOLUME`, `GRADUATED`; popunjen samo za `TIERED_USAGE`. |
| `ProrationPolicy` | `NONE`, `DAILY_ACTUAL_DAYS`, `NEXT_FULL_PERIOD`; plan mora eksplicitno izabrati za recurring rule. |
| `RoundingMode` | Tačno `ROUND_HALF_UP` na scale valute; H0 `RSD` koristi dve decimale. Svaki međurezultat ostaje exact decimal, bez binary float-a. |

Početni `CommercialMetricKey` registry je: `ACTIVE_PARTICIPANT_COUNT`, `ACTIVE_BOOKABLE_SPACE_COUNT`, `EVENT_REGISTRATION_COUNT`, `EVENT_CAPACITY`, `TOURNAMENT_TEAM_COUNT`, `FESTIVAL_REGISTRATION_COUNT`, `REALIZED_DIRECT_TRANSACTION_AMOUNT`, `REALIZED_MARKETPLACE_TRANSACTION_AMOUNT`, `REALIZED_SPONSORSHIP_AMOUNT`. Novi product/metric/authorization ključ nije slobodan string iz API-ja: mora prvo proći policy/catalog reviziju i owning-module ugovor.

### 2.1. `Organization`

Globalni pravno-komercijalni nosilac jedne ili više škola. Nije tenant-scoped.

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | `Identifier` | NE | PK, immutable, nikad se ne reciklira. |
| `organization_ref` | `Code64` | NE | Platformski provisioning/CRM ref; globalno unique; nije tajna. |
| `legal_name` | string(1..200) | NE | Trimovan prikazni naziv; nije access ključ. |
| `country_code` | `CountryCode` | NE | U MVP-u `RS`. |
| `registration_number` | nullable string(1..32) | DA | Ako postoji, normalizovan uppercase alfanumerički format; unique sa `country_code` među ne-arhiviranim redovima. |
| `status` | enum | NE | `ACTIVE`, `ARCHIVED`. |
| `created_at`, `updated_at` | `InstantUTC` | NE | Server vreme. |
| `created_by_actor_ref`, `updated_by_actor_ref` | `Identifier` | NE | Platform actor/service ref. |
| `version` | `UInt64` | NE | Početno `1`, raste za 1 po mutaciji. |

`legal_name` nije globalno unique: dve stvarne organizacije mogu imati isti naziv. Dedupe se oslanja na `organization_ref`, a kada postoji i na `(country_code, registration_number)`; sistem ne spaja redove po nazivu.

### 2.2. `School`

Jedini operativni tenant.

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | `Identifier` | NE | PK, immutable; M03 tenant ID. |
| `provisioning_reference` | `Code64` | NE | Globalno unique platformska oznaka odobrene škole/pilota. |
| `name` | string(1..160) | NE | Puni poslovni prikazni naziv. |
| `short_name` | nullable string(1..80) | DA | UI naziv; prazan string nije dozvoljen. |
| `school_kind` | enum | NE | `PRIVATE_SCHOOL`, `SPORTS_CLUB_ACADEMY`, `DANCE_SCHOOL_STUDIO`, `MUSIC_SCHOOL`, `ART_DRAMA_SCHOOL`, `EDUCATION_LANGUAGE_CENTER`, `ACTIVITY_WORKSHOP_CENTER`, `OTHER`. |
| `school_kind_other_label` | nullable string(1..80) | DA | Obavezno iff `school_kind=OTHER`; inače `null`. |
| `status` | enum | NE | `IN_PREPARATION`, `ACTIVE`, `DEACTIVATED`. |
| `timezone` | `IanaTimeZone` | NE | Default `Europe/Belgrade`; UI label može biti „Beograd”. |
| `currency` | `CurrencyCode` | NE | Tačno `RSD` u aktuelnom MVP-u. |
| `language_tag` | `LanguageTag` | NE | Default `sr-Latn-RS`. |
| `country_code` | `CountryCode` | NE | Tačno `RS` u aktuelnom MVP-u. |
| `contact_name_ciphertext` | nullable `EncryptedContact` | DA | Poslovni kontakt; nije owner/identity veza. |
| `contact_email_ciphertext` | `EncryptedContact` | NE | Potvrđena poslovna kontakt adresa. |
| `contact_email_fingerprint` | `Fingerprint256` | NE | Dedupe kontakta; nikad account-linking. |
| `contact_email_fingerprint_key_version` | `UInt64` | NE | Verzija odvojenog HMAC ključa; omogućava kontrolisanu rotaciju. |
| `contact_email_masked` | `DisplayString120` | NE | Minimalni admin prikaz. |
| `contact_phone_ciphertext` | nullable `EncryptedContact` | DA | E.164 vrednost kada postoji. |
| `contact_verified_at` | `InstantUTC` | NE | Platform potvrda kontakta pre provisioning-a. |
| `contact_verification_ref` | `Code64` | NE | Interni dokaz/CRM case ref bez raw sadržaja. |
| `logo_object_ref` | nullable `Identifier` | DA | Privatni/tenant-safe object metadata ref; PNG/JPEG, najviše 2 MiB. |
| `activated_at` | nullable `InstantUTC` | DA | Prvi uspešan `SCH-04`; nikad se ne briše pri deaktivaciji. |
| `deactivated_at` | nullable `InstantUTC` | DA | Aktuelni poslednji `SCH-05`; `null` kada nije `DEACTIVATED`. |
| `created_at`, `updated_at` | `InstantUTC` | NE | Server vreme. |
| `version` | `UInt64` | NE | Početno `1`, optimistic concurrency. |

Obavezni `CHECK` ugovori:

- `school_kind=OTHER` iff `school_kind_other_label IS NOT NULL`;
- `status=DEACTIVATED` iff `deactivated_at IS NOT NULL`;
- `activated_at IS NULL` samo dok škola nikada nije bila `ACTIVE`;
- `currency='RSD'` i `country_code='RS'` u trenutnom scope-u;
- `contact_email_*` vrednosti predstavljaju istu kanonizovanu adresu; puna adresa nije query/audit polje.

### 2.3. `OrganizationSchool`

Vremenski praćena pravno-komercijalna veza, ne access grant.

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | `Identifier` | NE | PK, immutable. |
| `organization_id` | `Identifier` | NE | FK → globalni `Organization.id`. |
| `school_id` | `Identifier` | NE | FK → `School.id`; škola se ne menja na redu. |
| `valid_from` | `InstantUTC` | NE | Efektivni početak. |
| `valid_to` | nullable `InstantUTC` | DA | `null` za jedinu aktuelnu vezu; mora biti `> valid_from`. |
| `change_reason_code` | `ReasonCode` | NE | Na prvom redu `INITIAL_PROVISIONING`; na transferu zatvoren razlog. |
| `case_reference` | `Code64` | NE | Platformski ugovorni/pravni dokaz; bez PII payload-a. |
| `created_by_actor_ref` | `Identifier` | NE | Platform actor. |
| `created_at` | `InstantUTC` | NE | Server vreme. |

Ograničenja:

- partial unique `UNIQUE(school_id) WHERE valid_to IS NULL`;
- nema preklapanja intervala za isti `school_id` (exclusion constraint ili ekvivalent pod zaključavanjem škole);
- od nastanka škole do sada mora postojati kontinuirana veza bez rupa; transfer zatvara stari i otvara novi red na istom `effective_at`;
- isti `(organization_id, school_id, valid_from)` je unique;
- red se ne briše; posle zatvaranja se ne menja.

### 2.4. `SchoolLocator`

Locator služi navigaciji/brandingu, ne autentifikaciji ili autorizaciji.

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | `Identifier` | NE | PK. |
| `school_id` | `Identifier` | NE | FK → `School.id`; immutable. |
| `kind` | enum | NE | `SLUG`, `SCHOOL_CODE`. |
| `normalized_value` | `NormalizedSlug` ili `SchoolCode` | NE | Tip zavisi od `kind`; globalno unique po `kind`. |
| `status` | enum | NE | `ACTIVE`, `RETIRED`. |
| `valid_from` | `InstantUTC` | NE | Server vreme aktiviranja locator-a. |
| `retired_at` | nullable `InstantUTC` | DA | Obavezno iff `RETIRED`; mora biti `> valid_from`. |
| `replaced_by_locator_id` | nullable `Identifier` | DA | Ista škola; obavezno kada je rotacija, opciono pri trajnom gašenju. |
| `created_by_actor_ref` | `Identifier` | NE | Platform/ovlašćeni school actor. |
| `version` | `UInt64` | NE | Optimistic concurrency. |

Tačno jedan aktivni `SLUG` i tačno jedan aktivni `SCHOOL_CODE` po školi. Poznavanje koda ne pravi nalog, Person, poziv, membership, role ili tenant context. Javna ruta sa nepoznatim/tuđim locatorom koristi M03 safe-not-found pravilo.

### 2.5. `SchoolStatusTransition`

Append-only autoritet za istorijsko stanje škole; `School.status` je trenutna projekcija poslednje tranzicije.

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | `Identifier` | NE | PK. |
| `school_id` | `Identifier` | NE | Tenant dimenzija/FK. |
| `sequence_no` | `UInt64` | NE | Po školi počinje od `1`, bez rupa u committed istoriji. |
| `from_status` | nullable School status | DA | `null` samo za kreiranje. |
| `to_status` | School status | NE | Mora odgovarati dozvoljenoj tranziciji iz §7. |
| `effective_at` | `InstantUTC` | NE | Server commit vreme; retroaktivni status nije podržan. |
| `reason_code` | `ReasonCode` | NE | `SCHOOL_CREATED`, `INITIAL_ACTIVATION` ili obavezni lifecycle razlog. |
| `actor_ref` | `Identifier` | NE | Stvarni actor; ne „on behalf of” kao zamena. |
| `on_behalf_of_person_id` | nullable `Identifier` | DA | Samo kada platform izvršava prvu aktivaciju na potvrđeni zahtev primary owner-a. |
| `correlation_id` | `Identifier` | NE | Povezuje tenant invalidaciju/audit/outbox. |
| `created_at` | `InstantUTC` | NE | Jednako ili posle `effective_at` u istoj transakciji. |

`UNIQUE(school_id, sequence_no)`. Red se ne update-uje i ne briše.

### 2.6. `SchoolOwnerNomination`

M04 namera koja M02 owner pozivu daje tačan ownership scope. Nije nalog, role ili primary owner term.

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | `Identifier` | NE | PK; koristi se kao M02 `ownership_designation_ref`. |
| `school_id` | `Identifier` | NE | Tenant/FK, immutable. |
| `target_person_id` | `Identifier` | NE | FK → globalni M06 `Person`; mora biti adult/account-eligible. |
| `target_school_person_profile_id` | `Identifier` | NE | Composite FK `(school_id,target_school_person_profile_id,target_person_id)` → M06 `SchoolPersonProfile(school_id,id,person_id)`. |
| `kind` | enum | NE | `INITIAL_PRIMARY_OWNER`, `ADDITIONAL_OWNER`. |
| `status` | enum | NE | `PENDING`, `FULFILLED`, `CANCELLED`. |
| `latest_invitation_id` | nullable `Identifier` | DA | M02 ref; replacement menja ref uz version, ne menja Person/kind. |
| `fulfilled_role_assignment_id` | nullable `Identifier` | DA | M05 OWNER role; obavezno iff `FULFILLED`. |
| `fulfilled_at` | nullable `InstantUTC` | DA | Obavezno iff `FULFILLED`. |
| `cancelled_at`, `cancellation_reason_code` | nullable | DA | Oba obavezna iff `CANCELLED`. |
| `created_by_actor_ref`, `created_at` | `Identifier`, `InstantUTC` | NE | Stvarni actor/vreme. |
| `version` | `UInt64` | NE | Optimistic concurrency. |

Obavezna pravila:

- najviše jedna `PENDING INITIAL_PRIMARY_OWNER` nominacija po školi;
- `INITIAL_PRIMARY_OWNER` se može napraviti samo kada nema aktivnog primary owner term-a;
- `ADDITIONAL_OWNER` ne sme ciljati osobu koja već ima aktivnu OWNER dodelu u toj školi;
- M02 invitation replacement sme promeniti samo `latest_invitation_id`; email i token ostaju u M02;
- odloženi composite FK/equivalent proverava da `latest_invitation_id`, kada postoji, pripada istoj školi, istoj target osobi i nosi ovu nominaciju kao `ownership_designation_ref`;
- `FULFILLED` i `CANCELLED` su terminalni;
- istekao/revoked M02 poziv ne oživljava niti terminalizuje nominaciju: ovlašćeni actor može izdati novi M02 poziv za istu još važeću `PENDING` nominaciju; eksplicitno odustajanje koristi `CANCELLED`.

### 2.7. `SchoolPrimaryOwnerTerm`

Vremenski sled tačno jednog primarnog vlasnika škole. `PRIMARY_OWNER` je designation nad aktivnom M05 `OWNER` dodelom, ne dodatna permission uloga.

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | `Identifier` | NE | PK. |
| `school_id` | `Identifier` | NE | Tenant/FK. |
| `owner_person_id` | `Identifier` | NE | Globalna Person; tenant dokaz kroz M06 membership i M05 role. |
| `owner_role_assignment_id` | `Identifier` | NE | Aktivna M05 `OWNER` dodela iste osobe/škole. |
| `valid_from` | `InstantUTC` | NE | Početak primarnosti. |
| `valid_to` | nullable `InstantUTC` | DA | `null` za aktuelni term. |
| `source_nomination_id` | nullable `Identifier` | DA | Obavezno za prvi term nastao M02 acceptance-om. |
| `reason_code` | `ReasonCode` | NE | `INITIAL_OWNER_ACCEPTED`, `OWNER_TRANSFER`, `PLATFORM_LEGAL_OVERRIDE`. |
| `created_by_actor_ref` | `Identifier` | NE | Actor transfera ili M02 system actor. |
| `case_reference` | nullable `Code64` | DA | Obavezno za platform override. |
| `created_at` | `InstantUTC` | NE | Server vreme. |

Partial unique: `UNIQUE(school_id) WHERE valid_to IS NULL`. Intervali iste škole ne smeju da se preklapaju. Transfer zatvara stari i otvara novi term na istom trenutku, u jednoj transakciji; nema praznine i nema dva primary owner-a.

Odloženi composite FK/equivalent mora dokazati da `owner_role_assignment_id` pripada istoj školi, istom `owner_person_id` i ulozi `OWNER`. Constraint se aktivira posle M05 schema koraka i pre bilo kog Foundation use-case-a.

### 2.8. `SchoolProductEntitlement`

Komercijalna dostupnost capability-ja za jednu školu. Izvorni ugovorni nosilac je aktuelna Organization, a izvršna dostupnost je uvek po School tenant-u.

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | `Identifier` | NE | PK. |
| `school_id` | `Identifier` | NE | Tenant/FK; obračunski i izvršni subjekt. |
| `source_organization_id` | `Identifier` | NE | Mora biti aktuelna Organization škole u `valid_from`. |
| `capability_key` | enum/registry | NE | Početni ključevi: `CORE_MVP`, `MYSOKOLA_BASIC`, `OPERATIONS`. |
| `status` | enum | NE | `ACTIVE`, `REVOKED`, `EXPIRED`. |
| `valid_from` | `InstantUTC` | NE | Ne može biti retroaktivno ranije od command commit-a u MVP-u. |
| `valid_until` | nullable `InstantUTC` | DA | Ako postoji, mora biti `> valid_from`; na `now >= valid_until` grant nije efektivan. |
| `commercial_reference` | `Code64` | NE | Odobreni ugovor/pilot/plan ref; bez iznosa ili PII payload-a. |
| `granted_by_actor_ref`, `granted_at` | `Identifier`, `InstantUTC` | NE | Platform actor/vreme. |
| `revoked_at`, `revocation_reason_code` | nullable | DA | Oba obavezna iff `REVOKED`. |
| `expired_at` | nullable `InstantUTC` | DA | Obavezno iff materijalizovan `EXPIRED`; read-time expiry je autoritet i pre materijalizacije. |
| `version` | `UInt64` | NE | Optimistic concurrency. |

Najviše jedan efektivan grant po `(school_id, capability_key)` u jednom trenutku. `CORE_MVP` ne nastaje automatski iz Organization veze. `MYSOKOLA_BASIC` i `OPERATIONS` su default absent. Entitlement ne daje nikome pristup: evaluacija ostaje `environment → product entitlement → tenant allowlist → capability flag → M05 permission → M03/M07 guard` gde je svaki sloj primenljiv.

### 2.9. `SubscriptionBillingSnapshot`

Immutable mesečni usage zapis po školi.

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | `Identifier` | NE | PK. |
| `school_id` | `Identifier` | NE | FK → School; obračunski subjekt. |
| `billing_month` | `LocalMonth` | NE | Mesec koji se završava na reference trenutku. |
| `billing_reference_at` | `InstantUTC` | NE | Prvi trenutak narednog meseca u tada važećoj School IANA zoni, konvertovan u UTC. |
| `school_timezone_snapshot` | `IanaTimeZone` | NE | Zona korišćena za izračunavanje. |
| `billed_child_count` | `NonNegativeInt` | NE | Distinct polaznici prema §6.9; naziv polja ostaje radi kontinuiteta. |
| `calculation_rule_version` | `Code64` | NE | Za ovu reviziju tačno `ACTIVE_GROUP_ENROLLMENT_DISTINCT_PERSON_V1`. |
| `source_cutoff_at` | `InstantUTC` | NE | Tačno jednako `billing_reference_at`; u račun ulaze događaji strogo pre njega. |
| `computed_at` | `InstantUTC` | NE | Može biti posle preseka. |
| `job_run_id` | `Identifier` | NE | M21 `commercial.subscription_usage_snapshot` execution ref. |
| `created_at` | `InstantUTC` | NE | Server vreme. |

`UNIQUE(school_id, billing_month)`. Nema status, `updated_at`, `version` ili `sequence_no`: snapshot se posle inserta nikad ne menja. Time se ispravlja redundantni stari `SubscriptionBillingSnapshot.sequence_no`; monotoni redni broj pripada samo korekcijama.

### 2.10. `SubscriptionBillingCorrection`

Append-only zamenski konačni broj za jedan snapshot; nikad delta.

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | `Identifier` | NE | PK. |
| `school_id` | `Identifier` | NE | Tenant dimenzija; composite FK sa snapshot-om. |
| `subscription_billing_snapshot_id` | `Identifier` | NE | FK → snapshot iste škole. |
| `sequence_no` | `UInt64` | NE | Po snapshot-u `1,2,3...`, bez duplikata. |
| `corrected_child_count` | `NonNegativeInt` | NE | Apsolutna efektivna vrednost posle ove korekcije. |
| `reason_code` | `ReasonCode` | NE | Zatvoren billing-correction registar. |
| `reason_note` | string(1..500) | NE | Bez imena deteta, emaila ili drugog child PII. |
| `evidence_reference` | `Code64` | NE | Interni case/source ref; ne raw dokument. |
| `created_by_user_account_id` | `Identifier` | NE | Globalni M01 account sa `platform.billing_administration`. |
| `created_at` | `InstantUTC` | NE | Server vreme. |

`UNIQUE(subscription_billing_snapshot_id, sequence_no)` i composite FK `(school_id, subscription_billing_snapshot_id) → SubscriptionBillingSnapshot(school_id,id)` obavezno garantuju da korekcija pripada istom tenant-u i tačno jednom snapshot-u.

Efektivni broj je:

`effective_billed_child_count = corrected_child_count korekcije sa najvećim sequence_no, ili snapshot.billed_child_count ako korekcija nema`.

### 2.11. Relacije i kardinalnosti

| Od | Relacija | Do |
|---|---|---|
| Organization | 1:N istorijski; 1:N aktivno | OrganizationSchool |
| School | 1:N istorijski; tačno 1 aktivno | OrganizationSchool |
| School | 1:N | SchoolLocator; tačno jedan aktivni po kind-u |
| School | 1:N append-only | SchoolStatusTransition |
| School | 1:N istorijski | SchoolOwnerNomination |
| School | 1:N istorijski; najviše 1 aktivno | SchoolPrimaryOwnerTerm |
| School | 1:N | SchoolProductEntitlement |
| School | 1:N, jedan po mesecu | SubscriptionBillingSnapshot |
| SubscriptionBillingSnapshot | 1:N append-only | SubscriptionBillingCorrection |
| School | tačno 1:1 | M03 TenantSecurityState |

### 2.12. `CommercialProductDefinition`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | UUID | NE | PK, immutable. |
| `product_key` | `ProductKey` | NE | Globalno unique, immutable. |
| `owner_module_id` | string(3..8) | NE | Za početni registry: SCHOOL_OS=M04, EVENTS=M30, VENUE=M33, SPONSORS=M31, COMMERCE=M32. |
| `localization_key` | Code64 | NE | Prikaz; nije pricing/auth ključ. |
| `status` | enum | NE | `DRAFT`, `ACTIVE`, `RETIRED`. |
| `created_at`, `activated_at`, `retired_at` | InstantUTC | uslovno | Lifecycle vremena; samo odgovarajuće stanje ima terminalno vreme. |
| `created_by_actor_ref`, `activated_by_actor_ref`, `retired_by_actor_ref` | UUID | uslovno | Platform actor-i. |
| `version` | UInt64 | NE | CAS. |

Retired product ostaje referencabilan iz istorijskog plana/ugovora; ne prima novu plan verziju ili novu agreement stavku.

### 2.13. `CommercialMetricDefinition`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | UUID | NE | PK. |
| `metric_key` | registry key | NE | Globalno unique. |
| `owner_module_id` | string(3..8) | NE | Modul koji proizvodi evidence. |
| `allowed_scope_kinds` | sorted enum[1..7] | NE | Zatvorena lista; empty forbidden. |
| `unit_kind` | enum | NE | `COUNT` ili `MONEY_AMOUNT`. |
| `rule_version` | Code64 | NE | Verzija formule/evidence schema. |
| `evidence_schema_hash` | `ContentHash` | NE | Kanonski ugovor izvora. |
| `status` | enum | NE | `DRAFT`, `ACTIVE`, `RETIRED`. |
| `created_at`, `activated_at`, `retired_at` | InstantUTC | uslovno | Kao product. |
| `version` | UInt64 | NE | CAS. |

`ACTIVE_PARTICIPANT_COUNT` je `COUNT`, owner M04/M09 port, dozvoljen samo za `SCHOOL`, rule version `ACTIVE_GROUP_ENROLLMENT_DISTINCT_PERSON_V1`. Grad, location, instructor i broj događaja nisu deo formule. `MONEY_AMOUNT` evidence je kanonski decimalni string na valuti i scale-u koje određuje objavljena metric schema, uz obavezan ISO 4217 `currency_code`; integer minor-unit i binary float nisu dozvoljeni kao API, persistence ili hash source of truth.

### 2.14. `CommercialPlanVersion`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | UUID | NE | PK. |
| `plan_key` | Code64 | NE | Stabilan porodica-plan ključ. |
| `version_no` | uint32 | NE | Po plan_key raste; unique `(plan_key, version_no)`. |
| `product_definition_id` | UUID | NE | FK na product. |
| `status` | enum | NE | `DRAFT`, `PUBLISHED`, `RETIRED`. |
| `currency_code` | CurrencyCode | NE | Sva monetary pravila ove verzije koriste istu valutu. |
| `effective_from`, `effective_until` | InstantUTC | NE/DA | `effective_until > effective_from`; nema retroaktivnog publish-a. |
| `customer_disclosure_document_version` | Code64 | NE | Verzija prikaza cene/uslova. |
| `customer_disclosure_hash` | ContentHash | NE | Dokaz onoga što kupac vidi/prihvata. |
| `canonical_content_hash` | ContentHash | NE | Plan + rules + tiers, reproducibilan. |
| `created_at`, `created_by_actor_ref` | InstantUTC, UUID | NE | Platform actor. |
| `published_at`, `published_by_actor_ref` | InstantUTC, UUID | uslovno | Oba iff PUBLISHED/RETIRED. |
| `retired_at`, `retired_by_actor_ref` | InstantUTC, UUID | uslovno | Oba iff RETIRED. |
| `version` | UInt64 | NE | CAS dok je DRAFT; posle publish-a se ne menja. |

PUBLISHED/RETIRED red i njegove rules/tiers su immutable. Ispravka ili promena cene je nova `version_no` sa budućim `effective_from`.

### 2.15. `CommercialPlanChargeRule`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | UUID | NE | PK. |
| `plan_version_id` | UUID | NE | FK. |
| `rule_key` | Code64 | NE | Unique u plan verziji. |
| `charge_kind` | `ChargeKind` | NE | Određuje dozvoljena polja. |
| `billing_period` | `BillingPeriod` | NE | Mora odgovarati charge kind-u. |
| `metric_definition_id` | UUID | DA | Obavezno samo za `PER_UNIT_USAGE`, `TIERED_USAGE`, `PERCENTAGE` i `PERCENTAGE_WITH_CAP`; null za fixed/free/zero-rated i discount rule. |
| `discount_target_rule_id` | UUID | DA | Obavezno iff je `FIXED_DISCOUNT` ili `PERCENTAGE_DISCOUNT`; FK na pozitivan non-discount charge rule iste plan verzije. |
| `commercial_scope_kind` | `CommercialScopeKind` | NE | Mora biti u metric allowed scopes. |
| `amount` | `MoneyAmount >= 0` | DA | Obavezno samo za fixed/per-unit/fixed-discount gde je primenljivo. |
| `percentage_bps` | `BasisPoints` | DA | Obavezno za percentage/percentage-discount. |
| `cap_amount` | `MoneyAmount >= 0` | DA | Obavezno za `PERCENTAGE_WITH_CAP`; inače null. |
| `included_quantity` | int64 >=0 | DA | Obavezno za `ZERO_RATED_INCLUDED` ili kada usage plan ima included allowance. |
| `threshold_quantity` | int64 >=0 | DA | Null znači bez praga; ako postoji, threshold_behavior određuje ishod. |
| `threshold_behavior` | `ThresholdBehavior` | NE | Obavezno čak i bez praga; bez praga koristi `CONTRACTED_OVERAGE` samo ako formula pokriva svu usage. |
| `tier_mode` | `TierMode` | DA | Obavezno iff TIERED_USAGE. |
| `proration_policy` | `ProrationPolicy` | DA | Obavezno za FIXED_RECURRING; inače null. |
| `free_period_units` | uint16 >0 | DA | Obavezno iff FREE_PERIOD. |
| `free_period_unit` | enum `DAY\|BILLING_PERIOD` | DA | Obavezno iff FREE_PERIOD. |
| `rounding_mode` | `RoundingMode` | DA | Obavezno za percentage i tier/per-unit formule; inače null. |
| `exclusivity_group_key` | Code64 | NE | Sprečava dve SOKOLA naknade za isti chargeable event/transaction. |
| `priority` | int16 | NE | Niži broj pobeđuje unutar grupe; duplicate priority u plan verziji/grupi nije dozvoljen. |
| `tax_category_key` | Code64 | NE | Klasifikacija, ne stopa; M32/poreska konfiguracija obračunava. |
| `status` | enum | NE | `ACTIVE`, `RETIRED`; u DRAFT planu se menja, posle publish-a immutable. |

Tačna field matrica: FIXED (`amount` da; metric/percentage/cap/tier/discount-target null) · PER_UNIT (metric+`amount` da; discount-target null) · TIERED (metric+tier_mode da; amount/percentage/cap/discount-target null; najmanje jedan tier) · PERCENTAGE (metric+percentage da; cap/discount-target null) · PERCENTAGE_WITH_CAP (metric+percentage+`cap_amount` da; discount-target null) · FIXED_DISCOUNT (`amount`+discount-target da; metric/percentage/cap/tier null) · PERCENTAGE_DISCOUNT (percentage+discount-target da; metric/amount/cap/tier null) · FREE_PERIOD (free_period_units+unit da; metric i sva monetary/discount polja null) · ZERO_RATED_INCLUDED (included_quantity da; metric i sva monetary/discount polja null).

Discount target mora biti druga `ACTIVE` rule iste `plan_version_id`, mora predstavljati pozitivan charge i ne sme biti `FIXED_DISCOUNT`, `PERCENTAGE_DISCOUNT`, `FREE_PERIOD` ili `ZERO_RATED_INCLUDED`. Self-target, lanac popusta i ciklus nisu dozvoljeni. `FIXED_DISCOUNT` daje `min(amount, target_charge_amount)`. `PERCENTAGE_DISCOUNT` daje `target_charge_amount × percentage_bps / 10000`, zatim `ROUND_HALF_UP` na scale valute. Ukupan popust nad jednom target stavkom ne može preći njen pozitivan iznos; rezultat nikad nije negativan. M32 sme samo primeniti ovu objavljenu formulu i dokazani target — ne sme birati target po redosledu, nazivu ili sličnosti.

### 2.16. `CommercialPlanChargeTier`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `charge_rule_id` | UUID | NE | Rule mora biti TIERED_USAGE. |
| `ordinal` | uint16 | NE | Počinje 1 bez rupa; unique po rule. |
| `lower_bound_inclusive` | int64 >=0 | NE | Prvi 0; sledeći jednak prethodnom upper. |
| `upper_bound_exclusive` | int64 > lower | DA | Null samo za poslednji open-ended tier. |
| `flat_amount` | `MoneyAmount >= 0` | DA | Tačno jedno od flat/per-unit polja je popunjeno. |
| `per_unit_amount` | `MoneyAmount >= 0` | DA | Tačno jedno od flat/per-unit polja je popunjeno. |

Tier intervali ne smeju imati rupu/preklapanje. VOLUME bira jedan tier za celu količinu; GRADUATED primenjuje svaki tier samo na svoj segment. Formula je deo canonical hash-a.

### 2.17. `CommercialAgreement`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | UUID | NE | PK. |
| `agreement_ref` | Code64 | NE | Globalno unique ugovorni ref. |
| `payer_organization_id` | UUID | NE | FK Organization; platiša/primalac računa. |
| `status` | enum | NE | `DRAFT`, `PENDING_ACCEPTANCE`, `ACCEPTED`, `ACTIVE`, `SUSPENDED`, `CANCELLED`, `TERMINATED`, `EXPIRED`. |
| `currency_code` | CurrencyCode | NE | Svi item planovi iste valute u jednoj verziji ugovora. |
| `starts_at`, `ends_at` | InstantUTC | NE/DA | `ends_at > starts_at`; retroactive activation forbidden. |
| `billing_cycle_anchor_local_day` | uint8 1..28 | DA | Obavezno za monthly stavke; null kada ih nema. |
| `renewal_policy` | enum | NE | `NO_AUTO_RENEW`, `AUTO_RENEW_SAME_TERMS`, `REQUIRES_NEW_ACCEPTANCE`. |
| `notice_period_days` | uint16 | NE | Eksplicitna vrednost ugovora; nema skrivenog defaulta. |
| `terms_document_version` | Code64 | NE | Verzija komercijalnih uslova. |
| `terms_document_hash` | ContentHash | NE | Dokaz prihvaćenih uslova. |
| `acceptance_mode` | enum | DA | Trenutno samo `PLATFORM_RECORDED_EXTERNAL_CONTRACT`; budući self-service zahteva novi ugovor. |
| `acceptance_evidence_ref` | Code64 | DA | Opaque dokaz; obavezno od statusa ACCEPTED nadalje. |
| `accepted_at` | InstantUTC | DA | Obavezno za ACCEPTED/ACTIVE/SUSPENDED/TERMINATED/EXPIRED. |
| `accepted_organization_name_snapshot` | string(1..200) | DA | Obavezno uz acceptance; nije auth dokaz. |
| `recorded_by_platform_actor_ref` | UUID | DA | Platform billing actor koji je proverio dokaz. |
| `suspended_at`, `suspend_reason_code` | InstantUTC, ReasonCode | DA | Oba iff SUSPENDED. |
| `terminated_at`, `termination_reason_code` | InstantUTC, ReasonCode | DA | Oba iff TERMINATED. |
| `created_at`, `created_by_actor_ref` | InstantUTC, UUID | NE | Audit. |
| `version` | UInt64 | NE | CAS. |

Agreement acceptance ne daje platform/school permission. Izmena plan-a, cene, scope-a, payer Organization ili materijalnih uslova posle acceptance-a zahteva novu agreement verziju/novi agreement i novo acceptance evidence; stari se ne prepisuje.

### 2.18. `CommercialAgreementItem`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `agreement_id`, `plan_version_id` | UUID | NE | Plan mora biti PUBLISHED i currency ista kao agreement. |
| `item_key` | Code64 | NE | Unique po agreement. |
| `product_definition_id` | UUID | NE | Mora odgovarati plan-u. |
| `commercial_scope_kind` | CommercialScopeKind | NE | Dozvoljen za product/rules. |
| `commercial_scope_ref` | UUID | NE | Validira ga owner-module resolver. Za SCHOOL mora postojati aktivna OrganizationSchool veza ka payer Organization pri aktivaciji. |
| `status` | enum | NE | `PENDING`, `ACTIVE`, `SUSPENDED`, `ENDED`. |
| `starts_at`, `ends_at` | InstantUTC | NE/DA | U granicama agreement-a. |
| `entitlement_capability_keys` | sorted Code64[] | NE | Može biti empty; svaki ključ poznat registry-ju. |
| `created_at`, `created_by_actor_ref` | InstantUTC, UUID | NE | Audit. |
| `activated_at`, `suspended_at`, `ended_at` | InstantUTC | uslovno | Lifecycle. |
| `version` | UInt64 | NE | CAS. |

Unique open item `(agreement_id, product_definition_id, commercial_scope_kind, commercial_scope_ref, item_key)`. Isti scope može imati više proizvoda, ali charge rules sa istom `exclusivity_group_key` ne smeju dvaput oceniti isti chargeable ref.

### 2.19. `CommercialAgreementAdjustment`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id`, `agreement_item_id` | UUID | NE | PK/FK. |
| `adjustment_key` | Code64 | NE | Unique po item-u. |
| `adjustment_kind` | enum | NE | `FIXED_DISCOUNT`, `PERCENTAGE_DISCOUNT`, `FREE_PERIOD`, `NEGOTIATED_RULE_OVERRIDE`. |
| `target_charge_rule_id` | UUID | DA | Obavezno za override/rule-specific discount; isti plan item. |
| `amount` | `MoneyAmount >= 0` | DA | Popunjeno ako i samo ako je adjustment fixed. |
| `percentage_bps` | BasisPoints | DA | Iff percentage. |
| `override_payload_hash` | ContentHash | DA | Obavezno iff negotiated override; konkretan payload je verzionisan ugovorni dodatak. |
| `stacking_group_key` | Code64 | NE | Popusti iste grupe koriste policy ispod. |
| `stacking_policy` | enum | NE | `EXCLUSIVE` ili `ORDERED`. |
| `application_order` | int16 | NE | Unique po item/group za ORDERED; kod EXCLUSIVE niži broj je jedini pobednik. |
| `status` | enum | NE | `SCHEDULED`, `ACTIVE`, `REVOKED`, `EXPIRED`. |
| `valid_from`, `valid_until` | InstantUTC | NE/DA | U agreement/item periodu. |
| `reason_code`, `approval_evidence_ref` | ReasonCode, Code64 | NE | Bez slobodnog/skrivenog popusta. |
| `created_at`, `created_by_actor_ref` | InstantUTC, UUID | NE | Platform actor. |
| `revoked_at`, `revoked_by_actor_ref`, `revoke_reason_code` | uslovno | DA | Sva iff REVOKED. |
| `version` | UInt64 | NE | CAS. |

Aktivan adjustment se ne update-uje; ispravka je revoke + novi red. Ne može povećati charge iznad objavljenog pravila bez novog prihvaćenog agreement evidence-a. `override_payload_hash` sam nije izvršna formula: `NEGOTIATED_RULE_OVERRIDE` sme proizvesti cenu samo kada isti prihvaćeni ugovorni dodatak razrešava verzionisani, schema-valid payload čiji kanonski hash tačno odgovara polju i čiji evaluator postoji u objavljenoj plan/policy verziji. Nedostupan, nepoznat, schema-nevalidan ili hash-mismatch payload daje fail-closed `COMMERCIAL_PLAN_CONTENT_INVALID`; sistem ne nagađa cenu, popust ili entitlement. U `EXCLUSIVE` grupi primenjuje se samo aktivni adjustment sa najnižim `application_order`; drugi su konflikt pri aktivaciji ako imaju isti prioritet. U `ORDERED` grupi M32 primenjuje ascending order na rezultat prethodnog koraka i rezultat nikad ne spušta ispod nule. Percentage rezultat je `ROUND_HALF_UP(base_amount * percentage_bps / 10000, currency_scale)` nad exact-decimal vrednostima; H0 `currency_scale=2`.

### 2.20. `CommercialAgreementStatusTransition`

Append-only istorija: `id UUID`, `agreement_id UUID`, `sequence_no UInt64`, `from_status nullable agreement status`, `to_status agreement status`, `effective_at InstantUTC`, `reason_code ReasonCode`, `actor_ref UUID`, `correlation_id UUID`, `created_at InstantUTC`. Unique `(agreement_id, sequence_no)`; sequence počinje 1 i nema committed rupa. `from_status=null` samo za DRAFT create. Svaka status komanda menja `CommercialAgreement.status`, upisuje sledeći transition, CommandReceipt, audit i outbox u istoj transakciji. Transition se ne update-uje ili briše.

### 2.21. Komercijalne relacije i kardinalnosti

| Od | Relacija | Do |
|---|---|---|
| CommercialProductDefinition | 1:N | CommercialMetricDefinition (preko owner_module_id porta, ne FK) |
| CommercialProductDefinition | 1:N | CommercialPlanVersion |
| CommercialPlanVersion | 1:N | CommercialPlanChargeRule |
| CommercialPlanChargeRule | 1:N (samo TIERED_USAGE) | CommercialPlanChargeTier |
| Organization | 1:N | CommercialAgreement (kao payer) |
| CommercialAgreement | 1:N | CommercialAgreementItem |
| CommercialAgreement | 1:N append-only | CommercialAgreementStatusTransition |
| CommercialAgreementItem | 1:N | CommercialAgreementAdjustment |
| CommercialAgreementItem | N:1 | CommercialPlanVersion (mora biti PUBLISHED) |
| CommercialAgreementItem | 0:1 (kada SCHOOL scope) | SchoolProductEntitlement.commercial_agreement_item_id |

Veza postojećih M04 entiteta sa komercijalnim modelom:

- **`Organization`** — Organization je payer/contracting customer. Ne postoji implicitna permission ili globalni Organization workspace. Registration/contact podaci su ugovorni atributi i ne daju access.
- **`SchoolProductEntitlement`** — `school_id` ostaje izvršni tenant, ne platiša; `commercial_agreement_item_id UUID nullable` je obavezan kada je komercijalni režim za proizvod uključen. Item mora biti ACTIVE, scope SCHOOL, za istu školu, pod aktivnim agreement-om i mora sadržati capability key. Pilot/legacy entitlement sme privremeno imati null samo uz `commercial_reference` i `source_kind=PILOT_OR_LEGACY`; migracija ne sme izmisliti agreement ili cenu. Suspension/termination agreement-a u istoj transakciji ili kroz autoritativni read-time composite guard čini capability neefektivnim; outbox nije authorization autoritet.
- **`SubscriptionBillingSnapshot`** — `school_id` je usage scope, ne obračunski/platiša subjekt; `metric_key` je kanonska konstanta `ACTIVE_PARTICIPANT_COUNT`. `SubscriptionBillingSnapshot.billed_child_count` (§2.9) i commercial `ACTIVE_PARTICIPANT_COUNT` metrika (§2.13, §4.6) jesu isti broj: distinct aktivno upisane `Person` po School/mesecu prema `ACTIVE_GROUP_ENROLLMENT_DISTINCT_PERSON_V1`. Commercial resolver čita postojeći snapshot i ne pokreće drugu brojačku logiku. Snapshot je immutable i ne sadrži child/person listu; M32 referencira snapshot ID kao evidence, ne kopira roster. Jedna Person se broji jednom po School/month čak i sa više grupa/lokacija/programa; ista Person u dve škole broji se jednom u svakoj school usage stavci. Konsolidacija invoice-a ne menja count.

## 3. POSLOVNA PRAVILA I INVARIJANTE

### 3.1. Organization i tenant

1. Organization može imati više škola, ali ne daje cross-school pristup, listu dece, agregat finansija ili pretragu osoba.
2. Korisnik vidi školu samo ako M03/M05/M06 dokazuju njegovo pravo baš u toj školi; Organization veza se ne koristi kao dokaz.
3. School mora od kreiranja imati jednu aktuelnu Organization vezu. Organization mora biti `ACTIVE`.
4. Organization se arhivira samo ako nema aktuelnu School vezu i nema efektivan entitlement koji je ona izdala.
5. Promena Organization ne menja `School.id`, tenant podatke, URL identitet istorijskih objekata, primary owner ili subscription snapshote.
6. Transfer Organization je platformska, step-up, reason+case radnja. U istoj transakciji zatvara staru vezu, otvara novu i zamenjuje aktivne entitlement-e punim eksplicitno odobrenim setom za novu Organization; nema implicitnog kopiranja neodobrenih capability-ja.

### 3.2. Kreiranje škole

1. Samo actor sa `platform.schools.create` i svežom M01 step-up potvrdom kreira školu.
2. `SCH-01` zahteva postojeću aktivnu Organization, postojeći M06 adult/account-eligible `initial_owner_person_id`, potvrđen poslovni kontakt, jedinstven `provisioning_reference`, pun profil i request ID.
3. Jedan application use-case i jedna lokalna transakcija kreiraju School `IN_PREPARATION`, početni OrganizationSchool, status transition #1, dva locator-a, M03 TenantSecurityState kroz `TEN-05`, minimalni M06 `SchoolPersonProfile` za initial owner-a, `INITIAL_PRIMARY_OWNER` nominaciju koja referencira taj profil, audit, outbox i receipt.
4. M04 domen ne upisuje M06 tabelu direktno: application orchestrator poziva vlasnički M06 port. `SCH-01` ne kreira lokaciju, UserAccount, AuthIdentity, membership, role ili invitation. M20 orkestrira UI; M02 poziv je posebna komanda.
5. Isti request/payload vraća isti rezultat. Drugi request sa istim `provisioning_reference` vraća konflikt, ne postojeći School kao „uspeh”.
6. Naziv nije identity/dedupe ključ i može se ponoviti kod različitih pravnih škola.

### 3.3. School profil i zaštićene vrednosti

1. `name`, `short_name`, school kind, kontakt i logo menjaju se uz `expected_version`, permission i audit.
2. School actor nikad ne može promeniti `provisioning_reference`, Organization vezu, status, currency ili country običnim profile patch-em; mass assignment je odbijen.
3. `timezone` može menjati primary owner ili platform actor uz step-up, reason i `expected_version` samo dok ne postoji nijedan time-bearing ili billing relevantan zapis: TermOccurrence, RecurringScheduleRule, AttendanceSession, Event, Obligation/Payment, GroupEnrollment status istorija ili SubscriptionBillingSnapshot.
4. Kada takav zapis postoji, aktuelna implementacija odbija promenu sa `SCHOOL_TIMEZONE_CHANGE_REQUIRES_MIGRATION`; M04 ne pomera stare termine niti reinterpretira istoriju.
5. Currency ostaje `RSD`, country `RS`; druga vrednost vraća `SCHOOL_LOCALE_NOT_SUPPORTED`. Nema tihog konvertovanja novca.
6. Language tag se može menjati bez promene istorijskih podataka; invalid/unsupported tag je validation greška.
7. Logo mora biti PNG/JPEG, najviše 2 MiB i proći file safety proveru; object ref druge škole je safe-not-found.

### 3.4. Prvi, dodatni i primarni owner

1. Škola u pripremi sme privremeno imati nula aktivnih OWNER dodela samo dok ima jednu `PENDING INITIAL_PRIMARY_OWNER` nominaciju. Time se precizira stara preširoka rečenica „škola uvek ima vlasnika”.
2. M02 `INITIAL_OWNER` acceptance atomarno kreira/reuse-uje M06 membership, M05 OWNER role, označava nominaciju `FULFILLED` i kreira prvi active `SchoolPrimaryOwnerTerm`.
3. Posle prvog owner acceptance-a, škola ne sme ostati bez najmanje jedne aktivne OWNER role i jednog active primary term-a.
4. `ADDITIONAL_OWNER` acceptance dodaje OWNER role i fulfils nominaciju, ali ne menja primary owner-a.
5. Poslednja aktivna OWNER role ne može se revoke/suspend/end. Role na koju pokazuje active primary term ne može se ukloniti pre atomskog transfera primarnosti.
6. Redovni transfer primarnosti pokreće aktuelni primary owner, uz step-up, obavezan razlog i target koji već ima aktivan M06 membership, aktivnu M05 OWNER role i aktivan account.
7. Platform override je dozvoljen samo actoru sa `platform.school_ownership.override`, uz step-up, reason `PLATFORM_LEGAL_OVERRIDE` i obavezan `case_reference`; audit pokazuje stvarnog platform actor-a. Nema skrivene impersonation sesije.
8. Transfer ne menja role set; samo zatvara stari i otvara novi primary term. Stari owner ostaje OWNER dok ga posebna M05 komanda ne promeni.
9. Primalac mora biti različit od aktuelnog primary owner-a; self-transfer je idempotentni no-op samo ako isti request replay-uje prethodno uspešan rezultat, inače `PRIMARY_OWNER_ALREADY_CURRENT`.

### 3.5. Aktivacija škole

`IN_PREPARATION → ACTIVE` je dozvoljeno samo kada neposredno pre commit-a važi:

1. School profil ima validan naziv, contact, `Europe/Belgrade` ili drugi validan IANA zone ID, `RSD`, `sr-Latn-RS` ili podržan tag i `RS`;
2. Organization je `ACTIVE` i postoji tačno jedna aktuelna OrganizationSchool veza;
3. M03 TenantSecurityState postoji;
4. postoji najmanje jedna aktivna M05 OWNER role;
5. postoji tačno jedan active SchoolPrimaryOwnerTerm vezan za aktivnu OWNER role iste osobe/škole;
6. `CORE_MVP` entitlement je efektivan;
7. actor je aktuelni primary owner sa `school.lifecycle.activate` ili platform actor sa `platform.schools.lifecycle.manage` koji navodi `on_behalf_of_person_id` aktuelnog primary owner-a;
8. `expected_version`, step-up i eksplicitna potvrda su važeći.

Aktivacija ne zahteva lokaciju, grupu, člana, cenu, raspored, finansijski profil, import ili završene onboarding celine. To pripada M20 readiness-u. `School.status=ACTIVE` ne znači „sve je spremno za prvi radni dan”.

### 3.6. Deaktivacija i reaktivacija

1. Samo `platform.schools.lifecycle.manage` actor sa step-up potvrdom, `expected_version`, zatvorenim reason code-om i reason note-om može deaktivirati/reaktivirati školu.
2. Deaktivacija u jednoj transakciji menja School status, dodaje status transition, poziva M03 `TEN-04`, opoziva sve M02 pozive u `DRAFT|AWAITING_APPROVAL|ACTIVE` razlogom `SCHOOL_DEACTIVATED`, invalidira acceptance attempt-e, upisuje audit/outbox/receipt.
3. Posle commit-a nijedan novi regularni request, query, download, export, websocket subscribe ili user-scoped job škole ne prolazi. Outbox ubrzava cleanup, ali autoritet su School status i tenant version.
4. Deaktivacija ne briše Organization vezu, owner-a, membership, role, podatke, audit, snapshote ili druge škole korisnika.
5. Entitlement zapisi ostaju istorijski, ali nijedan capability škole nije izvršiv dok je School `DEACTIVATED`.
6. Reaktivacija ponovo proverava aktivnu Organization, active primary owner/OWNER role, TenantSecurityState i efektivan `CORE_MVP` entitlement; poziva `TEN-04` i ne oživljava stare kontekste ili opozvane pozive.
7. Posle reaktivacije korisnik bira/dobija novi validan M03 kontekst. Potreban pristup bez postojeće role dobija se novim M02 pozivom.
8. Deaktivacija zbog komercijalnog razloga nikad nije automatski rezultat snapshot-a, korekcije ili nepostojeće invoice logike.

### 3.7. Locator pravila

1. Slug i School code se generišu/normalizuju server-side i globalno su unique po vrsti.
2. Promena locator-a je rotacija: novi active red i retirement starog su atomski.
3. Stari locator ne preusmerava na zaštićeni sadržaj bez M03 provere. Dozvoljen je samo neutralni redirect ili safe-not-found prema odluci rute.
4. School code može pomoći izboru škole/login discovery-ju, ali nikad ne otvara javnu registraciju niti daje membership/role.
5. Locator se ne koristi u composite FK ili audit identitetu; koristi se stabilni School ID.

### 3.8. Product entitlement

1. Entitlement dodeljuje/opoziva samo platform actor sa `platform.product_entitlements.manage`, step-up, commercial ref, reason i expected version kada menja postojeći red.
2. Efektivan je samo ako `status=ACTIVE`, `valid_from <= now`, `valid_until IS NULL OR now < valid_until`, source Organization je i dalje aktuelna za školu i School nije `DEACTIVATED`.
3. `now == valid_until` znači neefektivan. Read-time guard je autoritet i kada expiry job još nije materijalizovao `EXPIRED`.
4. Novi grant za isti capability atomarno terminalizuje prethodni active grant i kreira novi; istorija se ne update-uje da sakrije stare komercijalne reference.
5. Entitlement promena odmah invalidira entitlement/authorization/navigation cache za školu; zahtev koji počne posle commit-a ne može proći na stale cache-u. Kada svežina nije dokazana, čita se autoritativni store fail-closed.
6. `MYSOKOLA_BASIC` i `OPERATIONS` su odsutni dok nisu eksplicitno grantovani; dodatni tenant allowlist/feature flagovi i permission-i i dalje moraju proći.
7. Entitlement ne kreira role i ne daje Organization actoru pravo u školi.

### 3.9. Subscription usage računica

1. `billing_reference_at` za `billing_month=M` je prvi lokalni trenutak narednog meseca `00:00:00.000` u School IANA zoni, konvertovan u UTC.
2. Koristi se stanje strogo pre preseka: događaj sa `effective_at == billing_reference_at` pripada narednom mesecu.
3. M21 published job `commercial.subscription_usage_snapshot` pokreće neutralni application coordinator, koji pravi snapshot samo za School čija poslednja `SchoolStatusTransition` strogo pre preseka daje `ACTIVE`. Aktivacija tačno na preseku ne pravi snapshot za prethodni mesec; deaktivacija tačno na preseku ne ukida prethodni mesec.
4. Obračunski polaznik je svaki distinct `Person` koji u toj školi ima bar jedan M09 `GroupEnrollment` čija poslednja statusna tranzicija strogo pre preseka glasi `Aktivno`/kanonski `ACTIVE`.
5. Naziv `billed_child_count` ostaje zbog kontinuiteta, ali računica se namerno ne izvodi iz uzrasta ili datuma rođenja: svaki aktivno upisani polaznik se broji, pa punoletstvo ne pravi komercijalnu rupu.
6. `U pripremi`, `Privremeno obustavljeno` i `Završeno` se ne broje. Ako nema statusne tranzicije pre preseka, enrollment se ne broji.
7. Jedna Person se broji najviše jednom po School/mesecu bez obzira na broj grupa. Ista Person u dve različite škole broji se jednom u svakoj.
8. M06 Person merge istorija se razrešava „as of” billing reference: dve Person koje su već bile objedinjene pre preseka broje se jednom; merge posle preseka ne menja već napravljen snapshot.
9. Snapshot sa `0` je validan za aktivnu školu bez aktivnih polaznika.
10. Kasni JOB koristi istoriju statusa, ne trenutne live kolone. Ako izvorna istorija nije potpuna, ne upisuje izmišljeni broj; job failuje i ide u retry/dead-letter sa `SUBSCRIPTION_SOURCE_HISTORY_INCOMPLETE`.
11. Naknadna backdated ispravka M09/M06 istorije ne menja snapshot. Platform billing actor pravi korekciju sa dokazom.
12. Snapshot/correction nikad ne stvara M12 `Obligation`, `PaymentRecord`, refund, fakturu, poreski zapis ili automatsku naplatu.

### 3.10. Granični slučajevi — deterministični ishodi

1. Dva paralelna `SCH-01` sa istim request ID/payload-om: jedan School; oba dobijaju isti receipt.
2. Isti provisioning ref sa drugim request ID-em: drugi dobija `SCHOOL_PROVISIONING_REFERENCE_EXISTS`; nema delimičnih podataka.
3. TenantSecurityState insert uspe, a owner nomination insert padne: cela SCH-01 transakcija se rollback-uje.
4. Prvi owner invite istekne: School ostaje `IN_PREPARATION`, nominacija ostaje `PENDING`; novi poziv može referencirati istu nominaciju.
5. Dva acceptance-a za prvog owner-a: M02/M04 locks dozvoljavaju jedan primary term; drugi je replay/already accepted, bez duplog owner-a.
6. Owner acceptance i School activation trče paralelno: activation koja ne vidi committed owner term dobija guard failure; retry posle acceptance-a može uspeti.
7. Dva primary-owner transfera sa istom expected version: tačno jedan uspeva; drugi `PRIMARY_OWNER_TRANSFER_CONFLICT`.
8. Target primary transfera izgubi OWNER role neposredno pre commit-a: transfer se rollback-uje.
9. Poslednja OWNER role se pokušava ukloniti u M05: M04 guard odbija, čak i ako frontend prikazuje dugme.
10. Organization transfer i School deaktivacija su paralelni: zaključavanje School reda daje serijski rezultat; oba audit traga koriste stvarne finalne verzije, bez dve aktivne Organization veze.
11. Organization se pokušava arhivirati sa aktivnom školom: `ORGANIZATION_HAS_ACTIVE_SCHOOLS`.
12. Timezone promena nakon prvog TermOccurrence-a, čak i obrisanog/otkazanog: blokirana; istorija se ne reinterpretira.
13. Slug rotacija i dva paralelna zahteva: jedan active slug; gubitnik stale/conflict.
14. School code iz škole A koristi korisnik škole B: ne daje pristup niti potvrđuje postojanje zaštićenih podataka.
15. Entitlement istekne dok je korisnik na otvorenom ekranu: prvi sledeći query/command posle roka fail-closed; nema čekanja cache TTL-a.
16. Entitlement revoke i visokorizična mutacija se ukrste: mutacija ponovo proverava entitlement neposredno pre commit-a i ne commit-uje posle revoke-a.
17. `CORE_MVP` istekne: School status ostaje `ACTIVE`, ali Core poslovne funkcije vraćaju entitlement grešku; auth/account security i dozvoljeni platform recovery ostaju dostupni.
18. School se deaktivira tokom M02 callback-a: M02 finalni guard odbija acceptance; nema account/access parcijalnog commita.
19. School se reaktivira pre originalnog invitation expiry-ja: stari poziv je ipak `REVOKED` i ne oživljava.
20. Enrollment pređe u ACTIVE tačno na reference trenutku: ne broji se za završeni mesec.
21. Enrollment pređe iz ACTIVE u SUSPENDED tačno na reference trenutku: broji se za završeni mesec.
22. Jedna Person ima tri active enrollment-a: count +1, ne +3.
23. `commercial.subscription_usage_snapshot` se pokrene dvaput: drugi vraća postojeći snapshot; ne pravi correction.
24. Isti job za školu deaktiviranu posle preseka, ali pre izvršenja: koristi status as-of presek i ipak pravi snapshot.
25. Isti job ne može dokazati istorijski status: ne upisuje nulu; retry/dead-letter.
26. Dve correction komande paralelno: parent snapshot lock daje sequence 1 i 2; nema duplikata.
27. Identičan correction retry posle timeout-a: isti rezultat/sequence; nema novog reda.
28. Isti idempotency key sa drugim corrected count-om: `M04_IDEMPOTENCY_KEY_REUSED`.
29. School admin sa svim school permissions pokuša correction: 403; samo platform billing permission.
30. Correction reason note sadrži prepoznati email/datum rođenja ili drugi child PII: validation odbija i ništa ne upisuje.

### 3.11. Komercijalne invarijante

1. Cena postoji samo u PUBLISHED plan verziji ili prihvaćenom adjustment-u; nijedna cena nije konstanta koda.
2. Published plan/rule/tier je immutable; korekcija je nova buduća plan verzija.
3. ACTIVE agreement zahteva acceptance evidence i najmanje jedan validan item.
4. Item ne može biti ACTIVE ako plan nije PUBLISHED/effective, product nije ACTIVE, scope resolver nije active ili scope ne pripada payer Organization.
5. OrganizationSchool veza nikad nije access grant.
6. Grad/location/space/instructor/event se ne naplaćuje ako prihvaćeni plan nema takvu metriku.
7. Event-only i venue-only scope ne kreira School.
8. Hibrid je jedan agreement sa više item-a; identity ostaje globalan, access domeni odvojeni.
9. `threshold_behavior` je obavezan. Samo `CONTRACTED_OVERAGE` sa prihvaćenom formulom može napraviti dodatni charge; `REQUIRE_ACCEPTANCE` blokira do nove saglasnosti.
10. Za jedan `chargeable_ref + exclusivity_group_key` može postojati najviše jedna SOKOLA charge assessment stavka. Provider fee je zasebna kategorija i mora biti prikazan odvojeno.
11. Price change nije retroaktivan: zatvoren usage period i nastala assessment stavka ostaju vezani za originalni plan version.
12. Usage source outage/corruption je 503/retry/attention; nikad guessed zero.
13. Charge, invoice i settlement ne nastaju u M04 transakciji.
14. Komercijalni entiteti/log/audit/outbox/telemetry ne sadrže podatke deteta.
15. Entitlement, permission, tenant/subject guard i feature flag ostaju četiri odvojena sloja.
16. Migracija postojećih škola/entitlement-a ne kreira cenu, plan, agreement acceptance ili dug bez dokaza.
17. Discount rule je vezan za tačno jedan pozitivan target rule iste immutable plan verzije. Popust ne targetira drugi popust, ne formira ciklus, ne prelazi target iznos i ne proizvodi negativan charge.

## 4. TENANT & SECURITY GUARD

### 4.1. Obavezni guard lanac

Za school-scoped command/query redosled je:

1. validna M01 session/step-up gde je zahtevano;
2. M03 `TenantExecutionContext` ili eksplicitni platformski operation context;
3. `School.status` i M03 `tenant_access_version`;
4. product entitlement/allowlist/flag gde je funkcija gated;
5. M05 permission i owner/primary-owner guard;
6. M06 membership/Person dokaz gde postoji globalni Person FK;
7. tenant-safe lookup svih school-scoped referenci;
8. expected version/idempotency/concurrency;
9. ponovna provera visokorizičnih guardova neposredno pre commit-a.

Client `school_id`, Organization ID, slug, school code, Person ID ili role ID nikad nisu dovoljni. School repository koristi `WHERE school_id=:active_school AND id=:id` ili dokazivo ekvivalentnu izolaciju. Cross-tenant resurs je spolja isti safe 404 kao nepostojeći.

### 4.2. Globalni podaci

- Organization i platform listu škola čita samo platformski actor sa eksplicitnom dozvolom; to ne otvara tenant poslovne tabele.
- Školski actor može dobiti samo minimalni naziv aktuelne Organization svoje škole ako je proizvodu potreban, ne listu drugih škola te Organization.
- Globalni `Person`/`UserAccount` FK je običan FK, ali svaka owner operacija mora dokazati M06 membership i M05 OWNER role iste škole.
- `created_by_user_account_id` na correction-u ne dobija tenant pristup; platform permission je zaseban dokaz.

### 4.3. Zaštita podataka dece

M04 ne čuva listu Person ID-eva korišćenih u snapshot-u, imena dece, datume rođenja, roditelje, grupe ili enrollment detalje. Čuva samo agregat. `commercial.subscription_usage_snapshot` obradu radi tenant po tenant, u memoriji/projekciji sa minimalnim Person ID-em, i odbacuje radni skup posle izračunavanja. Log, audit, telemetry, dead-letter i correction reason ne sadrže child PII.

School kontakt podaci su encrypted at rest, maskirani u listama, izostavljeni iz telemetry-ja i dostupni samo purpose-limited administrativnom prikazu. Email fingerprint nije account/person linking ključ.

### 4.4. Deaktivacija bez stale prozora

School status promena i M03 `TEN-04` version bump moraju biti u istoj lokalnoj transakciji modularnog monolita. Zahtev koji počne posle commit-a proverava autoritativni status/version i ne prolazi kroz stale cache. Visokorizična mutacija započeta ranije ponavlja status/version guard pred svoj commit. Realtime/cache cleanup preko outbox-a nije authorization autoritet.

### 4.5. Platform actor i podrška

Platform scope nije lažni School tenant. Svaka platform komanda ima stvarni actor, permission, step-up, reason/case gde je propisano, correlation i audit. Ne postoji trajni skriveni SuperAdmin pregled child podataka. Support Access iz M05 ne nasleđuje `platform.schools.*`, `platform.product_entitlements.manage` ili `platform.billing_administration`.

### 4.6. Commercial Tenant & Security Guard

- M04 commercial catalog je platform-managed globalni skup; mutacije zahtevaju `PLATFORM_BILLING_ADMIN`, odgovarajući granularni permission (§8.1.1), step-up ≤5 min, reason/ticket i audit.
- Agreement/query vidljivost platform actor-a ne daje business drill-down u School/Event/Venue podatke.
- `commercial_scope_ref` prolazi owner-module resolver. Nepoznat/neaktivan resolver je fail-closed 503 (`COMMERCIAL_SCOPE_RESOLVER_UNAVAILABLE`); nepoznat ili tuđ scope 422 (`COMMERCIAL_SCOPE_INVALID`/`COMMERCIAL_SCOPE_ORGANIZATION_MISMATCH`) bez curenja.
- Za SCHOOL resolver proverava aktuelni `OrganizationSchool` relation pri aktivaciji. Kasniji Organization transfer zahteva eksplicitno agreement-item rebind/termination plan; ništa se ne prebacuje automatski.
- Konsolidovani usage/račun koristi samo school ID + aggregate count/evidence ref. Nema child IDs ili names.
- Cache key uključuje plan version/agreement/item/version/scope. High-risk activation/publish/acceptance ponavlja version/status guard pred commit.

## 5. LIFECYCLE & TRANSITIONS

### 5.1. `Organization`

| Iz | Komanda | U | Dozvoljeno | Guard/posledica |
|---|---|---|---:|---|
| ne postoji | `ORG-01` | `ACTIVE` | DA | Platform create; audit/outbox. |
| `ACTIVE` | `ORG-02` | `ACTIVE` | DA | Profil/version; bez access posledice. |
| `ACTIVE` | `ORG-03` | `ARCHIVED` | DA | Nema aktivnih School veza/entitlement-a; terminalno. |
| `ARCHIVED` | bilo šta osim query | — | NE | Ne reaktivira se u MVP-u. |

### 5.2. `School`

| Iz | Komanda | U | Dozvoljeno | Obavezna posledica |
|---|---|---|---:|---|
| ne postoji | `SCH-01` | `IN_PREPARATION` | DA | Org link, locators, status #1, TEN-05, nomination, audit/outbox. |
| `IN_PREPARATION` | `SCH-04` | `ACTIVE` | DA | Activation guards, status event, `activated_at`. |
| `ACTIVE` | `SCH-05` | `DEACTIVATED` | DA | Platform only; TEN-04 + M02 bulk revoke + cache/realtime invalidation. |
| `DEACTIVATED` | `SCH-06` | `ACTIVE` | DA | Platform only; ponovni guards + TEN-04; stari contexts/invites ne oživljavaju. |
| `IN_PREPARATION` | `SCH-05` | — | NE | Nedovršena škola se ne „deaktivira”; platform može otkazati nominaciju, ali School ostaje istorijski IN_PREPARATION. |
| `DEACTIVATED` | `IN_PREPARATION` | — | NE | Zabranjen povratak. |
| bilo koje | delete/archive | — | NE | School nema hard-delete/arhivu u MVP-u. |

### 5.3. `SchoolOwnerNomination`

| Iz | Komanda/događaj | U | Posledica |
|---|---|---|---|
| ne postoji | SCH-01/OWN-01 | `PENDING` | Spremna za zaseban M02 owner poziv. |
| `PENDING` | M02 replacement | `PENDING` | Menja samo latest invitation ref/version. |
| `PENDING` | M02 acceptance/OWN-03 | `FULFILLED` | Owner role ref; za initial kreira primary term. |
| `PENDING` | OWN-02 | `CANCELLED` | Reason/audit; M02 open poziv se revoke-uje istoj transakciji. |
| `FULFILLED`/`CANCELLED` | bilo šta | — | Terminalno. |

### 5.4. `SchoolPrimaryOwnerTerm`

| Iz | Komanda | U | Pravilo |
|---|---|---|---|
| ne postoji | first owner acceptance | active term | Tačno jednom za prvi owner. |
| active term A | OWN-04 transfer B | ended A + active B | Isti effective instant, jedna transakcija. |
| active term | delete/end bez successor-a | — | Zabranjeno. |

### 5.5. `SchoolProductEntitlement`

| Iz | Komanda/uslov | U | Posledica |
|---|---|---|---|
| ne postoji | ENT-01 | `ACTIVE` | Grant sa commercial ref. |
| `ACTIVE` | ENT-01 replacement | `REVOKED` + novi `ACTIVE` | Atomski; reason `REPLACED`. |
| `ACTIVE` | ENT-02 | `REVOKED` | Odmah neefektivan; cache invalidation. |
| `ACTIVE` | `now >= valid_until` | efektivno expired / `EXPIRED` | Read-time deny; JOB može materijalizovati. |
| `REVOKED`/`EXPIRED` | bilo šta | — | Terminalno; novi grant je novi red. |

### 5.6. `OrganizationSchool`, locator, snapshot i correction

- OrganizationSchool: prvi active red; transfer atomarno zatvara stari i otvara novi. Zatvoren red je immutable.
- SchoolLocator: `ACTIVE → RETIRED`; rotacija pravi novi active red. Retired se ne reaktivira.
- SchoolStatusTransition, SubscriptionBillingSnapshot i SubscriptionBillingCorrection nemaju mutable lifecycle; append-only/immutable su od inserta.

### 5.7. `CommercialProductDefinition` / `CommercialMetricDefinition`

| From | Komanda | To | Uslov |
|---|---|---|---|
| ne postoji | COM-01/COM-04 create | DRAFT | Unique key. |
| DRAFT | COM-02/COM-05 activate | ACTIVE | Owner module, schema/resolver i reference validni. |
| ACTIVE | COM-03/COM-06 retire | RETIRED | Nove plan/item reference blokirane; istorija ostaje. |
| RETIRED | bilo šta | — | Terminalno. |

### 5.8. `CommercialPlanVersion`

| From | Komanda | To | Uslov |
|---|---|---|---|
| ne postoji | COM-07 create | DRAFT | Unique plan/version. |
| DRAFT | COM-08 replace draft content | DRAFT | CAS; puni canonical payload, nikad partial patch. |
| DRAFT | COM-09 publish | PUBLISHED | Product/metrics active; rules/tiers validni; future effective_from; hash i disclosure postoje. |
| PUBLISHED | COM-10 retire | RETIRED | Ne menja postojeće agreement item-e; blokira nove. |
| PUBLISHED/RETIRED | content mutation | — | 409 `COMMERCIAL_PLAN_IMMUTABLE`. |

### 5.9. `CommercialAgreement`

| From | Komanda | To | Uslov |
|---|---|---|---|
| ne postoji | COM-11 create | DRAFT | Organization ACTIVE. |
| DRAFT | COM-12 submit | PENDING_ACCEPTANCE | ≥1 validan item; terms/disclosure frozen. |
| DRAFT/PENDING_ACCEPTANCE/ACCEPTED | COM-17 cancel | CANCELLED | Nije aktiviran. |
| PENDING_ACCEPTANCE | COM-13 record acceptance | ACCEPTED | Evidence validan; frozen content hash se poklapa. Nema entitlement-a ili charge-a. |
| ACCEPTED | COM-14 activate | ACTIVE | Plan effective; scope resolver prolazi; `starts_at <= now`. Ako je starts_at u budućnosti, ostaje ACCEPTED do determinističkog activation job-a koji poziva isti command contract. |
| ACTIVE | COM-15 suspend | SUSPENDED | Reason; entitlement composite guard odmah deny gde je ugovor uslov. |
| SUSPENDED | COM-16 resume | ACTIVE | Plan/scope/evidence i dalje validni. |
| ACTIVE/SUSPENDED | COM-17 terminate | TERMINATED | Reason/effective time; bez retroaktivnog brisanja charge evidence-a. |
| ACCEPTED/ACTIVE/SUSPENDED | read-time now ≥ ends_at | EXPIRED | Job samo materijalizuje; nikad ne aktivira istekli ugovor. |
| CANCELLED/TERMINATED/EXPIRED | bilo šta | — | Terminalno; novi ugovor za nastavak. |

### 5.10. `CommercialAgreementItem`

| From | Događaj | To |
|---|---|---|
| create u draft agreement-u (COM-18) | add item | PENDING |
| PENDING | parent activation + item guards | ACTIVE |
| ACTIVE | parent/item suspend | SUSPENDED |
| SUSPENDED | resume + guards | ACTIVE |
| PENDING/ACTIVE/SUSPENDED | end/parent terminal | ENDED |
| ENDED | bilo šta | — terminalno |

### 5.11. `CommercialAgreementAdjustment`

| From | Događaj | To |
|---|---|---|
| create (COM-19), valid_from > now | — | SCHEDULED |
| create (COM-19), valid_from ≤ now | — | ACTIVE |
| SCHEDULED | now ≥ valid_from | ACTIVE read-time |
| SCHEDULED/ACTIVE | COM-20 revoke | REVOKED |
| SCHEDULED/ACTIVE | now ≥ valid_until | EXPIRED read-time |
| REVOKED/EXPIRED | bilo šta | — terminalno |

### 5.12. `commercial.effective_transition`

M21 job je PLATFORM coordinator sa izolovanim agreement shard-ovima, a ne PER_SCHOOL job. Jedan `CommercialAgreement` može sadržati item-e za više škola ili buduće non-school scope-ove, pa samo agreement aggregate određuje jedan redosled parent tranzicija. Semantic key je `utc_5m_bucket:agreement_shard:transition_policy_version`; shard funkcija i policy verzija su deo published job definicije.

Za svaki claim worker zaključava jedan `CommercialAgreement` i njegove item/adjustment redove stabilno po UUID-u, koristi CAS/fencing i u jednoj M04 transakciji izvršava najviše jednu sledeću autoritativnu tranziciju:

1. `ACCEPTED→ACTIVE` kada je `starts_at<=database_now<ends_at` ili `ends_at` ne postoji, acceptance/evidence/plan/product/svi scope resolver-i i organization ownership i dalje prolaze; koristi isti poslovni guard kao COM-14, ali system principal iz published M21 job-a ne lažira ljudski step-up;
2. `ACCEPTED|ACTIVE|SUSPENDED→EXPIRED` kada je `ends_at<=database_now`; istek ima prednost nad aktivacijom/resume-om;
3. pripadajući item `PENDING→ACTIVE`, `ACTIVE|SUSPENDED→ENDED` i adjustment `SCHEDULED→ACTIVE`, `SCHEDULED|ACTIVE→EXPIRED` samo kao posledicu efektivnog parent stanja i sopstvenih poluotvorenih granica;
4. povezani school entitlement postaje efektivan ili neefektivan u istoj transakciji gde M04 poseduje red; za drugi owner scope koristi se outbox, ali read-time composite guard odmah failuje i pre consumer-a.

Request/read-time evaluacija `starts_at<=now<ends_at`, item/adjustment intervala, parent statusa i entitlement-a ostaje authorization i pricing autoritet. Kašnjenje, pad ili duplikat job-a ne produžava pristup, ne aktivira istekao ugovor i ne stvara charge. Dva shard worker-a koja vide isti agreement daju jedan CAS commit; identičan retry vraća postojeći receipt. Guard failure ostavlja agreement `ACCEPTED` i emituje PII-free attention kod; ne nagađa scope niti parcijalno aktivira samo jednu školu.

Published job principal ima tačno internu capability `commercial.effective_transition.execute`, vezanu za `job_definition_version`, `job_execution_id`, agreement shard i važeći fencing token. Ona ne nasleđuje ljudsku platform/school ulogu i ne može pozvati COM-01..COM-20 van ove state-machine tranzicije. Svaki commit beleži `actor_kind=SYSTEM`, job execution/definition/fencing dokaz i correlation ID; odsutan ili stale dokaz failuje pre prvog business write-a.

## 6. ERROR CATALOG

| Kod | HTTP | Opis i bezbedni ishod |
|---|---:|---|
| `M04_UNAUTHENTICATED` | 401 | M01 session/step-up nije važeći; nema payload-a. |
| `M04_INPUT_INVALID` | 400 | Nevalidan tip/format/obavezno polje/enum. |
| `M04_FORBIDDEN` | 403 | Actor nema permission ili owner guard; bez detalja tuđeg resursa. |
| `M04_RESOURCE_NOT_FOUND_SAFE` | 404 | Resurs ne postoji u dozvoljenom scope-u ili pripada drugom tenant-u. |
| `M04_STALE_VERSION` | 409 | `expected_version` nije aktuelan; ništa nije promenjeno. |
| `M04_IDEMPOTENCY_KEY_REUSED` | 409 | Isti request ID/key sa drugim kanonskim payload-om. |
| `M04_IDEMPOTENCY_IN_PROGRESS` | 409 | Isti key/payload je još u obradi; odgovor uključuje `Retry-After: 1`. |
| `ORGANIZATION_REFERENCE_EXISTS` | 409 | `organization_ref` već postoji. |
| `ORGANIZATION_REGISTRATION_EXISTS` | 409 | Isti country/registration broj već postoji. |
| `ORGANIZATION_ARCHIVED` | 409 | Arhivirana Organization ne može dobiti novu školu/entitlement. |
| `ORGANIZATION_HAS_ACTIVE_SCHOOLS` | 409 | Archive blokiran aktuelnom School vezom. |
| `ORGANIZATION_HAS_ACTIVE_ENTITLEMENTS` | 409 | Archive blokiran efektivnim grantom. |
| `ORGANIZATION_TRANSFER_INCOMPLETE` | 422 | Nema pune nove Organization/case/entitlement specifikacije. |
| `SCHOOL_PROVISIONING_REFERENCE_EXISTS` | 409 | Drugi School već koristi ref. |
| `SCHOOL_STATUS_TRANSITION_INVALID` | 409 | Iz trenutnog statusa komanda nije dozvoljena. |
| `SCHOOL_ACTIVATION_NOT_READY` | 422 | Jedan ili više §3.5 guardova ne prolazi; ovlašćenom actoru vraća zatvorene reason kodove bez PII. |
| `SCHOOL_PRIMARY_OWNER_REQUIRED` | 422 | Nema tačno jednog validnog primary owner term-a. |
| `SCHOOL_CORE_ENTITLEMENT_REQUIRED` | 422 | Nema efektivnog CORE_MVP grant-a. |
| `SCHOOL_TENANT_SECURITY_STATE_MISSING` | 500 | Integrity failure; fail-closed, correlation alert. |
| `SCHOOL_TIMEZONE_CHANGE_REQUIRES_MIGRATION` | 409 | Postoje istorijski/time-bearing podaci; obična izmena zabranjena. |
| `SCHOOL_LOCALE_NOT_SUPPORTED` | 422 | Currency/country/language nije podržan u aktivnom scope-u. |
| `SCHOOL_CONTACT_NOT_VERIFIED` | 422 | Nedostaje verifikacioni dokaz kontakta. |
| `SCHOOL_LOGO_INVALID` | 422 | Tip, veličina ili safety provera loga ne prolazi. |
| `SCHOOL_LOCATOR_CONFLICT` | 409 | Slug/code je već active za drugu školu. |
| `SCHOOL_DEACTIVATED` | 403 | Regularna school radnja je blokirana; nema podataka. |
| `OWNER_NOMINATION_CONFLICT` | 409 | Već postoji nekompatibilna pending nominacija/owner. |
| `OWNER_TARGET_NOT_ELIGIBLE` | 422 | M06 adult/account/membership eligibility ne prolazi. |
| `OWNER_ROLE_REQUIRED` | 422 | Target transfera nema aktivnu M05 OWNER role. |
| `LAST_OWNER_PROTECTED` | 409 | Radnja bi ostavila školu bez aktivnog owner-a. |
| `PRIMARY_OWNER_TRANSFER_REQUIRED` | 409 | Pokušava se ukloniti aktuelni primary owner bez transfera. |
| `PRIMARY_OWNER_ALREADY_CURRENT` | 409 | Novi target je već primary owner, a nije receipt replay. |
| `PRIMARY_OWNER_TRANSFER_CONFLICT` | 409 | Paralelni transfer/promena role/statusa. |
| `ENTITLEMENT_NOT_EFFECTIVE` | 403 | Capability nije komercijalno dostupan; ne govori ništa o permission-u. |
| `ENTITLEMENT_CONFLICT` | 409 | Postoji active grant koji nije pravilno replacement-ovan. |
| `ENTITLEMENT_SOURCE_ORGANIZATION_INVALID` | 422 | Source Organization nije aktuelna Organization škole. |
| `SUBSCRIPTION_BILLING_MONTH_INVALID` | 400 | Nije prvi dan meseca ili je budući/nepodržan period. |
| `SUBSCRIPTION_SNAPSHOT_ALREADY_EXISTS` | 409 | Drugi business request pokušava duplikat; identičan job retry vraća postojeći kao uspeh. |
| `SUBSCRIPTION_SOURCE_HISTORY_INCOMPLETE` | 503 | Istorijsko stanje nije dokazivo; snapshot nije upisan. |
| `SUBSCRIPTION_SNAPSHOT_NOT_FOUND_SAFE` | 404 | Snapshot ne postoji ili nije u dozvoljenom scope-u. |
| `SUBSCRIPTION_CORRECTION_INVALID` | 422 | Count/reason/evidence/note ne prolazi; bez upisa. |
| `SUBSCRIPTION_CORRECTION_PII_FORBIDDEN` | 422 | Reason note sadrži zabranjeni child/contact PII. |
| `SUBSCRIPTION_AUTHORITY_UNAVAILABLE` | 503 | M09/M06/School history autoritet nije pouzdano dostupan; fail-closed. |
| `M04_INTERNAL_SAFE` | 500 | Neočekivana greška; samo correlation ID izlazi klijentu. |

**Komercijalne greške:**

| Kod | HTTP | Značenje |
|---|---:|---|
| `COMMERCIAL_PRODUCT_UNKNOWN` | 422 | Product key/definition nije poznat. |
| `COMMERCIAL_PRODUCT_NOT_ACTIVE` | 409 | Product nije ACTIVE za novu referencu. |
| `COMMERCIAL_METRIC_UNKNOWN` | 422 | Metric nije registrovan. |
| `COMMERCIAL_METRIC_NOT_ACTIVE` | 409 | Metric nije ACTIVE. |
| `COMMERCIAL_METRIC_SCOPE_INVALID` | 422 | Metric nije dozvoljen za scope. |
| `COMMERCIAL_PLAN_NOT_FOUND` | 404 | Plan verzija nije pronađena. |
| `COMMERCIAL_PLAN_NOT_PUBLISHED` | 409 | Plan nije PUBLISHED/effective. |
| `COMMERCIAL_PLAN_IMMUTABLE` | 409 | Pokušaj izmene published/retired sadržaja. |
| `COMMERCIAL_PLAN_CONTENT_INVALID` | 422 | Rule/tier/field matrica, hash ili disclosure nije validan. |
| `COMMERCIAL_AMOUNT_INVALID` | 422 | Money input nije kanonski decimalni string, van je opsega ili ima nedozvoljenu preciznost. |
| `COMMERCIAL_PRICE_NOT_CONFIGURED` | 409 | Nema objavljenog prihvaćenog pravila; sistem ne pogađa cenu. |
| `COMMERCIAL_CURRENCY_MISMATCH` | 422 | Agreement/item/plan valute se razlikuju. |
| `COMMERCIAL_AGREEMENT_NOT_FOUND` | 404 | Agreement nije pronađen. |
| `COMMERCIAL_AGREEMENT_INVALID_TRANSITION` | 409 | Lifecycle prelaz nije dozvoljen. |
| `COMMERCIAL_AGREEMENT_EVIDENCE_REQUIRED` | 422 | Nedostaje prihvaćen terms/disclosure/evidence. |
| `COMMERCIAL_AGREEMENT_STALE_VERSION` | 409 | Expected version nije aktuelan. |
| `COMMERCIAL_SCOPE_INVALID` | 422 | Scope kind/ref ne postoji ili ne odgovara product-u. |
| `COMMERCIAL_SCOPE_ORGANIZATION_MISMATCH` | 422 | Scope ne pripada payer Organization. |
| `COMMERCIAL_SCOPE_RESOLVER_UNAVAILABLE` | 503 | Owner-module resolver nije dokazivo dostupan/svež. |
| `COMMERCIAL_RETROACTIVE_CHANGE_FORBIDDEN` | 409 | Pokušaj retroaktivne cene/ugovora/adjustment-a. |
| `COMMERCIAL_SILENT_OVERAGE_FORBIDDEN` | 409 | Prag traži block/new acceptance, nema contracted overage-a. |
| `COMMERCIAL_DUPLICATE_PLATFORM_FEE_FORBIDDEN` | 409 | Ista exclusivity grupa već ima SOKOLA stavku. |
| `COMMERCIAL_USAGE_SOURCE_UNAVAILABLE` | 503 | Usage/evidence nije kompletan; nema zero fallback-a. |
| `COMMERCIAL_PII_FORBIDDEN` | 422 | Commercial payload sadrži podatke deteta ili nedozvoljeni PII. |
| `COMMERCIAL_IDEMPOTENCY_KEY_REUSED` | 409 | Isti key sa drugim canonical payload hash-em. |
| `COMMERCIAL_CONCURRENT_CHANGE` | 409 | Plan/agreement/scope se promenio pre commit-a. |

Za javni/tenant locator resurs safe 404 ne razlikuje „ne postoji” od „druga škola”. Platform lifecycle query može vratiti precizne integrity kodove samo actoru sa odgovarajućom platform dozvolom.

## 7. IDEMPOTENCY & CONCURRENCY

### 7.1. Opšti receipt ugovor

Sve M04 mutacije primaju `request_id: Identifier`; eksterne HTTP mutacije mogu ga mapirati na `Idempotency-Key`. Receipt unique scope je `(actor_or_service_scope, command_id, request_id)` i čuva `payload_hash`, status/result ref, correlation i vreme najmanje 30 dana. Isti key+isti hash vraća isti poslovni rezultat bez novih audit/outbox redova. Isti key+drugi hash vraća `M04_IDEMPOTENCY_KEY_REUSED`. Ako je isti key/payload još u obradi, server čeka najviše do command timeout-a, zatim vraća `M04_IDEMPOTENCY_IN_PROGRESS` sa `Retry-After: 1`; ne pokreće drugu obradu.

### 7.2. Zaključavanje i redosled

1. School mutacije zaključavaju `School` red ili koriste compare-and-swap `version`.
2. Organization transfer zaključava redove stabilnim redosledom: Organization ID-evi rastuće, zatim School, aktuelni OrganizationSchool, active entitlement-i, TenantSecurityState.
3. Owner acceptance/transfer zaključava: School → nomination/current primary term → target membership/OWNER role po stabilnom ID redosledu → receipt.
4. School status transition sequence nastaje pod School parent lock-om; nikad `SELECT MAX()` bez zaključanog parenta.
5. Locator rotacija zaključava School i oba relevantna locator reda; DB unique je poslednja zaštita.
6. `commercial.subscription_usage_snapshot` koristi unique `(school_id,billing_month)` i per-school/month advisory/row lock ili ekvivalent. Dupli worker dobija isti snapshot rezultat.
7. Correction zaključava parent snapshot, zatim računa `MAX(sequence_no)+1` u istoj transakciji. Prazna child tabela nije race jer je parent zaključan.
8. Visokorizične komande ponavljaju School status, primary owner/role, entitlement i auth/security verzije neposredno pre commit-a.

### 7.3. Transakcione granice

- SCH-01: School + OrganizationSchool + locators + first status + TEN-05 + nomination + receipt + audit + outbox = jedna lokalna DB transakcija.
- SCH-05/06: School/status history + TEN-04 + M02 bulk revoke/invalidation gde je primenljivo + receipt/audit/outbox = jedna transakcija modularnog monolita. Ako infrastruktura fizički ne može jednu transakciju, operacija je blokirana dok ne postoji dokazivo ekvivalentan fail-closed saga ugovor; nije dozvoljen period otvorenog pristupa.
- OWN-03: M02 acceptance, M06 membership, M05 OWNER role, nomination, prvi primary term i receipt/audit/outbox = jedna transakcija.
- OWN-04: zatvaranje starog i otvaranje novog primary term-a + receipt/audit/outbox = jedna transakcija.
- ORG-04: stari/novi OrganizationSchool + entitlement replacement + receipt/audit/outbox = jedna transakcija.
- `commercial.subscription_usage_snapshot`: jedan snapshot + receipt/job outcome + audit/outbox = jedna transakcija po školi/mesecu.
- SUB-02 correction: jedan append-only red + receipt/audit/outbox = jedna transakcija.

Provider/email/telemetry slanje je posle commit-a kroz outbox; ne određuje poslovni uspeh.

### 7.4. Commercial idempotency i concurrency

**Idempotency:** sve COM komande koriste M00 receipt scope `(command_id, actor/security_scope, request_id)` i canonical payload hash; HTTP adapter mapira `request_id` na `Idempotency-Key`. Retry istog payload-a vraća isti resource/version/result i ne pravi novi audit/outbox. Isti key + drugi payload vraća 409 `COMMERCIAL_IDEMPOTENCY_KEY_REUSED`. Natural unique constraints ostaju poslednja DB zaštita.

**Globalni lock/CAS redosled gde je primenljiv:**

1. Product/Metric definition;
2. PlanVersion → Rule → Tier;
3. Organization;
4. CommercialAgreement → AgreementItem → Adjustment;
5. School/owner-scope aggregate;
6. Entitlement;
7. Receipt/audit/outbox/invalidation.

Publish zaključava plan i sve draft rules/tiers, ponovo računa canonical hash, proverava complete field matrix i samo tada commit-uje. Agreement activation zaključava agreement/items, ponovo proverava plan/effective date/scope relation i u istoj transakciji pravi entitlement deltu. Organization transfer i agreement-item rebind se serializuju preko School/OrganizationSchool agregata; nijedan silent auto-rebind.

## 8. ACCEPTANCE KRITERIJUMI I IZVRŠNI UGOVOR

### 8.1. Komande

| ID | Naziv | Autoritet | Ključni input | Rezultat |
|---|---|---|---|---|
| `ORG-01` | `CreateOrganization` | `platform.organizations.manage` + step-up | ref, legal profile, request_id | Organization ACTIVE. |
| `ORG-02` | `UpdateOrganization` | ista platform dozvola | patch, expected_version, reason, request_id | Versioned profile. |
| `ORG-03` | `ArchiveOrganization` | ista platform dozvola + step-up | expected_version, reason, request_id | ARCHIVED ili guard error. |
| `ORG-04` | `TransferSchoolOrganization` | `platform.schools.ownership.manage` + step-up | school, new org, effective entitlement set, case, reason, versions, request_id | Atomska history/entitlement promena. |
| `SCH-01` | `CreateSchoolFoundation` | `platform.schools.create` + step-up | §3.2 podaci, `initial_owner_person_id`, request_id | School IN_PREPARATION + M06 SchoolPersonProfile + nomination, atomski. |
| `SCH-02` | `UpdateSchoolProfile` | `school.profile.manage` ili platform | dozvoljeni patch, expected_version, request_id | Profil bez protected mass assignment-a. |
| `SCH-03` | `ChangeSchoolTimezone` | primary owner/platform + step-up | timezone, reason, expected_version, request_id | Promena samo pre dependent istorije. |
| `SCH-04` | `ActivateSchool` | primary owner ili platform on-behalf-of | confirmation, expected_version, request_id | ACTIVE. |
| `SCH-05` | `DeactivateSchool` | platform lifecycle + step-up | reason code/note, expected_version, request_id | DEACTIVATED + immediate revoke. |
| `SCH-06` | `ReactivateSchool` | platform lifecycle + step-up | reason code/note, expected_version, request_id | ACTIVE, bez oživljavanja starih poziva/konteksta. |
| `LOC-01` | `RotateSchoolLocator` | `school.profile.manage`/platform | kind, desired/generated value, expected locator version, request_id | Novi active, stari retired. |
| `OWN-01` | `CreateOwnerNomination` | primary owner za additional; platform za initial | target Person + tenant-safe SchoolPersonProfile, kind, request_id | PENDING nomination. |
| `OWN-02` | `CancelOwnerNomination` | creator ili viši owner/platform | expected_version, reason, request_id | CANCELLED + M02 revoke. |
| `OWN-03` | `FulfillOwnerNomination` | isključivo M02 internal acceptance | nomination, role ref, versions, request_id | FULFILLED; ako škola nema nijedan efektivan `PrimaryOwnerTerm`, isti commit kreira prvi term za prihvaćenog nominovanog OWNER-a; ako efektivan term već postoji, ne menja ga. |
| `OWN-04` | `TransferPrimaryOwnership` | current primary ili platform override | target owner, reason/case, expected school/term versions, request_id | Novi primary term. |
| `ENT-01` | `GrantOrReplaceSchoolEntitlement` | `platform.product_entitlements.manage` + step-up | school, capability, validity, commercial ref, reason, request_id | Jedan active grant. |
| `ENT-02` | `RevokeSchoolEntitlement` | ista platform dozvola + step-up | id, expected_version, reason, request_id | REVOKED. |
| `SUB-01` | `GenerateMonthlySubscriptionSnapshot` | M21 `commercial.subscription_usage_snapshot` system principal | school, month, request_id | Immutable snapshot ili idempotent replay. |
| `SUB-02` | `CorrectSubscriptionBillingSnapshot` | `platform.billing_administration` + step-up | snapshot, absolute count, reason/evidence, request_id | Append-only correction. |

### 8.1.1. Permission registry i ne-impliciranje

M05 će fizički registrovati sledeće stabilne ključeve, ali ne sme promeniti njihovo značenje:

| Permission | Scope | Tačno pravo |
|---|---|---|
| `platform.organizations.manage` | PLATFORM | ORG-01–03; ne daje tenant poslovni pristup. |
| `platform.schools.create` | PLATFORM | SCH-01 za odobrenu školu. |
| `platform.schools.lifecycle.manage` | PLATFORM | SCH-04 on-behalf-of i SCH-05/06. |
| `platform.schools.ownership.manage` | PLATFORM | ORG-04 pravno-komercijalni transfer School-a. |
| `platform.school_ownership.override` | PLATFORM | Emergency/legal OWN-04, uz case ref. |
| `platform.product_entitlements.manage` | PLATFORM | ENT-01/02. |
| `platform.billing_administration` | PLATFORM | SUB-02 i platform billing query. |
| `school.profile.manage` | SCHOOL | SCH-02, dozvoljeni locator i pre-history timezone profil; ne status/currency/Organization. |
| `school.lifecycle.activate` | SCHOOL | SCH-04 samo ako je actor aktuelni primary owner. |
| `school.owners.manage` | SCHOOL | Additional-owner nominacija/cancel; samo primary owner može dodeliti OWNER scope. |
| `school.subscription_usage.view` | SCHOOL | Read-only vlastiti original/effective aggregate; ne correction/evidence/child listu. |

**Kanonski commercial permission ključevi:**

| Permission | Scope | Tačno pravo | Default binding |
|---|---|---|---|
| `platform.commercial.catalog.manage` | PLATFORM | COM-01..06 (product/metric lifecycle). | Isključivo `PLATFORM_BILLING_ADMIN`. |
| `platform.commercial.plans.manage` | PLATFORM | COM-07..10 (plan version lifecycle). | Isključivo `PLATFORM_BILLING_ADMIN`. |
| `platform.commercial.agreements.manage` | PLATFORM | COM-11, COM-12, COM-14..18 (agreement lifecycle i item-i). | Isključivo `PLATFORM_BILLING_ADMIN`. |
| `platform.commercial.agreements.acceptance.record` | PLATFORM | COM-13 isključivo (evidence-recording je namerno odvojen od punog agreement lifecycle-a). | Isključivo `PLATFORM_BILLING_ADMIN`. |
| `platform.commercial.adjustments.manage` | PLATFORM | COM-19..20 (adjustment add/revoke). | Isključivo `PLATFORM_BILLING_ADMIN`. |
| `platform.commercial.read` | PLATFORM | Svi commercial query-ji iz §8.2.1. | Isključivo `PLATFORM_BILLING_ADMIN`. |

**Nijedna School rola, Organization veza, payer status, `CommercialAgreement`, Support grant ili entitlement ne daje ijedan od ovih šest ključeva.** Svaka COM mutacija dodatno zahteva: named platform account; odgovarajući granularni permission iznad; step-up autentifikaciju staru najviše 5 minuta; `ticket_ref`; zatvoren `reason_code`; `expected_version` gde postoji aggregate; M00 idempotency receipt; audit i outbox u istoj transakciji. Ako query koristi internal service principal (npr. za `ResolveCommercialRuleForChargeableRef`), njegov identitet i dozvoljeni query moraju biti eksplicitni — nikad anonymous ili Organization-wide business drill-down.

Nijedan platform permission ne implicira drugi. Nijedan school permission ne implicira platform permission. OWNER role ne daje `platform.billing_administration`, a platform Support Access ne daje nijedan permission iz ove tabele automatski.

### 8.1.2. Zatvoreni reason-code registri

Komanda odbija vrednost van odgovarajuće liste. `reason_note` je dodatno obavezan za ORG-04, SCH-05/06, OWN-04, ENT-02 i SUB-02; 1–500 UTF-8 znakova, bez tokena ili child/contact PII.

| Radnja | Dozvoljeni reason kodovi |
|---|---|
| ORG-02 update | `LEGAL_NAME_CORRECTION`, `REGISTRY_DATA_CORRECTION`, `ADMINISTRATIVE_CORRECTION` |
| ORG-03 archive | `LEGAL_ENTITY_CLOSED`, `CREATED_IN_ERROR`, `NO_LONGER_USED` |
| ORG-04 transfer | `LEGAL_OWNERSHIP_TRANSFER`, `CORPORATE_RESTRUCTURE`, `CREATED_UNDER_WRONG_ORGANIZATION` |
| SCH-03 timezone | `INITIAL_PROFILE_CORRECTION`, `SCHOOL_RELOCATION_BEFORE_OPERATIONS` |
| SCH-05 deactivate | `PILOT_PAUSED`, `CONTRACT_TERMINATED`, `SECURITY_INCIDENT`, `LEGAL_REQUEST`, `CREATED_IN_ERROR`, `OPERATIONAL_PAUSE` |
| SCH-06 reactivate | `PILOT_RESUMED`, `CONTRACT_RESTORED`, `SECURITY_REMEDIATED`, `LEGAL_RESTRICTION_LIFTED`, `OPERATIONAL_RESUME` |
| OWN-02 cancel nomination | `WRONG_PERSON`, `REQUEST_WITHDRAWN`, `SCHOOL_PROVISIONING_CANCELLED` |
| OWN-04 transfer | `OWNER_REQUEST`, `LEGAL_REPRESENTATIVE_CHANGE`, `PLATFORM_LEGAL_OVERRIDE` |
| ENT-01 grant/replace | `CONTRACT_ACTIVATED`, `PILOT_APPROVED`, `PLAN_CHANGED`, `ORGANIZATION_TRANSFER`, `REPLACED` |
| ENT-02 revoke | `CONTRACT_SUSPENDED`, `CONTRACT_ENDED`, `PILOT_ENDED`, `PLAN_CHANGED`, `ORGANIZATION_TRANSFER`, `SECURITY_RESTRICTION` |
| SUB-02 correction | `LATE_ENROLLMENT_HISTORY`, `STATUS_HISTORY_CORRECTION`, `PERSON_MERGE_CORRECTION`, `DATA_MIGRATION_CORRECTION`, `CALCULATION_DEFECT` |

Sistemski kodovi, koje klijent ne bira, jesu `SCHOOL_CREATED`, `INITIAL_ACTIVATION`, `INITIAL_OWNER_ACCEPTED`, `SCHOOL_DEACTIVATED`, `REPLACED` i `ENTITLEMENT_EXPIRED`.

### 8.1.3. Commercial command registry — COM-01..20

| ID | Komanda | Obavezni input | Atomski rezultat |
|---|---|---|---|
| `COM-01` | `CreateProductDefinition` | product key, owner module, localization, idempotency | DRAFT + receipt/audit/outbox. |
| `COM-02` | `ActivateProductDefinition` | id, expected_version, reason/ticket | ACTIVE. |
| `COM-03` | `RetireProductDefinition` | id, expected_version, reason/ticket | RETIRED. |
| `COM-04` | `CreateMetricDefinition` | full metric contract | DRAFT. |
| `COM-05` | `ActivateMetricDefinition` | id/version/reason | ACTIVE. |
| `COM-06` | `RetireMetricDefinition` | id/version/reason | RETIRED. |
| `COM-07` | `CreateCommercialPlanVersion` | plan/product/version/currency/effective/disclosure | DRAFT. |
| `COM-08` | `ReplaceDraftPlanContent` | id/version/full canonical rules+tiers | DRAFT version+1; nikad partial patch. |
| `COM-09` | `PublishCommercialPlanVersion` | id/version/reason/ticket/step-up | PUBLISHED immutable. |
| `COM-10` | `RetireCommercialPlanVersion` | id/reason/ticket/step-up | RETIRED. |
| `COM-11` | `CreateCommercialAgreement` | payer org, dates/currency/renewal/notice/terms | DRAFT. |
| `COM-12` | `SubmitAgreementForAcceptance` | agreement/version | Frozen PENDING_ACCEPTANCE content hash. |
| `COM-13` | `RecordExternalAgreementAcceptance` | agreement/version/evidence ref/snapshot/step-up | PENDING_ACCEPTANCE → ACCEPTED; evidence append, bez entitlement-a. |
| `COM-14` | `ActivateCommercialAgreement` | agreement/version/step-up | ACTIVE + active items + entitlement effects. |
| `COM-15` | `SuspendCommercialAgreement` | agreement/version/reason/step-up | SUSPENDED + immediate entitlement deny where linked. |
| `COM-16` | `ResumeCommercialAgreement` | agreement/version/reason/step-up | ACTIVE samo posle svih guardova. |
| `COM-17` | `CancelOrTerminateCommercialAgreement` | agreement/version/reason/step-up | CANCELLED ili TERMINATED prema state-u. |
| `COM-18` | `AddCommercialAgreementItem` | agreement/version/plan/scope/dates/capabilities | PENDING item; samo pre frozen acceptance. |
| `COM-19` | `AddCommercialAgreementAdjustment` | item/version/full adjustment/evidence | SCHEDULED ili ACTIVE append-only. |
| `COM-20` | `RevokeCommercialAgreementAdjustment` | adjustment/version/reason | REVOKED + novi audit/outbox; original ne nestaje. |

Permission binding za COM-01..20 (§8.1.1 dopuna — vidi i M05 §3.3): COM-01..06 → `platform.commercial.catalog.manage`; COM-07..10 → `platform.commercial.plans.manage`; COM-11, COM-12, COM-14..18 → `platform.commercial.agreements.manage`; COM-13 → `platform.commercial.agreements.acceptance.record`; COM-19..20 → `platform.commercial.adjustments.manage`. Default binding za svih šest ključeva ima isključivo `PLATFORM_BILLING_ADMIN`. Nijedna School rola, Organization veza, payer status, CommercialAgreement ili Support grant ne daje ove permission-e.

### 8.2. Query-ji

| ID | Naziv | Scope | Minimalni rezultat |
|---|---|---|---|
| `M04-Q01` | `GetSchoolProfile` | M03 context + permission | Profil trenutne škole; maskiran kontakt, bez platform refs. |
| `M04-Q02` | `GetSchoolLifecycle` | primary owner/platform | status i status history; bez drugih tenant podataka. |
| `M04-Q03` | `GetSchoolOwnership` | primary owner/owner-management permission | active owners iz M05 projection + primary term + pending nominations; bez auth identity-ja. |
| `M04-Q04` | `ListPlatformSchools` | platform scope | Minimalni provisioning/status/owner-invite/readiness summary; bez child/finance/content podataka. |
| `M04-Q05` | `ResolveSchoolLocator` | public/minimal ili M03 | Neutralni school branding/login discovery; locator nije access. |
| `M04-Q06` | `ListSchoolEntitlements` | platform; school owner read-only | Capability/status/validity; commercial ref samo platformi. |
| `M04-Q07` | `GetSubscriptionUsageMonth` | platform billing; school read-only permission | Original/effective count i correction metadata; bez child liste/reason evidence za school actor. |

Lista/cursor/count se tenant-filterira pre sortiranja/paginacije. Platform list ima determinističan sort `created_at desc, id` i page size default 20/max 100.

### 8.2.1. Commercial query ugovori

| Query | Scope | Minimalni rezultat |
|---|---|---|
| `GetCommercialProductCatalog` | `platform.commercial.read` | Product/metric registry sa statusima. |
| `GetPublishedPlanVersion` | `platform.commercial.read` | Jedna PUBLISHED plan verzija sa rules/tiers. |
| `GetCommercialAgreement` | `platform.commercial.read` | Jedan agreement sa item/status istorijom. |
| `ListOrganizationCommercialAgreements` | `platform.commercial.read` | Agreements za jednu Organization; bez cross-Organization curenja. |
| `GetEffectiveAgreementItemsForScope` | `platform.commercial.read` + owner-module resolver | Aktivni item-i za tačan scope ref. |
| `ResolveCommercialRuleForChargeableRef` | Interni service principal, eksplicitan identitet i dozvoljen query — nikad anonymous ili Organization-wide drill-down | Vraća rule/evidence refs i odluku `CONTRACTED\|BLOCK\|REQUIRES_ACCEPTANCE\|NOT_CONFIGURED`; ne kreira charge. |

Svi commercial query-ji zahtevaju `platform.commercial.read` osim gde je eksplicitno drugačije navedeno; nijedan ne dozvoljava anonymous pristup niti Organization-wide business drill-down bez eksplicitnog scope filtera.

### 8.3. Audit/outbox događaji

Obavezni audit event tipovi:

- `organization.created`, `organization.updated`, `organization.archived`;
- `school.created`, `school.profile_updated`, `school.timezone_changed`, `school.activated`, `school.deactivated`, `school.reactivated`, `school.organization_transferred`, `school.locator_rotated`;
- `school.owner_nomination_created`, `school.owner_nomination_cancelled`, `school.owner_nomination_fulfilled`, `school.primary_owner_transferred`;
- `subscription.entitlement_granted`, `subscription.entitlement_replaced`, `subscription.entitlement_revoked`, `subscription.entitlement_expired`;
- `subscription.billing_snapshot_generated`, `subscription.billing_snapshot_corrected`.

Audit sadrži actor, platform/support context, school/organization ID gde je primenljivo, command, aggregate/version, pre/post status, reason code, correlation, request ID i rezultat. Ne sadrži plaintext kontakt, child Person ID listu, token, provider claim ili correction dokaz. Outbox nosi minimalni schema-versioned payload; consumer ignoriše nepoznata dodatna polja, ne nepoznatu major verziju.

### 8.3.1. Commercial audit/outbox događaji

Obavezni audit event tipovi:

- `commercial_product.created`, `commercial_product.activated`, `commercial_product.retired`;
- `commercial_metric.created`, `commercial_metric.activated`, `commercial_metric.retired`;
- `commercial_plan_version.created`, `commercial_plan_version.content_replaced`, `commercial_plan_version.published`, `commercial_plan_version.retired`;
- `commercial_agreement.created`, `commercial_agreement.submitted`, `commercial_agreement.acceptance_recorded`, `commercial_agreement.activated`, `commercial_agreement.suspended`, `commercial_agreement.resumed`, `commercial_agreement.cancelled`, `commercial_agreement.terminated`, `commercial_agreement.expired`;
- `commercial_agreement_item.added`;
- `commercial_agreement_adjustment.added`, `commercial_agreement_adjustment.revoked`.

Svaki commercial audit zapis sadrži actor, permission korišćen, ticket_ref, reason_code, aggregate/version, pre/post status, correlation, request ID i rezultat. Nikad ne sadrži child PII, plaintext kontakt osobe upisane u `accepted_organization_name_snapshot` van organizacionog naziva, ili raw negotiated override payload (samo `override_payload_hash`). Outbox koristi isti schema-versioned obrazac kao ostatak M04; consumer ignoriše nepoznata dodatna polja, ne nepoznatu major verziju. Audit failure blokira commercial radnju — nema commit-a bez uspešnog audit upisa u istoj transakciji.

### 8.4. `commercial.subscription_usage_snapshot`

Job se planira prvog dana meseca u 00:10 po lokalnoj zoni svake škole i izvršava tenant po tenant prema M21 katalogu. Retry profil `BILLING_5` daje najviše 5 pokušaja u 24 sata od preseka, zatim dead-letter/attention bez lažnog snapshot-a. Manual replay koristi isti `(school_id,billing_month)` business key. Telemetry ostaje `TEL-006` start, `TEL-007` success, `TEL-008` failure, `TEL-009` retry, `TEL-010` dead-letter sa stabilnim `job_key`; bez child PII.

### 8.5. Acceptance kriterijumi

Detaljna deterministična matrica je u `02-M04-QA-I-TRACEABILITY.md`. Modul nije primljen dok ne prođu najmanje:

1. schema/constraint testovi za sva polja, enums, unique i temporal overlap pravila;
2. state-machine test svake dozvoljene i zabranjene tranzicije;
3. dve škole/dve Organization/dva naloga cross-tenant testovi za command/query/list/count/export/cache;
4. M02 initial/additional owner i M03 deactivate/reactivate integracioni testovi;
5. paralelni create, transfer, activation, locator, entitlement, subscription-usage job i correction testovi;
6. timezone/reference-boundary i distinct Person billing testovi;
7. dokaz da snapshot/correction ne dodiruje M12 finansije;
8. audit/outbox redaction i atomic rollback testovi;
9. brownfield migracija sa exception report-om umesto automatskog merge-a/brisanja;
10. dokaz da javni staging conflict „registracija naloga/školski code kao pristup” nije backend put za kreiranje pristupa;
11. svih M04-QA-109..129 iz `02-M04-QA-I-TRACEABILITY.md` prolaze: komercijalni model 109–126 i deferred Foundation reference/atomicity testovi 127–129.

## 9. Brownfield migracija i očuvanje postojećeg rada

Claude Code prvo mapira stvarni repo i za svaku stavku koristi `PRESERVE`, `ADAPT`, `IMPLEMENT`, `REMOVE_CONFLICT` ili `VERIFY_IN_REPO`. Ne prepisuje funkcionalan raspored, finansije, PWA shell ili postojeći tenant UI samo zbog naziva klase/tabele.

Migracija mora biti idempotentna i forward-safe:

1. postojeći School dobija stabilan `provisioning_reference`, Organization i OrganizationSchool bez promene School ID-a;
2. postojeći statusi mapiraju se samo `U pripremi→IN_PREPARATION`, `Aktivna→ACTIVE`, `Deaktivirana→DEACTIVATED`; nepoznat status ide u exception report, ne u guessed mapping;
3. TenantSecurityState se kreira kroz M03 TEN-05 ako nedostaje;
4. postojeće owner role se ne proglašavaju sve primary; tačno jedan dokazani primary dobija active term. Ako dokaz ne postoji ili ima više kandidata, School ostaje/ide u kontrolisani exception i regularna ownership mutacija je fail-closed;
5. aktivna School bez owner-a, Organization veze ili CORE entitlement-a ne dobija izmišljene podatke; evidentira se remediation;
6. stari `valid_from/valid_to` date podaci konvertuju se samo uz dokazanu školsku zonu i jasno pravilo početka dana; ambigvitet ide u exception report;
7. redundantni snapshot `sequence_no`, ako postoji, ignoriše se/uklanja tek nakon verifikacije da nema consumer semantiku; correction sequence ostaje;
8. correction red bez `school_id` dobija ga isključivo preko dokazanog parent snapshot-a;
9. postojeći snapshot-i se ne recompute-uju ili update-uju;
10. javna self-registration ili school-code grant putanja se uklanja/disable-uje ako može napraviti nalog/pristup mimo M02; login discovery bez granta se može sačuvati;
11. pre irreversible DDL postoji backup i forward-recovery plan; rollback ne sme oživeti deaktiviranu školu, revoke-ovan entitlement/poziv ili duplu Organization vezu.

`CURRENT-CODE-BASELINE` ostaje `UNRESOLVED` dok stvarni repo nije pregledan. Dokumentacija ne tvrdi da migracije ili testovi već postoje.
