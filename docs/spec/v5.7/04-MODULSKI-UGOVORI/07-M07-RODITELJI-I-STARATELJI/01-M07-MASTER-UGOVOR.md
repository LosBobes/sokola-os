---
tip: modulni-implementacioni-ugovor
modul-id: M07
naziv: Porodice, staratelji i platioci
status: SPEC_CANDIDATE
revizija: "1.2"
datum: 2026-09-15
schema-zavisnosti: [M04, M06]
read-portovi: [M06]
application-guardovi: [M01, M03, M05]
izlazni-portovi-za: [M02, M05, M09, M12, M13, M14, M15, M16, M17, M18, M19, M20, M28]
---

# M07 — Porodice, staratelji i platioci

## 0. Autoritet

M07 je jedini vlasnik `Family`, `FamilyMembership`, `GuardianChildLink`, `RelationshipVerificationRecord`, `PayerChildLink`, `PrimaryGuardianContactDesignation` i `PrimaryPayerDesignation`. M06 poseduje osobe i školska članstva; M05 poseduje role/grant i proverava M07 subject-basis; M12 poseduje zaduženja, podelu finansijske odgovornosti, ledger i novac.

`Family` je tenant-scoped organizaciona/finansijska grupa, ne auth domen i ne dokaz starateljstva. Starateljstvo i pravo na child podatke nastaju samo iz ACTIVE verifikovanog `GuardianChildLink`. Payer odnos je odvojen i daje samo finansijski scope.

## 1. Cilj i granice

### 1.1. M07 radi

- modeluje jednu ili više porodičnih/household grupa po detetu i školi;
- povezuje odrasle i zavisne članove porodice bez automatskog auth prava;
- vodi dokazanu vezu odrasla osoba–dete;
- vodi više aktivnih staratelja po detetu;
- određuje najviše jedan primarni kontakt i najviše jednog primarnog platioca po detetu/školi;
- omogućava više aktivnih payer veza koje aktivni M12 koristi za capability-gated model podeljene odgovornosti;
- daje M02 dokaz za guardian poziv i M05 minimalni subject/payer resolver;
- trenutno opoziva pristup kada se veza opozove.

### 1.2. Non-goals

- M07 ne kreira `Person`, `UserAccount`, `Invitation`, role ili permission — M06/M01/M02/M05.
- Ne odlučuje iznose, 50/50 procente, dug, kredit, povraćaj ili alokaciju uplate — M12.
- Ne čuva sudske odluke, lične dokumente, fotografije dokumenata ili medicinske podatke.
- Ne predstavlja pravno utvrđivanje starateljstva; beleži školsku proveru i operativno pravo pristupa.
- Ne šalje poruke i ne kreira automatske notifikacije — M13/M14.
- Primarni kontakt/platioc ne dobija automatski šire dozvole.
- Jedna `Family` ne može obuhvatiti više škola i nije sredstvo za cross-tenant zbir/pretragu.
- H0 ne dozvoljava roditelju da sam aktivira drugog staratelja; može samo inicirati M02 zahtev koji škola odobrava.

## 2. Entiteti i polja

### 2.0. Tipovi

`Identifier`=UUID; `InstantUTC`=UTC/TIMESTAMPTZ; `LocalDate`=YYYY-MM-DD; `Version`=uint64 ≥1; `Code64`=ASCII runtime code 1..64. Svi tenant entiteti imaju `school_id` i `UNIQUE(school_id,id)` za kompozitne FK-ove.

### 2.1. `Family`

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id` | Identifier | DA | PK. |
| `school_id` | Identifier | DA | FK → M04 School; tenant. |
| `display_label` | string(1..100)? | NE | Interni label škole; ne koristi se za identitet. |
| `status` | enum | DA | `ACTIVE`, `ARCHIVED`. |
| `created_by_account_id` | Identifier | DA | M01 actor. |
| `archive_reason_code` | Code64? | NE | Obavezno kada je ARCHIVED. |
| `created_at`, `updated_at` | InstantUTC | DA | Server time. |
| `version` | Version | DA | CAS. |

### 2.2. `FamilyMembership`

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id` | Identifier | DA | PK. |
| `school_id` | Identifier | DA | Tenant. |
| `family_id` | Identifier | DA | Tenant-safe FK → Family. |
| `person_id` | Identifier | DA | FK → M06 Person. |
| `school_membership_id` | Identifier | DA | Composite FK `(school_id,school_membership_id,person_id)` → M06 SchoolMembership; status mora biti otvoren pri kreiranju. |
| `member_kind` | enum | DA | `ADULT`, `DEPENDENT`; nije role/permission. |
| `status` | enum | DA | `ACTIVE`, `ENDED`. |
| `effective_from` | LocalDate | DA | Poslovni datum. |
| `effective_until` | LocalDate? | NE | Obavezno u ENDED; ne pre from. |
| `end_reason_code` | Code64? | NE | Obavezno u ENDED. |
| `created_at`, `updated_at` | InstantUTC | DA | Server time. |
| `version` | Version | DA | CAS. |

