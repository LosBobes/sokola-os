---
tip: modulni-implementacioni-ugovor
modul-id: M15
naziv: Dokumenti, verzije i dokaz prihvatanja
status: SPEC_CANDIDATE
revizija: "1.3"
datum: 2026-09-15
schema-zavisnosti: [M04, M06]
read-portovi: [M07, M09, M12, M16]
application-orchestration: [consent-evidence-coordinator-M17-plus-M15]
application-guardovi: [M01, M03, M05]
izlazni-portovi-za: [M13, M17, M19, M20, M21, M28]
offline-policy: DENY
---

# M15 — Dokumenti, verzije i dokaz prihvatanja

## 1. Cilj, autoritet i granice

M15 bezbedno čuva logički dokument, njegove neizmenjive verzije, tipizirani pristup, kratkotrajno preuzimanje i dokaz elektronskog prihvatanja/čitanja/odbijanja. Poseduje `Document`, `DocumentVersion`, `DocumentAccess`, `DocumentAcceptanceRequirement`, `DocumentAcceptanceEvidence`, `DocumentDownloadTicket` i audit pristupa.

M15 ne određuje pravni osnov obrade, retention kategoriju ili validnost saglasnosti (M17), ne predstavlja klik kao kvalifikovani elektronski potpis, ne čuva zdravstvene dokumente u H0, ne poseduje Event/Group/Person/Guardian/Obligation i ne šalje email priloge. Nema diff/merge/rollback UI-ja, ali puna immutable istorija verzija i hash-eva je obavezna.

## 2. Entiteti, polja i relacije

Svi tenant entiteti imaju `school_id`, kompozitne tenant FK-ove i opaque UUID. Vreme je UTC; object storage key nikad nije korisnički unos niti javni URL.

Precizni tipovi: svi `id`/`*_id` su UUID; svi `*_at`/`*_until` su `TIMESTAMPTZ`; `version` je `BIGINT >= 1`; `version_no` je `INTEGER > 0`; `size_bytes` je `BIGINT`; SHA-256/payload hash je lowercase `CHAR(64)`; kodovi su zatvoreni `varchar(96)` registri; IP ciphertext je enkriptovani `BYTEA`, nikad plaintext. Polje je obavezno osim kada eksplicitno piše nullable. Aggregate/command red sa surrogate `id` ima `UNIQUE(school_id,id)` i svaki tenant FK uključuje `school_id`; digest-keyed ticket/session/receipt bez surrogate ID-a ima eksplicitni tenant-prefiksirani PK/UNIQUE i nijedan tenant-less lookup.

`Document`: `id`, `school_id`, `document_type` (`CONTRACT`,`RULEBOOK`,`HOUSE_RULES`,`PRIVACY_NOTICE`,`PAYMENT_PROOF`,`OPERATIONAL`,`EVENT_INFORMATION`,`OTHER_NON_HEALTH`), `title` varchar(200), `owner_scope_type` (`SCHOOL`,`PARTICIPANT`,`GROUP`,`EVENT`,`OBLIGATION`), `owner_scope_id` nullable samo za SCHOOL, `status` (`DRAFT`,`PUBLISHED`,`RETIRED`), `current_version_id` nullable, `created_by_account_id`, `created_at`, `updated_at`, `retired_at` nullable, `retired_by_account_id` nullable, `version`. Jedan document je jedan logički identitet kroz verzije.

