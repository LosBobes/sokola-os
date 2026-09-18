---
tip: modulni-implementacioni-ugovor
modul-id: M02
naziv: Pozivnice i aktivacija pristupa
status: SPEC_CANDIDATE
datum: 2026-09-15
revizija: "1.5"
schema-zavisnosti: [M04, M06]
read-portovi: [M01, M03, M05, M07]
izlazni-portovi-za: [M01, M03, M05, M06, M07, M19, M20, M21, M28]
---

# M02 — Pozivnice i aktivacija pristupa

M02 uključuje `INV-11`, ne kreira guardian vezu tokom acceptance-a i koristi zaseban `PAYER_ACCESS` tok zasnovan na unapred ACTIVE M07 vezi.

## 1. Cilj, granice i autoritet

M02 je jedini redovni H0 put kojim odrasla osoba dobija prvi ili dodatni pristup konkretnoj školi u SOKOLA OS-u. Modul vodi poziv od pripreme i odobrenja, preko bezbedne isporuke i potvrde spoljnog identiteta, do atomskog nastanka tačno odobrenog školskog pristupa.

Kanonski rezultat je:

- SOKOLA MVP je `invite-only`; ne postoji javna self-registration forma koja pravi `Person`, `UserAccount`, članstvo ili ulogu;
- svaki poziv pripada tačno jednoj `School` tenant granici i tačno jednom unapred postojećem M06 `SchoolPersonProfile` zapisu odrasle `Person` u toj školi;
- poziv dokazuje odobrenu nameru pristupa, a ne identitet sam po sebi;
- provider-verifikovani `issuer + subject` je jedini ključ kojim M01 nalazi postojeći `AuthIdentity`/`UserAccount`;
- potvrđeni email claim sme se porediti sa adresom primaoca samo kao anti-forwarding dokaz za konkretan poziv; nikad se ne koristi za traženje, linkovanje ili spajanje `UserAccount`/`Person`;
- prvi `UserAccount` i prvi `AuthIdentity`, ako su potrebni, nastaju atomarno tek u završnoj transakciji prihvatanja, zajedno sa odobrenim pristupom;
- poziv traje tačno 168 sati od izdavanja, koristi se najviše jednom i ne može se oživeti;
- dete nema nalog, poziv ni autentifikacioni identitet u MVP-u;
- školski, role, guardian i ownership guardovi ponovo se proveravaju neposredno pre commit-a.

M02 propisuje poslovno ponašanje, logičke podatke, sigurnosne garancije, greške i dokaze. Stvarni repo bira framework, ORM, fizički API stil, queue, email provider, algoritam zaključavanja i izgled koda, pod uslovom da sve garancije ostanu dokazive.

### 1.1. Non-goals

M02 nije vlasnik:

- OIDC autentifikacije, `UserAccount`, `AuthIdentity`, `Session` ili provider registra — M01;
- tenant resolvera, aktivne škole, workspace-a i cross-tenant izolacije — M03;
- `School`/`Organization`, subscription-a, vlasničkog ugovora ili prenosa `PRIMARY_OWNER` statusa — M04;
- registra uloga, dozvola, delegabilnosti ili Support Access-a — M05;
- `Person`, `SchoolPersonProfile`, deduplikacije/merge-a, `SchoolMembership` lifecycle-a ili adult/account eligibility odluke — M06 (`PersonReferencePort`, `PersonEligibilityPort` i `MEM-01..05`);
- `GuardianChildLink`, primarnog kontakta, billing contact-a i child subject dozvola — M07;
- opšte komunikacije i kampanje — M13/M14; M02 emituje samo bezbedan zahtev za transakcionu isporuku poziva;
- prihvatanje ugovora/pravilnika, privacy notice acknowledgement i granularne foto/video odluke — M15/M17 digitalni onboarding. M02 ne naziva invitation acceptance pravnim consent-om i ne uslovljava atomsko kreiranje naloga opcionim saglasnostima; posle prve autentifikacije application routing može zahtevati zaseban onboarding pre ulaska u zaštićene poslovne površine.
- javne registracije škole, javne prijave na događaje, child login-a, lokalne lozinke, magic-link login-a, SMS/Viber/WhatsApp poziva, automatskog person merge-a ili automatskog prenosa vlasništva.

Invitation email nije dokaz da osoba ima pravo nad detetom, zaposlenjem ili školom. Poznavanje tokena, školskog koda, emaila ili imena nije zamena za provider dokaz i završne M03–M07 guardove.

## 2. Vlasništvo i portovi prema drugim modulima

| Ugovor | Vlasnik | Obavezna M02 upotreba |
|---|---|---|
| `VerifiedPrincipal`/proof, account+identity create/link guard | M01 | Tačan issuer/subject proof; bez email-linkinga; atomarno kreiranje prvog naloga i identiteta. |
| `School` tenant i `TenantExecutionContext` | M03/M04 | Admin komande su tenant-scoped; javni token samo interno razrešava jednu školu. |
| School status/setup/owner designation | M04 | Izdavanje i prihvatanje zavise od aktuelnog statusa i posebnog owner toka. |
| Role/permission policy i grant authority | M05 | Validacija ko sme da pozove, šta sme da dodeli i da li je snapshot još važeći. |
| `Person`, school profile, eligibility i `SchoolMembership` | M06 (`PersonReferencePort`, `PersonEligibilityPort`, `MEM-01..05`) | Composite profile/person dokaz mora pripadati tačnoj školi; target je odrasla/account-eligible osoba. |
| Guardian/payer odnos i approval | M07 | Poziv referencira unapred ACTIVE `GuardianChildLink` ili `PayerChildLink`; ne kreira odnos. |
| Transakciona email isporuka | M02 delivery adapter | At-least-once isporuka iste generacije tokena; M02 ne poziva M14. M14 sme konzumirati status događaj samo kada ga njegova objavljena notification-policy verzija eksplicitno mapira; odsustvo mape je deterministički no-op i ne stvara reverse dependency. |
| Audit/outbox/jobs/telemetry | M21 | Transakcioni trag, retry i expiry materijalizacija bez promene read-time autoriteta. |

Aktivni M04–M07 ugovori i ova tabela čine jedan strogo imenovan port ugovor. Svaka buduća promena mora kroz novi DCR atomarno izmeniti obe strane i pripadajuće contract testove. Implementacija ne sme izmišljati privremeni drugi izvor istine.

## 3. Kanonski tipovi

Tipovi iz M03 (`Identifier`, `UInt64`, `InstantUTC`, `Code64`, `DisplayString120`, `Nullable<T>`) važe i ovde. Dodatni logički tipovi su:

| Tip | Tačno značenje |
|---|---|
| `Boolean` | Isključivo `true` ili `false`; `null` nije dozvoljen. |
| `EmailAddress254` | ASCII email dužine `3..254`; nakon trimovanja spoljnog ASCII whitespace-a mora imati jedan validan mailbox oblik. Lokalni deo i domen porede se lowercase; domen se čuva u kanonskom IDNA A-label obliku. Ne primenjuju se Gmail dot pravila, uklanjanje `+tag` dela ni provider-specifična ekvivalencija. Ovo je delivery/anti-forwarding vrednost, ne identity ključ. |
| `EmailFingerprint` | HMAC-SHA-256 nad `EmailAddress254` sa verzionisanim tajnim ključem; koristi se za dedupe/pretragu bez izlaganja emaila. Nije reverzibilan i ne izlazi klijentu. |
| `Digest256` | Tačno 256-bitni digest, prikazan lowercase hex ili binarno; poređenje je constant-time gde sadrži security vrednost. |
| `SecretToken` | Kriptografski slučajna vrednost sa najmanje 256 bita entropije; URL-safe kodiranje; postoji u plaintext-u samo pri generisanju, kontrolisanoj dekripciji radi isporuke i u linku primaoca. |
| `EncryptedPII` | AEAD ciphertext; ključ je van poslovne baze, ima key version i autentifikovani context. Plaintext se ne pojavljuje u query rezultatima, logu ili auditu. |
| `CanonicalGrantSpec` | Verzionski kanonski JSON/value object: `role_key`, sortirani permission ključevi ako su eksplicitni, jedan scope i policy version. Jednaka semantika daje jednake bajtove i isti hash. |
| `ReasonCode` | `Code64` iz zatvorenog registra. Slobodan tekst ne može zameniti obavezni reason code. |

