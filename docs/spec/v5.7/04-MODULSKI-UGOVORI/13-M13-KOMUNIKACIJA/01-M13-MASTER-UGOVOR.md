---
tip: modulni-implementacioni-ugovor
modul-id: M13
naziv: Ručna komunikacija
status: SPEC_CANDIDATE
revizija: "1.4"
datum: 2026-09-15
schema-zavisnosti: [M04, M06]
read-portovi: [M06, M07, M09, M15, M17]
application-guardovi: [M01, M03, M05]
izlazni-portovi-za: [M14, M17, M18, M19, M21, M28, M34]
offline-policy: DENY
---

# M13 — Ručna komunikacija

## 1. Cilj, autoritet i granice

M13 omogućava ovlašćenom školskom osoblju da pripremi, pregleda ciljnu publiku, objavi, isporuči i kontrolisano povuče jednosmernu komunikaciju. Poseduje samo ručno inicirane poruke i njihovu isporuku: `CommunicationDraft`, `CommunicationAudience`, `RecipientSnapshot`, `PublishedCommunication`, `CommunicationReadReceipt`, `CommunicationDelivery` i `CommunicationCorrectionLink`.

M13 ne poseduje automatske notifikacije/attention stavke (M14), dokument ili download (M15), događaj (M16), osobu/guardian/group (M06/M07/M09), invitation email (M02), marketing kampanju/CRM (M34) niti privatni chat. Zakazano buduće objavljivanje nije H0: publish je eksplicitna online komanda ovlašćenog actor-a i ne postoji `communication.scheduled_publish`. H0 kanali su `IN_APP` i `EMAIL`; SMS/Viber/WhatsApp/push su van H0. Poruka nikad nije direktno upućena detetovom nalogu; dete nema samostalni H0 nalog.

## 2. Entiteti, polja i relacije

Tipovni ugovor: svi `id`, `*_id`, actor/resource/subject reference i `request_id` su UUID; svi `*_at` su UTC `TIMESTAMPTZ`; `version` je `BIGINT >= 1`; SHA-256 je lowercase `CHAR(64)`; enum vrednosti su DB `CHECK`/ekvivalent, ne slobodan string. Polje je obavezno osim kada eksplicitno piše nullable. Svaki tenant FK je kompozitan `(school_id, referenced_id)`. Aggregate/command red sa surrogate `id` ima `UNIQUE(school_id,id)`; keyed receipt/projection bez surrogate ID-a mora imati eksplicitni kompozitni PK/UNIQUE koji počinje sa `school_id` i nijedan tenant-less lookup.

Svi ID-evi su UUID/opaque, vreme UTC `TIMESTAMPTZ`, runtime identifikatori English ASCII. Svaki tenant zapis ima `school_id` i `UNIQUE(school_id,id)`; svaki tenant FK uključuje `school_id`.

### 2.1. CommunicationDraft i audience

`CommunicationDraft`: `id`, `school_id`, `author_membership_id`, `subject` varchar(160), `body_plaintext` varchar(10000), `language_code` BCP47, `attached_document_id` nullable, `status` (`DRAFT`,`ARCHIVED`), `version` bigint, `created_at`, `updated_at`, `archived_at nullable`. `archived_at` je null iff DRAFT i non-null iff ARCHIVED. Slobodan tekst je PII-risk; enkriptovan je at rest i redaktovan iz logova.

`CommunicationDraftDisposition`: append-only retention tombstone: `id`, `school_id`, `draft_id`, `last_draft_version`, `disposition` (`RETENTION_EXPIRED`,`PUBLISHED_SOURCE_PURGED`,`MANUAL_ARCHIVE_PURGED`), `last_activity_at`, `warning_event_id nullable`, `disposed_at`, `system_request_id`, `legal_hold_ref nullable`, `created_at`. Unique `(school_id,draft_id)` i `(school_id,system_request_id)`. Ne sadrži subject/body, recipient, email, child/basis ID ili reverzibilan content hash. Tombstone dokazuje purge i sprečava retry da rekreira/ponovo obriše draft.