`DocumentVersion`: `id`, `school_id`, `document_id`, `version_no` positive int, `storage_object_key`, `media_type` (`application/pdf`,`image/jpeg`,`image/png`), `size_bytes` 1..10485760, `content_sha256`, `document_metadata_hash`, `status` (`UPLOADING`,`SCANNING`,`AVAILABLE`,`REJECTED`,`WITHDRAWN`), `scan_engine_version` nullable, `scan_result_code` nullable, `scan_completed_at` nullable, `uploaded_by_account_id`, `created_at`, `updated_at`, `available_at` nullable, `withdrawn_at` nullable, `withdrawn_by_account_id` nullable, `withdraw_reason_code` nullable, `version`. Unique `(school_id,document_id,version_no)` i `(school_id,document_id,content_sha256)`: isti byte sadržaj se ne objavljuje kao dve verzije istog logičkog Document-a, ali isti template bytes smeju pripadati različitim Document zapisima. Sadržaj/metadata/hash se nikad ne menjaju nakon izlaska iz UPLOADING; korekcija je nova verzija.

`DocumentAccess`: `id`, `school_id`, `document_id`, `access_version_no UInt32`, `scope_type` isti zatvoren enum, `scope_id` nullable samo kada je `scope_type=SCHOOL`, `visibility` (`STAFF_ONLY`,`AUTHORIZED_GUARDIANS`,`AUTHORIZED_PAYERS`,`STAFF_AND_AUTHORIZED_GUARDIANS`,`EXPLICIT_REQUIREMENT_SUBJECTS`), `status` (`ACTIVE`,`RETIRED`), `effective_from`, `effective_until nullable`, `created_by_account_id`, `created_at`, `supersedes_access_id nullable`, `retired_at nullable`, `retired_by_account_id nullable`, `retire_reason_code nullable`, `version`. Unique `(school_id,document_id,access_version_no)`; partial/exclusion constraint dozvoljava najviše jedan efektivni ACTIVE glavni access interval po Document-u. ACTIVE ima retire trio null; RETIRED zahteva ceo trio i zadržava prethodni interval. Nova verzija atomski retires prethodnu i referencira je; istorijski red se ne prepisuje. `EXPLICIT_REQUIREMENT_SUBJECTS` znači da subjekt aktivnog requirement-a sme videti tačnu verziju pre odluke; nikad ne znači da je već prihvatio. Scope tip mora odgovarati owner scope-u. EVENT se validira samo M16 read portom; M16 ne čita M15 nazad.

`DocumentAcceptanceRequirement`: `id`, `school_id`, `document_id`, `document_version_id`, `requirement_type` (`ACCEPTANCE`,`ACKNOWLEDGEMENT`,`OPTIONAL_DECISION`), `subject_type` (`ADULT_SELF`,`PARTICIPANT_BY_GUARDIAN`), `scope_type/id`, `mandatory_for_service` boolean, `decision_deadline` nullable, `status` (`DRAFT`,`ACTIVE`,`RETIRED`), `legal_purpose_key`, `legal_basis_code`, `legal_policy_version_ref UUID`, `legal_policy_content_hash CHAR(64)`, `created_at`, `activated_at` nullable, `activated_by_account_id` nullable, `retired_at` nullable, `retired_by_account_id` nullable, `version`. Ova četiri legal polja su immutable snapshot/ref vrednosti koje neutralni coordinator proverava prema M17 pre aktivacije; M15 nema fizički FK niti schema import ka M17. Time M17 sme fizički referencirati M15 document/evidence bez M15↔M17 ciklusa. Optional consent ne može imati `mandatory_for_service=true`. Requirement je vezan za jednu konkretnu immutable verziju.