Sva vremena daje server. Rok je otvoren na početku, zatvoren na kraju: poziv je upotrebljiv kada `issued_at <= now < expires_at`; na `now == expires_at` više ne važi.

## 4. Entiteti, polja i relacije

### 4.1. `Invitation`

`Invitation` je tenant-scoped odobrenje jedne namere pristupa. Ne predstavlja nalog, membership, role assignment ili guardian link.

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | `Identifier` | NE | PK, immutable, nepredvidiv. |
| `school_id` | `Identifier` | NE | FK → `School.id`; immutable; tenant poziva. |
| `kind` | enum | NE | `INITIAL_OWNER`, `OWNER_ACCESS`, `STAFF_ACCESS`, `GUARDIAN_ACCESS`, `PAYER_ACCESS`. |
| `target_school_person_profile_id` | `Identifier` | NE | M06 `SchoolPersonProfile.id`; immutable; obavezni tenant-scoped target. |
| `target_person_id` | `Identifier` | NE | M06 `Person.id`; immutable; sa prethodna dva polja čini composite tenant-safe referencu. Nikad child/account-ineligible osoba. |
| `recipient_email_ciphertext` | `EncryptedPII` | NE | Adresa isporuke; čita se samo za purpose-limited delivery/admin prikaz. |
| `recipient_email_fingerprint` | `EmailFingerprint` | NE | Dedupe i anti-forwarding poređenje; nije auth/link ključ. |
| `grant_spec` | `CanonicalGrantSpec` | NE | Tačno odobrena uloga/dozvole/scope; immutable nakon izdavanja. |
| `grant_spec_hash` | `Digest256` | NE | Hash kanonskog snapshot-a; payload/idempotency i race dokaz. |
| `grant_authority_version` | `UInt64` | NE | M05/M04 revizija odobrenja pri izdavanju; ponovo se validira pri acceptance-u. |
| `guardian_child_link_id` | `Nullable<Identifier>` | DA | Obavezno samo za `GUARDIAN_ACCESS`; link mora biti za target osobu i istu školu. `PENDING_VERIFICATION` je dozvoljen samo dok je poziv `AWAITING_APPROVAL`; pre izdavanja mora biti M07 `ACTIVE`. |
| `payer_child_link_id` | `Nullable<Identifier>` | DA | Obavezno samo za `PAYER_ACCESS`; M07 link mora biti ACTIVE, za target osobu i istu školu. |
| `ownership_designation_ref` | `Nullable<Identifier>` | DA | Obavezno za `INITIAL_OWNER`/`OWNER_ACCESS`; M04 referenca, ne M02 owner master. |
| `request_source` | enum | NE | `SCHOOL_ACTOR`, `PRIMARY_GUARDIAN`, `PLATFORM_ONBOARDING`. |
| `requested_by_actor_ref` | `Identifier` | NE | Server-resolved actor/service ref; nije client person ID. |
| `approved_by_actor_ref` | `Nullable<Identifier>` | DA | Obavezno pre izdavanja ako je `request_source=PRIMARY_GUARDIAN`. |
| `status` | enum | NE | `DRAFT`, `AWAITING_APPROVAL`, `ACTIVE`, `ACCEPTED`, `EXPIRED`, `REVOKED`, `SUPERSEDED`. |
| `token_digest` | `Nullable<Digest256>` | DA | Obavezno za `ACTIVE` i terminalni izdat poziv; `null` dok nije izdat. Globalno unique. |
| `token_key_version` | `Nullable<UInt64>` | DA | Obavezno iff `token_digest != null`; omogućava rotaciju ključa. |
| `issued_at` | `Nullable<InstantUTC>` | DA | Obavezno iff poziv je ikada izdat. |
| `expires_at` | `Nullable<InstantUTC>` | DA | Tačno `issued_at + 168h`; obavezno iff izdat. |
| `accepted_at` | `Nullable<InstantUTC>` | DA | Obavezno iff `status=ACCEPTED`. |
| `accepted_by_user_account_id` | `Nullable<Identifier>` | DA | M01 nalog; obavezno iff `status=ACCEPTED`; mora pripadati `target_person_id`. |
| `revoked_at` | `Nullable<InstantUTC>` | DA | Obavezno iff `status=REVOKED`. |
| `revoked_by_actor_ref` | `Nullable<Identifier>` | DA | Obavezno iff `status=REVOKED`. |
| `revocation_reason_code` | `Nullable<ReasonCode>` | DA | Obavezno iff `status=REVOKED`; zatvoren registar. |
| `superseded_at` | `Nullable<InstantUTC>` | DA | Obavezno iff `status=SUPERSEDED`. |
| `superseded_by_invitation_id` | `Nullable<Identifier>` | DA | Obavezno iff `status=SUPERSEDED`; ista škola i ista poslovna namera. |
| `replaces_invitation_id` | `Nullable<Identifier>` | DA | Novi poziv može referencirati prethodni terminalni/aktivni poziv iste škole i namere. |
| `created_at`, `updated_at` | `InstantUTC` | NE | Server vreme. |
| `version` | `UInt64` | NE | Početno `1`; raste tačno za 1 pri svakoj promeni. |

Obavezna ograničenja:

1. `expires_at = issued_at + 168 sati` bez lokalnog kalendarskog zaokruživanja.
2. `DRAFT` i `AWAITING_APPROVAL` nemaju token/issued/expiry/accepted/revoked/superseded polja.
3. `ACTIVE` ima token/issued/expiry i nema terminalna polja.
4. `ACCEPTED`, `EXPIRED`, `REVOKED`, `SUPERSEDED` su terminalni.
5. Tačno jedan subject link je popunjen za `GUARDIAN_ACCESS` ili `PAYER_ACCESS`; za owner/staff oba su `null`. `GUARDIAN_ACCESS` koristi samo `guardian_child_link_id`, a `PAYER_ACCESS` samo `payer_child_link_id`.
6. Ownership referenca je popunjena samo za owner vrste.
7. Partial unique sprečava više od jednog neterminalnog poziva za isti `(school_id, target_school_person_profile_id, kind, grant_spec_hash, subject_scope_fingerprint)` u statusu `DRAFT|AWAITING_APPROVAL|ACTIVE`.
8. `token_digest` je globalno unique za sve pozive, uključujući terminalne.
9. Aktivni poziv se ne menja. Ispravka emaila, osobe, vrste ili grant-a pravi novi poziv i superseduje stari.
10. Composite FK `(school_id, target_school_person_profile_id, target_person_id)` referencira M06 unique `(school_id, id, person_id)`. Sam FK na globalni `Person.id` nije dovoljan.

`subject_scope_fingerprint` je kanonski hash child/branch/group/ownership reference dela `grant_spec`; može biti fizička kolona ili dokazivo ekvivalentan unique izraz.

Maskirani email je response projekcija izvedena u memoriji iz purpose-limited dekripcije `recipient_email_ciphertext`; ne čuva se kao treća kopija adrese. Projekcija otkriva najviše prvi Unicode grapheme lokalnog dela, fiksni `***` i bezbedno skraćen domen, nikada pun lokalni deo. Ne upisuje se u audit, outbox, receipt ili telemetry.

### 4.2. `InvitationAcceptanceAttempt`