Partial `UNIQUE(school_id,family_id,person_id) WHERE status='ACTIVE'`. Ista osoba može biti član više Family grupa u istoj školi, što podržava razdvojena domaćinstva; to samo po sebi ne daje međusobnu vidljivost.

### 2.3. `GuardianChildLink`

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id` | Identifier | DA | PK. |
| `school_id` | Identifier | DA | Tenant. |
| `guardian_person_id` | Identifier | DA | M06 Person sa otvorenim GUARDIAN membership-om. |
| `child_person_id` | Identifier | DA | M06 Person sa otvorenim PARTICIPANT membership-om; ne sme biti isti ID. |
| `guardian_school_membership_id` | Identifier | DA | Tenant-safe triple FK ka GUARDIAN membership-u iste osobe. |
| `child_school_membership_id` | Identifier | DA | Tenant-safe triple FK ka PARTICIPANT membership-u istog deteta. |
| `relationship_kind` | enum | DA | `PARENT`, `LEGAL_GUARDIAN`, `AUTHORIZED_CAREGIVER`, `OTHER_VERIFIED`. |
| `status` | enum | DA | `PENDING_VERIFICATION`, `ACTIVE`, `REJECTED`, `REVOKED`. |
| `requested_by_account_id` | Identifier | DA | Actor koji je inicirao. |
| `requested_at` | InstantUTC | DA | Server time. |
| `activated_at`, `rejected_at`, `revoked_at` | InstantUTC? | NE | Uslovno po statusu. |
| `decision_by_account_id` | Identifier? | NE | Obavezan za ACTIVE/REJECTED/REVOKED; school approver. |
| `decision_reason_code` | Code64? | NE | Obavezan za REJECTED/REVOKED. |
| `version` | Version | DA | CAS i authorization version. |

Partial `UNIQUE(school_id,guardian_person_id,child_person_id) WHERE status IN ('PENDING_VERIFICATION','ACTIVE')`.

### 2.4. `RelationshipVerificationRecord`

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id` | Identifier | DA | PK, immutable. |
| `school_id` | Identifier | DA | Tenant. |
| `link_kind` | enum | DA | `GUARDIAN_CHILD`, `PAYER_CHILD`. |
| `guardian_child_link_id` | Identifier? | NE | Popunjen iff `link_kind=GUARDIAN_CHILD`; tenant-safe FK. |
| `payer_child_link_id` | Identifier? | NE | Popunjen iff `link_kind=PAYER_CHILD`; tenant-safe FK. |
| `verification_method` | enum | DA | `SCHOOL_RECORD`, `IN_PERSON_DOCUMENT_CHECK`, `SIGNED_DECLARATION`, `MIGRATION_VERIFIED`. |
| `evidence_reference_digest` | char(64)? | NE | Keyed HMAC tenant-internog case reference-a; nikad broj dokumenta, ime ili hash niskoentropijskog PII-ja. |
| `verified_by_account_id` | Identifier | DA | Ovlašćeni school actor; ne nalog osobe čija se guardian/payer veza potvrđuje. |
| `verified_at` | InstantUTC | DA | Server time. |
| `policy_version` | Code64 | DA | Verzija procedure provere. |

CHECK zahteva tačno jedan link FK u skladu sa `link_kind`. Partial unique dozvoljava tačno jedan activation dokaz po guardian/payer linku. Za `IN_PERSON_DOCUMENT_CHECK` čuva se samo činjenica provere i opcioni keyed case digest; nema slike, broja ili običnog hash-a dokumenta u M07.