`DocumentAcceptanceEvidence`: append-only `id`, `school_id`, `requirement_id`, `document_id`, `document_version_id`, `document_content_sha256`, `giver_person_id`, `giver_account_id` nullable, `subject_person_id`, `participant_profile_id` nullable, `subject_scope_key` `varchar(128)`, `decision_generation` `BIGINT >=1`, `decision` (`ACCEPTED`,`ACKNOWLEDGED`,`DECLINED`,`CONSENT_GRANTED`,`CONSENT_DECLINED`,`CONSENT_WITHDRAWN`), `channel` (`AUTHENTICATED_WEB_PWA`,`STAFF_ASSISTED`,`API_MIGRATION`), `occurred_at`, `recorded_at`, `actor_type` (`SUBJECT`,`AUTHORIZED_STAFF`,`TRUSTED_MIGRATION`), `recorded_by_account_id` nullable, `recorded_by_system_identity` nullable `varchar(128)`, `source_system_code` nullable `varchar(96)`, `source_evidence_hash` nullable lowercase `CHAR(64)`, `authorization_basis_type/id`, `reason_code` nullable, `evidence_payload_hash`, `correlation_id`, `idempotency_key_hash`, `supersedes_evidence_id` nullable, `ip_address_ciphertext` nullable, `ip_retention_until` nullable. Nema update/delete. Unique `(school_id,requirement_id,giver_person_id,subject_scope_key,decision_generation)`; `subject_scope_key` je nenull `PERSON:<subject_person_id>` za ADULT_SELF ili `PARTICIPANT:<participant_profile_id>` za PARTICIPANT_BY_GUARDIAN, čime nullable SQL semantika ne može propustiti duplikat.

Dozvoljene su samo sledeće actor/channel kombinacije, obezbeđene DB CHECK-om i application guard-om:

- `AUTHENTICATED_WEB_PWA + SUBJECT`: `giver_account_id` je non-null, `recorded_by_account_id=giver_account_id`, system/source polja su null, a aktivna M01 sesija pripada tom nalogu;
- `STAFF_ASSISTED + AUTHORIZED_STAFF`: `recorded_by_account_id` je non-null i, ako giver ima nalog, različit je od `giver_account_id`; system/source polja su null; prisutnost davaoca, step-up, posebna permission i `reason_code` su obavezni;
- `API_MIGRATION + TRUSTED_MIGRATION`: `recorded_by_account_id` je null, a allow-listed `recorded_by_system_identity`, `source_system_code`, `source_evidence_hash` i `reason_code` su non-null; `giver_account_id` sme biti null jer istorijski davalac ne mora imati SOKOLA nalog.

Za svaku kombinaciju `giver_person_id` i `subject_person_id` ostaju obavezni, `recorded_at >= occurred_at`, a migration može preneti samo dokazivu odluku — nikad pretpostavljeni opt-in. IP je NULL po default-u i dozvoljen je samo za `AUTHENTICATED_WEB_PWA` uz aktivnu M17 policy odluku, dokumentovanu neophodnost, encryption i rok; ciphertext i retention datum su oba null ili oba non-null.

`DocumentDownloadTicket`: `ticket_digest`, `school_id`, `document_version_id`, `account_id`, `authorization_version`, `subject_basis_hash`, `issued_at`, `expires_at` ≤ issued+60s, `used_at nullable`, `status` (`ACTIVE`,`USED`,`EXPIRED`,`REVOKED`), `version`. Raw ticket se vraća jednom i ne loguje; single-use exchange token. PK/unique je `(school_id,ticket_digest)`.

`DocumentDownloadSession`: `session_digest`, `school_id`, `document_version_id`, `account_id`, `authorization_version`, `subject_basis_hash`, `status` (`ACTIVE`,`COMPLETED`,`EXPIRED`,`REVOKED`), `byte_length`, `issued_at`, `expires_at` ≤ issued+10min, `last_range_at` nullable, `completed_at` nullable, `version`. Atomski uspešan consume ticket-a pravi najviše jednu download sesiju i samo tada vraća njen raw token. Svaki initial/range zahtev ponovo proverava M01 sesiju, M03 tenant, M05 permission, M07/M12 subject basis, document/version/access i `authorization_version`. Sesija ne produžava TTL, ne sadrži storage URL i ne daje pravo drugom account-u.

`DocumentAccessLogEntry`: append-only `id`, `school_id`, `document_id`, `document_version_id`, `account_id`, `action` (`VIEW_METADATA`,`DOWNLOAD`,`ACCEPTANCE_DECISION`), `authorization_basis_type`, `authorization_basis_id`, `occurred_at`, `correlation_id`; bez filename-a, title-a, IP-a i child imena.

