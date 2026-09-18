---
tip: modulni-implementacioni-ugovor
modul-id: M06
naziv: Ljudi i školska članstva
status: SPEC_CANDIDATE
revizija: "1.3"
datum: 2026-09-15
schema-zavisnosti: [M04]
application-guardovi: [M01, M03, M05]
izlazni-portovi-za: [M02, M03, M05, M07, M08, M09, M10, M11, M12, M13, M14, M16, M17, M18, M19, M20, M28]
---

# M06 — Ljudi i školska članstva

## 0. Autoritet

M06 je jedini vlasnik entiteta `Person`, `PersonSensitiveIdentifier`, `SchoolMembership`, `SchoolPersonProfile`, `ParticipantProfile`, `StaffProfile` i `PersonMergeHistoryEntry`. `Person` nije nalog: M01 poseduje `UserAccount`, `AuthIdentity` i sesije, a M01 `UserAccount.person_id` referencira M06 `Person.id`. M06 nema direktnu schema, read ili domain zavisnost ka M01, M05 ili M07; autentifikacija/autorizacija i prikaz podatka „ima nalog“ orkestriraju se u application/query composition sloju bez M06→M01 poziva.

Ovaj ugovor koristi neutralni naziv `PARTICIPANT`, a ne `STUDENT`, kako bi isti model podržao sport, ples, glumu, muziku i edukativne programe. UI naziv je tenant/i18n konfiguracija i ne menja runtime enum.

## 1. Cilj i granice

### 1.1. M06 radi

- vodi jednu globalnu osobu, uključujući dete bez naloga;
- vodi nezavisne epizode odnosa osobe sa svakom školom;
- vodi minimalni lokalni profil škole, profil učesnika i profil osoblja;
- daje M02 read port za proveru da li odrasla osoba sme dobiti nalog;
- daje M03/M05 read port sa minimalnim činjenicama o članstvu;
- otkriva moguće duplikate bez automatskog spajanja;
- omogućava strogo kontrolisan tenant-lokalni merge;
- štiti kontaktne, identifikacione i zdravstveno-bezbednosne podatke.

### 1.2. Non-goals

- M06 ne autentifikuje, ne kreira nalog i ne povezuje identitete provajdera — M01/M02.
- Ne poseduje školu, pretplatu, ogranke, programe, grupe ili upise — M04/M08/M09.
- Ne poseduje uloge, dozvole ili Support Access — M05.
- Ne određuje ko je čiji staratelj, primarni kontakt ili platilac — M07.
- Ne poseduje finansije, HR obračun, ugovore, dokumente ili retention rokove — M12/M15/M17.
- Ne pravi globalnu pretragu osoba niti otkriva postojanje osobe drugoj školi.
- Ne koristi email, telefon ili ime kao automatski identity/account-link ključ.
- Ne dozvoljava samostalni nalog deteta u H0/MVP-u.
- Ne radi cross-tenant merge u H0; takav slučaj ostaje eksplicitno blokiran do privacy-governed procesa.

## 2. Entiteti i polja

### 2.0. Logički tipovi

- `Identifier`: UUID.
- `InstantUTC`: trenutak sa vremenskom zonom, skladišten kao UTC/TIMESTAMPTZ.
- `LocalDate`: ISO `YYYY-MM-DD`, bez vremenske zone.
- `Version`: pozitivan `uint64`, početna vrednost 1.
- `EncryptedPII`: aplikaciono enkriptovan envelope sa `ciphertext`, `algorithm_id`, `key_id` i nonce/tag metapodacima; plaintext nije u DB/logu/auditu.
- `BlindIndex`: HMAC/keyed-hash normalizovane vrednosti, sa zasebnim ključem od encryption ključa.
- Svi runtime identifikatori, enum-i, permission/error/event kodovi su na engleskom; korisnički podaci su puni UTF-8.

