---
tip: modulni-implementacioni-ugovor
modul-id: M20
naziv: Onboarding škole i kontrolisani CSV/XLSX import
status: SPEC_CANDIDATE
revizija: "1.8"
datum: 2026-09-16
schema-zavisnosti: [M04]
read-portovi: [M01, M02, M04, M06, M07, M08, M09, M10, M12, M15, M17]
application-orchestration: [import-row-M06-plus-M07-plus-M09, initial-owner-read-composition]
application-guardovi: [M01, M03, M05]
izlazni-portovi-za: [M21]
offline-policy: DENY
horizont: H0_MVP_REQUIRED
---

# M20 — Onboarding škole i kontrolisani import

## 1. Cilj i granice

M20 poseduje vođeni onboarding progress/readiness i import staging: šemu, upload, mapiranje, parser rezultat, validaciju, duplicate resolution, potvrdu, izvršenje i rezultat po redu. Ne poseduje School (M04), pozivnicu (M02), Person/ParticipantProfile (M06), guardian/family vezu (M07), program/lokaciju (M08), group/enrollment (M09), finansije (M12), dokument (M15) niti audit/job infrastrukturu (M21).

H0 import podržava zvanični UTF-8 CSV i XLSX bez makroa, formula i spoljnih veza. Ciljevi su tačno: dete/polaznik; jedan primarni staratelj po detetu; guardian-child veza; enrollment u već postojeći program/grupu; school-local `external_reference`/`import_row_key`. Import ne kreira nalog, poziv, školu, ogranak, program, grupu, lokaciju, termin, obavezu, uplatu ili istorijski finansijski zapis.

Non-goals: univerzalni ETL, automatsko spajanje po imenu/emailu, import zdravstvenih podataka/dokumenata/slobodnih beleški, background screen-scraping, cross-school migracija, payroll, SSO provisioning, automatski pilot GO.

## 2. Entiteti i polja

Svi ID-jevi su UUID, `*_at` su UTC `TIMESTAMPTZ`, `version` je `BIGINT >=1`, a school business date koristi IANA zonu. Polje je obavezno osim kada piše nullable. Import PII je šifrovan, kratkotrajan i nikada u logu/eventu/telemetry-ju.

### 2.1 `SchoolOnboardingRun`

`id`, `school_id`, `status NOT_STARTED|IN_PROGRESS|READY_FOR_REVIEW|READY|BLOCKED|CANCELLED`, `current_step_key nullable`, `required_step_set_version`, `readiness_snapshot_hash nullable`, `started_by_account_id nullable`, `started_at nullable`, `reviewed_by_account_id nullable`, `reviewed_at nullable`, `cancelled_by_account_id nullable`, `cancelled_at nullable`, `cancel_reason_code nullable`, `blocker_codes text[]`, `version`, `created_at`, `updated_at`. Unique jedan run sa statusom `NOT_STARTED|IN_PROGRESS|READY_FOR_REVIEW|READY|BLOCKED` po School. Ne kreira School; nastaje posle M04 School foundation. NOT_STARTED je sistemski kreirana prazna projekcija bez lažnog startera; prva uspešna `StartOnboarding` komanda postavlja immutable starter/time par.

### 2.2 `OnboardingStepState`

`id`, `school_id`, `run_id`, `step_key enum(SCHOOL_PROFILE,INITIAL_OWNER,STRUCTURE,STAFF,PARTICIPANTS,GROUP_ENROLLMENTS,SCHEDULE,FINANCE_CONFIGURATION,INVITATIONS,READINESS)`, `status NOT_STARTED|IN_PROGRESS|COMPLETED|BLOCKED|SKIPPED_NOT_APPLICABLE`, `owner_module`, `owner_resource_ids jsonb`, `owner_versions jsonb`, `evidence_hash nullable`, `blocker_codes text[]`, `completion_reason_code nullable`, `completed_at nullable`, `completed_by_account_id nullable`, `version`, `created_at`, `updated_at`. Unique `(school_id,run_id,step_key)`. M20 ne prepisuje owner state; status se potvrđuje read portom. Obavezni korak ne može SKIPPED.

### 2.3 `ImportSchemaVersion`

Globalni, release-managed registry; immutable posle publish-a: `id`, `schema_key`, `version_no`, `target_bundle CHILD_GUARDIAN_ENROLLMENT`, `format CSV|XLSX`, `header_contract jsonb`, `field_contract jsonb`, `normalization_rules jsonb`, `max_rows`, `max_file_bytes`, `template_sha256`, `status DRAFT|PUBLISHED|RETIRED`, `content_hash`, `published_at nullable`, `published_by_system_identity nullable varchar(128)`, `retired_at nullable`, `retired_by_system_identity nullable varchar(128)`, `release_evidence_ref nullable`, `release_evidence_hash nullable CHAR(64)`, `version`, `created_at`, `updated_at`. Nema `school_id`: isti potpisani schema ugovor važi za sve tenant-e, ali nijedan school/support API ne može da ga kreira, izmeni, objavi ili povuče. Upis je dozvoljen samo verifikovanom deployment system identity-ju kroz migraciju/release artefakt čiji hash postoji u M21 evidence-u; evidence polja su immutable logical snapshot reference+hash, ne fizički FK/read dependency M20→M21. Aplikaciona DB uloga nema direct DML pravo nad registry tabelom. H0 schema je zaključana u [[05-M20-IMPORT-SCHEMA-V1]]; generički JSON nije dozvola da runtime nagađa tip, requiredness, enum ili normalizaciju. H0 limits: 5.000 data rows, 10 MiB, jedan worksheet, tačno ugovoreni header-i (nikad proizvoljnih 100 poslovnih kolona), cell text max 2.000 Unicode scalar-a; parser nikad ne evaluira formule.

### 2.4 `ImportBatch`