`CommunicationAudience`: `id`, `school_id`, `draft_id`, `audience_type` (`ALL_ACTIVE_GUARDIANS`,`GROUP_GUARDIANS`,`PARTICIPANT_GUARDIANS`,`ACTIVE_STAFF`), `scope_id nullable`, `scope_key varchar(128)`, `created_at`. Za GROUP/PARTICIPANT tip `scope_id` je obavezan i `scope_key` je tačno `GROUP:<lower-uuid>` ili `PARTICIPANT:<lower-uuid>`; za široke tipove `scope_id` je null, a `scope_key` je literal `ALL_ACTIVE_GUARDIANS` ili `ACTIVE_STAFF`. DB CHECK vezuje sva tri polja. Unique `(school_id,draft_id,audience_type,scope_key)` sprečava duplikat i za široke selector-e bez oslanjanja na SQL NULL semantiku.

`RecipientPreview`: kratkotrajna, server-side projekcija: `preview_id`, `school_id`, `draft_id`, `draft_version`, `audience_hash`, `recipient_set_hash`, `recipient_count`, `excluded_count`, `expires_at` (najviše 15 min), `created_by_account_id`. Ne sadrži listu emailova u klijentskom tokenu.

### 2.2. Objavljena poruka i snapshot

`PublishedCommunication`: `id`, `school_id`, `source_draft_id`, `subject_snapshot`, `body_ciphertext`, `language_code`, `document_version_id` nullable, `status` (`PUBLISHED`,`WITHDRAWN`), `recipient_count`, `published_by_account_id`, `published_at`, `withdrawn_at nullable`, `withdraw_reason_code nullable`, `version`. `withdrawn_at` i reason su oba null iff PUBLISHED i oba non-null iff WITHDRAWN. Sadržaj, audience i dokument verzija su immutable posle publish-a.

`RecipientSnapshot`: `id`, `school_id`, `communication_id`, `recipient_account_id`, `recipient_person_id`, `basis_type` (`STAFF_MEMBERSHIP`,`GUARDIAN_CHILD_LINK`), `basis_id`, `participant_profile_id` nullable, `delivery_locale`, `created_at`. Unique `(school_id,communication_id,recipient_account_id,basis_type,basis_id)`. Snapshot dokazuje zašto je primalac uključen; ne daje buduće pravo čitanja.

`CommunicationReadReceipt`: `school_id`, `communication_id`, `recipient_account_id`, `first_read_at`, `last_read_at`, `read_count`, `version`; unique po komunikaciji/primaocu. Server receipt je autoritet, ne client telemetry.

`CommunicationCorrectionLink`: `school_id`, `correction_communication_id`, `corrected_communication_id`, `created_at`; oba zapisa iste škole, bez ciklusa, jedan original može imati niz korekcija.

### 2.3. Isporuka

`CommunicationDelivery`: `id`, `school_id`, `communication_id`, `recipient_account_id`, `channel` (`IN_APP`,`EMAIL`), `status` (`QUEUED`,`SUBMITTING`,`DISPATCHED`,`RETRY_SCHEDULED`,`DELIVERED`,`PERMANENTLY_FAILED`,`SUPPRESSED`), `provider_message_ref` nullable opaque, `provider_idempotency_key_hash`, `attempt_count`, `next_attempt_at nullable`, `last_error_class` nullable zatvoren kod, `lease_token_hash nullable`, `lease_until nullable`, `fencing_token UInt64`, `created_at`, `updated_at`, `version`. Unique `(school_id,communication_id,recipient_account_id,channel)`. Provider idempotency ključ je stabilan za isti delivery i nikad ne sadrži email/account plaintext. `next_attempt_at` je obavezan samo za QUEUED/RETRY_SCHEDULED; lease par je non-null samo u SUBMITTING; terminalni statusi imaju oba para null. `last_error_class` je non-null samo za RETRY_SCHEDULED/PERMANENTLY_FAILED/SUPPRESSED. DISPATCHED zahteva provider ref kada ga provider vraća i znači samo prihvaćen submission; DELIVERED zahteva verifikovan callback/poll ili, za IN_APP, durable inbox dostupnost. DB CHECK sprovodi celu matricu.

Email adresa se dobija just-in-time iz autorizovanog kontaktnog porta, ne kopira u delivery. Email sadrži samo naziv škole, neutralnu informaciju da postoji nova poruka, expiry-safe deep link i pomoć; nema subject/body, imena deteta, finansija, prisustva ili priloga.

## 3. Poslovna pravila i invarijante