Kratkotrajni pokušaj omogućava provider round-trip bez trajnog `PENDING_LINK UserAccount` naloga.

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | `Identifier` | NE | PK, nepredvidiv. |
| `invitation_id` | `Identifier` | NE | FK → `Invitation.id`. |
| `school_id` | `Identifier` | NE | Kopija tenant dimenzije; composite FK ka istom `Invitation`. |
| `browser_binding_digest` | `Digest256` | NE | Veže pokušaj za HttpOnly acceptance cookie/browser transakciju. |
| `status` | enum | NE | `STARTED`, `IDENTITY_VERIFIED`, `COMPLETED`, `FAILED`, `CANCELLED`, `EXPIRED`. |
| `started_at` | `InstantUTC` | NE | Server vreme. |
| `expires_at` | `InstantUTC` | NE | Tačno `started_at + 15 min`; ne produžava se callback-om. |
| `principal_proof_ref` | `Nullable<Identifier>` | DA | Jednokratna M01 proof referenca; obavezna samo u `IDENTITY_VERIFIED`; raw claim/token se ne čuva. |
| `verified_user_account_id` | `Nullable<Identifier>` | DA | Popunjen samo ako issuer+subject već pripada aktivnom nalogu. |
| `verified_at` | `Nullable<InstantUTC>` | DA | Obavezno u `IDENTITY_VERIFIED` i `COMPLETED`. |
| `completed_at` | `Nullable<InstantUTC>` | DA | Obavezno iff `COMPLETED`. |
| `failure_reason_code` | `Nullable<ReasonCode>` | DA | Obavezno iff `FAILED`; ne izlazi javno ako otkriva stanje. |
| `created_at`, `updated_at` | `InstantUTC` | NE | Server vreme. |
| `version` | `UInt64` | NE | Optimistic concurrency. |

Pokušaj ne sadrži email, ime, child podatak, provider token, issuer ili subject. `principal_proof_ref` važi najviše pet minuta i najkasnije do `InvitationAcceptanceAttempt.expires_at`; M01 ga može potrošiti samo jednom za ovu invitation/purpose/correlation kombinaciju.

Više pokušaja može postojati istorijski, ali najviše pet neterminalnih pokušaja po pozivu u jednom satu; svaki ima zasebnu browser vezu. Samo jedan može završiti jer acceptance transakcija zaključava `Invitation` i unique pristupne ciljeve.

### 4.3. `InvitationDeliveryAttempt`

| Polje | Tip | Null | Pravilo |
|---|---|---:|---|
| `id` | `Identifier` | NE | PK. |
| `invitation_id`, `school_id` | `Identifier` | NE | Tenant-safe FK. |
| `attempt_no` | `UInt64` | NE | Počinje od `1`; unique `(invitation_id, attempt_no)`. |
| `status` | enum | NE | `QUEUED`, `SUBMITTING`, `SUBMITTED`, `RETRYABLE_FAILED`, `TERMINAL_FAILED`. |
| `provider_message_ref_digest` | `Nullable<Digest256>` | DA | Samo hash/bezbedna pseudoreferenca, nikad provider payload. |
| `last_failure_category` | `Nullable<ReasonCode>` | DA | Bez emaila/provider tajne. |
| `next_retry_at` | `Nullable<InstantUTC>` | DA | Samo za retryable stanje. |
| `submitted_at` | `Nullable<InstantUTC>` | DA | Provider je prihvatio zahtev; ne znači delivery/read. |
| `lease_token_hash` | `Nullable<Digest256>` | DA | Non-null samo u `SUBMITTING`; raw lease se ne čuva. |
| `lease_until` | `Nullable<InstantUTC>` | DA | Non-null samo u `SUBMITTING`; kraći od M21 max runtime-a. |
| `fencing_token` | `UInt64` | NE | Monotono raste pri svakom claim/reclaim-u. |
| `created_at`, `updated_at` | `InstantUTC` | NE | Server vreme. |
| `version` | `UInt64` | NE | Concurrency zaštita workera. |

`QUEUED` nema provider/failure/submitted/lease rezultat. `SUBMITTING` ima samo aktivni lease par. `SUBMITTED` zahteva `submitted_at`, provider ref ako ga provider vraća i nema lease/failure/retry. `RETRYABLE_FAILED` zahteva safe failure+`next_retry_at`, a `TERMINAL_FAILED` safe failure bez retry vremena; oba nemaju lease/submitted vreme. DB CHECK sprovodi matricu.

M21 `invitation.delivery_dispatch` pod invitation row lock-om claim-uje najstariji dospeli pokušaj, postavlja `SUBMITTING`, lease i novi fencing token, pa poziva provider van duge DB transakcije sa stabilnim provider idempotency ključem izvedenim iz `(invitation_id, token_generation)`. Callback/rezultat može commit-ovati samo uz aktuelni fence. Potvrđen submission u istoj transakciji daje `SUBMITTED` i §4.4 tombstone; transient ili nejasan timeout daje `RETRYABLE_FAILED`. Kada retry dospe, pod istim invitation lock-om nastaje sledeći `attempt_no` u `QUEUED`, najviše pet provider pokušaja ukupno sa backoff-om 1m, 5m, 30m i 2h. Peti neuspeh, ne-ACTIVE invitation ili `database_now>=min(delete_after,expires_at)` daje `TERMINAL_FAILED` bez novog pokušaja i bez produženja secret roka.

Nejasan provider timeout može proizvesti dva ista emaila samo ako provider ne poštuje idempotency ključ. To je dozvoljena at-least-once isporuka i ne može proizvesti dupli pristup jer token i acceptance ostaju jednokratni. Stale worker posle lease expiry-ja ne može upisati status niti obrisati secret.

### 4.4. `InvitationTokenDeliverySecret` (precizirano 03.09.2026, A01 — deterministička tombstone semantika)

Ovo je purpose-limited tehnički zapis, ne poslovni master:

- `invitation_id: Identifier`, PK/FK;
- `token_ciphertext: Nullable<EncryptedPII>`, kad postoji AEAD sa `invitation_id`, `school_id` i `token_key_version` kao authenticated context;
- `encryption_key_ref: Nullable<Code64>`, ključ nije u bazi;
- `created_at: InstantUTC`, `delete_after: InstantUTC`, `deleted_at: Nullable<InstantUTC>`;
- `delete_after <= created_at + 24h`.

`delete_after` je stroga granica upotrebljivosti, ne približan cleanup datum. Kada je `database_now >= delete_after`, ni delivery worker ni administrativni read ne smeju tražiti dekripciju; servis i KMS policy fail-closed odbijaju korišćenje čak i ako maintenance još nije materijalizovao tombstone. Katalogizovani M21 posao `invitation.expiry_scan` materijalizuje dospele tombstone zapise u prvom uspešnom petnaestominutnom prozoru. Kašnjenje duže od 15 minuta od `delete_after` emituje PII-free security alert i incident, ali nikada ne produžava pravo dekripcije.

**Tačno jedan od dva stanja, nikad mešano:**

1. `deleted_at IS NULL` → `token_ciphertext` i `encryption_key_ref` su OBA non-null (aktivan, još neisporučen secret);
2. `deleted_at IS NOT NULL` → `token_ciphertext` i `encryption_key_ref` su OBA null (obrisan tombstone).

Brisanje je jedna atomska tranzicija koja u ISTOJ transakciji postavlja `token_ciphertext=null`, `encryption_key_ref=null`, `deleted_at=commit_at`. Ne postoji treće stanje niti formulacija "marker ili brisanje" kao dve alternative — obrisani red UVEK ostaje kao tombstone red (isti `invitation_id` PK), nikad hard-delete od strane ove komande.

**Isti determinizam za sve okidače brisanja:** `INV-11` (revoke-all), pojedinačan `INV-06` revoke, `INV-05` replace/supersede, read-time expiry, i potvrđen provider submission SVI koriste identičnu tranziciju iznad — nema posebne semantike po okidaču.

Plaintext token nikada nije u poslovnoj tabeli, auditu, telemetry-ju, exception-u, URL access logu ili analytics-u. Ni ciphertext ni `encryption_key_ref` nisu u auditu, receipt-u, outbox payload-u, logu ili telemetry-ju — samo u ovoj tabeli. `Invitation.token_digest` (odvojeno polje, ne ovaj secret) ostaje trajno radi verifikacije i istorije.

### 4.5. `InvitationCommandReceipt`

Može koristiti zajedničku M00 receipt tabelu. Semantika je obavezna:

- unique `(actor_or_public_attempt_scope, command_id, request_id)`;
- `canonical_payload_hash`, rezultat/ref, `created_at`, `expires_at`;
- receipt za terminalni acceptance čuva se najmanje 30 dana; admin mutation receipt najmanje 30 dana; javni start-attempt najmanje do isteka poziva plus 24 sata;
- isti ključ/drugi payload je `IDEMPOTENCY_KEY_REUSED`.

## 5. Vrste poziva i tačan pristup