### 2.1. `Person`

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id` | Identifier | DA | PK, globalan, immutable. |
| `first_name` | string(1..100) | DA | Trim spoljašnjih razmaka; Unicode tekst, bez case normalizacije prikaza. |
| `last_name` | string(1..100) | DA | Isto. |
| `birth_date` | LocalDate? | NE | Nepoznato je dozvoljeno; za age-guard znači „uzrast nije dokazan“. |
| `email_ciphertext` | EncryptedPII? | NE | Kontakt, nikad login/link ključ. |
| `email_blind_index` | BlindIndex? | NE | Samo kandidat za dedupe; mora biti oba null ili oba non-null sa ciphertext-om. |
| `phone_ciphertext` | EncryptedPII? | NE | E.164 normalizacija pre enkripcije; kontakt, ne auth. |
| `phone_blind_index` | BlindIndex? | NE | Samo kandidat za dedupe. |
| `dedupe_status` | enum | DA | `CLEAR`, `POTENTIAL_DUPLICATE`, `REVIEWED_DISTINCT`, `MERGED`. |
| `merged_into_person_id` | Identifier? | NE | Popunjen isključivo kada je `dedupe_status=MERGED`; ne sme pokazati na sebe. |
| `created_at`, `updated_at` | InstantUTC | DA | Server time. |
| `version` | Version | DA | CAS. |

`Person` nema `password`, provider subject, external login reference, role, `school_id` niti auth status.

### 2.2. `PersonSensitiveIdentifier`

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id` | Identifier | DA | PK. |
| `person_id` | Identifier | DA | FK → `Person.id`. |
| `identifier_type` | enum | DA | H0: `JMBG`; proširenje zahteva novu eksplicitnu enum vrednost. |
| `issuing_country_code` | char(2) | DA | ISO 3166-1 alpha-2; za JMBG `RS`. |
| `value_ciphertext` | EncryptedPII | DA | Nikad plaintext van kratkog command scope-a. |
| `value_blind_index` | BlindIndex | DA | Exact dedupe; nikad se ne vraća klijentu. |
| `lawful_purpose_code` | string(1..64) | DA | Zatvoren M17 registar; nema slobodnog „za svaki slučaj“. |
| `collected_by_account_id` | Identifier | DA | Audit actor iz M01. |
| `collected_at` | InstantUTC | DA | Server time. |
| `redacted_at` | InstantUTC? | NE | Posle redakcije ciphertext više nije čitljiv. |
| `version` | Version | DA | CAS. |

`UNIQUE(person_id, identifier_type, issuing_country_code)`. JMBG nije obavezan za registraciju, poziv ili redovan rad. Maloletnost sama po sebi ne stvara blanket zabranu ako postoji dokumentovan zakonit i nužan razlog, ali nepoznat/nevažeći razlog, nedostupan privacy-purpose policy ili suvišno prikupljanje mora biti odbijeno. Fotografija ličnog dokumenta nije dozvoljena u H0. Capability `people.sensitive_identifier` je default OFF; uključuje se tek kada M17 privacy-purpose registry ima potvrđen aktivan osnov i retention. M17 je jedini vlasnik te politike, bez reverse schema zavisnosti ili promene M06 vlasništva nad identifikatorom.