1. Autor može imati više draftova; naslov je obavezan nakon trim-a, body 1–10000 Unicode znakova. HTML/script se ne prihvata; rendering escape-uje sadržaj.
2. Preview računa trenutno dozvoljene primaoce preko M06/M07/M09. Osoba sa više osnova dobija jedan account delivery, ali snapshot čuva svaki relevantan basis bez otkrivanja drugog deteta u poruci.
3. Publish zahteva neistekao preview, isti `draft_version`, isti audience i ponovo izračunat isti `recipient_set_hash`. Nula primalaca blokira publish.
4. Ako postoji dokument, M15 vraća tačnu immutable `document_version_id` i potvrđuje pristup svakog primaoca. Dokument nije email attachment.
5. Publish je jedna transakcija: zaključava draft; kreira PublishedCommunication, snapshot-e, IN_APP delivery redove odmah kao `DELIVERED`, EMAIL redove kao `QUEUED`, audit, outbox i receipt; zatim arhivira draft. Partial publish nije dozvoljen.
6. `PUBLISHED` sadržaj se ne menja. Ispravka je nova poruka sa correction linkom; povlačenje ne briše istoriju i ne opoziva već pročitano znanje.
7. Read zahteva aktuelni tenant, M05 permission i aktivni subject basis. Snapshot sam nije dovoljan posle guardian/staff revoke-a.
8. Delivery status ne znači da je poruka pročitana. Provider acceptance nije `DELIVERED` ako provider ne daje takav dokaz.
9. Retry samo za transient greške, exponential backoff+jitter, najviše 8 pokušaja/48h; permanent bounce/unsubscribed/policy suppression je terminalan. In-app ostaje nezavisan.
10. Nema automatske poruke iz M13. Sistemski događaj konzumira M14, nikad M13.
11. Offline create/edit/publish/withdraw/read-write je DENY. UI može lokalno držati neosetljiv unos samo u memoriji do isteka sesije; nema durable child-scoped draft cache-a.
12. Značajna objavljena komunikacija ima retention prema M17; hard delete nije redovan lifecycle.
13. Server draft inactivity rok je tačno 90×24h od poslednjeg uspešnog create/update/audience commit-a. Na 83×24h M13 jednom emituje `CommunicationDraftExpiryWarningRequestedV1`; producer ne poziva M14. Na ili posle 90×24h posao `communication.draft_retention` zaključava draft, ponavlja version/last-activity i M17 legal-hold proveru, upisuje disposition+audit+outbox i fizički briše draft/audience u jednoj transakciji. Nema PII/content-a u tombstone-u.
14. Nova uspešna izmena pre purge commit-a bumpuje version/updated_at i poništava staru eligibility; job je no-op i novi warning/expiry se računa od novog vremena. Precizan ACTIVE M17 legal hold odlaže purge, ali nije pravo čitanja drafta; po release-u sledeći job ponovo ocenjuje 90-dnevni rok. Manualno ARCHIVED i publish-source draftovi smeju se purge-ovati istim pravilom jer objavljena immutable poruka ostaje poseban autoritet.
15. M21 `communication.delivery_dispatch` je jedini EMAIL delivery job. Claim pod kratkim row lock-om radi `QUEUED|RETRY_SCHEDULED→SUBMITTING`, povećava attempt i fencing token i upisuje lease; provider poziv je van duge DB transakcije. Samo aktuelni fence može dati DISPATCHED/RETRY_SCHEDULED/terminalni rezultat. Lease expiry vraća due retry sa istim provider idempotency ključem; stale worker ne menja red. M21 job retry profil ne resetuje M13 limit od osam provider pokušaja/48h.

### 3.1. Granični slučajevi

| # | Slučaj | Deterministički rezultat |
|---:|---|---|
| 1 | Guardian link opozvan između preview-a i publish-a | Recipient hash se menja; 409 stale preview; nema publish-a. |
| 2 | Ista osoba guardian dvoje dece u istoj ciljnoj grupi | Jedna poruka/delivery; dva basis snapshot-a; bez duplog emaila. |
| 3 | Dokument zamenjen posle preview-a | Stara verzija više nije dozvoljena: 409; novi preview obavezan. |
| 4 | Dva taba objave isti draft različitim ključevima | Draft row lock; tačno jedan publish, drugi 409 already published. |
| 5 | Email trajno padne | In-app ostaje dostupna; EMAIL permanently failed; staff aggregate bez PII. |
| 6 | Korisnik povučenoj poruci pristupa preko starog linka | Ako subject basis važi, vidi neutralno WITHDRAWN stanje, ne uklonjeni sadržaj ako policy nalaže conceal. |
| 7 | Cross-tenant document/group ID | Safe 404; nema preview count-a ili existence hint-a. |
| 8 | Objavljivanje tokom school suspension-a | 409/403 prema M04/M05; nema partial zapisa. |
| 9 | Draft je upozoren, autor ga izmeni minut pre 90 dana | Update version/updated_at pobeđuje; stari job ne briše, novi rok kreće od izmene. |
| 10 | Legal hold važi na 90. dan, zatim se ukine | Dok traje hold nema purge-a; posle release-a sledeći run pravi tačno jedan tombstone i purge. |