`id`, `school_id`, `schema_version_id`, `requested_by_account_id`, `source_format CSV|XLSX`, `status UPLOADED|SCANNING|PARSING|MAPPING_REQUIRED|VALIDATING|RESOLUTION_REQUIRED|READY_FOR_CONFIRMATION|QUEUED|EXECUTING|CANCEL_REQUESTED|COMPLETED|COMPLETED_WITH_ERRORS|FAILED|CANCELLED|EXPIRED`, `file_hmac CHAR(64)`, `file_hmac_key_version UInt32`, `canonical_content_hmac nullable CHAR(64)`, `canonical_content_hmac_key_version nullable UInt32`, `row_count nullable`, `valid_count UInt32 default 0`, `warning_count UInt32 default 0`, `blocker_count UInt32 default 0`, `confirmed_preview_hash nullable`, `confirmed_by_account_id nullable`, `confirmed_at nullable`, `authorization_version`, `cancel_requested_by_account_id nullable`, `cancel_requested_at nullable`, `terminal_at nullable`, `failure_code nullable`, `expires_at`, `version`, `created_at`, `updated_at`. Fingerprint-i su lowercase tenant-keyed HMAC-SHA-256, ne raw hash potencijalno prepoznatljivog PII fajla: `file_hmac=HMAC-SHA-256(key[version], UTF8("SOKOLA-M20-FILE-V1") || 0x0A || raw_file_bytes)`, a `canonical_content_hmac=HMAC-SHA-256(key[version], UTF8("SOKOLA-M20-CONTENT-V1") || 0x0A || canonical_rows_json_utf8)`. Canonical rows su niz redova sortiranih po `row_number`, svaki u tačnom schema-v1 canonical obliku; filename, format i workbook metadata nisu deo sadržaja. Canonical content HMAC i njegova key verzija su oba null ili oba non-null. Partial unique `(school_id,file_hmac_key_version,file_hmac,schema_version_id) WHERE status IN (UPLOADED,SCANNING,PARSING,MAPPING_REQUIRED,VALIDATING,RESOLUTION_REQUIRED,READY_FOR_CONFIRMATION,QUEUED,EXECUTING,CANCEL_REQUESTED)` sprečava paralelni aktivni duplikat u istoj key verziji; upload tokom key rotacije primenjuje §3.21 i ne može zaobići dedupe promenom verzije. Terminalni ponovni upload sme dobiti novi batch, ali trajni business-key receipt sprečava ponovljen owner upis.

### 2.5 `ImportFileObject`

`id`, `batch_id`, `school_id`, `storage_object_key`, `encryption_key_ref`, `content_type_detected`, `scan_status PENDING|CLEAN|REJECTED|FAILED`, `scan_engine_version nullable`, `scan_failure_code nullable`, `size_bytes UInt64`, `uploaded_at`, `scan_completed_at nullable`, `delete_after`. Unique `(school_id,batch_id)`. PENDING nema scan engine/result vreme; CLEAN zahteva engine+completed time i null failure; REJECTED/FAILED zahtevaju engine+completed time+safe failure code. Privatni object, bez javnog URL-a; raw file TTL max 7 dana posle terminalnog batch-a, kandidat PII max 30 dana, rezultat bez PII prema retention policy-ju.

### 2.6 `ImportColumnMapping`

`id`, `school_id`, `batch_id`, `source_column_index UInt16`, `source_header_ciphertext`, `target_field_key nullable`, `transform_key nullable`, `mapping_status AUTO_EXACT|USER_CONFIRMED|IGNORED`, `confirmed_by_account_id nullable`, `confirmed_at nullable`, `version`, `created_at`, `updated_at`. AUTO_EXACT zahteva target+transform i null confirmation; USER_CONFIRMED zahteva target+transform+confirmation pair; IGNORED zahteva target/transform null i confirmation pair. Jedan source column najviše jednom; svako obavezno target polje tačno jednom. Fuzzy mapping nikad nije AUTO_EXACT.

### 2.7 `ImportRowCandidate`

Staging-only: `id`, `batch_id`, `school_id`, `row_number UInt32`, `import_row_key_ciphertext BYTEA`, `import_row_key_encryption_key_version UInt32`, `import_row_key_digest CHAR(64)`, `import_row_key_digest_key_version UInt32`, `child_external_reference_ciphertext`, `guardian_external_reference_ciphertext`, `canonical_payload_ciphertext`, `candidate_hash CHAR(64)`, `candidate_hash_key_version UInt32`, `status PARSED|VALID|WARNING|BLOCKED|RESOLUTION_REQUIRED|READY|EXECUTED|REJECTED|EXPIRED`, `validation_codes text[]`, `rejected_by_account_id nullable`, `rejected_at nullable`, `executed_at nullable`, `expired_at nullable`, `version`, `created_at`, `updated_at`. Row-key digest je tenant-keyed HMAC-SHA-256 sa domainom `SOKOLA-M20-ROW-KEY-V1`; plaintext key postoji samo u ograničenoj parser memoriji i envelope-encrypted polju, nikad u indeksu/logu/eventu. `candidate_hash` je zasebno domain-separated tenant-keyed HMAC-SHA-256 prema [[05-M20-IMPORT-SCHEMA-V1]], nikad raw SHA nad niskoentropijskim PII i nikad se ne vraća klijentu. `UNIQUE(batch_id,row_number)` i `UNIQUE(batch_id,import_row_key_digest_key_version,import_row_key_digest)`; composite FK `(school_id,batch_id)` mora pripadati istom batch-u. Candidate ne referencira nepostojeću `schema_version_id` kolonu: schema se uzima preko immutable batch-a. Candidate nije Person, nalog, guardian ili enrollment i nije vidljiv drugim modulima pre execute-a.

### 2.8 `DuplicateCandidateMatch`

