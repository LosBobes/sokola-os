---
tip: qa-i-traceability
modul-id: M02
status: SPEC_CANDIDATE
datum: 2026-09-16
revizija: "1.5"
schema-zavisnosti: [M04, M06]
obavezni-scenariji: 84
---

# M02 — QA i traceability

## 1. Deterministični acceptance scenariji

Svaki scenario koristi sintetičke podatke. Osnovni fixture ima škole `S-A` i `S-B`; odrasle osobe `P-A1`, `P-A2`, `P-B1`; decu `C-A1`, `C-A2`, `C-B1`; postojeći nalog `U-A1` vezan za `P-A1`; dva OIDC principal-a sa istim verified email claim-om, ali različitim `(issuer, subject)` parovima; aktivne/suspendovane role i kontrolisani email/provider adapter.

| ID | Setup / radnja | Očekivani dokaz |
|---|---|---|
| M02-QA-001 | Ovlašćeni actor u `S-A` kreira staff draft za account-eligible `P-A2`. | Jedan `DRAFT`, bez tokena/delivery-ja/naloga; tenant i grant snapshot su tačni. |
| M02-QA-002 | Isti INV-01 request se pošalje dvaput sa istim payload-om. | Isti receipt i isti draft; nema drugog reda. |
| M02-QA-003 | Isti INV-01 request ID se ponovi sa drugim emailom. | 409 `IDEMPOTENCY_KEY_REUSED`; prvi draft nepromenjen. |
| M02-QA-004 | Dva paralelna actor-a kreiraju istu neterminalnu nameru. | Tačno jedan poziv; drugi 409 `INVITATION_DUPLICATE_ACTIVE`. |
| M02-QA-005 | INV-01 cilja dete/`PARTICIPANT` `C-A1`. | 422 `INVITATION_TARGET_INELIGIBLE`; nema drafta/naloga. |
| M02-QA-006 | INV-01 dobije nevalidan/duži od 254 email. | 422 `INVITATION_EMAIL_INVALID`; nema PII parcijalnog reda. |
| M02-QA-007 | Email `User+tag@example.invalid` se uporedi sa `user+tag@example.invalid`. | Isti fingerprint; `+tag` nije uklonjen. |
| M02-QA-008 | Email `user@example.invalid` se uporedi sa `u.ser@example.invalid`. | Različit fingerprint; nema provider-specifične dot ekvivalencije. |
| M02-QA-009 | Primary guardian `P-A1` zahteva dodatnog guardian-a za `C-A1`, uz M07 link primaoca u `PENDING_VERIFICATION`. | `AWAITING_APPROVAL`; nema tokena, expiry-ja ni emaila. |
| M02-QA-010 | Isti guardian pokuša INV-04 pre school approval-a. | 409 `INVITATION_APPROVAL_REQUIRED`; stanje ostaje isto. |
| M02-QA-011 | Škola prvo M07-verifikuje link primaoca, zatim odobri M02-QA-009. | M07 link je ACTIVE; M02 issue transakcija daje `ACTIVE`, digest/ciphertext, 168h expiry, audit/outbox/delivery attempt; M02 nije kreirao link. |
| M02-QA-012 | Škola odbije guardian zahtev uz razlog. | `REVOKED`, `APPROVAL_REJECTED`; token nikad nije generisan. |
| M02-QA-013 | Guardian zahteva poziv za `C-B1` iz druge škole. | 404 `INVITATION_NOT_FOUND_SAFE`, bez child imena ili potvrde da dete postoji. |
| M02-QA-014 | Dodatni guardian, koji nije primary contact, pokreće novi guardian invite. | 403 `INVITATION_GRANT_NOT_ALLOWED`; nema zahteva. |
| M02-QA-015 | Actor bez delegabilnog permission-a pravi staff invite. | 403; grant/poziv ne nastaju. |
| M02-QA-016 | Običan staff invite cilja owner ili platform-admin ulogu. | 403 `INVITATION_GRANT_NOT_ALLOWED`; mora poseban owner tok. |
| M02-QA-017 | `INITIAL_OWNER` se izda školi koja već ima primary owner-a. | 409; nema drugog initial-owner poziva. |
| M02-QA-018 | `OWNER_ACCESS` prođe bez sveže step-up autentifikacije primary owner-a. | 401 `RBAC_STEP_UP_REQUIRED`; nema tokena ni promene ownership-a. |
| M02-QA-019 | `OWNER_ACCESS` je prihvaćen. | Owner pristup može nastati; `PRIMARY_OWNER` se ne prenosi. |
| M02-QA-020 | DRAFT se izmeni sa tačnim expected version-om. | Polja i version se menjaju; token i dalje `null`. |
| M02-QA-021 | Dva paralelna update-a koriste istu version. | Jedan uspeh; drugi 409 `INVITATION_STALE_VERSION`. |
| M02-QA-022 | Pokuša se menjanje emaila/grant-a na `ACTIVE` pozivu. | 409 invalid transition; potreban replacement. |
| M02-QA-023 | DRAFT se izda u trenutku `T0`. | `expires_at=T0+168h`; token ima ≥256 bita entropije, digest globalno unique. |
| M02-QA-024 | DB fail pre commit-a issue transakcije. | Nema ACTIVE poziva, ciphertext-a, delivery reda, audit success-a ili outbox-a. |
| M02-QA-025 | `invitation.delivery_dispatch` claim-uje red, adapter je spor, lease istekne, a stari worker kasno vrati success. | Samo aktuelni fencing token može commit-ovati; stale worker ne upisuje `SUBMITTED` i ne briše secret. Poziv ostaje durable ACTIVE, bez lažnog delivery success-a. |
| M02-QA-026 | Provider prihvati submission, odgovor se izgubi, a retry sa stabilnim provider idempotency ključem stigne dvaput. | Provider koji podržava ključ šalje jednom; inače su moguća dva ista emaila. U oba slučaja postoje jedan poziv, najviše pet attempt redova i najviše jedan pristup. |
| M02-QA-027 | Provider potvrdi submission sa aktuelnim fence-om; kontrolni slučaj iscrpi pet transient pokušaja. | Prvi tok atomarno daje `SUBMITTED`+secret tombstone, digest i ACTIVE invitation ostaju; kontrolni tok daje `TERMINAL_FAILED` bez šestog pokušaja ili novog tokena. |
| M02-QA-028 | Neisporučeni secret dostigne `delete_after`; maintenance kasni 14 min, zatim radi, a drugi worker/retry radi paralelno. | Od tačnog `delete_after` nijedan read/delivery/KMS zahtev ne može dekriptovati secret; `invitation.expiry_scan` u prvom uspešnom prozoru pravi tačno jedan §4.4 tombstone. Oba workera dobijaju isti rezultat; kašnjenje preko 15 min bi dalo PII-free alert/incident. |
| M02-QA-029 | Admin izabere „Pošalji ponovo” za ACTIVE poziv. | Novi red/token; stari `SUPERSEDED`; promena je atomska. |
| M02-QA-030 | Stari token iz M02-QA-029 se otvori posle commit-a. | X02/410 `INVITATION_NOT_VALID`; nema race prozora. |
| M02-QA-031 | Replacement za EXPIRED/REVOKED poziv. | Novi ACTIVE referencira stari; stari terminalni status se ne menja. |
| M02-QA-032 | Pokuša se resend ACCEPTED poziva. | 409 invalid transition; postojeći pristup se ne menja. |
| M02-QA-033 | Četvrti replacement iste namere u 24h bez override-a. | 429; sa owner override-om zahteva reason/audit. |
| M02-QA-034 | Random/nepostojeći token se otvori. | Isti X02/410 oblik kao expired/revoked/accepted; bez timing/enumeration razlike izvan tolerancije. |
| M02-QA-035 | (a) Validan token se otvori prvi put; (b) isti `(token_digest_scope, browser_binding, request_id)` se ponovi; (c) isti token se otvori iz drugog browser_binding-a; (d) korak (c) se ponovi još 4 puta (ukupno 6. neterminalni pokušaj istog poziva u 60 min); (e) tokom cele sekvence proveriti URL/history/cache/proxy/error/analytics log. | (a) Nov 15-min `STARTED` attempt; URL odmah očišćen (replace, ne push); HttpOnly/Secure cookie; `Cache-Control: no-store`; nema naloga/pristupa. (b) Vraća ISTI attempt, ne pravi novi. (c) Pravi DRUGI, zaseban attempt (isti poziv sme imati više paralelnih pokušaja dok je ACTIVE). (d) Šesti neterminalni pokušaj vraća 429, rate limit iz M02 §6.5. (e) Raw token se ne pojavljuje ni na jednom od ovih mesta ni u jednom koraku. |
| M02-QA-036 | Inspect proxy/app/analytics log tokom M02-QA-035. | Nema raw tokena, emaila, child imena, provider claim-a ili acceptance cookie-ja. |
| M02-QA-037 | Pre-auth preview guardian poziva. | School/role/masked email/rok mogu biti vidljivi; child ime i drugi podaci nisu. |
| M02-QA-038 | Attempt callback koristi pogrešan browser binding/state. | 400 `INVITATION_ATTEMPT_INVALID`; bez proof-a/pristupa. |
| M02-QA-039 | Provider issuer nije u aktivnom M01 registru. | Provider proof odbijen; M02 attempt ne dobija verified stanje. |
| M02-QA-040 | Provider verified email ne odgovara recipient fingerprint-u. | 403 mismatch; invitation ostaje ACTIVE; target/child se ne otkriva. |
| M02-QA-041 | Dva principal-a imaju isti verified email, različite subject-e. | M01 ih ne linkuje/merge-uje; M02 ne koristi email za account lookup. |
| M02-QA-042 | Principal issuer+subject pripada `U-A1`, a invite target je `P-A1`. | `IDENTITY_VERIFIED`; završni accept reuse-uje isti nalog. |
| M02-QA-043 | Principal account pripada `P-A1`, a invite target je `P-A2`. | 403 identity mismatch/person conflict; nema merge-a ili novog pristupa. |
| M02-QA-044 | Target `P-A2` već ima nalog, ali principal subject nije linkovan. | 409 `INVITATION_ACCOUNT_LINK_REQUIRED`; nema novog AuthIdentity/naloga. |
| M02-QA-045 | Target `P-A2` nema nalog i svi finalni guardovi prolaze. | Tačno jedan UserAccount + prvi AuthIdentity + odobren pristup, svi u jednoj transakciji. |
| M02-QA-046 | DB fail posle pokušaja account insert-a, pre role/grant insert-a. | Potpun rollback; nema orphan UserAccount/AuthIdentity/PENDING_LINK/membership-a; M07 link ostaje nepromenjen. |
| M02-QA-047 | Isti INV-09 request se retry-uje posle timeout-a. | Isti success receipt; jedan nalog, identity, membership, grant i accepted transition. |
| M02-QA-048 | Dva različita attempt-a paralelno prihvataju isti poziv. | Tačno jedan commit; drugi safe already-used/receipt ishod; nema duplikata. |
| M02-QA-049 | Access iste namere nastane drugim validnim tokom pre INV-09 commit-a. | Poziv postaje ACCEPTED sa `access_already_present=true`; nema duplog granta. |
| M02-QA-050 | Existing account je `SUSPENDED`/`DISABLED`. | 403 `INVITATION_ACCOUNT_INACTIVE`; invitation ne aktivira nalog ili sesiju. |
| M02-QA-051 | Attempt dođe do `now==started_at+15min`. | 410 attempt expired; proof/accept se ne koristi. |
| M02-QA-052 | M01 proof je potrošen ili stariji od 5 min. | 401 `INVITATION_PROOF_EXPIRED`; nova autentifikacija potrebna. |
| M02-QA-053 | Korisnik cancel-uje STARTED/VERIFIED attempt. | Attempt `CANCELLED`; invitation ostaje ACTIVE ako rok/status dozvoljava. |
| M02-QA-054 | Invitation je ACTIVE do tačno `expires_at-1ms`, zatim `expires_at`. | Pre roka može nastaviti; na roku/posle je 410 bez obzira na `invitation.expiry_scan`. |
| M02-QA-055 | `invitation.expiry_scan` kasni sat vremena. | Expired token se sve vreme odbija read-time guardom; job samo materijalizuje status, a prekoračenje secret-cleanup SLO-a daje alert/incident bez produženja dekripcije. |
| M02-QA-056 | Revoke se commit-uje dok je provider callback u toku. | Finalni accept recheck odbija; attempt terminalan; nema pristupa. |
| M02-QA-057 | School se deaktivira dok je callback u toku. | Finalni accept fail-closed; druge škole naloga ostaju dostupne. |
| M02-QA-058 | Inviter izgubi grant authority ili policy version se promeni. | 409 `INVITATION_ACCESS_CHANGED`; stari snapshot ne dobija nova prava. |
| M02-QA-059 | Guardian invitation sa unapred ACTIVE M07 linkom za `C-A1` se prihvati. | Nastaju GUARDIAN role/grantovi samo za `C-A1`; M07 link se ne kreira/menja; query za `C-A2` i `C-B1` vraća safe 404. |
| M02-QA-060 | Guardian relationship je opozvan odmah posle acceptance-a. | Sledeći request je odbijen bez cache TTL prozora; invitation istorija ostaje. |
| M02-QA-061 | Cross-tenant admin iz `S-A` koristi invitation ID iz `S-B`. | 404 safe; list/count/audit ne otkrivaju `S-B`. |
| M02-QA-062 | List invitation query u `S-A` sa filterom/emailom iz `S-B`. | Rezultat/count ostaju samo `S-A`; email je maskiran. |
| M02-QA-063 | Public token poziva iz `S-B` se otvara uz aktivan context `S-A`. | Preview ne čita podatke `S-A`; acceptance ne menja context dok TEN-01 nije eksplicitan. |
| M02-QA-064 | Successful acceptance dodaje novu školu nalogu koji već ima drugu. | Samo target school access nastaje; drugi tab/context se ne menja; M03 suggestion je bezbedan. |
| M02-QA-065 | „Prvi put sam ovde” javna forma pokuša direktan account create bez invitation attempt-a. | Server odbija; nema Person/UserAccount-a. |
| M02-QA-066 | Korisnik unese validan školski kod bez poziva. | Može dobiti samo locator/help rezultat; nema članstva, role ili naloga. |
| M02-QA-067 | Inspect invitation email. | Samo škola, generička vrsta, rok, link i help; nema child/finance/attendance/permission liste. |
| M02-QA-068 | Inspect audit/outbox/telemetry/receipts. | Nema raw tokena/digesta, plaintext emaila, subject-a, child imena ili provider payload-a. |
| M02-QA-069 | Revoke i accept počnu sa istom version paralelno. | Tačno jedna terminalna tranzicija; ako revoke commit prvi, nema pristupa; ako accept prvi, revoke invitation više ne ukida nastali access. |
| M02-QA-070 | M04–M07 autoritet nije pouzdano dostupan u finalnom guardu. | 503 fail-closed; nema parcijalnog upisa ili lažnog success-a. |
| M02-QA-071 | Škola ima po jedan DRAFT/AWAITING_APPROVAL/ACTIVE poziv i sve terminalne statuse; M04 SCH-05 poziva INV-11. | Samo tri otvorena prelaze u REVOKED; njihovi attempts terminalni FAILED/CANCELLED; njihovi secrets prolaze §4.4 tombstone (ciphertext/key_ref=null, deleted_at=commit_at); terminalni pozivi/attempts/secrets nepromenjeni; receipt sadrži samo command_receipt_id+revoked_count=3+attempts_invalidated_count. |
| M02-QA-072 | Identičan INV-11/SCH-05 retry istim (school_id, source_school_version, request_id). | Isti command_receipt_id/revoked_count/attempts_invalidated_count; bez ijedne nove tranzicije, audit ili outbox zapisa. |
| M02-QA-073 | Stvarna paralelna INV-09 vs SCH-05 trka, oba kontrolisana redosleda. | Dokazuje ishod §11.4: SCH-05 prvi → nema pristupa; INV-09 prvi → ACCEPTED ostaje, škola se ipak deaktivira; nema parcijalnog account/access upisa. |
| M02-QA-074 | M04 SCH-06 reaktivacija posle INV-11 revoke-a. | Nijedan revoked invite/attempt/token ne oživljava; novi pristup zahteva nov M02 invite. |
| M02-QA-075 | Škola kreira `PAYER_ACCESS` draft za adult Person sa ACTIVE M07 `PayerChildLink`, bez guardian link-a. | Draft uspeva; grant spec sadrži M05 `PAYER`, finance-only permission-e i `PAYER_CHILD_LINK` basis. |
| M02-QA-076 | `PAYER_ACCESS` cilja pending/revoked/cross-tenant payer link. | Pending/revoked daje 409 `INVITATION_ACCESS_CHANGED`; cross-tenant daje 404 safe; nema tokena. |
| M02-QA-077 | PAYER invite se prihvati za osobu bez naloga, ali sa ACTIVE M07 linkom koji referencira ACTIVE CONTACT membership. | Account/identity + PAYER role/grants nastaju atomarno uz reuse tačno tog membership-a; M02 ne kreira drugi membership, a M07 link ostaje nepromenjen. |
| M02-QA-078 | PAYER posle acceptance-a čita attendance/document/profile. | Svaki child-data endpoint vraća safe 404; dozvoljena M12 finansijska projekcija prolazi svoj guard. |
| M02-QA-079 | Guardian invitation se pokuša izdati dok je primaočev M07 link još PENDING_VERIFICATION. | 409 `INVITATION_APPROVAL_REQUIRED`; nema tokena/emaila. |
| M02-QA-080 | Guardian/payer link je ACTIVE pri issue-u, ali REVOKED pre INV-09 commit-a. | 409 `INVITATION_ACCESS_CHANGED`; nema account/access partial write-a. |
| M02-QA-081 | INV-01 u `S-A` pošalje `target_school_person_profile_id` iz `S-B`, ili profile iz A upari sa drugim globalnim `target_person_id`. | Owner-resolve/composite FK daje safe 404 `TENANT_RESOURCE_NOT_FOUND_SAFE`; nema poziva, count/signala o targetu niti globalne person pretrage. |
| M02-QA-082 | Guardian/payer link je ACTIVE, ali membership koji link referencira je TERMINATED, pogrešnog tipa ili promenjen neposredno pre INV-09 commit-a. | Issue/accept fail-closed sa 409 `INVITATION_ACCESS_CHANGED`; M02 ne kreira zamenski GUARDIAN/CONTACT membership i nema account/role partial write-a. |
| M02-QA-083 | INV-04 commit uspe, a delivery worker još nije preuzeo red. | HTTP 200 transition odgovor sadrži `invitation.status=ACTIVE`, `delivery_status=QUEUED`; nema 202/error objekta i UI ne tvrdi da je email isporučen. |
| M02-QA-084 | Admin lista/detail traži maskirani recipient email; zatim se pregledaju Invitation red, audit, receipt, outbox, logs i telemetry. | Maskirana vrednost se purpose-limited izvodi u memoriji iz ciphertext-a; ne postoji treća stored email kolona niti email/maska u auditu, receipt-u, outbox-u ili observability-ju. |