## 3. Poslovna pravila i invarijante

1. Upload koristi server-issued object key, deklarisani size/media i završni streaming SHA-256. Ekstenzija nije dokaz; magic bytes, parser safety i malware scan su obavezni pre AVAILABLE.
2. Dozvoljeni su samo PDF/JPEG/PNG ≤10 MiB. Encrypted/password PDF, aktivni sadržaj, polyglot, macro/executable ili nečitljiv parser rezultat se odbija.
3. Zdravstveni/medicinski dokument je H0 zabranjen nezavisno od izabrane kategorije; UI upozorenje nije jedina kontrola.
4. Publish Document-a zahteva AVAILABLE verziju, validan tenant scope/access i expected version. `current_version_id` se atomski menja; prethodna verzija ostaje immutable dostupna samo kroz istorijski/audit/acceptance guard.
5. Nova verzija ne prepisuje postojeće evidence. Svaki novi zahtev prihvatanja cilja novu verziju/hash; ponovni acceptance je potreban samo ako novi ACTIVE requirement to eksplicitno zahteva.
6. Download nikad ne vraća trajni storage URL. Issue ticket ponovo proverava current permission, subject, document/access/version status; download ponovo proverava ticket binding, expiry, single-use i authorization version.
7. `DocumentAccess` snapshot nije permission. Guardian/Payer pravo zavisi od aktuelnog M07 basis-a i eksplicitne visibility kategorije; PAYER nikad dobija ugovor/dete dokument samo zato što plaća.
8. `PAYMENT_PROOF` zahteva M12 Obligation/Payer subject guard i visibility; nije dostupan drugom guardian-u bez odgovarajućeg finansijskog basis-a.
9. Acceptance komanda prikazuje requirement i tačan hash/verziju neposredno pre odluke; client šalje expected requirement/document versions. Server upisuje evidence, audit/outbox/receipt u jednom commit-u.
10. `ACKNOWLEDGED` znači dokaz da je notice prikazan/pročitan prema ugovoru, ne saglasnost. `ACCEPTED` je elektronsko prihvatanje, ne QES. `DECLINED` opcionog zahteva ne blokira aplikaciju; mandatory contract decline može blokirati samo tačno definisanu uslugu, ne auth ili druge tenant-e.
11. M17 je source of truth za Consent status i legal basis; M15 je source of truth za tačan dokument/hash i evidence red. Neutralni application coordinator za M17 odluku upisuje M17 `ConsentDecision`, odgovarajući M15 evidence (`GRANTED→CONSENT_GRANTED`, `DECLINED→CONSENT_DECLINED`, `WITHDRAWN→CONSENT_WITHDRAWN`), oba owner audit/outbox zapisa i jedan command receipt u istoj lokalnoj transakciji. M15 ne poziva M17 domain handler, a M17 ne upisuje M15 tabelu direktno. M15 legal-policy vrednosti su aktivacioni snapshot/ref bez fizičkog M15→M17 FK-a; njihov M17 dokaz se čuva hash-vezano, pa nema schema ciklusa. Istorijski dokaz se ne briše i ne znači da saglasnost još važi.
12. Staff-assisted evidence zahteva posebnu permission, step-up, prisutnog davaoca, reason i audit; nije dozvoljeno masovno ili retroaktivno prihvatanje.
13. Dokument se nikad ne stavlja u email/push payload/cache. Offline view/download/acceptance je DENY.
14. Retire/withdraw sprečava nova preuzimanja, ali zadržava dokazni hash/evidence prema M17 retention/legal hold ugovoru.
15. Conditional-null DB pravila su obavezna. Document DRAFT ima null current/retire polja; PUBLISHED ima non-null current version i null retire polja; RETIRED ima retire actor/vreme i zadržava prethodni current version ako je ikada bio objavljen. Version UPLOADING/SCANNING ima sva scan-result/available/withdraw polja null; AVAILABLE zahteva scan engine/result/completed i `available_at`; REJECTED zahteva scan engine/result/completed i nema available/withdraw polja; WITHDRAWN zadržava scan+available dokaz i zahteva withdraw actor/vreme/reason. Requirement DRAFT ima sva activation/retire polja null; ACTIVE zahteva activation actor/vreme; RETIRED zadržava activation i zahteva retire actor/vreme. Ticket `used_at` je non-null iff USED; DownloadSession `completed_at` je non-null iff COMPLETED. Početna stanja ne koriste izmišljene timestamp/actor vrednosti.
16. Consume ticket-a nije byte stream. On atomski menja Ticket ACTIVE→USED i izdaje jednu DownloadSession. Byte/range stream koristi samo aktivnu DownloadSession; mrežni prekid se nastavlja unutar iste sesije i istog TTL-a. Po isteku ili opozivu klijent traži novi ticket posle pune autorizacije.