`id`, `school_id`, `row_candidate_id`, `target_type PERSON|PARTICIPANT_PROFILE|GUARDIAN_RELATION|ENROLLMENT`, `candidate_target_id nullable`, `match_basis enum(EXTERNAL_REFERENCE,IMPORT_ROW_KEY,MANUAL_VERIFIED)`, `confidence_class EXACT|POSSIBLE`, `display_projection_ciphertext`, `status OPEN|LINK_CONFIRMED|CREATE_NEW_CONFIRMED|ROW_REJECTED|STALE`, `resolved_by_account_id nullable`, `resolved_at nullable`, `resolution_reason_code nullable`, `staled_at nullable`, `stale_reason_code nullable`, `expected_target_version nullable`, `version`, `created_at`, `updated_at`. OPEN ima sva resolution/stale polja null. LINK_CONFIRMED, CREATE_NEW_CONFIRMED i ROW_REJECTED su korisničke odluke i zahtevaju resolution actor/time/reason, dok su stale polja null. LINK_CONFIRMED zahteva target ID+expected version; CREATE_NEW_CONFIRMED i ROW_REJECTED zabranjuju target ID. STALE je sistemski prelaz kada target/version više ne važi: zahteva `staled_at+stale_reason_code`, nema korisnički actor/time/reason i zadržava target samo kao opaque istorijsku referencu koja se ne izvršava. Email/ime nisu automatic basis. Possible match zahteva ručnu odluku ovlašćenog aktera; M20 ne spaja Person zapise.

### 2.9 `ImportBusinessKeyReceipt`

Trajni dedupe autoritet preko batch-eva: `id`, `school_id`, `schema_key`, `import_namespace_key`, `import_row_key_ciphertext BYTEA`, `import_row_key_encryption_key_version UInt32`, `target_bundle`, `first_candidate_hash CHAR(64)`, `first_candidate_hash_key_version UInt32`, `effective_status COMMITTED|REJECTED_FINAL`, `owner_receipts jsonb`, `effective_result_hash`, `first_batch_id`, `first_execution_id`, `decided_at`, `version`, `created_at`, `updated_at`. `import_namespace_key` je iz published schema verzije i za H0 je `CHILD_GUARDIAN_ENROLLMENT_V1`; nije korisnički proizvoljan namespace. Plaintext row key se ne čuva; ciphertext služi samo kontrolisanom ponovnom HMAC obračunu/reconciliation-u. Owner receipts sadrže samo owner command/receipt/resource opaque ID i hash, bez PII payload-a.

`ImportBusinessKeyDigestAlias` je lookup/unique autoritet: `id UUID`, `school_id`, `receipt_id`, `digest CHAR(64)`, `digest_key_version UInt32`, `status ACTIVE|RETIRED`, `created_at`, `retired_at nullable`. Digest je `HMAC-SHA-256(tenant_key_version, "SOKOLA-M20-BUSINESS-KEY-V1\n" || schema_key || "\n" || import_namespace_key || "\n" || target_bundle || "\n" || normalized_import_row_key)`. Unique su `(school_id,digest_key_version,digest)` i `(school_id,receipt_id,digest_key_version)`; kompozitni FK vezuje alias i receipt iste škole. ACTIVE ima null `retired_at`, RETIRED ga zahteva. Svaki neistekao receipt ima najmanje jedan ACTIVE alias, a tokom rotacije tačno po jedan za svaku lookup verziju. Alias nema reverzibilan row key i nije poslovni receipt sam za sebe.

Isti business key i isti `candidate_hash`, izračunat ključem čija je verzija zabeležena u `first_candidate_hash_key_version`, vraća prethodni rezultat bez owner poziva. Isti business key i drugi hash je `IMPORT_ROW_KEY_CONFLICT` i zahteva novi, eksplicitno različit `import_row_key` nakon ljudske korekcije; H0 ga ne pretvara u update. `REJECTED_FINAL` se čuva samo kada je red potvrđeno izvršen i owner ga terminalno odbije; pre-confirm staging reject ne zauzima trajni business key.

Pre owner write-a row transakcija pokušava da stekne semantic key kroz insert-on-conflict/row lock nad unique ACTIVE digest aliasom za svaku registry lookup verziju. Ne postoji commitovan `PENDING` receipt: za novu nameru finalni `ImportBusinessKeyReceipt`, svi njegovi potrebni ACTIVE aliasi i COMMITTED/REJECTED_FINAL rezultat nastaju u istoj lokalnoj transakciji sa owner upisima, M20 rezultatom, auditom i outbox-om. Ako konkurent već drži bilo koji alias, zahtev čeka/ponavlja čitanje; posle njegovog commit-a svi izračunati aliasi moraju voditi na isti receipt, pa se vraća isti rezultat za isti hash ili konflikt za drugi hash. Rollback oslobađa claim i ne ostavlja alias, receipt ili lažni durable uspeh.

### 2.10 `ImportExecution` i `ImportRowResult`

Execution: `id`, `batch_id`, `school_id`, `confirmed_preview_hash`, `status QUEUED|RUNNING|CANCEL_REQUESTED|COMPLETED|COMPLETED_WITH_ERRORS|FAILED|CANCELLED`, `lease_token_hash nullable`, `lease_until nullable`, `fencing_token UInt64`, `started_at nullable`, `cancel_requested_at nullable`, `cancel_requested_by_account_id nullable`, `completed_at nullable`, `failure_code nullable`, `total_row_count UInt32`, `created_count UInt32`, `linked_count UInt32`, `duplicate_count UInt32`, `rejected_count UInt32`, `retryable_failure_count UInt32`, `terminal_failure_count UInt32`, `unprocessed_count UInt32`, `version`, `created_at`, `updated_at`. U svakom terminalnom stanju zbir sedam outcome count-a mora biti `total_row_count`; `unprocessed_count` je nenula samo za CANCELLED/FAILED pre obrade svih redova.