## 2. Scenario-po-paragraf normativna mapa

| QA opseg | Normativni oslonac u M02 masteru |
|---|---|
| 01–04 | §§4.1, 8 INV-01, 11.1 |
| 05–08 | §§3, 4.1, 6.1 |
| 09–14 | §§5, 6.1, 7.1, 8 INV-01/03 |
| 15–19 | §§5, 6.1, 8 INV-01/04/09 |
| 20–22 | §§4.1, 6.1, 8 INV-02, 11 |
| 23–28 | §§3, 4.1/4.3/4.4, 6.1, 11.3, 12 |
| 29–33 | §§6.1/6.4/6.5, 7.1, 8 INV-05 |
| 34–37 | §§6.2/6.3, 8 INV-07/Q01, 9 |
| 38–41 | §§6.3, 8 INV-08, 9, M01 port iz §2 |
| 42–46 | §§1, 4.2, 6.3, 11.2/11.3 |
| 47–50 | §§6.3, 10, 11.1/11.3 |
| 51–53 | §§4.2, 6.3, 7.2, 8 INV-08/10 |
| 54–58 | §§3 (vremenska granica), 6.4, 7, 8 INV-06/09 |
| 59–60 | §§5, 6.3, 9, M07 port iz §2 |
| 61–64 | §§6.3, 8 INV-Q02/Q03, 9 |
| 65–67 | §§1, 6.2, 13 |
| 68 | §§4.4/4.5, 9, 12 |
| 69–70 | §§6.3/6.4, 10, 11.2/11.3 |
| 71–74 | §11.4 (novo, INV-11 puna mehanika) |
| 75–80 | §§4.1, 5, 6.1/6.3, 9, 11.3; M05/M07 subject-basis portovi |
| 81–84 | §§4.1, 6.1–6.3, 8–9, 11–12; M06 composite profile/membership i delivery response ugovori |