### 2.5. `PayerChildLink`

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id` | Identifier | DA | PK. |
| `school_id` | Identifier | DA | Tenant. |
| `payer_person_id` | Identifier | DA | Odrasla M06 Person; guardian link nije obavezan. |
| `child_person_id` | Identifier | DA | PARTICIPANT u istoj školi. |
| `payer_school_membership_id` | Identifier | DA | Tenant-safe triple FK ka ACTIVE `CONTACT` ili `GUARDIAN` membership-u payer osobe. |
| `child_school_membership_id` | Identifier | DA | Tenant-safe triple FK ka ACTIVE `PARTICIPANT` membership-u deteta. |
| `family_id` | Identifier | DA | Family u kojoj su oba lica ACTIVE ili payer ima posebno verifikovan sponsor osnov. |
| `basis_kind` | enum | DA | `FAMILY_ADULT`, `SPONSOR_VERIFIED`, `OTHER_VERIFIED`. |
| `status` | enum | DA | `PENDING_VERIFICATION`, `ACTIVE`, `REJECTED`, `REVOKED`. |
| `requested_by_account_id`, `requested_at` | Identifier, InstantUTC | DA | Inicijator/vreme. |
| `decision_by_account_id`, `decision_reason_code` | Identifier?, Code64? | NE | Uslovno kao Guardian link. |
| `activated_at`, `rejected_at`, `revoked_at` | InstantUTC? | NE | Uslovno. |
| `version` | Version | DA | CAS/authorization version. |

Partial `UNIQUE(school_id,payer_person_id,child_person_id) WHERE status IN ('PENDING_VERIFICATION','ACTIVE')`. Više različitih ACTIVE payer-a je dozvoljeno; M12 određuje da li i kako se deli obaveza.

### 2.6. `PrimaryGuardianContactDesignation`

| Polje | Tip | Obavezno | Pravilo |
|---|---|---:|---|
| `id` | Identifier | DA | PK, history row. |
| `school_id`, `child_person_id` | Identifier | DA | Tenant + dete. |
| `guardian_child_link_id` | Identifier | DA | Mora biti ACTIVE i za isto dete/školu. |
| `status` | enum | DA | `ACTIVE`, `SUPERSEDED`, `REVOKED`. |
| `designated_by_account_id`, `designated_at` | Identifier, InstantUTC | DA | School actor. |
| `ended_at`, `end_reason_code` | InstantUTC?, Code64? | NE | Obavezno za terminalne statuse. |
| `version` | Version | DA | CAS. |

Partial `UNIQUE(school_id,child_person_id) WHERE status='ACTIVE'`.

### 2.7. `PrimaryPayerDesignation`

Polja su ista kao §2.6, sa `payer_child_link_id` umesto guardian link-a. Link mora biti ACTIVE i za isto dete/školu. Tačno nula ili jedan ACTIVE primarni payer po detetu/školi; ostali ACTIVE payer linkovi ostaju dozvoljeni.

## 3. Poslovna pravila i invarijante

1. `Family`, članstvo, guardian veza, payer veza i primarnost su različite činjenice; nijedna se ne izvodi iz prezimena, email-a, adrese ili druge tabele.
2. Dete može pripadati više ACTIVE Family grupa; porodice ne vide jedna drugu samo zato što dele dete.
3. Dete može imati više ACTIVE guardian linkova i više ACTIVE payer linkova.
4. `relationship_kind` ne sadrži `PRIMARY`; primarnost je istorijski designation.
5. Guardian i payer link nastaju `PENDING_VERIFICATION`; ACTIVE i tačno jedan odgovarajući immutable verification record nastaju atomarno tek posle school approval-a.
6. Osoba čija se guardian/payer veza potvrđuje ne može sama potvrditi vezu. Approver mora imati M05 pravo i mora biti drugi UserAccount.
7. Payer link ne daje pristup rasporedu, prisustvu, dokumentima, zdravlju, komunikaciji ili profilu deteta; samo M12 finansijskim operacijama koje izričito prihvataju `PAYER_CHILD_LINK` basis.
8. Primarni guardian contact je samo redosled službene komunikacije škole; ne daje dodatne child permissions.
9. Primarni payer je default billing kontakt; ne određuje procenat odgovornosti. M12 može koristiti više ACTIVE payer linkova za podelu.
10. Opoziv link-a i svih designation-a koji ga referenciraju je jedna transakcija, uz version bump, audit, outbox i M05 invalidation signal.
11. Zahtev koji počne posle revoke commit-a ne može proći stale cache. High-risk write koji je počeo ranije ponavlja check neposredno pre commit-a.
12. Završetak M06 membership-a čini link neefektivnim odmah; application consumer zatvara/revokuje otvorene veze idempotentno, ali request-time resolver ne čeka consumer.
13. Arhiviranje Family je dozvoljeno samo kada nema ACTIVE FamilyMembership, guardian/payer linka koji je isključivo oslonjen na nju ili otvorene M12 obaveze/credit; application orchestration proverava portove bez M12→M07 ciklusa.
14. Guardian može inicirati zahtev za poziv drugog staratelja samo za dete za koje ima ACTIVE link; M02 invitation ostaje PENDING school approval i ne može sam kreirati M07 link.
15. Nema globalnog „family account-a“ ni deljenja kredencijala. Svaki odrasli koristi svoj M01 nalog.

### 3.1. Edge cases

| Slučaj | Ishod |
|---|---|
| Razvedeni roditelji imaju odvojene Family grupe i isto dete | Dozvoljeno; oba mogu imati zaseban guardian/payer link, bez međusobne vidljivosti. |
| Dva approver-a paralelno aktiviraju isti pending link | Jedan uspe; drugi 409 `M07_STALE_VERSION`; jedan verification record. |
| Aktivni primarni guardian je opozvan | Link i designation se opozivaju atomarno; primarni kontakt može privremeno biti nula, nikad stale. |
| Dva zahteva paralelno postavljaju različit primarni kontakt | Jedan konačni ACTIVE red; loser dobija 409; nema dva primarna. |
| Payer nije guardian | Dozvoljen ACTIVE payer posle zasebne provere i sa ACTIVE CONTACT membership-om; child podaci i dalje sakriveni. |
| Payer je u Family A, dete samo u Family B | 422 `M07_PAYER_BASIS_INVALID`, osim eksplicitnog verifikovanog sponsor procesa. |
| Guardian A traži drugog guardian-a B preko poznatog UUID-a | Safe 404, osim minimalnog school-approved contact flow-a; nema email/phone leak-a. |
| M06 link postane TERMINATED dok offline klijent ima stare podatke | Sledeći API/sync safe denied; lokalni zaštićeni cache se briše kroz M01/M19 revoke signal. |

## 4. Tenant & Security Guard

Obavezni lanac: M01 session → M03 school context → M05 permission → M07 subject-basis → resource action guard. Nijedan frontend workspace, Family membership, Organization, ugovor ili feature flag ne preskače server guard.

- Svaki FK između tenant tabela sadrži isti `school_id`; direktan DB upis cross-school para mora pasti.
- Nepostojeći, cross-tenant i child/guardian/payer kojeg actor nema pravo da zna daju isti 404 `M07_NOT_FOUND_SAFE`.
- Guardian query vraća samo sopstvene ACTIVE linkove i dozvoljene child projekcije. Ne vraća druge odrasle, njihove kontakte, Family strukturu ili payer detalje.
- Payer query vraća samo finansijsku child referencu potrebnu M12; bez profila, zdravlja, prisustva i dokumenata.
- School staff vidi samo ono za šta ima granularne M05 ključeve; child sensitive kategorije imaju dodatne guards.
- Support pristup ide isključivo kroz M05 grant; standard support dobija masked relation metadata, ne evidence sadržaj.
- Audit/event sadrži opaque ID-jeve, command/status/reason/policy version; ne sadrži imena, kontakte, dokumente ili slobodni opis odnosa.
- Sve M07 write operacije su online-only. Nema optimistic konačnog success-a, IndexedDB kopije family grafova ili offline poziva.

Minimalni permission ključevi: `school.families.view`, `school.families.manage`, `school.guardians.view`, `school.guardians.manage`, `school.guardians.primary_contact.manage`, `school.payers.view`, `school.payers.manage`, `school.payers.primary.manage`.

## 5. Lifecycle & transitions

### 5.1. Family

| From | Komanda | To | Guard |
|---|---|---|---|
| — | `FAM-01 CreateFamily` | ACTIVE | School active. |
| ACTIVE | `FAM-02 ArchiveFamily` | ARCHIVED | Nema §3.13 blokera; reason. |
| ARCHIVED | bilo koja transition | — | Terminalno u H0; nova grupa je novi ID. |

### 5.2. FamilyMembership

| From | Komanda | To | Guard |
|---|---|---|---|
| — | `FAM-03 AddFamilyMember` | ACTIVE | Family ACTIVE, tenant-safe Person. |
| ACTIVE | `FAM-04 EndFamilyMembership` | ENDED | Reason/date; ne sme ostaviti aktivan dependent link bez validne osnove. |
| ENDED | bilo šta | — | Terminalno; povratak je novi red. |

### 5.3. GuardianChildLink i PayerChildLink

| From | Komanda | To | Guard |
|---|---|---|---|
| — | `GRD-01` ili `PAY-01` | PENDING_VERIFICATION | Validni M06 tipovi; nema open duplikata. |
| PENDING_VERIFICATION | `GRD-02` ili `PAY-02` | ACTIVE | Distinct approver; odgovarajući verification record atomarno. |
| PENDING_VERIFICATION | `GRD-03` ili `PAY-03` | REJECTED | Reason obavezan. |
| PENDING_VERIFICATION/ACTIVE | `GRD-04` ili `PAY-04` | REVOKED | Reason; designation-i zatvoreni atomarno. |
| REJECTED/REVOKED | bilo šta | — | Terminalno; nova provera je novi ID. |

### 5.4. Primary designation

| From | Komanda | To | Guard |
|---|---|---|---|
| — | Designate | ACTIVE | Referencirani link ACTIVE; zaključan unique child ključ. |
| ACTIVE | Replace | SUPERSEDED | Stari i novi red menjaju se u istoj transakciji. |
| ACTIVE | Remove/revoke link | REVOKED | Reason obavezan. |
| SUPERSEDED/REVOKED | bilo šta | — | Terminalno. |

## 6. Error catalog

| Kod | HTTP | Značenje |
|---|---:|---|
| `M07_AUTHENTICATION_REQUIRED` | 401 | Nema M01 sesije. |
| `M07_CONTEXT_REQUIRED` | 409 | Nema validnog school context-a. |
| `M07_NOT_FOUND_SAFE` | 404 | Unknown/cross-tenant/skriven subject. |
| `M07_FORBIDDEN` | 403 | Poznati same-tenant resurs, nedostaje akcija. |
| `M07_VALIDATION_FAILED` | 422 | Polje, tip, datum ili reason ne prolazi. |
| `M07_FAMILY_ARCHIVE_BLOCKED` | 409 | Postoji aktivna veza/član/finansijski blocker. |
| `M07_FAMILY_MEMBERSHIP_EXISTS` | 409 | Otvoreno isto članstvo. |
| `M07_RELATIONSHIP_EXISTS` | 409 | Open guardian/payer prirodni ključ postoji. |
| `M07_RELATIONSHIP_INVALID_TRANSITION` | 409 | Lifecycle prelaz nije dozvoljen. |
| `M07_RELATIONSHIP_VERIFICATION_REQUIRED` | 422 | Aktivacija nema validan dokaz/policy. |
| `M07_SELF_VERIFICATION_FORBIDDEN` | 403 | Guardian/payer potvrđuje sebe. |
| `M07_MEMBERSHIP_TYPE_MISMATCH` | 422 | M06 tip ne odgovara guardian/child/payer ulozi. |
| `M07_PAYER_BASIS_INVALID` | 422 | Family/sponsor osnov nije potvrđen. |
| `M07_PRIMARY_LINK_NOT_ACTIVE` | 409 | Designation cilja neaktivan link. |
| `M07_PRIMARY_CONFLICT` | 409 | Concurrency/unique konflikt primarnosti. |
| `M07_STALE_VERSION` | 409 | expected version nije aktuelan. |
| `M07_CONCURRENT_AUTHORIZATION_CHANGE` | 409 | Link/context/permission promenjen pre commit-a. |
| `M07_IDEMPOTENCY_KEY_REUSED` | 409 | Isti key, drugi payload. |
| `M07_IDEMPOTENCY_IN_PROGRESS` | 409 | Isti command još traje; Retry-After. |
| `M07_DEPENDENCY_UNAVAILABLE` | 503 | Autoritativni M06/M12 guard nije dostupan; fail-closed. |

## 7. Idempotency, concurrency, API i događaji

Svaka write komanda zahteva stabilni `request_id: UUID`, koji je kanonski idempotency ključ i HTTP `Idempotency-Key`, plus `expected_version` kada target postoji. Scope je `(command_code, actor_account_id, school_id, request_id)`. Receipt, svi domain redovi, audit i outbox su jedna transakcija. Retry istog hash-a vraća isti rezultat; drugi hash je 409.

Lock redosled: `school_id` → child Person → Family → FamilyMembership → guardian/payer link → primary designation. Pri replace-u se zaključava unique `(school_id,child_person_id)` pre čitanja aktivnog reda. DB partial unique constraints su poslednja zaštita.

### 7.1. Komande

| ID | Komanda | Obavezni input | Rezultat |
|---|---|---|---|
| `FAM-01` | `CreateFamily` | school, optional label, IDs | ACTIVE Family. |
| `FAM-02` | `ArchiveFamily` | family, version, reason, IDs | ARCHIVED ili potpuni fail. |
| `FAM-03` | `AddFamilyMember` | family, person, kind, date, IDs | ACTIVE membership. |
| `FAM-04` | `EndFamilyMembership` | membership, version, date/reason, IDs | ENDED. |
| `GRD-01` | `RequestGuardianChildLink` | guardian/child, relationship kind, IDs | PENDING_VERIFICATION. |
| `GRD-02` | `VerifyAndActivateGuardianLink` | link/version, method, policy/optional evidence digest, request/correlation IDs | ACTIVE + immutable guardian verification. |
| `GRD-03` | `RejectGuardianLink` | link/version/reason, IDs | REJECTED. |
| `GRD-04` | `RevokeGuardianLink` | link/version/reason, IDs | REVOKED + designation close. |
| `GRD-05` | `DesignatePrimaryGuardianContact` | child/link, expected current ID/version, IDs | One ACTIVE designation. |
| `GRD-06` | `RemovePrimaryGuardianContact` | designation/version/reason, IDs | REVOKED. |
| `PAY-01` | `RequestPayerChildLink` | payer/child membership-i, family/basis, request/correlation IDs | PENDING_VERIFICATION. |
| `PAY-02` | `VerifyAndActivatePayerLink` | link/version, method, policy/evidence digest, request/correlation IDs | ACTIVE + immutable payer verification. |
| `PAY-03` | `RejectPayerLink` | link/version/reason, request/correlation IDs | REJECTED. |
| `PAY-04` | `RevokePayerLink` | link/version/reason, request/correlation IDs | REVOKED + payer designation close. |
| `PAY-05` | `DesignatePrimaryPayer` | child/payer link, expected current, IDs | One ACTIVE designation. |
| `PAY-06` | `RemovePrimaryPayer` | designation/version/reason, IDs | REVOKED. |

### 7.2. Read portovi

- `GuardianSubjectBasisPort.resolve(school_id, guardian_person_id, child_person_id)` → active link ID+version + guardian/child membership versions ili `NOT_FOUND`; bez PII.
- `PayerSubjectBasisPort.resolve(...)` → active payer link ID+version + payer/child membership versions + `FINANCE_ONLY`; bez guardian implikacije.
- `PrimaryContactPort.get(school_id, child_id)` → zero/one active guardian link.
- `EligiblePayersPort.listForBilling(school_id, child_id)` → ACTIVE payer link opaque ID-jevi; M12 određuje iznose/procente.

### 7.3. Outbox događaji

`GuardianLinkActivated|Revoked`, `PayerLinkActivated|Revoked`, `PrimaryGuardianChanged`, `PrimaryPayerChanged`, `FamilyArchived`; payload: `event_id`, `occurred_at`, `school_id`, relevant opaque IDs, new status/version, reason code. Nema imena, kontakta, evidence reference-a ili dokumenta. M14 može konzumirati događaj; M07 ne poziva M14.

## 8. Acceptance kriterijumi

1. Svih 52 scenarija iz [[02-M07-QA-I-TRACEABILITY]] prolazi bez preskakanja.
2. Nema `PRIMARY`/`ADDITIONAL` u `relationship_kind`; primarnost je zaseban istorijski entitet.
3. Guardian i payer prava su odvojena i negativni testovi potvrđuju da payer nema child-data pristup.
4. Više porodica/staratelja/payer-a po detetu radi bez međusobnog curenja.
5. Aktivacija guardian ili payer veze bez tačno jednog tipiziranog immutable verification record-a nije moguća.
6. U svakom trenutku postoji najviše jedan aktivni primarni kontakt i platioc po child/school; nula je dozvoljena.
7. Revoke je atomski, odmah efektivan i ne zavisi od outbox consumer-a/cache invalidacije.
8. Cross-tenant/sakriven target, list, count, cursor i search ne odaju postojanje podatka.
9. Sve mutacije su online-only i server-confirmed.
10. Repo implementacija se klasifikuje `PRESERVE|ADAPT|IMPLEMENT|REMOVE_CONFLICT|VERIFY_IN_REPO`; dokument nije dokaz postojećeg koda.