Result append-only: `id`, `school_id`, `execution_id`, `row_candidate_id`, `business_key_receipt_id nullable`, `status CREATED|LINKED|SKIPPED_DUPLICATE|REJECTED|FAILED_RETRYABLE|FAILED_TERMINAL`, `owner_receipts jsonb`, `created_resource_ids jsonb`, `error_codes text[]`, `result_hash`, `attempt_no UInt16`, `created_at`. Unique `(execution_id,row_candidate_id,attempt_no)`; partial unique jedan efektivni terminal result po `(execution_id,row_candidate_id)` za `CREATED|LINKED|SKIPPED_DUPLICATE|REJECTED|FAILED_TERMINAL`. CREATED/LINKED/SKIPPED_DUPLICATE zahtevaju business-key receipt; FAILED_RETRYABLE ga nema osim ako owner durable receipt već dokazuje efekat, u kom slučaju retry mora završiti kao dedupe terminal outcome. Nema PII u result/error kodovima.

### 2.11 `ImportCommandReceipt`

`id`, `school_id`, `actor_account_id`, `command_name`, `idempotency_key_hash`, `request_hash`, `outcome SUCCEEDED|REJECTED`, `result_ref nullable`, `response_hash`, `created_at`, `expires_at`. Unique `(school_id,actor_account_id,command_name,idempotency_key_hash)`; SUCCEEDED zahteva result ref, REJECTED ga ima null; minimum 30 dana.

### 2.11a `ImportIssueReport` i download autorizacija

`ImportIssueReport`: `id`, `school_id`, `batch_id`, `requested_by_account_id`, `authorization_version`, `source_batch_version UInt64`, `source_issue_set_hash CHAR(64)`, `status QUEUED|BUILDING|AVAILABLE|FAILED|EXPIRED|REVOKED`, `build_job_execution_id nullable UUID`, `build_fencing_token nullable UInt64`, `row_count nullable UInt32`, `storage_object_key nullable`, `encryption_key_ref nullable`, `content_sha256 nullable`, `failure_code nullable`, `available_at nullable`, `expires_at nullable`, `revoked_at nullable`, `revocation_reason_code nullable`, `version`, `created_at`, `updated_at`. `source_issue_set_hash` kanonski pokriva batch/schema/mapping/validation generation i sortirane parove `(row_number,column_key?,error_code)`; ne sadrži raw vrednost, external reference ili PII. Partial unique `(school_id,batch_id,requested_by_account_id,authorization_version) WHERE status IN (QUEUED,BUILDING,AVAILABLE)` sprečava paralelne aktivne kopije, dok command receipt rešava retry.

BUILDING zahteva oba build polja i M21 fencing proveru; AVAILABLE zadržava build dokaz i zahteva row/object/key/hash/available i `expires_at=available_at+24h`; FAILED zahteva bezbedan failure code i nema object/key/hash; EXPIRED zadržava dokaznu metadata-u, ali objekat više ne postoji; REVOKED zahteva revoke vreme+reason i nema byte pristupa. Ostala stanja nemaju downloadable rezultat. H0 report sadrži samo `row_number`, opcioni schema `column_key` i zatvorene error code-ove; nema external reference, imena, kontakta, datuma rođenja, raw ćelije ili canonical payload-a.

`ImportIssueDownloadTicket`: `ticket_digest`, `school_id`, `report_id`, `account_id`, `authorization_version`, `issued_at`, `expires_at` najviše 60s, `used_at nullable`, `status ACTIVE|USED|EXPIRED|REVOKED`, `version`; PK `(school_id,ticket_digest)`. `ImportIssueDownloadSession`: `session_digest`, `school_id`, `report_id`, `account_id`, `authorization_version`, `status ACTIVE|COMPLETED|EXPIRED|REVOKED`, `issued_at`, `expires_at` najviše 10min bez produženja, `last_range_at nullable`, `completed_at nullable`, `version`; PK `(school_id,session_digest)`. Consume ticket-a atomski pravi najviše jednu sesiju; svaki byte/range zahtev ponavlja M01/M03/M05, batch/report tenant, `school.import.manage`, current authorization version i report TTL. Nema javnog/trajnog URL-a ni tokena u logu.

### 2.12 Conditional-null i lifecycle CHECK matrica

- Onboarding NOT_STARTED ima `current_step_key`, starter/time, readiness/review/cancel polja null i prazne blocker-e. IN_PROGRESS/READY_FOR_REVIEW/READY/BLOCKED zahtevaju immutable starter/time par; READY_FOR_REVIEW/READY zahtevaju readiness hash, review actor/time je obavezan samo za READY; BLOCKED jedini zahteva non-empty blocker-e; CANCELLED zahteva starter/time i cancel actor/time/reason, nema readiness/review polja i terminalan je. COMPLETED step zahteva evidence hash i completion pair, a `completion_reason_code=NULL`; SKIPPED_NOT_APPLICABLE zahteva completion pair + `completion_reason_code` i zabranjuje evidence hash; BLOCKED step jedini ima blocker-e; ostala stanja imaju completion pair/reason null. `blocker_codes` nisu skip reason.
- Schema DRAFT ima publish/retire system-identity vremena i oba release-evidence polja null; PUBLISHED zahteva publish pair i verifikovan M21 `release_evidence_ref+release_evidence_hash`; RETIRED zahteva publish, release-evidence i retire pair. Objavljeni header/field/normalization JSON tačno hashira dokument [[05-M20-IMPORT-SCHEMA-V1]]. Runtime school/support credential i aplikaciona DB rola ne mogu napraviti nijednu od tih tranzicija.
- Batch QUEUED/EXECUTING/CANCEL_REQUESTED/COMPLETED* zahteva confirmation actor/time/hash; CANCEL_REQUESTED i CANCELLED zahtevaju cancel actor/time par, dok drugi statusi taj par zabranjuju; svaki terminalni status zahteva `terminal_at`; FAILED zahteva failure code. Drugi statusi ne smeju izmišljati ova polja. `row_count` postaje non-null od završetka PARSING i counts su uvek nenegativni.
- Candidate REJECTED zahteva `rejected_by_account_id+rejected_at` i druga terminalna vremena null; EXECUTED zahteva samo `executed_at`; EXPIRED zahteva samo `expired_at`; ostala stanja sva ova polja imaju null. Staging expiry ne briše trajni business-key receipt ili owner podatak.
- Execution QUEUED nema lease/start/complete; RUNNING jedini ima lease hash/until i started time; CANCEL_REQUESTED i CANCELLED zahtevaju isti immutable cancel actor/time par, a drugi statusi ga zabranjuju. CANCEL_REQUESTED može zadržati aktivan lease samo do završetka otvorene row transakcije; terminalna stanja nemaju lease i zahtevaju completed time. FAILED zahteva failure code; ostala terminalna stanja ga imaju null.
- IssueReport QUEUED nema build/object/result polja; BUILDING ima samo job execution/fencing dokaz; AVAILABLE ima kompletan encrypted object/hash/count/time/TTL skup i nema failure/revoke polja; FAILED ima samo build dokaz+failure; EXPIRED briše object/key i ima istekao TTL; REVOKED ima revoke pair i nema object/key. DB CHECK odbija svaku drugu kombinaciju.