Svaki pojedinačni scenario ima najmanje jednu tačnu normativnu vezu kroz svoj opseg. Integrator sme proširiti mapu na jedan-red-po-scenariju, ali ne sme zameniti je tvrdnjom da test već postoji.

## 3. Obavezne automatizovane grupe

- unit: EmailCanonicalizer v1, expiry boundary, lifecycle matrice, grant canonical hash, public error projection, reason registry;
- integration: issue/replace/revoke transakcije, M01 account+first identity atomarnost, M03 tenant lookup, M05 grant authority, M06 eligibility/membership, M07 guardian+payer scope, outbox/receipt;
- concurrency: duplicate draft, update version, replace race, revoke-vs-accept, two-attempt accept, account/person duplicate protection;
- security: token entropy/digest/constant-time compare, referrer/log redaction, browser binding, callback replay, email anti-forwarding bez account linking-a, IDOR/BOLA, rate limit;
- delivery/job: provider timeout/duplicate submission, pet-attempt limit, lease/fencing, secret deletion, `invitation.delivery_dispatch` i `invitation.expiry_scan` lag/read-time expiry;
- e2e: staff existing/new account, guardian approval+acceptance, first owner, wrong identity, expired/replaced link, context suggestion;
- migration: svaki legacy status, plaintext token removal/rotation, incomplete invite exception, public registration block, forward recovery;
- privacy: pre/post-auth projekcija, izvedeni maskirani email bez treće kopije, child izolacija i audit/outbox/telemetry/receipt redaction.