## 4. Tenant i Security Guard

Svaki request: M01 session → M03 active School/version → M04 entitlement/status → M05 permission → M13 resource + M06/M07/M09 subject guard. `school_id` iz body-ja nije autoritet. Query uvek tenant-scoped; object storage nije direktno izložen. Cross-tenant/skriven ID vraća safe 404.

Permission ključevi: `school.communications.view`, `school.communications.compose`, `school.communications.publish`, `school.communications.withdraw`, `school.communications.delivery_view`. OWNER/MANAGER imaju sve; LIMITED_ADMIN samo eksplicitnim grantom; INSTRUCTOR može compose/view samo za aktivno dodeljene grupe, ali publish samo uz eksplicitni grant; GUARDIAN vidi samo svoje aktivne snapshot+basis poruke; PAYER nema komunikacije po default-u. Support scope ne sme uključiti body, child basis ili recipient list; standardni masking ne može otkriti sadržaj.

Rate limits: preview 30/min/actor/school, publish 10/min, read 120/min. Logovi/metric labels imaju school hash, command/error code, latency/count; bez subject/body/email/person/child ID-a. Audit beleži opaque IDs, actor, permission/policy version, reason, timestamp, correlation; ne sadržaj.

## 5. Lifecycle i tranzicije

| Entitet | Iz | Komanda/događaj | U | Uslov |
|---|---|---|---|---|
| Draft | — | CreateDraft | DRAFT | permission |
| Draft | — | CreateCorrectionDraft | DRAFT | vidljiv original; immutable correction link + reason |
| Draft | DRAFT | ArchiveDraft ili successful Publish | ARCHIVED | expected version |
| Draft | DRAFT/ARCHIVED | 90d inactivity retention bez hold-a | PURGED (tombstone; draft red ne postoji) | row lock, expected observed version, disposition+audit+outbox atomski |
| Published | — | Publish | PUBLISHED | validan fresh preview, ≥1 recipient |
| Published | PUBLISHED | Withdraw | WITHDRAWN | step-up za high reach; reason |
| Delivery IN_APP | — | publish materialization | DELIVERED | isti durable publish commit |
| Delivery EMAIL | — | publish materialization | QUEUED | isti durable publish commit; due odmah |
| Delivery EMAIL | QUEUED/RETRY_SCHEDULED | `communication.delivery_dispatch` claim | SUBMITTING | lease+novi fence; attempt+1 |
| Delivery EMAIL | SUBMITTING | provider accepted | DISPATCHED | aktuelni fence; idempotency key |
| Delivery | DISPATCHED | provider delivered | DELIVERED | verified callback/poll |
| Delivery EMAIL | SUBMITTING/DISPATCHED | transient/ambiguous failure | RETRY_SCHEDULED | aktuelni fence/callback dedupe; attempt<8 i <48h |
| Delivery | bilo koje neterminalno | permanent failure/policy | PERMANENTLY_FAILED/SUPPRESSED | zatvoren reason |

Za poslovno uređivanje ARCHIVED je terminalan, ali retention sme da ga dispositionuje u PURGED; WITHDRAWN, DELIVERED, PERMANENTLY_FAILED, SUPPRESSED i PURGED su terminalni. Nema povratne tranzicije niti rekreiranja drafta sa istim ID-em.

## 6. Error katalog