### 3.1. Edge cases

| # | Slučaj | Rezultat |
|---:|---|---|
| 1 | Fajl kaže PDF, magic bytes executable | REJECTED; object quarantined, bez javnog URL-a. |
| 2 | Dva publish-a različitih verzija | Document lock/CAS; jedan current, drugi 409. |
| 3 | Guardian opozvan posle ticket izdavanja | Download fail closed/revoked. |
| 4 | Requirement promenjen dok korisnik čita | 409 stale; ponovni prikaz tačne verzije. |
| 5 | Dva klika Accept | Jedan evidence; isti receipt. |
| 6 | Dva staratelja daju odluku za isto dete | Dva zasebna evidence; M17 određuje čija odluka je pravno dovoljna. |
| 7 | M17 withdrawal posle GRANTED | Novi `CONSENT_WITHDRAWN` evidence i M17 WITHDRAWN decision nastaju atomski; stari grant/evidence ostaju immutable. |
| 8 | Mreža prekine download posle prvog range-a | Nastavak koristi istu aktivnu download sesiju do fiksnog TTL-a; ne koristi USED ticket ponovo. |
| 9 | Dva paralelna consume-a istog ticket-a | Samo jedan dobija DownloadSession; drugi neutralno 410, bez druge sesije. |
| 10 | Dokument retired posle acceptance-a | Evidence ostaje, nova preuzimanja blokirana. |
| 11 | EVENT ID iz druge škole | M16 port safe 404; nema DocumentAccess-a. |
| 12 | Optional photo decision DECLINED | Pristup aplikaciji ostaje; M17 consent nije ACTIVE. |
| 13 | IP policy nije aktivna | `ip_address_ciphertext` mora biti NULL. |
| 14 | Migrirana odluka davaoca bez SOKOLA naloga | Dozvoljena samo uz giver Person, trusted system identity i source evidence hash; nema izmišljenog account-a. |
| 15 | Staff zapisuje odluku, ali actor nije sačuvan | Cela komanda se odbija; giver i recorder se nikad ne poistovećuju prećutno. |

## 4. Tenant i Security Guard

Request lanac: M01→M03→M04 entitlement/status→M05 permission→M15 resource→M06/M07/M09/M12/M16 subject/scope. Cross-tenant/skiven target je safe 404. Storage bucket je private, encryption at rest, tenant-bound key/context, antivirus sandbox; filename se sanitizuje i nije storage key.

Permissions: `school.documents.view`, `school.documents.manage`, `school.documents.publish`, `school.documents.download`, `school.documents.accept`, `school.documents.record_assisted_acceptance`, `school.documents.access_log_view`. Owner/Manager upravljanje; Limited samo grant; Instructor staff/group scope; Guardian subject scope; Payer samo PAYMENT_PROOF gde M12 basis važi. Support ne može download, accept niti videti content/title/subject; može samo agregat scan health bez PII. Break-glass nema dokument content/export.