| `kind` | Ko pokreće | Obavezni scope | Poseban guard |
|---|---|---|---|
| `INITIAL_OWNER` | Platform onboarding actor | jedna škola u pripremi + M04 pending primary-owner designation | Škola nema aktivnog primary owner-a; obična staff komanda ne može izdati. |
| `OWNER_ACCESS` | Aktuelni primary owner uz svežu M01 autentifikaciju | jedna škola + M04 owner designation | Dodaje owner pristup; ne prenosi primary owner status. Transfer ostaje M04 posebna atomska komanda. |
| `STAFF_ACCESS` | Owner/manager/admin samo u granicama M05 delegabilnosti | school ili jedan dozvoljeni branch/group scope | Actor ne može dodeliti pravo koje nema ili koje nije delegabilno. Platform admin nije cilj ove vrste. |
| `GUARDIAN_ACCESS` | Škola ili aktivni primary guardian kao zahtev | tačno jedno dete iste škole | Primary guardian zahtev ide u `AWAITING_APPROVAL`; škola odobrava pre slanja. Ne daje billing-contact status automatski. |
| `PAYER_ACCESS` | Ovlašćena škola | tačno jedno dete iz ACTIVE M07 `PayerChildLink` | Dodeljuje M05 `PAYER` + isključivo finance-related CHILD grantove; ne daje guardian/child-data prava. |

Jedan roditelj sa više dece dobija zaseban guardian access grant po detetu. UI može grupisati više poziva, ali baza i acceptance ne smeju napraviti jedan implicitni cross-child scope.

## 6. Poslovna pravila i invarijante

### 6.1. Kreiranje i izdavanje

1. Svaki poziv zahteva unapred postojeći `(school_id, target_school_person_profile_id, target_person_id)` koji `PersonReferencePort.resolveForInvitation` potvrđuje kao jednu M06 composite referencu. Email-only kreiranje osobe/profila je zabranjeno.
2. M06 `PersonEligibilityPort.check(target_person_id)` mora potvrditi da je target account-eligible odrasla osoba (`birth_date` postoji, uzrast ≥18 i status nije `MERGED`). Dete ili osoba samo sa PARTICIPANT kontekstom ne može biti cilj; nepoznat `birth_date` vraća `NOT_ELIGIBLE`, ne grešku.
3. Admin komanda koristi M03 `TenantExecutionContext`; client `school_id` nije autoritet.
4. M05/M04 validiraju da actor sme dodeliti tačan `grant_spec`, uključujući owner i custom permission ograničenja.
5. Primary guardian može samo zahtevati poziv dodatnom guardian-u za dete za koje ima ACTIVE guardian link i ACTIVE primary-contact designation. Zahtev može referencirati primaočev M07 `PENDING_VERIFICATION` link, ali ne šalje email i ne može biti izdat dok škola zasebno ne verifikuje i aktivira taj link.
6. `DRAFT` se može menjati uz `expected_version`. `AWAITING_APPROVAL` menja samo ovlašćena škola kroz approve/reject. Posle izdavanja security payload je immutable.
7. Izdavanje u jednoj DB transakciji generiše `SecretToken`, upisuje digest, kratkotrajni ciphertext za delivery, `ACTIVE`, `issued_at`, `expires_at`, audit, outbox i receipt.
8. Email delivery se izvršava posle commit-a. Provider neuspeh ne poništava istoriju; UI prikazuje delivery status odvojeno od invitation statusa.
9. Eksplicitno „Pošalji ponovo” uvek pravi novi `Invitation` i novi token. Ako je stari `ACTIVE`, prelazi u `SUPERSEDED` u istoj transakciji.
10. Novi poziv za pogrešnu adresu ne menja email aktivnog poziva; superseduje ga.

### 6.2. Sadržaj i privatnost emaila

Email sadrži samo zvanični naziv škole, generički naziv vrste pristupa, UTC/lokalno razumljiv rok, bezbedan link i uputstvo za neočekivan poziv. Ne sadrži child ime, datum rođenja, grupu, prisustvo, finansije, dokumente, druge škole, kompletnu permission listu, provider podatke ili lozinku.

Početna token stranica može prikazati naziv škole, generičku ulogu, maskirani email i rok. Child ime se ne prikazuje pre provider provere i potvrde da principal odgovara pozivu. Posle te provere M07 vraća purpose-limited child display; ne vraćaju se drugi child podaci.

### 6.3. Prihvatanje

1. Otvaranje tokena radi constant-time digest lookup i vraća enumeration-safe X02 stanje za nepoznat, istekao, opozvan, supersedovan ili accepted poziv.
2. Token ruta odmah zamenjuje sirovi token nepredvidivim HttpOnly/Secure/SameSite acceptance cookie-em i čisti URL kroz redirect/replace-state ekvivalent pre učitavanja trećih strana. `Referrer-Policy: no-referrer`; stranica nema analytics/third-party resurse dok je token u URL-u.
3. `INV-07 StartAcceptance` pravi 15-minutni `InvitationAcceptanceAttempt`; ne pravi `Person`, `UserAccount`, membership, role ili guardian odnos.
4. M01 provider callback vraća server-internal proof. Provider mora biti u aktivnom registru; issuer i subject se obrađuju po M01.
5. Provider mora dati verifikovan email claim čija M02 `EmailAddress254` kanonizacija daje isti fingerprint kao recipient. Ovo je dokaz da pozvani kontroliše adresu, ne ključ za account lookup.
6. M01 zatim nalazi postojeći nalog isključivo preko `issuer+subject`.
7. Ako postojeći nalog pripada istoj `target_person_id`, acceptance može nastaviti. Ako pripada drugoj Person, odbija se bez merge-a.
8. Ako issuer+subject nije linkovan, a target Person već ima aktivni/suspendovani nalog, M02 ne dodaje novi identity samo na osnovu emaila i ne pravi drugi nalog; vraća kontrolisani `INVITATION_ACCOUNT_LINK_REQUIRED`.
9. Ako issuer+subject nije linkovan i target Person nema nalog, M01 kreira jedan `UserAccount` i prvi `AuthIdentity` unutar završne atomske transakcije, tek nakon svih guardova.
10. Korisnik mora eksplicitno izabrati „Prihvati poziv”. Provider login sam po sebi ne aktivira pristup.
11. Završna transakcija zaključava invitation, target SchoolPersonProfile/Person/account i relevantne M04–M07 ciljeve; ponovo proverava token/attempt/rok/status/email proof/account/composite profile/Person/School/grant authority i owner/guardian/payer subject basis.
12. Za `INITIAL_OWNER`, `OWNER_ACCESS` i `STAFF_ACCESS` acceptance reuse-uje odgovarajući ACTIVE M06 `STAFF` membership iste profile/person/škole ili atomarno orkestrira `MEM-01` pa `MEM-02` za novu STAFF epizodu. Za `GUARDIAN_ACCESS` mora reuse-ovati tačno ACTIVE `GUARDIAN` membership koji referencira M07 `GuardianChildLink`; za `PAYER_ACCESS` tačno ACTIVE `CONTACT` ili `GUARDIAN` membership koji referencira M07 `PayerChildLink`. Guardian/payer acceptance nikad ne kreira niti aktivira membership, `GuardianChildLink` ili `PayerChildLink`.
13. U istoj transakciji nastaju ili se reuse-uju tačno jedan nalog/identity, dozvoljeni membership rezultat i M05 role/grant, zatim `Invitation=ACCEPTED`, attempt `COMPLETED`, receipt, audit i outbox. Subject linkovi moraju ostati ACTIVE neposredno pre commit-a. Guardian dobija `GUARDIAN` sa `GUARDIAN_CHILD_LINK`; payer dobija `PAYER` sa `PAYER_CHILD_LINK` i isključivo M12 finance-related permission-e.
14. Neuspeh bilo kog koraka vraća celu transakciju. Nema orphan naloga, praznog membership-a, role bez membership-a, guardian prava bez veze ili accepted poziva bez pristupa.
15. Ako je potpuno isti pristup nastao drugom validnom transakcijom između izdavanja i prihvatanja, acceptance završava `ACCEPTED` kao bezbedan no-op nad pristupom, vraća `access_already_present=true` i ne duplira zapise.
16. Uspeh ne menja tiho `SessionTenantContext` u drugim tabovima. Vraća M03 context suggestion; ulazak/switch škole ide kroz TEN-01 i njegov `context_version` ugovor.