### 2.3. `SchoolMembership`

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id` | Identifier | DA | PK. |
| `school_id` | Identifier | DA | FK → M04 `School.id`; tenant kolona. |
| `person_id` | Identifier | DA | FK → `Person.id`. |
| `membership_type` | enum | DA | `PARTICIPANT`, `GUARDIAN`, `STAFF`, `CONTACT`. |
| `status` | enum | DA | `DRAFT`, `ACTIVE`, `SUSPENDED`, `TERMINATED`. |
| `start_date` | LocalDate | DA | Poslovni datum škole. |
| `end_date` | LocalDate? | NE | Obavezno samo za `TERMINATED`; ne pre `start_date`. |
| `suspension_reason_code` | string(1..64)? | NE | Obavezno samo u `SUSPENDED`. |
| `termination_reason_code` | string(1..64)? | NE | Obavezno samo u `TERMINATED`. |
| `is_first_activation` | boolean | DA | Izvedeno iz istorije istog `(school, person, type)`; immutable. |
| `created_at`, `updated_at` | InstantUTC | DA | Server time. |
| `version` | Version | DA | CAS. |

Partial `UNIQUE(school_id, person_id, membership_type) WHERE status <> 'TERMINATED'`. Za tenant-safe reference iz drugih modula postoje `UNIQUE(school_id,id)` i `UNIQUE(school_id,id,person_id)`. `SchoolMembership` nema `role` polje.

### 2.4. `SchoolPersonProfile`

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id` | Identifier | DA | PK. |
| `school_id` | Identifier | DA | Tenant. |
| `person_id` | Identifier | DA | FK → `Person.id`. |
| `local_person_code` | string(1..64)? | NE | Jedinstven unutar škole kada postoji; NFKC + outer trim, case-sensitive, bez control/BiDi/zero-width/soft-hyphen znakova. |
| `administrative_note` | string(0..500)? | NE | Ne sme sadržati zdravlje, finansije, nacionalni ID, lozinke ili tokene. |
| `created_at`, `updated_at` | InstantUTC | DA | Server time. |
| `version` | Version | DA | CAS. |

`UNIQUE(school_id, person_id)`, `UNIQUE(school_id,id,person_id)` i partial `UNIQUE(school_id, normalized_local_person_code)` kada code postoji. `normalized_local_person_code` je byte-stabilan rezultat NFKC+outer trim-a bez casefold-a; time ostaje u skladu sa case-sensitive M20 external reference ugovorom.

### 2.5. `ParticipantProfile`

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id` | Identifier | DA | PK. |
| `school_id` | Identifier | DA | Tenant. |
| `school_membership_id` | Identifier | DA | Kompozitni FK `(school_id, school_membership_id)` → `SchoolMembership(school_id,id)`; membership mora biti `PARTICIPANT`. |
| `discipline_category` | enum? | NE | `SPORT`, `DANCE`, `DRAMA`, `MUSIC`, `EDUCATION`, `OTHER`; UI koristi M08 program. |
| `level_label` | string(1..100)? | NE | Tenant-local prikazni nivo; nije globalni standard. |
| `prior_experience_note` | string(0..500)? | NE | Bez zdravstvenih/identifikacionih podataka. |
| `safety_note_ciphertext` | EncryptedPII? | NE | Samo minimalna informacija nužna za bezbedno izvođenje aktivnosti, uz M17 osnov/retention. |
| `created_at`, `updated_at` | InstantUTC | DA | Server time. |
| `version` | Version | DA | CAS. |

`UNIQUE(school_id, school_membership_id)`. Ne postoji ciphertext „reference“ niti kopija JMBG-a u profilu.

### 2.6. `StaffProfile`

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id` | Identifier | DA | PK. |
| `school_id` | Identifier | DA | Tenant. |
| `school_membership_id` | Identifier | DA | Tenant-safe FK; membership mora biti `STAFF`. |
| `engagement_type` | enum? | NE | `EMPLOYEE`, `CONTRACTOR`, `VOLUNTEER`, `OTHER`. |
| `specialization_codes` | sorted string(1..64)[] | NE | Najviše 50 vrednosti, bez duplikata. |
| `qualification_note` | string(0..500)? | NE | Ne sadrži platu, bankovni račun ili nacionalni ID. |
| `created_at`, `updated_at` | InstantUTC | DA | Server time. |
| `version` | Version | DA | CAS. |

`UNIQUE(school_id, school_membership_id)`.