Rate: upload prepare 20/h/actor, download ticket 60/min, acceptance 20/min. Observability samo media type/size bucket/status/latency/error/school hash; nema title/filename/hash/raw ticket/person/child. `content_sha256` je osetljiv interni dokaz i nije metric label/API list polje.

## 5. Lifecycle

| Entitet | Iz | Akcija | U |
|---|---|---|---|
| Document | — | Create | DRAFT |
| Document | DRAFT/PUBLISHED | Publish AVAILABLE version | PUBLISHED |
| Document | DRAFT/PUBLISHED | Retire | RETIRED |
| Version | — | PrepareUpload | UPLOADING |
| Version | UPLOADING | Finalize verified bytes | SCANNING |
| Version | SCANNING | Safe scan | AVAILABLE |
| Version | SCANNING | Unsafe/invalid | REJECTED |
| Version | AVAILABLE | Withdraw | WITHDRAWN |
| Requirement | DRAFT | Activate | ACTIVE |
| Requirement | ACTIVE | Retire | RETIRED |
| DocumentAccess | — | Set first access | ACTIVE |
| DocumentAccess | ACTIVE | Set successor | stari RETIRED + novi ACTIVE |
| DocumentAccess | ACTIVE | Retire without successor | RETIRED |
| Ticket | ACTIVE | Download | USED |
| Ticket | ACTIVE | ttl/revoke | EXPIRED/REVOKED |
| DownloadSession | — | Consume valid ticket | ACTIVE |
| DownloadSession | ACTIVE | Potpun byte stream | COMPLETED |
| DownloadSession | ACTIVE | ttl/access revoke | EXPIRED/REVOKED |

REJECTED/WITHDRAWN/RETIRED/USED/EXPIRED/REVOKED su terminalni u redovnom toku. Evidence nema state machine: append-only činjenica; korekcija/supersession je novi red.

## 6. Error katalog

| Kod | HTTP | Opis |
|---|---:|---|
| `M15_NOT_FOUND_SAFE` | 404 | Hidden/cross-tenant/missing. |
| `M15_PERMISSION_DENIED` | 403 | Poznata nedozvoljena akcija. |
| `M15_INVALID_FILE` | 422 | Media/magic/parser/size. |
| `M15_HEALTH_DOCUMENT_FORBIDDEN` | 422 | H0 medicinski sadržaj. |
| `M15_SCOPE_INVALID` | 422 | Scope/visibility mismatch. |
| `M15_VERSION_NOT_AVAILABLE` | 409 | Nije AVAILABLE/current dozvoljen. |
| `M15_SCAN_PENDING` | 409 | Scan nije završen. |
| `M15_STALE_VERSION` | 409 | CAS/requirement/version promenjen. |
| `M15_ACCEPTANCE_NOT_ALLOWED` | 403 | Nema giver/child authority. |
| `M15_EVIDENCE_ACTOR_INVALID` | 422 | Channel, actor ili dokazni identiteti nisu dozvoljena kombinacija. |
| `M15_SOURCE_EVIDENCE_REQUIRED` | 422 | Migracija nema trusted system/source proof. |
| `M15_OPTIONAL_CONSENT_CANNOT_BE_MANDATORY` | 422 | Anti-dark-pattern invariant. |
| `M15_TICKET_EXPIRED_OR_USED` | 410 | Neutralan ticket ishod. |
| `M15_DOWNLOAD_SESSION_EXPIRED_OR_REVOKED` | 410 | Range/download sesija više nije aktivna. |
| `M15_IDEMPOTENCY_KEY_REUSED` | 409 | Isti key, drugi payload. |
| `M15_RATE_LIMITED` | 429 | Limit. |
| `M15_DEPENDENCY_UNAVAILABLE` | 503 | Scope/scan/storage/subject port; fail closed. |

## 7. API, idempotency, concurrency i NFR