## 3. Pravila, invarijante i edge cases

1. Upload zahteva M01/M03/M04/M05 `school.import.manage`; execute dodatno zahteva `school.import.execute` i owner prava `school.people.manage`, `school.memberships.manage`, `school.guardians.manage`, `school.guardians.primary_contact.manage`, `school.groups.enrollments.manage`. Za batch >500 redova traži se svež step-up. Provera kompletnog skupa prava završava pre prvog row claim-a i svaki owner port je ponavlja za svoj resurs.
1a. Onboarding read/manage/review zahtevaju redom `school.onboarding.view`, `school.onboarding.manage`, `school.onboarding.review`; controlled recovery zahteva `school.import.recovery`. Tačni role binding-i/delegacija su u M05 registru; nijedan permission nije impliciran drugim.
2. MIME, extension i magic bytes moraju se slagati; ZIP bomb, macro, formula, external link, embedded object, password/encryption, hidden worksheet ili više worksheet-a se odbija.
3. CSV: UTF-8 sa opcionim BOM; delimiter mora biti eksplicitno detektovan iz dozvoljenog `, ; tab`, jedna konzistentna vrednost; nevalidan UTF-8 blokira. XLSX shared strings/cells se parsiraju bez formula evaluation-a.
4. Normalizacija ne menja identitet: pravila su po polju zaključana u [[05-M20-IMPORT-SCHEMA-V1]]; nema locale guessing-a. Ime/email nikad ne služe auto-link-u. School-local external reference i `import_row_key` su case-sensitive posle NFKC+outer trim-a. Normalizovani row key se odmah enkriptuje i HMAC-uje; ne postoji plaintext DB kolona.
5. Preview hash pokriva schema/version, `file_hmac`+verziju, mappings, sve candidate hash-eve+verzije, resolutions i owner target versions. Bilo kakva promena ga invalidira.
6. Confirm bez `blocker_count=0`, rešenih possible duplicates i svežih target versions je 409/422. Warning zahteva eksplicitni accepted warning set hash.
7. Execute nikad ne koristi preview podatak kao owner master. Ponovo autorizuje, učitava targete i poziva M06→M07→M09 owner portove determinističkim redosledom.
8. Jedan row je lokalna all-or-nothing transakcija za dete/profile, guardian relation i enrollment. Failure ne ostavlja polovičnu vezu. Različiti redovi mogu imati različit rezultat; batch zato može COMPLETED_WITH_ERRORS.
9. Cross-row shared guardian se zaključava po dokazivom external reference/manual target ID-u; nema duplicate Person pod paralelnim worker-ima.
10. Worker-i particionišu `row_number` range, claim-uju `SKIP LOCKED`/ekvivalent i koriste lease+fencing. Pre owner poziva unutar iste row transakcije stiču unique semantic key prema §2.9; durable final receipt commit-uje samo zajedno sa owner rezultatom, nikad pre njega.
11. Retry terminalno uspešnog reda, ponovni execution ili isti red u drugom batch-u vraća trajne owner receipts kada je `candidate_hash` isti pod key verzijom trajnog receipt-a; ne pravi novi owner zapis. Isti business key sa drugim payload hash-em je 409 konflikt, ne update i ne „poslednji pobeđuje“.
12. H0 import nema update režim. Existing exact/manual target može biti samo `LINKED`; razlika u imenu, kontaktu, authority činjenici ili enrollment scope-u blokira red i menja se kasnije kroz eksplicitnu owner komandu M06/M07/M09 sa sopstvenim permission-om, expected version-om i auditom.
13. Pozivi roditeljima su zaseban naknadni M02 tok; import rezultat ne šalje email/notifikaciju.
14. Cancel pre execute-a je dozvoljen. Cancel nad Batch `QUEUED|EXECUTING` i njegovim Execution `QUEUED|RUNNING` atomarno postavlja oba u `CANCEL_REQUESTED`; worker pre svakog claim-a i neposredno pre owner transakcije proverava oba statusa. Novi claim/write prestaje, već otvorena lokalna row transakcija sme završiti, zatim execution i batch prelaze `CANCELLED`; već commitovani redovi ostaju i svih `total_row_count` redova ulazi u tačno jedan outcome count, uključujući `unprocessed_count`. Nema blanket DB rollback-a preko commitovanih owner zapisa.
15. „Undo import” nije delete. Controlisana recovery komanda sme deaktivirati samo resurse kreirane tim batch-em koji nemaju kasnije reference/promene, uz owner expected version, reason, audit i row rezultat; ostalo ide manual remediation.
16. Rejected rows report je šifrovan, single-use, TTL 24h; sadrži row_number, external_reference ako je dozvoljen i error code, ne nepotrebni payload.
17. Onboarding READY je izveden iz svežih owner facts: ACTIVE School, initial owner accepted/active, najmanje jedan program+group, osoblje dodeljeno, participant/enrollment, najmanje jedan budući termin, finance config ako entitlement zahteva, obavezni dokument/privacy config i nula critical blocker-a. Ne znači pilot/legal GO.
18. Initial owner: M04 kreira foundation/nomination, M02 poziv, M01 nalog/identity posle dokaza, M06 membership, M05 role. M20 samo prikazuje stanje; ne kreira prečicu/javnu registraciju/kod škole.
19. Import i onboarding su online-only; nema IndexedDB raw fajla/candidate-a i nema optimistic final success-a.
20. M18 ne broji candidate preview kao participant; projection tek posle owner commit-a/watermark-a.
21. HMAC/key rotacija je tenant-scoped i fail-closed: registry stanje je `STABLE|PREPARING|DUAL_READ|CUTOVER`; najviše su dve digest lookup verzije aktivne. PREPARING batched decrypt→rehash postojećih receipt ključeva u nove `ImportBusinessKeyDigestAlias` redove bez logovanja plaintexta. Novi candidate koristi trenutnu write verziju; novi receipt tokom PREPARING/DUAL_READ mora dobiti ACTIVE alias za obe lookup verzije ili ceo row commit pada. File-upload dedupe računa HMAC za obe lookup verzije, ali čuva write verziju; ako bilo koja pronađe aktivni isti batch, vraća se taj batch. Različiti receipt-i za dva digest-a ili digest/payload mismatch su integrity incident i blokiraju tenant import. CUTOVER je pod kratkim tenant import-write lock-om: verifier dokazuje 100% alias backfill, file/batch reconciliation i unique bez konflikta, pa tek onda menja write verziju. Stari alias se označava RETIRED tek po isteku dual-read prozora; stari row-key digest i candidate-HMAC ključ ne uklanjaju se iz verifikacionog key store-a dok ijedan neistekao candidate/receipt referencira njihovu verziju. Rollback pre CUTOVER vraća STABLE na staru verziju; posle CUTOVER povratak je nova kontrolisana rotacija, nikad brisanje novih digest-a naslepo.