### 6.4. Expiry, revoke i replacement

- Read-time guard je autoritet: `database_now >= expires_at` znači expired čak i ako M21 `invitation.expiry_scan` još nije upisao `EXPIRED`.
- Prvi ovlašćeni read/mutation posle isteka može atomski materijalizovati `EXPIRED`; `invitation.expiry_scan` je idempotentna maintenance optimizacija i jedini published M02 scheduled job.
- Ručni revoke traži `expected_version` i obavezni reason code; važi odmah po commit-u.
- Revoke/supersede/expiry invalidira sve neterminalne acceptance attempts i briše preostali delivery ciphertext.
- Terminalni poziv se nikad ne vraća u `ACTIVE`; pravi se novi red i novi token.
- Accepted poziv se ne resenduje i ne superseduje samo radi ponovnog slanja. Promena postojećeg pristupa je M05/M06/M07 lifecycle, ne novi acceptance replay.

### 6.5. Abuse zaštita

- invalid/public token lookup: najviše 20 pokušaja po keyed-hash IP signalu u 10 minuta;
- start attempt: najviše 5 neterminalnih pokušaja po pozivu u 60 minuta;
- identity mismatch: najviše 5 po pozivu u 24 sata, zatim acceptance je privremeno zaključan 30 minuta;
- eksplicitni replacement/resend: najviše 3 nova poziva po `(school, target person, purpose)` u 24 sata; četvrti zahteva owner override, obavezan reason i audit;
- limiti ne potvrđuju da email, osoba, nalog ili škola postoji; `Retry-After` se vraća gde transport podržava;
- keyed-hash mrežni signal je minimizovan i čuva se najviše 24 sata, osim ako M17 odobri drugi security retention.

### 6.6. Granični slučajevi

Najmanje sledeći slučajevi imaju determinističan ishod:

1. Dva paralelna acceptance zahteva: tačno jedan commit; drugi dobija isti receipt/uspeh ili generički already-used rezultat bez drugog pristupa.
2. Rok ističe između provider callback-a i klika „Prihvati”: završna provera odbija; nalog/pristup ne nastaju.
3. Škola se deaktivira tokom callback-a: finalni commit se odbija; druge škole naloga ostaju netaknute.
4. Inviter izgubi pravo pre acceptance-a: `grant_authority_version`/M05 recheck blokira poziv; potreban je novi odobreni poziv.
5. Role policy se promeni: stari snapshot nikad ne dobija nova prava; ako više nije validan, acceptance se blokira `INVITATION_ACCESS_CHANGED`.
6. Link je prosleđen osobi sa drugim verified emailom: mismatch, bez target/child detalja i bez account linka.
7. Dve osobe imaju isti email claim kod različitih subject-a: ne spajaju se; samo issuer+subject određuje nalog.
8. Target Person već ima nalog, ali novi subject nije linkovan: nema automatskog linka; kontrolisani account-security tok je potreban.
9. Target Person je duplikat druge Person: M02 ne merge-uje; M06 `MRG-01 MergePersons` rešava pre novog poziva (ažurirano 04.09.2026).
10. Provider timeout posle otvaranja linka: attempt ostaje bez verified proof-a ili prelazi u `FAILED`; retry ne kreira nalog.
11. Email provider timeout posle mogućeg submission-a: ista generacija može stići dvaput, ali acceptance ostaje jednokratna.
12. `invitation.expiry_scan` kasni: expired link je i dalje odbijen tačno na `expires_at`, a delivery secret nije moguće dekriptovati od `delete_after`.
13. Admin ispravi email aktivnog poziva: update je odbijen; replacement daje novi token, stari odmah prestaje da važi.
14. Guardian poziv za dete druge škole: tenant-scoped lookup daje safe 404/422 bez child detalja.
15. Primarni guardian pokuša da zaobiđe school approval: email/token se ne generišu u `AWAITING_APPROVAL`.
16. Običan staff invite cilja owner/platform admin ulogu: odbijen pre izdavanja.
17. Acceptance na jednom tabu ne prebacuje drugi tab iz škole A u školu B.
18. Retry nakon DB timeout-a koristi isti request ID i ne duplira Person/account/membership/role/grant; M07 subject link se samo proverava, ne kreira.

## 7. Lifecycle i state machine

### 7.1. `Invitation`

| Iz | Komanda/uslov | U | Dozvoljeno | Obavezna posledica |
|---|---|---|---:|---|
| ne postoji | INV-01 school/platform draft | `DRAFT` | DA | Bez tokena i emaila. |
| ne postoji | INV-01 primary guardian request | `AWAITING_APPROVAL` | DA | Bez tokena i emaila; child scope zaključan. |
| `DRAFT` | INV-02 update | `DRAFT` | DA | `expected_version`; samo neizdata polja. |
| `DRAFT` | INV-04 issue | `ACTIVE` | DA | Token/digest, 168h expiry, ciphertext, audit/outbox. |
| `DRAFT` | INV-06 revoke/discard | `REVOKED` | DA | Reason obavezan. |
| `AWAITING_APPROVAL` | INV-03 approve+issue | `ACTIVE` | DA | School actor, token/delivery tek sada. |
| `AWAITING_APPROVAL` | INV-03 reject | `REVOKED` | DA | `APPROVAL_REJECTED` reason; bez tokena. |
| `ACTIVE` | INV-09 atomic accept | `ACCEPTED` | DA | Tačno odobren pristup; single-use. |
| `ACTIVE` | `database_now >= expires_at` / `invitation.expiry_scan` | `EXPIRED` | DA | Attempt invalidation; nema pristupa. |
| `ACTIVE` | INV-06 revoke | `REVOKED` | DA | Odmah nevažeći token; reason/audit. |
| `ACTIVE` | INV-05 replace | `SUPERSEDED` | DA | Novi poziv/token u istoj transakciji. |
| `ACCEPTED` | bilo šta | — | NE | Terminalan; access lifecycle je u vlasničkom modulu. |
| `EXPIRED`/`REVOKED` | INV-05 replacement | ostaje terminalan | DA | Novi `Invitation` referencira stari; stari se ne oživljava. |
| `SUPERSEDED` | bilo šta | — | NE | Terminalan. |

„Poslat” i „na čekanju” nisu dodatni lifecycle statusi. To su UI projekcije kombinacije `Invitation.status=ACTIVE` i poslednjeg `InvitationDeliveryAttempt.status`. „Poziv nije poslat” je `DRAFT` ili delivery stanje, ne paralelni enum.

### 7.2. `InvitationAcceptanceAttempt`

| Iz | Događaj | U | Posledica |
|---|---|---|---|
| ne postoji | INV-07 validan token | `STARTED` | 15-min browser-bound pokušaj. |
| `STARTED` | INV-08 validan M01 proof + email match | `IDENTITY_VERIFIED` | Jednokratni proof ref, bez pristupa. |
| `STARTED` | invalid/mismatch/provider terminal | `FAILED` | Bez naloga/pristupa; reason interno. |
| `STARTED`/`IDENTITY_VERIFIED` | korisnik odustane | `CANCELLED` | Invitation ostaje `ACTIVE` ako i dalje važi. |
| `STARTED`/`IDENTITY_VERIFIED` | `now >= expires_at` | `EXPIRED` | Novi pokušaj zahteva ponovno otvaranje validnog invitation linka. |
| `IDENTITY_VERIFIED` | INV-09 uspešan commit | `COMPLETED` | Invitation postaje `ACCEPTED` u istoj transakciji. |
| `IDENTITY_VERIFIED` | finalni guard padne | `FAILED` | Nema parcijalnog pristupa. |
| terminalan | bilo šta | — | Nikad se ne oživljava. |

## 8. Komande i query ugovor