Komande: `CreateDocument`, `PrepareVersionUpload`, `FinalizeVersionUpload`, `RecordScanOutcome` (trusted worker), `PublishVersion`, `WithdrawVersion`, `RetireDocument`, `SetDocumentAccess`, `CreateAcceptanceRequirement`, `ActivateRequirement`, `RecordAcceptanceDecision`, `IssueDownloadTicket`, `ConsumeDownloadTicket`, `CompleteDownloadSession`. Query/stream: `StreamDocumentRange`. Svaki write ima request/idempotency/correlation; mutacije expected version; reason gde je propisan. Receipt ≥30 dana.

| API ugovor | Obavezni poslovni input | Uspešan rezultat |
|---|---|---|
| `CreateDocument` | type/title/owner scope | DRAFT document; verzija nastaje tek kroz PrepareVersionUpload |
| `Prepare/FinalizeVersionUpload` | document/version, media/size; zatim object proof/hash | UPLOADING pa SCANNING |
| `RecordScanOutcome` | trusted worker, object+engine+result hash | AVAILABLE ili REJECTED |
| `SetDocumentAccess` | document/version, typed scope/visibility/effective interval | novi access version |
| `PublishVersion` | document/version IDs i oba expected version-a | PUBLISHED + current_version_id |
| `WithdrawVersion/RetireDocument` | target/version, zatvoren reason | terminalni status |
| `Create/ActivateAcceptanceRequirement` | exact document version/hash, subject, legal registry refs | DRAFT pa ACTIVE requirement |
| `RecordAcceptanceDecision` | requirement/document versions, giver/subject basis, decision/channel, tačan recorder/system dokaz | append-only evidence + receipt |
| `IssueDownloadTicket` | document/version + current subject basis | raw single-use token jednom, expiry ≤60s |
| `ConsumeDownloadTicket` | raw ticket + validna M01 sesija | ticket USED + jedna kratka DownloadSession; bez storage URL-a |
| `StreamDocumentRange` | raw session token + validna M01 sesija + validan HTTP byte range | ponovo autorizovan byte stream ili 206; nikad novi business side effect |
| `List/GetDocumentMetadata` | cursor/filter ili ID | minimalna autorizovana metadata projekcija |

Lock order: Document→Version→Access→Requirement→giver/participant semantic key. Scan callback dedupe object+engine version+result hash. Raw upload/ticket token je digest-only. Object delete je retention job tek posle DB tombstone/legal hold odluke; failure ne oživljava access.

List cursor default30/max100; upload streaming, bez celog fajla u app memoriji. p95 metadata≤300ms, ticket≤400ms, acceptance≤600ms; malware scan asinhron. Download podržava streaming/range uz isto authorizovano ticket pravilo. Storage quota/retention dolaze iz M04/M17; prekoračenje fail closed pre prepare-a.

Obavezni indeksi: document `(school_id,status,owner_scope_type,owner_scope_id,id)`; version unique `(school_id,document_id,version_no)` i lookup `(school_id,status,created_at,id)`; active access unique partial po document-u; requirement `(school_id,subject_type,scope_type,scope_id,status,id)`; evidence unique `(school_id,requirement_id,giver_person_id,subject_scope_key,decision_generation)`, unique receipt/idempotency guard i lookup `(school_id,requirement_id,recorded_at,id)`; ticket unique digest i partial `(status,expires_at)`; download session unique digest i `(school_id,account_id,status,expires_at)`; access log `(school_id,document_id,occurred_at,id)`. Storage object key i hash nisu javno pretraživi.

## 8. Acceptance kriterijumi

M15 prolazi samo uz `02-M15-QA-I-TRACEABILITY.md`: content spoof/polyglot/malware, immutable version/hash, parallel publish, subject revoke između issue/consume, one-time ticket, cross-tenant scope, exact acceptance evidence, optional-consent non-coercion, staff-assisted guard, no-QES claim, no-email/offline content, audit/retention/legal-hold i log redaction.