| Edge case | Ishod |
|---|---|
| Isti file upload dvaput dok je prvi aktivan | Vraća isti aktivni batch/receipt; ne parsira drugi put. |
| Isti red u novom terminalnom batch-u | Trajni business-key receipt vraća isti owner rezultat bez owner poziva. |
| Dva reda isti child key, različit payload | BLOCKED conflict; nema „poslednji pobeđuje”. |
| Guardian postoji globalno u drugoj školi | Ne linkuje emailom; samo dokaziv owner/manual target tok; nova school veza odvojena. |
| Group ugašena posle preview-a | Target version mismatch; row ne izvršava. |
| Worker padne posle owner commit-a | Receipt omogućava retry bez duplikata. |
| 499 valid, 1 invalid | Invalid je blocker pre confirmation ako nije eksplicitno rejected; execute samo confirmed READY skup. |
| Formula ćelija daje vidljivu vrednost | Fajl se odbija; cached value se ne prihvata. |
| Cancel usred 5.000 redova | Commitovani rezultati ostaju; novi claim prestaje; tačan count. |

## 4. Tenant/security/privacy

Pipeline: session → server tenant context → ACTIVE School/entitlement → import permission → batch/file school composite guard → M17 retention/purpose → owner resource/subject guards. Cross-tenant ID/file/job/report daje safe 404 bez count/timing leak-a. Storage key počinje nepredvidivim tenant namespace-om; download ticket single-use i reautorizovan.

Raw/candidate PII envelope-encrypted; keys odvojene; logs/outbox/jobs/dead-letter/telemetry samo opaque batch/row ID, schema/version, count bucket i error code. Antivirus parser radi u sandboxu bez mreže, sa CPU/memory/time limitom. Filename se ne loguje/renderuje bez encoding-a. CSV/XLSX formula injection se neutralizuje i u rejected reportu.

## 5. Lifecycle

Batch prelazi redom `UPLOADED→SCANNING→PARSING→MAPPING_REQUIRED?→VALIDATING→RESOLUTION_REQUIRED?→READY_FOR_CONFIRMATION→QUEUED→EXECUTING→COMPLETED|COMPLETED_WITH_ERRORS`; failure u scan/parser/validation/execution orkestraciji je FAILED; pre QUEUED može direktno CANCELLED; `QUEUED|EXECUTING→CANCEL_REQUESTED→CANCELLED`; TTL bilo kog pre-confirm neterminalnog stanja daje EXPIRED. FAILED/CANCELLED/EXPIRED/COMPLETED* su terminalni. `CANCEL_REQUESTED` nije terminalan i ne može nazad u EXECUTING.

Execution: `QUEUED→RUNNING→COMPLETED|COMPLETED_WITH_ERRORS|FAILED`; `QUEUED|RUNNING→CANCEL_REQUESTED→CANCELLED`. RUNNING može ostati dok već otvorena row transakcija završi; nakon cancel request-a ne sme claim-ovati/otvoriti novu. COMPLETED zahteva nula rejected/retryable/terminal-failure/unprocessed; COMPLETED_WITH_ERRORS zahteva najmanje jedan rejected ili terminal failure i nula retryable/unprocessed; FAILED/CANCELLED mogu imati unprocessed, ali zbir outcome-a uvek mora biti total. Execution ne završava dok postoji FAILED_RETRYABLE red koji nije prešao u terminalan rezultat ili iscrpeo attempts.

Row: `PARSED→VALID|WARNING|BLOCKED|RESOLUTION_REQUIRED→READY→EXECUTED`; row može REJECTED od ovlašćenog aktera. READY postaje BLOCKED ako target version zastari pre execute-a. Result je append-only.

Onboarding: `NOT_STARTED→IN_PROGRESS→READY_FOR_REVIEW→READY`; IN_PROGRESS/READY_FOR_REVIEW mogu BLOCKED, a BLOCKED→IN_PROGRESS posle re-evaluation; `IN_PROGRESS|READY_FOR_REVIEW|BLOCKED→CANCELLED`. NOT_STARTED se ne „otkazuje” sa izmišljenim starterom, a READY nije cancellation target. READY se povlači u IN_PROGRESS/BLOCKED ako owner fact kasnije više ne važi; current projection tada čisti readiness/review polja, dok prethodni snapshot hash, actor i vreme ostaju u immutable audit/receipt istoriji.