| ID | Naziv | Autoritet | Ključni input | Rezultat |
|---|---|---|---|---|
| `INV-01` | `CreateInvitationDraftOrRequest` | M03+M05; primary guardian kroz M07; platform onboarding | kind, target school-person-profile/person, email, grant/scope, request_id | `DRAFT` ili `AWAITING_APPROVAL`. |
| `INV-02` | `UpdateInvitationDraft` | Isti school actor koji i dalje ima grant authority | invitation_id, patch, expected_version, request_id | Izmenjen `DRAFT`; nema tokena. |
| `INV-03` | `ApproveOrRejectGuardianInvitation` | Ovlašćena škola, ne guardian | invitation_id, decision, expected_version, reason za reject, request_id | `ACTIVE`+delivery ili `REVOKED`. |
| `INV-04` | `IssueInvitation` | Ovlašćeni school/platform actor | draft_id, expected_version, request_id | `ACTIVE`, expiry, queued delivery. |
| `INV-05` | `ReplaceInvitation` | Ovlašćeni actor uz novu punu proveru | old_id, novi email/grant, reason, expected_version, request_id | Novi `ACTIVE`; stari active → `SUPERSEDED`. |
| `INV-06` | `RevokeInvitation` | Pošiljalac samo ako još ima pravo ili viši school actor | id, expected_version, reason, request_id | `REVOKED`; token odmah nevažeći. |
| `INV-07` | `StartAcceptance` | Javni bearer token + abuse guard | token, browser binding, request_id | `STARTED` attempt + safe preview. |
| `INV-08` | `CompleteInvitationIdentityProof` | M01 callback/internal port | attempt_id, M01 proof, request_id | `IDENTITY_VERIFIED` ili safe failure. |
| `INV-09` | `AcceptInvitation` | Browser-bound verified attempt + eksplicitna potvrda | attempt_id, expected invitation/version, request_id | Atomski pristup + `ACCEPTED`. |
| `INV-10` | `CancelAcceptance` | Browser-bound attempt | attempt_id, request_id | `CANCELLED`, bez pristupa. |
| `INV-11` | `RevokeAllOpenSchoolInvitations` | Isključivo M04 `SCH-05` internal call, ista lokalna transakcija | `school_id`, `reason_code=SCHOOL_DEACTIVATED`, `source_school_version`, `request_id`, `correlation_id` | Svi `DRAFT`/`AWAITING_APPROVAL`/`ACTIVE` pozivi škole → `REVOKED`, version+1; aktivni attempts terminalni `FAILED`/`CANCELLED`; delivery secret obrisan; summary receipt + individual audit refs. |
| `INV-Q01` | `GetPublicInvitationPreview` | Validan raw token ili attempt cookie | token/attempt ref | Minimalna pre-auth projekcija; child nikad. |
| `INV-Q02` | `ListSchoolInvitations` | M03 context + M05 permission | filter/status/cursor | Tenant-scoped lista; maskiran email, bez tokena. |
| `INV-Q03` | `GetInvitationAdminDetail` | Isti tenant + permission | invitation_id | Status, grant, delivery, audit refs; nema raw tokena. |

Svaka mutation komanda ima kanonski payload hash, stabilan `request_id UUID`, `correlation_id` i, kada menja postojeći red, `expected_version`. REST `Idempotency-Key` mora biti UUID jednak `request_id`; drugi transport prenosi isti semantički ključ. Query lista koristi server-side tenant filter pre count/cursor/page operacija.

INV-03 approve, INV-04 issue i INV-05 replacement vraćaju poslovni uspeh tek posle durable DB commit-a: prvi create odgovor je 201, a transition odgovor 200, sa `invitation.status=ACTIVE` i odvojenim `delivery_status=QUEUED|SUBMITTED|FAILED`. `QUEUED` je uspešan commit, nije HTTP greška niti tvrdnja da je email isporučen. Kasniji provider terminalni neuspeh ažurira samo delivery attempt; ne menja invitation status i ne generiše drugi token bez eksplicitnog INV-05.

## 9. Tenant & Security Guard

1. `Invitation.school_id` je obavezan i immutable; tenant veze koriste M03 composite FK/equivalent.
2. INV-01–06 i INV-Q02/Q03 zahtevaju M01 session, M03 `TenantExecutionContext`, aktuelne M06 `MembershipFactsPort` činjenice, M05 permission i subject/owner guard. Guardian koristi M07 `GuardianSubjectBasisPort`, payer `PayerSubjectBasisPort`.
3. Client-provided `school_id`, target/child ID, route, slug, school code ili email nikad nisu autoritet. Repository lookup je `WHERE school_id=active_school AND id=...` ili semantički ekvivalent.
4. Javni token lookup je jedini izuzetak od prethodno izabranog tenant konteksta: digest interno razrešava tačno jedan poziv i vraća samo purpose-limited public projection. Ne otvara tenant repository opšteg tipa.
5. Cross-tenant admin ID vraća safe 404; token failure vraća generičko X02 stanje bez razlikovanja nonexistent/expired/revoked/accepted/superseded.
6. Email je encrypted PII; fingerprint koristi tajni verzionisani HMAC, ne običan SHA emaila. Token digest koristi odvojeni tajni pepper/HMAC key od email fingerprint-a.
7. Raw token se nikad ne upisuje u access log. Reverse proxy/app rediguje `/prihvati-poziv/*`; analytics i error reporting ne dobijaju path segment.
8. Acceptance cookie je `Secure`, `HttpOnly`, `SameSite=Lax` ili stroži, kratkog 15-min TTL-a, purpose-bound i ne koristi se kao M01 session.
9. Child ime/podatak nije u emailu, pre-auth preview-u, logu, telemetry-ju ili javnoj grešci. Posle proof-a vraća se samo M07 dozvoljena minimalna projekcija ciljanog deteta.
10. High-risk acceptance ponavlja M01 authorization/proof, M03 school status, M05 grant version, M06 Person eligibility i odgovarajući M07 guardian/payer subject basis neposredno pre commit-a.
11. Outbox ubrzava email/cache/UI, ali poziv status i read-time expiry u autoritativnoj bazi određuju acceptance.
12. Nema globalne školske pretrage poziva, emaila ili osoba. Platform support nema implicitni pristup; svaki dozvoljeni pristup mora koristiti aktivni M05 Support Access ugovor.

## 10. Error catalog

Javni endpoint koristi neutralnu poruku i ne izlaže interne reason detalje. Ovlašćeni admin unutar tačnog tenant-a može dobiti precizniji kod gde je to bezbedno.