| Kod | HTTP | Značenje |
|---|---:|---|
| `M13_NOT_FOUND_SAFE` | 404 | Ne postoji, skriven ili drugi tenant. |
| `M13_PERMISSION_DENIED` | 403 | Poznat resurs, nedozvoljena akcija. |
| `M13_VALIDATION_FAILED` | 422 | Naslov/body/audience/channel nije validan. |
| `M13_NO_RECIPIENTS` | 422 | Fresh recipient set je prazan. |
| `M13_PREVIEW_EXPIRED` | 409 | Preview istekao. |
| `M13_STALE_RECIPIENT_PREVIEW` | 409 | Draft/audience/recipient/document version promenjen. |
| `M13_DOCUMENT_NOT_ACCESSIBLE` | 409 | M15 verzija nije dostupna svim primaocima. |
| `M13_ALREADY_PUBLISHED` | 409 | Draft već potrošen. |
| `M13_STALE_VERSION` | 409 | CAS neuspeh. |
| `M13_IDEMPOTENCY_KEY_REUSED` | 409 | Isti ključ, drugi hash. |
| `M13_SCHOOL_NOT_OPERATIONAL` | 409 | School lifecycle blokira akciju. |
| `M13_RATE_LIMITED` | 429 | Limit. |
| `M13_DEPENDENCY_UNAVAILABLE` | 503 | Autoritativni port nedostupan; fail closed. |

Error body je `{code,message_key,correlation_id,retryable,details?}` bez PII, recipient count-a za neautorizovanog aktera, stack/SQL/provider detalja.

## 7. API, idempotency, concurrency i NFR

Komande: `CreateDraft`, `UpdateDraft`, `SetAudience`, `ArchiveDraft`, `CreateCorrectionDraft`, `PrepareRecipientPreview`, `PublishCommunication`, `WithdrawCommunication`, `MarkCommunicationRead`; interna idempotentna `PurgeExpiredCommunicationDraft` poziva se samo iz objavljene M21 definicije. Write zahteva `Idempotency-Key`, `request_id`, `correlation_id`; mutacije `expected_version`; withdraw razlog. Isti key+canonical payload+actor+school+command vraća isti receipt najmanje 30 dana; drugi payload daje 409.

| API ugovor | Obavezni poslovni input | Uspešan rezultat |
|---|---|---|
| `Create/UpdateDraft` | subject, body, channels, expected_version za update | draft ID/status/version |
| `SetAudience` | draft ID/version, kompletan tipiziran selector set | novi draft version |
| `CreateCorrectionDraft` | original published ID, correction reason | novi DRAFT sa immutable correction linkom |
| `PrepareRecipientPreview` | draft ID/version | preview token/hash, expiry, agregirani count |
| `PublishCommunication` | draft/version, preview token/hash | published ID, recipient count, receipt |
| `WithdrawCommunication` | published ID/version, reason code | WITHDRAWN/version |
| `MarkCommunicationRead` | published ID/recipient binding | original ili novi read receipt |
| `ListInbox/GetCommunication` | cursor/filter ili ID | tenant/subject-scoped minimalna projekcija |
| `ListDeliveryHealth` | published ID, masked agregati | counts po statusu; recipient detalj samo uz delivery permission |

Lock order: Draft → audience rows → recipient basis sortirano → document version → PublishedCommunication. `communication.delivery_dispatch` koristi `SKIP LOCKED`/lease, fencing token i stabilan provider idempotency key; callback dedupe je provider+message+event. Provider poziv nije pod business DB lock-om. Audit/outbox/receipt su u istoj DB transakciji kao business write/status commit.

List API koristi cursor, default 30/max100; recipient preview vraća counts i maskirane kategorije, ne bulk PII. p95 list ≤300ms, publish DB commit ≤800ms za ≤5000 primalaca. H0 recipient set iznad 5000 se deterministički odbija 422 `M13_VALIDATION_FAILED` pre prvog publish upisa; nema silent truncation-a, parcijalne/batch objave ili poruke vidljive bez kompletnog snapshot-a. Maksimum: 20 audience selektora, 5000 H0 primalaca, subject160, body10000.

Obavezni indeksi: draft `(school_id,status,updated_at,id)`; disposition unique `(school_id,draft_id)`; published inbox `(school_id,recipient_account_id,published_at,id)` preko recipient snapshot-a; audience unique `(school_id,draft_id,audience_type,scope_key)`; delivery worker partial `(status,next_attempt_at,id)`; read receipt unique `(school_id,published_communication_id,recipient_account_id)`. Nijedan indeks ne koristi plaintext body/subject.

## 8. Acceptance kriterijumi

M13 je prihvatljiv samo ako `02-M13-QA-I-TRACEABILITY.md` prolazi: two-tenant concealment, stale recipient/document preview, duplicate guardian dedupe, parallel publish, immutable correction, delivery retry, current subject revoke, no-content email, no attachment, offline deny, 83/90-day retention race/legal hold, audit/outbox/receipt atomarnost i log redaction.