`OnboardingStepState`: `NOT_STARTED→IN_PROGRESS→COMPLETED|BLOCKED|SKIPPED_NOT_APPLICABLE`; `BLOCKED→IN_PROGRESS`; COMPLETED/SKIPPED mogu pre READY run-a ponovo postati IN_PROGRESS/BLOCKED samo kada owner version/hash dokaz promeni činjenicu, uz audit i novu run readiness verziju. SKIPPED je dozvoljen isključivo za korak koji `required_step_set_version` označava opcionim. Run/step su izvedene progress projekcije; owner facts i njihovi receipts ostaju autoritet i nijedna regresija ne briše prethodni audit/evidence hash.

`ImportColumnMapping`: parser može kreirati `AUTO_EXACT`; ovlašćeni actor pre confirm-a može `AUTO_EXACT|IGNORED→USER_CONFIRMED`, `AUTO_EXACT|USER_CONFIRMED→IGNORED` samo za opciono target polje, ili promeniti USER_CONFIRMED target uz expected version. Svaka promena posle validacije atomarno vraća Batch u MAPPING_REQUIRED, invalidira candidate/resolution/preview izvedene iz stare mape i zahteva novu validaciju; posle ConfirmImport mapping je immutable. Fuzzy/ambiguous vrednost nikada ne prelazi u AUTO_EXACT.

`DuplicateCandidateMatch`: `OPEN→LINK_CONFIRMED|CREATE_NEW_CONFIRMED|ROW_REJECTED`; `OPEN|LINK_CONFIRMED→STALE` kada owner target/version više nije važeći. LINK/CREATE/REJECT su eksplicitne odluke koje se ne prepisuju posle ConfirmImport; promena pre confirm-a stvara novu resolution generaciju i invalidira preview hash. STALE i odluke korišćene u potvrđenom preview-u su terminalne; nema izvršenja stale targeta.

`ImportIssueReport`: `—→QUEUED→BUILDING→AVAILABLE|FAILED`; QUEUED/BUILDING/AVAILABLE mogu u REVOKED na access/batch disposition, AVAILABLE prelazi u EXPIRED na TTL. FAILED/EXPIRED/REVOKED su terminalni. Download ticket: `—→ACTIVE→USED|EXPIRED|REVOKED`; session: `—→ACTIVE→COMPLETED|EXPIRED|REVOKED`. Dva consume-a istog ticket-a stvaraju najviše jednu ACTIVE session, a svaki range ponavlja autorizaciju.

`RequestImportIssueReport` je dozvoljen samo kada batch ima najmanje jedan issue i nalazi se u stabilnom stanju `RESOLUTION_REQUIRED`, `READY_FOR_CONFIRMATION`, `COMPLETED_WITH_ERRORS`, `FAILED` ili `CANCELLED`. U jednoj transakciji ponovo proverava M01/M03/M05, batch tenant/status/version, izračunava `source_issue_set_hash`, kreira QUEUED report+receipt+audit i `ImportIssueReportRequestedV1`. Ne gradi fajl u HTTP request-u.

M21 `import.issue_report_generate` consumer claim-uje QUEUED red preko JobExecution lease/fencing ugovora, prelazi ga u BUILDING i u read-only repeatable-read snapshot-u ponovo računa tačan source hash. Neusklađena batch verzija/hash atomarno menja `BUILDING→FAILED` sa `failure_code=IMPORT_REPORT_SOURCE_CHANGED`, bez object/key/hash/available polja; FAILED je terminalan i novi zahtev mora dobiti novi receipt nad aktuelnim source hash-em. Worker pre prvog reda i neposredno pre AVAILABLE commit-a ponavlja current account/session-state, M03 tenant, M05 `school.import.manage`, authorization version, batch visibility i M17 restriction; revoke ili gubitak prava daje REVOKED `AUTHORIZATION_CHANGED` i briše privremeni object. Validan worker bounded-memory stream-uje samo H0 allow-list kolone u privatni envelope-encrypted object, proverava content hash, zatim AVAILABLE+audit+outbox commit-uje samo uz aktuelni fencing token. Stale worker ne može objaviti ili vratiti terminalni report; nepotpun object se briše cleanup-om.

`import.expiry_cleanup` je jedini owner cleanup za raw fajlove, staging candidate-e i issue-report artefakte: na TTL-u čini report EXPIRED, opoziva ACTIVE ticket/session, briše finalni i nereferencirani privremeni object uz durable deletion receipt. Request-time report/ticket/session TTL i authorization guard blokiraju byte i pre job-a; cleanup nije grace period.

## 6. Error catalog