| Kod | HTTP | Kada | Bezbedna posledica |
|---|---:|---|---|
| `INVITATION_NOT_FOUND_SAFE` | 404 | Admin ID nije u aktivnoj školi ili ne postoji. | Ne razlikuje cross-tenant od nepostojećeg. |
| `INVITATION_NOT_VALID` | 410 | Javni token nonexistent/expired/revoked/accepted/superseded. | Jedna X02 poruka; bez škole/osobe/razloga. |
| `INVITATION_INVALID_TRANSITION` | 409 | Komanda nije dozvoljena iz statusa. | Bez izmene. |
| `INVITATION_STALE_VERSION` | 409 | `expected_version` se ne poklapa. | Učitati aktuelno stanje. |
| `INVITATION_DUPLICATE_ACTIVE` | 409 | Već postoji neterminalni poziv iste namere. | Vraća bezbednu ref postojećeg samo ovlašćenom actor-u. |
| `INVITATION_EMAIL_INVALID` | 422 | Email ne prolazi M02 canonicalizer. | Ne upisuje draft. |
| `INVITATION_TARGET_INELIGIBLE` | 422 | Target nije adult/account-eligible. | Bez kreiranja naloga. |
| `INVITATION_GRANT_NOT_ALLOWED` | 403 | Actor ne sme dodeliti grant/owner scope. | Bez drafta/izdavanja. |
| `INVITATION_APPROVAL_REQUIRED` | 409 | Guardian zahtev nije odobrila škola. | Nema tokena/emaila. |
| `INVITATION_CHILD_SCOPE_INVALID` | 422 | Child/guardian odnos nije validan u istoj školi. | Ovlašćenom actor-u generički scope problem; cross-tenant je 404. |
| `INVITATION_SCHOOL_UNAVAILABLE` | 409 | Škola ne dozvoljava issue/accept u aktuelnom statusu. | Druge škole nisu pogođene. |
| `INVITATION_ACCESS_CHANGED` | 409 | Grant policy/authority nije više ista/važeća. | Potreban nov poziv; nema starog proširenja prava. |
| `INVITATION_ACCESS_ALREADY_ACTIVE` | 409 | Create/issue otkriva da isti pristup već postoji. | Ne pravi poziv; acceptance race koristi idempotent no-op success. |
| `INVITATION_IDENTITY_MISMATCH` | 403 | Verified email ne odgovara recipient-u ili nalog pripada drugoj Person. | Bez target/child detalja i bez linka. |
| `INVITATION_ACCOUNT_LINK_REQUIRED` | 409 | Target Person već ima nalog, a novi subject nije linkovan. | Nema email auto-linka ni drugog naloga. |
| `INVITATION_ACCOUNT_INACTIVE` | 403 | Existing account je suspended/disabled/merged-retired. | Generičko uputstvo; status razlog se ne otkriva javno. |
| `INVITATION_ATTEMPT_INVALID` | 400 | Browser binding/state/callback se ne poklapa ili je replay. | Bez pristupa; pokušaj terminalan gde je primenljivo. |
| `INVITATION_ATTEMPT_EXPIRED` | 410 | Prošlo 15 min ili invitation više ne važi. | Ponovno otvaranje važećeg linka; bez reuse proof-a. |
| `INVITATION_PROOF_EXPIRED` | 401 | M01 proof istekao/potrošen. | Nova autentifikacija; bez parcijalnog upisa. |
| `INVITATION_DELIVERY_UNAVAILABLE` | 503 | Adapter/secret decryption/provider terminalno nije dostupan. | Poziv/pristup se ne lažno označava isporučenim; admin može replace. |
| `INVITATION_RATE_LIMITED` | 429 | Abuse/resend limit. | `Retry-After`; bez enumeration-a. |
| `IDEMPOTENCY_KEY_REUSED` | 409 | Isti request ID, drugi payload. | Prvi rezultat ostaje autoritet. |
| `TENANT_RESOURCE_NOT_FOUND_SAFE` | 404 | M03 cross-tenant resource. | Bez curenja. |
| `TENANT_AUTHORITY_UNAVAILABLE` | 503 | M03–M07 autoritet nije pouzdano dostupan. | Fail-closed; bez poslovnog upisa. |
| `INTERNAL_SAFE` | 500 | Neočekivan neuspeh. | Correlation ID; bez tokena/emaila/child PII. |

## 11. Idempotency, concurrency i transakcije

### 11.1. Idempotency ključevi

| Tok | Idempotency scope | Dodatna poslovna zaštita |
|---|---|---|
| INV-01 create | `(actor, school, INV-01, request_id)` | Partial unique neterminalne namere. |
| INV-02/03/04/06 | `(actor, school, command, request_id)` | `expected_version` na invitation redu. |
| INV-05 replace | `(actor, school, old_invitation_id, request_id)` | Lock starog + partial unique novog; stari i novi menjaju se atomarno. |
| INV-07 start | `(invitation_digest_scope, browser_binding, request_id)` | Token digest + abuse limits; ne koristi raw token kao receipt ključ. |
| INV-08 proof | `(attempt_id, INV-08, provider_state/request_id)` | M01 callback state i proof su jednokratni. |
| INV-09 accept | `(attempt_id, INV-09, request_id)` | Lock invitation/person/account/access ciljeva + terminal status. |
| `invitation.delivery_dispatch` | `(invitation_id, attempt_no)` + stabilan provider key po token generation-u | Invitation lock + lease/CAS/fence; najviše pet provider pokušaja; timeout sme dati dupli email, ne dupli grant. |
| `invitation.expiry_scan` — invitation | `(invitation_id, expires_at)` | `WHERE status=ACTIVE AND expires_at<=database_now`; idempotent. |
| `invitation.expiry_scan` — delivery secret | `(invitation_id, delete_after)` | Lock reda; ako je `deleted_at IS NULL AND delete_after<=database_now`, primeni jedinu §4.4 tombstone tranziciju. |

Raw `invitation_token` nije idempotency ključ u audit/receipt tabeli. Koristi se samo za constant-time digest verifikaciju. Receipt nikad ne sadrži token, email ili provider proof.

### 11.2. Locking i redosled

Implementacija koristi row lock, compare-and-swap/serializable transakciju ili dokazivo ekvivalentan mehanizam. Logički redosled zaključavanja je:

1. `Invitation`;
2. `(school_id, target_school_person_profile_id, target_person_id)` pa postojeći M01 `UserAccount`/`AuthIdentity` kandidati;
3. `SchoolMembership`/role grant/guardian-or-payer-basis/owner cilj po stabilnom ID redosledu; za guardian/payer se zaključava membership koji već referencira subject link, a ne pravi novi;
4. receipt i outbox.

Isti redosled važi u svim M02 tokovima kako bi se izbegao deadlock. Retry deadlock-a je ograničen i koristi isti request ID.

### 11.3. Atomske granice

- Issue/approve: status, token digest, encrypted delivery secret, delivery attempt, audit, outbox i receipt su jedna DB transakcija.
- Replace: novi poziv + novi token + stari `SUPERSEDED` + invalidacija attempts + audit/outbox/receipt su jedna DB transakcija.
- Revoke: status + attempt invalidation + secret tombstone tranzicija (§4.4 deterministička semantika) + audit/outbox/receipt su jedna DB transakcija.

### 11.4. RevokeAllOpenSchoolInvitations (`INV-11`)

**Ovo je jedini normativni tekst za `INV-11`.** `INV-11` znači isključivo `RevokeAllOpenSchoolInvitations` — nikad `CreateSchoolOwnerInvitation` ili bilo koja komanda za kreiranje.

**Autoritet:** isključivo M04 `SCH-05` internal call, u istoj lokalnoj transakciji modularnog monolita. Nema javnog HTTP endpoint-a; nijedan school ili platform actor ga ne poziva direktno.

**Input:** `school_id UUID`, `reason_code=SCHOOL_DEACTIVATED`, `source_school_version UInt64` (M04 School verzija u trenutku poziva), `request_id UUID`, `correlation_id UUID`.

**Idempotency scope:** `(school_id, source_school_version, request_id)`. Isti trojac vraća isti count/refs bez ijedne nove tranzicije, audit ili outbox zapisa — bezbedan retry posle mrežnog tajmauta.

**Lock redosled:** `School` red (već zaključan od strane pozivajuće `SCH-05` transakcije) → svi otvoreni `Invitation` redovi te škole sortirani po stabilnom `id` (sprečava deadlock sa paralelnim `INV-09`) → povezani `InvitationAcceptanceAttempt`/`InvitationTokenDeliverySecret` redovi.

**Target:** svaki `Invitation` red škole u statusu `DRAFT`, `AWAITING_APPROVAL` ili `ACTIVE`. `ACCEPTED`, `EXPIRED`, `REVOKED` i `SUPERSEDED` pozivi se NE diraju — već su terminalni.

**Rezultat (u istoj transakciji):**
- svaki target red prelazi u `REVOKED`, `version+1`, `revoke_reason_code=SCHOOL_DEACTIVATED`;
- svaki povezan aktivan `InvitationAcceptanceAttempt` prelazi u terminalni `FAILED` ili `CANCELLED` (interni, dosledan izbor — `CANCELLED` kada attempt još nije video M01 proof, `FAILED` kada je proof već bio u toku);
- svaki preostali `InvitationTokenDeliverySecret` prolazi kroz istu §4.4 tombstone tranziciju (ciphertext/key_ref→null, deleted_at=commit_at);
- svaki pojedinačno revokovani poziv dobija SVOJ interni audit događaj (`invitation.revoked`) — ti pojedinačni audit ID-evi NISU deo spoljnog receipt objekta, samo su upisani u audit log.

**Spoljni receipt sadrži isključivo:** jedan opaque `command_receipt_id`, `revoked_count`, `attempts_invalidated_count`. Bez liste invitation ID-eva, bez target Person ID-eva, bez emailova, bez pojedinačnih audit referenci.