### 2.7. `PersonMergeHistoryEntry`

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id` | Identifier | DA | PK. |
| `school_id` | Identifier | DA | H0 merge je tenant-lokalan. |
| `surviving_person_id`, `merged_person_id` | Identifier | DA | Različiti ID-jevi; istorija immutable. |
| `reason_code` | string(1..64) | DA | Zatvoren registar. |
| `merged_by_account_id` | Identifier | DA | Actor. |
| `merged_at` | InstantUTC | DA | Server time. |

## 3. Poslovna pravila i invarijante

1. Dete postoji kao `Person` + `PARTICIPANT` membership bez `UserAccount`.
2. Jedna osoba može imati više tipova članstva u istoj školi i članstva u više škola; nijedno ne prenosi prava u drugu školu.
3. M01 je jedini vlasnik veze naloga ka osobi; M06 je ne kreira niti menja.
4. Email/telefon/nacionalni identifikator služe samo za candidate matching. Sistem nikad automatski ne povezuje nalog ili spaja osobe.
5. `is_first_activation=true` samo ako nikad nije postojala ranija epizoda istog prirodnog ključa; povratnik dobija novi red i `false`.
6. Profil mora pripadati istom `school_id` kao membership i odgovarajućem membership tipu pri create i update-u.
7. `TERMINATED` membership je terminalan; reaktivacija znači nova epizoda.
8. Suspendovan/terminiran membership odmah je neefektivan za M03/M05, čak i ako invalidation event kasni.
9. Terminiranje membership-a koji nosi poslednju aktivnu OWNER ulogu ne sme ostaviti školu bez owner-a. Application use-case zaključava relevantne M05 assignments i M06 membership u stabilnom redosledu, poziva M05 owner invariant, pa tek onda vrši M06 tranziciju; M06 ne importuje M05.
10. M06 query nikad ne vraća globalnu listu svih škola/osoba actor-u škole.
11. Identifikacioni plaintext postoji samo u request-scoped memoriji do validacije/enkripcije i mora biti očišćen čim stack dozvoljava; ne ide u event, receipt, audit ili error.
12. `safety_note_ciphertext` se ne vraća kroz opšti profile endpoint; zahteva `school.participant.safety.view` i zaseban audit read.
13. Brisanje poslovno referencirane osobe je soft redaction/crypto-shred po M17 nalogu; finansijski/audit identitet ostaje kao opaque ID.
14. H0 merge je dozvoljen samo ako oba zapisa i sve njihove zavisne reference pripadaju aktivnoj školi. Bilo koja veza sa drugom školom blokira merge.
15. Merge je jedna transakcija: lock oba Person reda stabilnim ID redosledom, provera zavisnosti/konflikata, re-parent tenant-lokalnih zapisa, upis istorije, označavanje gubitnika, audit/outbox/receipt.

### 3.1. Obavezni edge cases

| Slučaj | Deterministički ishod |
|---|---|
| Dva paralelna create membership zahteva za isti prirodni ključ | Jedan commit; drugi 409 `M06_MEMBERSHIP_ALREADY_CURRENT`. |
| Isti email koriste dve stvarne osobe | Oba `Person` reda ostaju odvojena; candidate flag, bez auto-linka. |
| Birth date nedostaje pri account eligibility proveri | `NOT_ELIGIBLE`; nema naloga detetu/osobi bez dokazanog uzrasta. |
| Profil A dobije membership ID iz B | 404 `M06_NOT_FOUND_SAFE`; nema cross-tenant detalja. |
| Poslednji OWNER pokušava terminate membership | 409 `RBAC_LAST_OWNER_PROTECTED`; M06 stanje nepromenjeno. |
| Merge uključuje Person sa vezom u drugoj školi | 409 `M06_CROSS_TENANT_MERGE_NOT_SUPPORTED`; nema delimične izmene. |
| National ID policy verifier nije dostupan | 503 `M06_SENSITIVE_POLICY_UNAVAILABLE`; vrednost se ne upisuje. |
| Access revoked dok safety note read traje | Pre response serialization recheck; 409 `M06_CONCURRENT_AUTHORIZATION_CHANGE`, bez plaintext-a. |

## 4. Tenant & Security Guard

Svaka tenant operacija prolazi: M01 važeća sesija → M03 `TenantExecutionContext` → M05 permission → resource/subject guard → precommit/pre-serialization recheck za osetljive operacije. UI provera nije authorization.

- Svaki tenant entitet nosi `school_id`; svi međumodulski FK-ovi koriste `(school_id,id)` gde target pripada tenant-u.
- Existing cross-tenant i skriven child/subject target vraća isti 404 `M06_NOT_FOUND_SAFE` kao nepostojeći ID.
- 403 se koristi samo kada actor već legitimno zna da resurs postoji u aktivnoj školi, ali nema dozvoljenu akciju.
- Search se prvo tenant/subject filtrira, tek zatim računa `count`, cursor i sugestije.
- Platform rola sama ne daje Person podatke. Support ih dobija samo kroz M05 vremenski ograničen grant, masking i audit.
- Cache ključ uključuje `account_id`, `school_id`, M01/M03/M05/M07 verzije i query scope; bez dokazane svežine radi autoritativni read ili fail-closed.
- Logovi/metrike sadrže error/command kod, correlation ID, tenant HMAC i trajanje; ne sadrže ime, email, telefon, ID plaintext, safety note ni child payload.
- Primarna baza, backup-i, replike i object storage koriste enkripciju at rest i TLS in transit. Ime i datum rođenja su standardni PII: nisu u telemetry-ju/cache ključu/audit payload-u, a pristup im je tenant/subject ograničen; kontakt, nacionalni identifikator i safety note dodatno koriste navedenu field-level enkripciju.
- Local/PWA cache M06 PII nije dozvoljen u H0. M06 write komande zahtevaju online server confirmation; nema optimistic konačnog uspeha.

Minimalni permission ključevi: `school.people.basic.view`, `school.people.contact.view`, `school.people.manage`, `school.memberships.manage`, `school.participant.safety.view`, `school.people.sensitive_identifier.manage`, `school.people.sensitive_identifier.reveal`, `school.people.merge_local`.

## 5. Lifecycle & transitions

### 5.1. `SchoolMembership`

| From | Komanda | To | Guard |
|---|---|---|---|
| — | `MEM-01 CreateMembership` | `DRAFT` | Nema otvorene epizode prirodnog ključa. |
| `DRAFT` | `MEM-02 ActivateMembership` | `ACTIVE` | `start_date` validan; profile nije preduslov. |
| `DRAFT` | `MEM-05 TerminateMembership` | `TERMINATED` | Reason + end date; koristi se za odustajanje pre aktivacije. |
| `ACTIVE` | `MEM-03 SuspendMembership` | `SUSPENDED` | Reason obavezan. |
| `SUSPENDED` | `MEM-04 ReactivateMembership` | `ACTIVE` | I dalje važi School/Person i owner invariant. |
| `ACTIVE`/`SUSPENDED` | `MEM-05 TerminateMembership` | `TERMINATED` | Reason/end date + application-level M05 owner guard. |
| `TERMINATED` | bilo koja transition komanda | — | Zabranjeno; novi period je nov red. |

### 5.2. `Person.dedupe_status`

| From | Komanda/događaj | To |
|---|---|---|
| — | `PER-01 CreatePerson` | `CLEAR` ili `POTENTIAL_DUPLICATE` |
| `POTENTIAL_DUPLICATE` | `PER-03 MarkReviewedDistinct` | `REVIEWED_DISTINCT` |
| `CLEAR`/`POTENTIAL_DUPLICATE`/`REVIEWED_DISTINCT` | `MRG-01 MergePersons` za gubitnika | `MERGED` |
| `MERGED` | bilo koja mutation | — terminalno; read resolve vraća surviving opaque ID samo ovlašćenom actor-u. |

Profili nemaju sopstveni status; efektivnost prati membership. Sensitive identifier je active dok `redacted_at` nije postavljen; redakcija je terminalna za taj red, a novi zakoniti unos dobija novi ID.

## 6. Error catalog

| Kod | HTTP | Značenje |
|---|---:|---|
| `M06_AUTHENTICATION_REQUIRED` | 401 | Nema važeće M01 sesije. |
| `M06_CONTEXT_REQUIRED` | 409 | Nema važećeg M03 school context-a. |
| `M06_NOT_FOUND_SAFE` | 404 | Nepostojeći, cross-tenant ili skriven subject. |
| `M06_FORBIDDEN` | 403 | Poznati same-tenant resurs, nedostaje pravo. |
| `M06_VALIDATION_FAILED` | 422 | Polje/enum/datum ne prolazi zatvoren ugovor. |
| `M06_MEMBERSHIP_ALREADY_CURRENT` | 409 | Postoji otvorena epizoda prirodnog ključa. |
| `M06_MEMBERSHIP_INVALID_TRANSITION` | 409 | Prelaz nije u §5.1. |
| `M06_STALE_VERSION` | 409 | `expected_version` nije aktuelan. |
| `M06_PROFILE_TYPE_MISMATCH` | 422 | Profil i membership type se ne poklapaju. |
| `M06_PROFILE_ALREADY_EXISTS` | 409 | Profil za membership već postoji. |
| `M06_PERSON_NOT_ACCOUNT_ELIGIBLE` | 422 | M02 mutation cilja osobu bez dokazanog H0 eligibility-ja. |
| `M06_POTENTIAL_DUPLICATE` | 409 | Operacija koja zahteva razrešen identitet cilja unresolved candidate; Person create nije blokiran. |
| `M06_MERGE_MEMBERSHIP_CONFLICT` | 409 | Oba Person reda imaju otvoren isti membership ključ. |
| `M06_CROSS_TENANT_MERGE_NOT_SUPPORTED` | 409 | Jedna strana ima zavisnost van aktivne škole. |
| `M06_SENSITIVE_PURPOSE_INVALID` | 422 | Lawful purpose nije aktivan/dozvoljen. |
| `M06_SENSITIVE_POLICY_UNAVAILABLE` | 503 | M17 policy nije moguće autoritativno proveriti. |
| `M06_CONCURRENT_AUTHORIZATION_CHANGE` | 409 | Pravo/subject/context se promenio pre commit-a/response-a. |
| `M06_IDEMPOTENCY_KEY_REUSED` | 409 | Isti key, drugi canonical payload. |
| `M06_IDEMPOTENCY_IN_PROGRESS` | 409 | Isti zahtev je još u obradi; `Retry-After` obavezan. |

M05 owner guard može vratiti svoj stabilan `RBAC_LAST_OWNER_PROTECTED`; application endpoint ga ne prevodi u M06 kod.

## 7. Idempotency, concurrency, transakcije i API ugovori

Svaka write komanda zahteva stabilni `request_id: UUID`, koji je kanonski idempotency ključ i HTTP `Idempotency-Key`; scope je `(command_code, actor_account_id, school_id-or-GLOBAL, request_id)`. Canonical payload hash ne sadrži plaintext sensitive identifier. Isti ključ+hash vraća originalni receipt; isti ključ+drugi hash vraća 409. Receipt, domain upis, audit i outbox nastaju u istoj DB transakciji.

Svaki update/transition zahteva `expected_version`. Unique constraints su poslednja zaštita od trke. Lock redosled: School/Membership prirodni ključ → Person stabilnim ID redom → tenant profili → M05 assignment-i samo u application-orchestrated owner use-case-u. Deadlock retry je ograničen i koristi isti idempotency receipt.

### 7.1. Komande

| ID | Naziv | Obavezni input | Atomski rezultat |
|---|---|---|---|
| `PER-01` | `CreatePerson` | names, optional birth/contact, idempotency/request IDs | Person + blind indexes + optional candidate attention item. |
| `PER-02` | `UpdatePersonCore` | person, changed fields, expected version, IDs | Person version +1; candidate matching ponovo izračunat. |
| `PER-03` | `MarkReviewedDistinct` | person, expected version, reason, IDs | Dedupe status + audit. |
| `PER-04` | `UpsertSchoolPersonProfile` | school/person, fields, expected version when existing, IDs | One tenant profile. |
| `PER-05` | `CreateParticipantProfile` | school/membership, fields, IDs | Profil samo za PARTICIPANT. |
| `PER-06` | `UpdateParticipantProfile` | school/profile, fields, expected version, IDs | Version +1. |
| `PER-07` | `CreateStaffProfile` | school/membership, fields, IDs | Profil samo za STAFF. |
| `PER-08` | `UpdateStaffProfile` | school/profile, fields, expected version, IDs | Version +1. |
| `PER-09` | `SetSensitiveIdentifier` | person, type/country/value, lawful purpose, policy version, IDs | Encrypted row + blind index; no plaintext event. |
| `PER-10` | `RedactPersonData` | M17 erasure/order ref, scope, expected versions, IDs | Crypto-shred/redaction uz očuvane poslovne reference. |
| `MRG-01` | `MergePersonsLocal` | school, surviving/merged IDs, expected versions, reason, IDs | §3.15 transakcija ili potpuni rollback. |
| `MEM-01` | `CreateMembership` | school, person, membership type, start date, request/correlation IDs | DRAFT membership ili potpuni fail. |
| `MEM-02` | `ActivateMembership` | membership, expected version, request/correlation IDs | ACTIVE, version +1. |
| `MEM-03` | `SuspendMembership` | membership, expected version, reason, request/correlation IDs | SUSPENDED + access invalidation. |
| `MEM-04` | `ReactivateMembership` | membership, expected version, request/correlation IDs | ACTIVE samo ako svi aktuelni guardovi prolaze. |
| `MEM-05` | `TerminateMembership` | membership, expected version, end date, reason, request/correlation IDs | TERMINATED + application-orchestrated M05/M07 zatvaranje ili potpuni rollback. |

### 7.2. Read portovi

- `PersonEligibilityPort.check(person_id)` → `ELIGIBLE | NOT_ELIGIBLE | NOT_FOUND`; H0 eligibility: osoba nije `MERGED`, postoji `birth_date` i na dan provere ima najmanje 18 godina.
- `MembershipFactsPort.get(school_id, person_id|membership_id)` → samo membership ID/type/status/version; ne vraća Person PII.
- `PersonReferencePort.resolveForInvitation(school_id, school_person_profile_id, person_id)` → profile/person ID + njihove verzije ili safe `NOT_FOUND`; composite M06 constraint dokazuje isti school/person, bez globalne pretrage.
- `ParticipantSafetyPort.getForAssignedActivity(...)` → minimalna dekriptovana safety napomena samo nakon M05+M09 subject guard-a i audit read-a.

## 8. Acceptance kriterijumi

1. Svih 35 scenarija iz [[02-M06-QA-I-TRACEABILITY]] prolazi bez preskakanja.
2. Schema nema `StudentProfile`, `STUDENT`, `jmbg_ciphertext_ref`, Person auth polje niti M06→M05/M07 FK/import.
3. Svaki tenant FK negativni test odbija cross-school kombinaciju na DB i API nivou.
4. Email/telefon/nacionalni ID nikad automatski ne spajaju Person ili UserAccount.
5. Članstvo i profili podržavaju svih šest neutralnih disciplina bez domain grananja po „sportu“.
6. Cross-tenant/sakriven subject daje stabilan safe 404; list/count/cursor ne otkrivaju skrivene redove.
7. Sensitive identifier i safety note nikad nisu u logu, audit payload-u, outbox-u, receipt hash-u ili exception-u.
8. Paralelni create/update/merge testovi daju jedan deterministički pobednički commit i bez partial write-a.
9. Poslednji OWNER ne može izgubiti efektivno membership/role stanje kroz race.
10. Sve M06 mutacije su online-only; nijedan PWA retry ne prikazuje konačan uspeh pre server receipt-a.

## 9. Brownfield pravilo

Repo nije pregledan. Validne postojeće tabele i tokovi se `PRESERVE`; kompatibilne se `ADAPT`; konfliktni enum-i/FK/PII tokovi se migriraju bez gubitka istorije; nedostajuće se `IMPLEMENT`. Ni ovaj dokument ni ekran nisu dokaz implementacije.