| Code | HTTP | Značenje |
|---|---:|---|
| `IMPORT_UNAUTHENTICATED` | 401 | Nevažeća sesija. |
| `IMPORT_FORBIDDEN` | 403 | Nema permission/step-up. |
| `IMPORT_NOT_FOUND_SAFE` | 404 | Skriven/cross-tenant resurs. |
| `IMPORT_FILE_TOO_LARGE` | 413 | Prelazi 10 MiB/row limit. |
| `IMPORT_FILE_TYPE_INVALID` | 415 | MIME/magic/format konflikt. |
| `IMPORT_FILE_UNSAFE` | 422 | Malware/macro/formula/link/object/bomb. |
| `IMPORT_ENCODING_INVALID` | 422 | CSV nije validan UTF-8. |
| `IMPORT_SCHEMA_UNSUPPORTED` | 422 | Template/schema nije aktivna. |
| `IMPORT_MAPPING_INVALID` | 422 | Nedostaje/dupliran mapping. |
| `IMPORT_ROW_INVALID` | 422 | Row field validation. |
| `IMPORT_DUPLICATE_UNRESOLVED` | 409 | Possible duplicate nije rešen. |
| `IMPORT_ROW_KEY_CONFLICT` | 409 | Isti key, drugi payload. |
| `IMPORT_BUSINESS_RECEIPT_CORRUPT` | 500 | Receipt i owner rezultat se ne poklapaju; bez ponovnog owner write-a. |
| `IMPORT_PREVIEW_STALE` | 409 | Hash/target version promenjen. |
| `IMPORT_BLOCKERS_PRESENT` | 409 | Confirmation nije dozvoljen. |
| `IMPORT_IDEMPOTENCY_CONFLICT` | 409 | Isti request key, drugi hash. |
| `IMPORT_VERSION_CONFLICT` | 409 | CAS konflikt. |
| `IMPORT_EXECUTION_IN_PROGRESS` | 409 | Aktivna fenced execution. |
| `IMPORT_CANCELLED` | 410 | Batch otkazan. |
| `IMPORT_EXPIRED` | 410 | Batch/file/report istekao. |
| `IMPORT_REPORT_NOT_AVAILABLE` | 409 | Report nije AVAILABLE ili source nema dozvoljen issue snapshot. |
| `IMPORT_REPORT_SOURCE_CHANGED` | 409 | Batch/version/issue set se promenio posle zahteva; nema objavljenog objekta. |
| `IMPORT_REPORT_REVOKED` | 410 | Report/ticket/session je opozvan; nema byte pristupa. |
| `IMPORT_STORAGE_FAILED` | 503 | Privatni object nije durable. |
| `IMPORT_SCANNER_UNAVAILABLE` | 503 | Scan fail-closed. |
| `IMPORT_PARSER_LIMIT` | 422 | CPU/memory/time/cell limit. |
| `ONBOARDING_BLOCKED` | 409 | Readiness ima blocker. |
| `IMPORT_INTERNAL_SAFE` | 500 | Bez PII/stack leak-a. |
| `IMPORT_CONDITIONAL_STATE_INVALID` | 422 | Status i lifecycle/lease/count polja nisu konzistentni. |

## 7. API, concurrency i NFR

Commands: `StartOnboarding`, `CancelOnboarding`, `ReevaluateReadiness`, `UploadImport`, `SetColumnMappings`, `ValidateImport`, `ResolveDuplicate`, `RejectRow`, `ConfirmImport`, `CancelImport`, `RetryFailedRows`, `RequestControlledImportRecovery`, `RequestImportIssueReport`, `IssueImportIssueDownloadTicket`, `ConsumeImportIssueDownloadTicket`. Queries: `GetOnboarding`, `GetImportTemplate`, `GetBatch`, `GetImportPreview`, `GetImportProgress`, `ListRowIssues`, `GetImportIssueReport`, `DownloadImportIssueReportRange`. `ImportSchemaVersion` namerno nema runtime CRUD komandu; menja se samo verifikovanim release/migration putem iz §2.3. Zahtev i consume ticket-a su write komande sa receipt-om; byte-range je query koji pri svakom pozivu ponavlja sve guardove.

Svaki write ima idempotency key/hash/receipt i expected version. Confirmation potpisuje exact preview hash. Execution row transakcija uključuje owner writes+owner receipts+trajni business-key receipt+M20 result+audit+outbox. H0 zahteva zajedničku lokalnu transakciju modularnog monolita preko owner portova. Ako postojeći repo to još ne podržava, implementira se lokalni transakcioni coordinator pre aktivacije importa; nedovršena saga nije dozvoljena zamena za row all-or-nothing ugovor. Worker u bazi čuva samo digest lease tokena; raw lease credential postoji samo u memoriji aktuelnog worker-a i nikad u logu/dead-letteru.

Referentni profil `SOKOLA-NFR-IMPORT-V1`: 4 vCPU/8 GiB worker pool; PostgreSQL ekvivalent sa 4 vCPU/16 GiB; encrypted object store u istoj regiji; zvanični schema-v1 fixture sa 70% novih, 20% exact-link, 10% warning/redova, 20 shared staratelja, bez malware-a; file 10 MiB ili manje; dva aktivna tenanta. Upload je streaming, parser bounded-memory. Ciljevi: 500 redova validation preview p95≤60s; 1.000 p95≤120s ili background koji u ≤3s vraća durable job/progress ref; 5.000 obavezno background; process RSS ≤512 MiB po parser worker-u; max 4 worker-a po batch-u i najmanje jedan fair queue slot za drugi tenant. Progress je monoton po committed rezultatima. UI cursor 25/max100. Dokaz mora sadržati commit/config/schema/template/dataset hash, 30 merenih prolaza posle pet warm-up prolaza, raw percentile/memory/queue-fairness rezultat; cilj nije dostignut bez dokaza.

## 8. Audit, events, migration i acceptance

Audit: upload hash/schema, mapping/duplicate odluke, confirm preview hash, execute/cancel/retry/recovery, onboarding readiness i issue-report request/build outcome/revoke/expire/ticket consume; bez PII. Outbox: `ImportBatchConfirmedV1`, `ImportRowCommittedV1` (opaque IDs/result code), `ImportCompletedV1`, `OnboardingReadinessChangedV1`, `ImportIssueReportRequestedV1` i `ImportIssueReportAvailableV1`. Issue-report događaji nose samo school/report/batch opaque ID, source hash/version i authorization version; nikad issue redove ili object credential. M20 ne emituje owner događaj umesto owner modula.

Brownfield: repo-first inventar; postojeći import `PRESERVE|ADAPT|REMOVE_CONFLICT`; nikad legacy red prvoj školi/Person po imenu; shadow parse zvaničnih template-a; backfill trajnog business-key receipt-a samo iz dokazivih starih import receipts, inače bez nagađanja; failure injection; backup pre cutover; forward recovery za schema. Acceptance: oba formata isti candidate hash; security parser; duplicate/manual; cross-batch business dedupe; per-row atomicity/retry; cancel/recovery; tenant/storage/privacy; 5k performance; onboarding owner/initial invite/readiness; 100% QA bez skipped/flaky.