**Race ishod naspram paralelnog `INV-09 AcceptInvitation` (oba redosleda dokazana):**
- ako `SCH-05`/`INV-11` commit-uje PRVI: `INV-09` koji sledi ne pronalazi `ACTIVE` red (već je `REVOKED`) — pristup se NE pravi, `INV-09` vraća generičku "poziv ne važi" grešku;
- ako `INV-09` commit-uje PRVI: taj konkretan `Invitation` je već `ACCEPTED` (terminalan) PRE nego što `INV-11` stigne do njega u sortiranom redosledu — `INV-11` ga preskače (nije više u `DRAFT/AWAITING_APPROVAL/ACTIVE` skupu). Pristup ostaje validan, ali `SCH-05` nastavlja svoju transakciju i deaktivira školu — pristup toj školi postaje neupotrebljiv kroz M03 `TEN-04`/tenant status guard, NE kroz retroaktivno poništavanje već prihvaćenog poziva.

**Privatnost:** rezultat van platformskog operation context-a (npr. ako bi školski actor mogao da vidi ishod) ne otkriva recipient email, `target_person_id` ili listu pojedinačnih poziva — isključivo agregatni broj po statusu.

**Nula-open slučaj:** ako škola nema nijedan `DRAFT/AWAITING_APPROVAL/ACTIVE` poziv u trenutku poziva, `INV-11` je no-op koji ipak vraća uspešan receipt sa `revoked_count=0` — ne greška.
- Accept: account/identity (ako novi), membership, role/grant, invitation/attempt status, receipt, audit i outbox su jedna poslovna transakcija modularnog monolita. M07 guardian/payer link se samo ponovo proverava i ostaje M07-owned. Za `kind=INITIAL_OWNER` ista transakcija atomarno kreira i M04 `SchoolPrimaryOwnerTerm`, ne samo M05 `RoleAssignment`.
- Email provider poziv je posle commit-a; nikad se ne drži DB transakcija otvorena tokom mrežnog poziva.
- Ako repo fizički razdvaja baze tako da poslednja acceptance garancija nije moguća, Claude Code ne sme improvizovati eventual-consistency aktivaciju; mora prijaviti arhitektonski konflikt i implementirati jednu lokalnu authoritative transaction boundary ili dokazivo ekvivalentnu rezervaciju/compensation koja nikad ne izlaže parcijalan pristup.

## 12. Audit, outbox, telemetry i jobs

Audit događaji:

- `invitation.draft_created`;
- `invitation.approval_requested`;
- `invitation.approved` / `invitation.rejected`;
- `invitation.issued`;
- `invitation.delivery_submitted` / `invitation.delivery_failed`;
- `invitation.replaced`;
- `invitation.revoked`;
- `invitation.expired`;
- `invitation.acceptance_started`;
- `invitation.identity_verified` / `invitation.identity_rejected`;
- `invitation.accepted`;
- `invitation.acceptance_failed`.

Audit nosi `school_id`, pseudoreference actor/target/account, invitation ID, kind, grant hash, from/to status, reason code, correlation i vreme. Ne sadrži raw/hashed email koji se može koristiti van purpose-a, token/digest, provider subject/claim, child ime, browser binding, IP ili delivery ciphertext.

Obavezni outbox događaji:

- `invitation.delivery_requested.v1` — payload ima masked/template podatke i `delivery_secret_ref`, ne plaintext token;
- `invitation.status_changed.v1`;
- `access.activated_from_invitation.v1`;
- `identity.authorization_invalidated` samo kada M01/M05 posledica zahteva version bump.

Consumer dedupe koristi `event_id`; email delivery je at-least-once. M02 ima tačno dva published scheduled ključa: `invitation.delivery_dispatch` za due provider pokušaje i `invitation.expiry_scan` koji u odvojenim bounded stranicama (a) materijalizuje dospele invitation expiry tranzicije i invalidira neterminalne acceptance attempt-e i (b) materijalizuje §4.4 tombstone za svaki delivery secret sa `delete_after<=database_now`. Oba toka koriste stabilan row-lock redosled i gore navedene child business ključeve; retry ne pravi novu poslovnu posledicu. Ne postoji zaseban secret-cleanup runtime alias. Security-critical token/acceptance failure telemetry se ne sample-uje, ali nema PII.

## 13. UI X01/X02, navigacija i pristupačnost

Postojeće površine ostaju:

- X01 „Prihvati poziv”;
- X02 „Poziv ne važi”;
- A03 „Škola i prvi poziv”;
- postojeći deo M02 „Ljudi i pozivi”; nema nove top-level MVP površine.

X01 koraci su: bezbedan pregled → provider potvrda → pregled tačnog pristupa → eksplicitno prihvatanje → M03 izbor/otvaranje škole. Provider interakcije van SOKOLA ne računaju se u tri-klika ugovor. Child detalj nije na prvom koraku.

Obavezna stanja: loading, valid pre-auth preview, provider redirect, wrong identity, approval pending, expired attempt, invalid/expired/revoked/superseded/accepted token kroz jedan X02, school unavailable, grant changed, provider unavailable, acceptance in progress, network timeout with retry, accepted success i safe context suggestion.

Javna prijava može imati „Prvi put sam ovde”, ali ta radnja sme isključivo da objasni invite-only tok ili zatraži otvaranje postojećeg poziva. Ne prikazuje formu ime/prezime/email/lozinka koja kreira nalog. „Kod škole” je tenant locator/onboarding pomoć, nikad aktivacioni dokaz.

## 14. Migracija i brownfield pravila

Claude Code u završnoj predaji prvo mapira postojeći repo:

1. legacy invitation statuse mapira deterministički: `nacrt→DRAFT`; `poslat|na čekanju|aktivan→ACTIVE`; `prihvaćen|iskorišćen→ACCEPTED`; `istekao→EXPIRED`; `opozvan→REVOKED`; `zamenjen→SUPERSEDED`;
2. aktivni legacy poziv bez dokazivog composite `(school_id, target_school_person_profile_id, target_person_id)`, grant snapshot-a, token digest-a ili validnog expiry-ja ne aktivira se automatski; ide u exception report i bezbedno se revoke-uje/superseduje; profile se ne bira pretragom emaila/imena;
3. plaintext token se migrira samo u digest ako je još validan, zatim plaintext briše; ako dokaz brisanja nije moguć, token se rotira replacement-om;
4. legacy `PENDING_LINK UserAccount` se ne pretvara automatski u nalog; M01 pravilo ostaje autoritet;
5. email podudaranje ne backfill-uje account/person veze;
6. accepted poziv bez dokazivog tačnog membership/role/guardian rezultata ide u exception report; ne kreira se širi grant;
7. public registration endpoint koji može kreirati nalog bez validnog M02 attempt-a se gasi/ograničava pre realnog pilota;
8. migracija i backfill su idempotentni, sa backup-om i forward recovery-jem; rollback ne vraća raw token niti oživljava terminalni poziv.

## 15. Acceptance kriterijumi i Definition of Done

M02 je dokumentaciono kompletan kada:

1. svih osam obaveznih oblasti ovog ugovora postoji: cilj/granice, entiteti/polja, pravila/edge cases, tenant/security, lifecycle, errors, idempotency/concurrency i acceptance;
2. M01 email/linking i account atomarnost nisu prekršeni;
3. M03 School tenant/context i safe 404/403 pravila su propagirana;
4. M04–M07 portovi imaju jednoznačne pre/post uslove bez duplog source of truth-a;
5. svaki status/prelaz, komanda, greška i audit/outbox događaj ima determinističnu semantiku;
6. QA dokument mapira svaki scenario na normativni paragraf;
7. svi aktivni ugovori koriste isti entity/status/idempotency/route/UI/config model bez paralelnog source of truth-a;
8. ne tvrdi se da je stvarni kod implementiran dok repo nije pregledan.

M02 je implementaciono gotov tek kada svih 84 automatizovanih unit, integration, security, race, migration i e2e scenarija iz `02-M02-QA-I-TRACEABILITY.md` prolaze nad najmanje dve škole, dva odrasla naloga sa istim email claim-om ali različitim subject-om, jednim target Person bez naloga, jednim sa postojećim nalogom, guardian scope-om za dva deteta i kontrolisanim provider/email failure fixture-ima. Nijedan test ne koristi realne podatke dece.