Suite pada ako bilo koji od 84 scenarija nije pokrenut, preskočen je ili zavisi od realne mreže/vremena umesto kontrolisanih adaptera i test clock-a.

## 4. Traceability ka aktivnim ugovorima

| Aktivni autoritet | M02 obavezna veza |
|---|---|
| M00/DCR-20260907-01 rev. 2.3 | Invite-only, server guards, receipt/audit/outbox i atomski application coordinator. |
| M01 master | No email linking, no `PENDING_LINK`; account i prva provider identity nastaju atomarno tek u validnom accept-u. |
| M03 master | Invitation school nije tenant authority; acceptance koristi tačan server context i safe-404 pravilo. |
| M04 master | School status, owner nomination i entitlement/provisioning uslovi proveravaju se pre commit-a. |
| M05 master | Issuer/approver authority i role activation koriste tačan permission/policy version. |
| M06 master | Poziv cilja postojeću odraslu `Person`/school profile; M02 ne spaja Person po emailu. |
| M07 master | Guardian/payer activation zahteva aktuelni verifikovani odnos i odvojeni subject basis. |
| M21 job katalog | Read-time expiry ostaje autoritet; materialization job je idempotentan i ne oživljava poziv. |

## 5. Definition of QA evidence

Za svaki automatizovani test čuva se: test ID, fixture/seed ID, command/query, očekivani kod i stanje, stvarno stanje, audit/outbox provera, broj nastalih redova i correlation ID. Dok repo nije pregledan, svi M02 scenario statusi su `SPECIFIED_NOT_IMPLEMENTATION_VERIFIED`.
