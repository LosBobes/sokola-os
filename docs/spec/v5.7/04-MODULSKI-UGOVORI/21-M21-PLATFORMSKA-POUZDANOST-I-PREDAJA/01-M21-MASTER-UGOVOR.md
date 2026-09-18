---
tip: modulni-implementacioni-ugovor
modul-id: M21
naziv: Audit, outbox, jobs, telemetry, backup/restore, QA i handover
status: SPEC_CANDIDATE
revizija: "2.1"
datum: 2026-09-16
schema-zavisnosti: [M04]
read-portovi: [M01, M03, M04, M05]
application-policy-portovi: [M17]
application-guardovi: [M01, M03, M05]
izlazni-portovi-za: [M22, M23, M24, M25, M26, M27, M28, M29, M30, M31, M32, M33, M34]
offline-policy: DENY
horizont: H0_MVP_REQUIRED_AND_H2_PILOT_READINESS
---

# M21 — Platformska pouzdanost i predaja

## 1. Cilj i granice

M21 standardizuje append-only audit, transactional outbox transport, background jobs, dead-letter/replay, PII-free telemetry, health/alerts, konfiguracione guardove, backup/restore dokaz, migration/deploy/rollback i programerski handover. Poslovni modul ostaje vlasnik svog događaja i upisuje outbox u istoj transakciji; M21 poseduje transport/operativni lifecycle.

M21 nije SIEM, data warehouse, accounting ledger, business workflow, support impersonation, pravni/compliance sertifikat, zero-downtime obećanje bez dokaza ili zamena za owner audit odluku. Ne loguje sadržaj dece radi „debugging-a”.

## 2. Entiteti i polja

Svaki deklarisani surrogate `id` je UUID; audit/time-sortable ID može biti UUIDv7 ili dokazivo ekvivalentan. Registry/head entitet bez surrogate ID-a koristi tačno deklarisan stabilni prirodni ključ i nije izuzetak koji aplikacija sme proizvoljno proširiti. Svi `*_at`, `*_until`, `*_after` i `db_point_in_time` su UTC `TIMESTAMPTZ`; `version` je `BIGINT >=1`; hash je lowercase `CHAR(64)`. Polje je obavezno osim kada piše nullable. Tenant-bound red sa surrogate ID-em ima `school_id`, `UNIQUE(school_id,id)` i kompozitne tenant FK-ove; nullable School važi samo za registry-allow-listed PLATFORM scope.

### 2.0a Kanonski byte/hash/potpis ugovor

`CanonicalJsonV1` je RFC 8785 JCS nad objektom koji je prethodno prošao svoju zatvorenu schema verziju. UUID je lowercase string; UTC vreme je RFC3339 string sa tačno šest decimalnih cifara i sufiksom `Z`; `NUMERIC(18,2)` je string sa tačno dve decimale; binary je base64url bez padding-a; dozvoljeni null se emituje kao `null`, a odsutno opciono polje se izostavlja. Rezultat je UTF-8 bez BOM-a i bez završnog newline-a. Nevalidan Unicode, nepoznato polje, `NaN`/infinity, binary float za novac ili nepoznata schema verzija blokiraju hashiranje i poslovni commit.

`HashV1(domain,value) = lowercase_hex(SHA-256(UTF8(domain) || 0x0A || CanonicalJsonV1(value)))`. Domain je tačan ASCII literal naveden ispod; ne prosleđuje se iz klijenta. Kontrolni vektor je `domain=SOKOLA-CANONICAL-TEST-V1`, value `{"a":1,"b":"x"}`, bez završnog newline-a, i mora dati `a86c94641070bd858e558d02644c8f398c3169541d8cb423278060b8dd302da2` u svakom podržanom runtime-u. Neusaglašen vektor je startup/release blocker.

### 2.1 `AuditEvent`

Append-only: `id`, `occurred_at`, `recorded_at`, `scope_kind SCHOOL|PLATFORM`, `school_id nullable`, `actor_type USER|SYSTEM|SUPPORT`, `actor_account_id nullable`, `support_access_id nullable`, `action_code`, `resource_type`, `resource_id` opaque, `outcome SUCCESS|DENIED|FAILED`, `reason_code nullable`, `correlation_id`, `request_id`, `authorization_version nullable`, `before_fingerprint nullable`, `after_fingerprint nullable`, `metadata_allowlist jsonb`, `audit_chain_key`, `partition_key`, `sequence_no UInt64`, `previous_hash nullable`, `event_hash`, `retention_policy_version_id`. SCHOOL zahteva school_id, PLATFORM ga zabranjuje. USER zahteva account i null support access; SUPPORT zahteva oba; SYSTEM zahteva oba null. DENIED/FAILED zahtevaju zatvoren reason, SUCCESS ga ima samo ako action schema izričito dozvoljava. `shard = first_uint16_be(SHA-256(UTF8("SOKOLA-AUDIT-SHARD-V1") || 0x0A || CanonicalJsonV1({"resource_id":resource_id,"resource_type":resource_type}))) mod 16`; stabilni `audit_chain_key=(school_or_PLATFORM,shard_0..15)`, a mesečni `partition_key=(audit_chain_key,UTC_YYYY_MM(recorded_at))`; za platform event `school_or_PLATFORM='PLATFORM'`. `sequence_no` je monoton od 1 unutar jednog partition-a, `previous_hash` je null samo za sequence 1 tog partition-a, a unique je `(partition_key,sequence_no)`. Serializovan/CAS partition-head određuje redosled. `event_hash=HashV1("SOKOLA-AUDIT-EVENT-V1", kompletan allow-listed AuditEvent objekat bez event_hash)`, pa hash uključuje `previous_hash`, sequence, tenant/scope, actor, resource, outcome, vremena i retention policy. Nema update/delete regularnim API-jem. Hash chain je tamper-evidence, ne blockchain i ne dokazuje da događaj nikad nije izostavljen; completeness se prati business/audit/outbox contract testom, dok seal lanac ispod povezuje uzastopne neprazne mesečne segmente istog `audit_chain_key`.

### 2.1a `AuditSegmentSeal` i `AuditSegmentVerification`

`AuditSegmentSeal` je append-only immutable dokaz koji nastaje tek po zatvaranju perioda: `id`, `scope_kind SCHOOL|PLATFORM`, `school_id nullable`, `audit_chain_key`, `partition_key`, `period_start_utc`, `period_end_utc`, `first_sequence_no UInt64`, `last_sequence_no UInt64`, `event_count UInt64`, `first_event_hash`, `last_event_hash`, `segment_digest`, `previous_segment_seal_hash nullable`, `seal_hash`, `signature_algorithm`, `signing_key_id`, `signature`, `sealed_at`, `retention_policy_version_id`, `created_at`. SCHOOL zahteva non-null `school_id`, PLATFORM ga zabranjuje; scope/school moraju biti jednaki svim AuditEvent redovima segmenta i izvedenom `audit_chain_key`. Unique `(partition_key)`, a SCHOOL red izlaže i `UNIQUE(school_id,id)` za tenant-safe potomke. Period je tačno UTC kalendarski mesec iz partition key-a; count je `>=1`, prvi sequence je 1, a poslednji sequence i count moraju odgovarati ponovnom čitanju celog segmenta. Prazan segment se ne kreira. Prvi neprazan mesečni segment datog `audit_chain_key` ima null previous seal; svaki naredni neprazan mesec pokazuje na `seal_hash` neposredno prethodnog zapečaćenog nepraznog segmenta istog scope-a i chain-a, čak i kada između postoje prazni meseci. Segment se ne zapečaćuje dok prethodni neprazan segment istog chain-a nije zapečaćen.

`segment_digest=HashV1("SOKOLA-AUDIT-SEGMENT-V1", {audit_chain_key,partition_key,period_start_utc,period_end_utc,first_sequence_no,last_sequence_no,event_count,event_hashes})`, gde je `event_hashes` uređeni niz svih lowercase hash-eva po `sequence_no`. `signature_algorithm` je za H0 tačno `ED25519`. `seal_hash=HashV1("SOKOLA-AUDIT-SEAL-V1", kompletan seal objekat bez seal_hash i signature)`, pa uključuje previous seal, algorithm i signing key ID. `signature` je base64url-bez-padding Ed25519 potpis nad 32 raw byte-a dekodiranog `seal_hash`-a. Managed private key nije dostupan aplikacionom read/write korisniku; javni ključ i algoritam ostaju dostupni za verifikaciju najmanje koliko i seal. Seal i potpis se više nikad ne menjaju.

`AuditSegmentVerification` je zaseban append-only rezultat provere: `id`, `scope_kind SCHOOL|PLATFORM`, `school_id nullable`, `seal_id`, `verification_no UInt32`, `outcome VERIFIED|CORRUPT`, `check_set_version`, `verified_at`, `verified_by_system_identity`, `failure_code nullable`, `computed_segment_digest`, `computed_previous_seal_hash nullable`, `previous_verification_hash nullable`, `verification_hash`, `created_at`; unique `(seal_id,verification_no)`. Scope/school su obavezno jednaki seal-u; SCHOOL koristi composite FK `(school_id,seal_id)`, a PLATFORM provereni platform-scope FK/equivalent bez nullable-UNIQUE oslanjanja. VERIFIED zahteva null failure i potpuno poklapanje; CORRUPT zahteva safe failure code. `verification_hash=HashV1("SOKOLA-AUDIT-VERIFY-V1", kompletan verification objekat bez verification_hash)` i time uključuje scope, school i prethodni verification hash. Prva provera ima null previous hash, svaka sledeća mora pokazati na neposredno prethodnu za isti seal. Najnoviji verification outcome određuje operativno zdravlje, ali nikada ne menja seal ili prethodnu verifikaciju.

`AuditArchiveEvidence` je zaseban append-only dokaz, ne polje koje menja seal: `id`, `scope_kind SCHOOL|PLATFORM`, `school_id nullable`, `seal_id`, `archive_generation UInt32`, `encrypted_archive_ref`, `encryption_key_id`, `object_manifest_hash`, `archive_content_hash`, `archive_size_bytes UInt64`, `verified_at`, `verified_by_system_identity`, `verification_hash`, `retention_until`, `created_at`; unique `(seal_id,archive_generation)`. Scope/school moraju biti jednaki seal-u i koriste isti composite/platform FK obrazac kao verification. `verification_hash=HashV1("SOKOLA-AUDIT-ARCHIVE-V1", kompletan evidence objekat bez verification_hash)`. Arhiva obuhvata tačno partition/seal iz reference, manifest i byte hash se ponovo računaju pre VERIFIED dokaza, objekat je private/envelope-encrypted, a dokaz ne menja ni seal ni AuditEvent. Nova arhivska kopija je nova generacija; regularni update/delete nije dozvoljen.

### 2.2 `OutboxMessage`

`id`, `scope_kind SCHOOL|PLATFORM`, `school_id nullable`, `producer_module`, `producer_stream_key`, `producer_sequence_no UInt64`, `event_type`, `schema_version`, `aggregate_type`, `aggregate_id`, `aggregate_version`, `semantic_sequence UInt16`, `payload_json`, `headers_allowlist`, `payload_hash CHAR(64)`, `occurred_at`, `available_at`, `status PENDING|CLAIMED|PUBLISHED|DEAD_LETTERED|CANCELLED`, `attempt_count UInt16`, `lease_owner nullable`, `lease_token_hash nullable`, `lease_expires_at nullable`, `fencing_token UInt64`, `published_at nullable`, `last_error_code nullable`, `cancellation_reason_code nullable`, `created_at`, `updated_at`. `semantic_sequence` je `0..65535`, pri čemu je 0 jedini događaj tog tipa za aggregate verziju, a 1..65535 su deterministički owner-deklarisani dodatni događaji iste verzije. CLAIMED jedini ima lease owner/hash/expiry; PUBLISHED zahteva `published_at`; DEAD_LETTERED zahteva last error; CANCELLED zahteva cancellation reason. Ostala terminalna polja su null. `producer_stream_key` je zatvoren registry ključ oblika `school:{school_id}:{producer_module}:{stream_name}` ili `platform:{producer_module}:{stream_name}`; ne sadrži PII. Unique `(producer_stream_key,producer_sequence_no)` i unique `(producer_stream_key,aggregate_type,aggregate_id,aggregate_version,event_type,semantic_sequence)`. Nastaje u istoj DB transakciji sa business write-om.

`payload_hash` je istorijski naziv za hash celog immutable transport envelope-a, ne samo body-ja: `HashV1("SOKOLA-OUTBOX-ENVELOPE-V1", {id,scope_kind,school_id,producer_module,producer_stream_key,producer_sequence_no,event_type,schema_version,aggregate_type,aggregate_id,aggregate_version,semantic_sequence,payload_json,headers_allowlist,occurred_at,available_at})`. Posle insert-a sva polja iz tog objekta i `payload_hash` su immutable; menjaju se samo transport lifecycle/lease/attempt/error vremena kroz CAS. Publisher pre svakog slanja ponovo računa hash, broker envelope nosi isti hash, a consumer pre ikakvog efekta računa isti canonical hash i poredi ga sa broker vrednošću i `InboxReceipt.payload_hash`. Mismatch je terminalni integrity incident, bez tolerantnog procesiranja.

### 2.2a `OutboxStreamHead`

`producer_stream_key`, `scope_kind SCHOOL|PLATFORM`, `school_id nullable`, `producer_module`, `stream_name`, `last_allocated_sequence_no UInt64`, `version`, `created_at`, `updated_at`. Unique stream key. SCHOOL/PLATFORM conditional school pravilo je isto kao za Outbox. Business transakcija zaključava odgovarajući head, povećava sequence tačno za 1 i upisuje poruku; rollback vraća oba. Sequence se ne dodeljuje pre transakcije i nema commitovane rupe. Cancel/dead-letter poruka zadržava dodeljeni sequence, a downstream barrier računa njen terminalni disposition kao obrađenu poziciju, ne preskače je nevidljivo.

### 2.3 `InboxReceipt`

`id`, `consumer_name`, `message_id`, `event_type`, `schema_version`, `scope_kind SCHOOL|PLATFORM`, `school_id nullable`, `payload_hash`, `status PROCESSING|SUCCEEDED|FAILED_RETRYABLE|FAILED_TERMINAL`, `lease_token_hash nullable`, `lease_until nullable`, `fencing_token UInt64`, `attempt_count UInt16`, `processed_at nullable`, `result_hash nullable`, `last_error_code nullable`, `created_at`, `updated_at`. Unique `(consumer_name,message_id)`. PROCESSING jedini ima lease hash/until i nema processed time; SUCCEEDED zahteva processed time+result hash; FAILED_RETRYABLE/FAILED_TERMINAL zahtevaju processed time+last error. Isti ID sa drugim `payload_hash`, `event_type` ili `schema_version` je security incident, a consumer nikad ne nagađa nepoznatu schema verziju.

### 2.4 `JobDefinitionVersion`

Immutable posle publish-a: `id`, `job_key`, `version_no`, `owner_module`, `schedule_or_trigger`, `tenant_scope PLATFORM|PER_SCHOOL`, `concurrency_policy FORBID_OVERLAP|REPLACE|ALLOW_BOUNDED`, `max_concurrency UInt16`, `max_runtime_seconds UInt32`, `lease_seconds UInt32`, `heartbeat_seconds UInt32`, `max_attempts UInt16`, `retry_profile_key`, `dead_letter_policy`, `pii_class NONE|OPAQUE_IDS_ONLY`, `enabled_default boolean`, `status DRAFT|PUBLISHED|RETIRED`, `content_hash`, `published_at nullable`, `published_by_account_id nullable`, `retired_at nullable`, `retired_by_account_id nullable`, `version`, `created_at`, `updated_at`. Published vrednosti moraju tačno odgovarati [[05-M21-JOB-CATALOG-V1]]; unknown ključ/verzija se ne izvršava.

### 2.5 `JobExecution`

Jedna logička poslovna namera bez attempt lease-a: `id`, `job_key`, `job_definition_version`, `scope_kind SCHOOL|PLATFORM`, `school_id nullable`, `execution_scope_key varchar(128)`, `trigger_type SCHEDULED|EVENT|MANUAL|RECOVERY`, `scheduled_for`, `semantic_scope_hash`, `status QUEUED|RUNNING|SUCCEEDED|FAILED_FINAL|CANCEL_REQUESTED|CANCELLED|TIMED_OUT|DEAD_LETTERED`, `current_attempt_no`, `progress_count`, `checkpoint_ciphertext nullable`, `last_error_code nullable`, `correlation_id`, `created_at`, `started_at nullable`, `finished_at nullable`, `version`. SCHOOL zahteva non-null school i `execution_scope_key='SCHOOL:'+lower(school_id)`; PLATFORM zahteva null school i literal `execution_scope_key='PLATFORM'`. Unique `(job_key,job_definition_version,execution_scope_key,semantic_scope_hash)`. Nenull izvedeni scope ključ sprečava nullable-UNIQUE duplikate platformskih execution-a. `scheduled_for` je planirani instant za SCHEDULED, owner event `available_at` za EVENT i DB-clock vreme prihvatanja za MANUAL/RECOVERY. Identical trigger/retry vraća isti execution; nova poslovna namera mora imati drugi owner-defined semantic scope.

### 2.5a `JobAttempt`

Fizički pokušaj: `id`, `job_execution_id`, `attempt_no UInt16`, `status CLAIMED|RUNNING|SUCCEEDED|FAILED_RETRYABLE|FAILED_TERMINAL|TIMED_OUT|CANCELLED|LEASE_LOST`, `lease_owner`, `lease_token_hash`, `fencing_token UInt64`, `lease_expires_at`, `heartbeat_at`, `checkpoint_input_hash nullable`, `checkpoint_output_hash nullable`, `error_code nullable`, `claimed_at`, `started_at nullable`, `finished_at nullable`, `version`. `UNIQUE(job_execution_id,attempt_no)` i partial unique najviše jedan `CLAIMED|RUNNING` pokušaj. CLAIMED ima null started/finished/error; RUNNING zahteva started i null finished/error; svaki terminalni status zahteva finished, a neuspešni statusi zahtevaju safe error. Novi retry kreira `attempt_no+1`; ne menja istorijski pokušaj. Checkpoint plaintext schema dozvoljava samo opaque cursor/ID i count, a vrednost u `JobExecution` je šifrovana i CAS/fencing upisana. Raw lease token se ne čuva.

### 2.6 `DeadLetterRecord`

`id`, `source_type OUTBOX|INBOX|JOB`, `source_id`, `scope_kind SCHOOL|PLATFORM`, `school_id nullable`, `owner_module`, `failure_code`, `sanitized_payload_reference`, `sanitized_payload_hash`, `payload_key_version`, `payload_delete_after`, `first_failed_at`, `last_failed_at`, `attempt_count UInt16`, `replay_attempt_count UInt16`, `status OPEN|REPLAY_APPROVED|REPLAYING|REPLAY_FAILED|RESOLVED|DISCARDED`, `approval_generation UInt16`, `approved_by_account_id nullable`, `approved_at nullable`, `approval_reason_code nullable`, `last_replay_attempt_id nullable`, `last_replay_failure_code nullable`, `resolved_at nullable`, `resolved_by_account_id nullable`, `resolution_reason_code nullable`, `version`, `created_at`, `updated_at`. `sanitized_payload_reference` je opaque referenca na zasebno envelope-encrypted recovery telo čija je schema allow-listed po source type/version; `sanitized_payload_hash=HashV1("SOKOLA-DEAD-LETTER-PAYLOAD-V1", kanonski allow-listed recovery objekat)` pre enkripcije, key version identifikuje managed encryption ključ, a `payload_delete_after` je UTC `TIMESTAMPTZ` iz M17 retention politike. Referenca, dead-letter red, audit ili log nikad ne nose raw token, kontakt, business content, exception ili ključ. Posle `payload_delete_after` ili legalnog disposition-a byte se briše uz deletion receipt; replay zatim više nije dozvoljen. REPLAY_APPROVED/REPLAYING zahtevaju approval trio i još dostupno recovery telo sa poklopljenim hash-em; REPLAY_FAILED zahteva replay attempt+failure; RESOLVED/DISCARDED zahtevaju resolution trio. Replay koristi original semantic idempotency identity. Odobravalac nije isti account kao replay executor za CRITICAL owner događaj.

### 2.7 `TelemetryEvent`

Nije audit: `id`, `event_name`, `occurred_at`, `recorded_at`, `environment`, `app_version`, `route_or_operation_key`, `module`, `status_or_error_code`, `duration_ms UInt32`, `count_bucket`, `device_bucket nullable`, `network_bucket nullable`, `tenant_pseudonym_daily nullable`, `actor_pseudonym_daily nullable`, `correlation_sample_id nullable`, `sampling_policy_version`, `delete_after TIMESTAMPTZ`. Zabranjeni su school/person/child/resource raw ID, ime, email, telefon, IP, URL query/path param, search tekst, message/document content, token, amount/reference. Cardinality i retention su bounded.

### 2.8 `BackupArtifact` i `RestoreRehearsal`

`BackupArtifact`: `id`, `scope FULL_SERVICE`, `status STARTED|VERIFIED|FAILED|EXPIRED`, `encrypted_location_ref`, `key_version`, `db_point_in_time`, `object_manifest_hash nullable`, `size_bucket nullable`, `retention_until`, `verification_hash nullable`, `failure_code nullable`, `created_by_system_identity`, `started_at`, `completed_at nullable`, `expired_at nullable`, `version`. H0 dozvoljava samo atomsku evidence celinu `FULL_SERVICE`: DB point-in-time + verzionisani object manifest + potrebna konfiguraciona/schema metadata; tenant-only ili DB-only artifact nije označen VERIFIED restore kandidat. VERIFIED zahteva manifest/size/verification/completed; FAILED zahteva failure+completed; EXPIRED je dozvoljen samo iz VERIFIED i zahteva expired time.

`RestoreRehearsal`: `id`, `backup_id`, `target_isolated_environment`, `status PLANNED|RUNNING|VERIFIED|FAILED|DESTROYED`, `planned_by_account_id`, `approved_by_account_id`, `approved_at`, `approval_reason_code`, `started_at nullable`, `completed_at nullable`, `pre_destroy_outcome nullable enum(VERIFIED,FAILED)`, `rpo_observed_seconds nullable`, `rto_observed_seconds nullable`, `integrity_check_hash nullable`, `tenant_isolation_test_result nullable`, `application_smoke_hash nullable`, `evidence_ref nullable`, `failure_code nullable`, `destroyed_at nullable`, `version`, `created_at`, `updated_at`. Planner i approver su dva različita aktuelna platform account-a; approval time/reason su obavezni pre PLANNED commit-a i ostaju immutable. PLANNED nema runtime/result polja; RUNNING zahteva start; VERIFIED zahteva sve result/evidence vrednosti; FAILED zahteva completed+failure; DESTROYED zahteva `destroyed_at`, `pre_destroy_outcome` jednak poslednjem VERIFIED/FAILED stanju i zadržava odgovarajuće rezultate/evidence. Restore nikad ne radi direktno preko production-a.

### 2.9 `ReleaseCandidateEvidence`

`id`, `commit_sha`, `build_artifact_sha256`, `dependency_lock_hash`, `migration_head`, `config_schema_version`, `test_manifest_hash`, `security_scan_hash`, `sbom_hash`, `status ASSEMBLING|VALIDATED|REJECTED|DEPLOYED|ROLLED_BACK|SUPERSEDED`, `validated_at nullable`, `validated_by_system_identity nullable`, `rejected_at nullable`, `rejection_reason_code nullable`, `deployment_ref nullable`, `deployed_at nullable`, `rollback_ref nullable`, `rolled_back_at nullable`, `superseded_by_candidate_id nullable`, `superseded_at nullable`, `version`, `created_at`, `updated_at`. Evidence identifikatori i hash-evi su obavezni već pri čuvanju candidate reda i ne smeju biti placeholder-i. ASSEMBLING ima sva lifecycle/result polja null. VALIDATED zahteva samo validation par. REJECTED zahteva reject vreme+reason; validation par ostaje non-null samo kada tranzicija ide iz VALIDATED zbog naknadno opozvanog/nevažećeg dokaza, dok su deploy/rollback/supersede polja null. DEPLOYED zahteva validation par+deployment ref/time i null reject/rollback/supersede polja. ROLLED_BACK zadržava validation+deployment dokaz, zahteva rollback ref/time i ima reject/supersede null. SUPERSEDED zahteva superseding candidate/time, čuva svaki stvarno ranije nastao validation/deployment dokaz, ali reject/rollback polja su null; target kandidat je drugi postojeći red i ne sme biti SUPERSEDED ka ovom redu ili formirati ciklus. Ova conditional matrica je DB CHECK/ekvivalent constraint. Dokumentacija ne izmišlja vrednosti; popunjava ih CI/repo.

### 2.10 Zajedničke lifecycle i credential zabrane

- `JobExecution` QUEUED ima `current_attempt_no=0` i start/finish null; RUNNING ima start, najmanje jedan attempt i finish null; svaki terminalni status zahteva finish. FAILED_FINAL/DEAD_LETTERED/TIMED_OUT zahtevaju safe error; SUCCEEDED/CANCELLED ga imaju samo ako zatvoren owner schema to traži. CANCEL_REQUESTED ima null finish i ne prima novi attempt.
- JobDefinition DRAFT ima publish/retire polja null; PUBLISHED zahteva publish par; RETIRED zahteva publish i retire par. Lease/heartbeat su pozitivni, `heartbeat_seconds<=lease_seconds/3` i `lease_seconds<max_runtime_seconds`.
- Raw auth, lease, download, provider ili replay credential se nikada ne čuva u bazi, audit-u, payload-u, dead-letteru ili logu; čuva se samo digest gde je poređenje potrebno.
- Terminalni operational status i njegovi required timestamp/reason/hash uslovi moraju biti DB CHECK/ekvivalent constraints, ne samo application validacija.
- `actor_account_id`, `support_access_id`, `published_by_account_id`, `planned_by_account_id`, `approved_by_account_id` i srodni M01/M05 actor identifikatori su opaque write-time validirani snapshot reference. M21 ne uvodi fizički reverse schema FK ka M01/M05 tabelama; postojanje, tenant/scope, permission i authorization version proveravaju se njihovim verzionisanim portovima pre lokalnog M21 commit-a, a kasnija deaktivacija aktera ne prepisuje istorijski dokaz.

## 3. Kanonski JOB katalog

Svaka izvršiva H0 ili M28 pre-pilot akcija, njen stabilni `job_key`, trigger, semantic identity, runtime, lease, pokušaji i retry politika zaključani su u [[05-M21-JOB-CATALOG-V1]]. Grupni nazivi `JOB-01..20` su supersedovani opisni aliasi i nisu runtime ključevi. Katalog v1 ima 40 konkretnih definicija: 39 H0 i jednu M28 definiciju koja ostaje disabled dok M28 nije omogućen. Unknown ili samo „familija” job ne sme da startuje u produkciji bez published `JobDefinitionVersion` koji se tačno poklapa sa katalogom. Promena semantike zahteva novu definition verziju, ne tihu izmenu reda.

## 4. Pravila i invarijante

1. Business write+a njegov audit/outbox/receipt su jedna lokalna transakcija kada pripadaju istom store-u; rollback vraća sve.
2. Audit i telemetry su fizički/logički odvojeni: audit je dokaziv i strogo autorizovan; telemetry je minimizovana operativna statistika i nikad zamena za audit.
3. Outbox je at-least-once; consumer mora inbox dedupe. „Exactly once” tvrdnja je zabranjena osim semantičkog exactly-once efekta dokazanog unique/CAS ugovorom.
4. Publisher claim koristi lease+fencing; fencing sprečava stale DB ack/checkpoint/result commit. Ako broker ne podržava fencing, stari proces još može poslati poruku: transport zato ostaje at-least-once, a InboxReceipt i owner unique/CAS sprečavaju duplu poslovnu posledicu. PUBLISHED se upisuje tek posle durable broker potvrde i uspešnog CAS-a važećeg lease-a.
4a. Producer sequence je bez commitovanih rupa unutar jednog `producer_stream_key`: head increment i outbox insert su jedna transakcija. Consumer čuva najvišu kontinuirano dispositionovanu sekvencu i skup kasnijih primljenih sekvenci; poruka `N+2` ne pomera barijeru preko nedostajuće `N+1`. `DEAD_LETTERED|CANCELLED` ne nestaje: owner-approved terminal disposition eksplicitno zatvara sequence poziciju i ulazi u barrier/evidence zapis.
5. Retry samo za allow-list transient kodove, exponential backoff+jitter, max attempts; validation/auth/conflict je terminalno osim nove eksplicitne komande.
6. Dead-letter replay zahteva owner permission, razlog, preview/scope, step-up/dual control gde katalog traži i idempotency; ne menja payload/tenant niti preskače noviju aggregate verziju. Neuspešan replay atomarno prelazi u `REPLAY_FAILED`, čuva sanitized failure code i attempt ref. Novi pokušaj zahteva novu approval generation; nema beskonačnog automatskog replay loop-a.
7. Job `scheduled_for` i business zone su eksplicitni; DST duplicate/nonexistent local instant rešava owner modul. Scheduler ne nagađa.
8. Per-school queue ima fairness i limite; poison tenant ne blokira druge.
9. Audit metadata je action-specifična allow-list. Free-form exception/stack/request body nikad u audit tabeli; stack samo restricted error system sa redaction/retention.
10. Audit query/export primenjuje tenant+permission pre count/page; support vidi samo sopstvene support action-e i School admin review prema M05.
11. Hash verification failure ili seal/signature mismatch je critical incident; ne briše/popravlja automatski red. Mesečni `AuditSegmentSeal` nastaje tek kada je UTC period zatvoren i sequence/count/hash su ponovo izračunati; seal je zauvek immutable. Svaka kasnija provera dodaje novi `AuditSegmentVerification`; CORRUPT rezultat ne menja prethodni VERIFIED dokaz niti seal, ali najnovije operativno zdravlje postaje CORRUPT i blokira disposition/release.
11a. Audit retention ne znači „čuvaj sve zauvek“. M17 published policy/legal hold određuje disposition. Event red se sme izbrisati/pseudonimizovati tek posle validnog `AuditSegmentSeal`, verifikovanog enkriptovanog arhivskog izvoza ako policy to zahteva, isteka retention-a i provere legal hold-a. Ne-PII seal, count, period, hash i disposition audit ostaju prema zasebnom evidence policy-ju; brisanje istorijskih redova ne sme se predstavljati kao i dalje dostupna row-level verifikacija.
12. Telemetry sample ne sme promeniti audit, billing ili security decision. Daily pseudonym se ne koristi za cross-day tracking.
13. Secrets/config dolaze iz managed secret/config store-a; startup validira schema, unknown/missing unsafe value failuje pre saobraćaja. Secret se rotira bez upisa plaintexta u repo/log.
14. Health endpoint public vraća samo generic status; detailed health zahteva platform permission i nema tenant counts/nazive.
15. Backup je enkriptovan in transit/at rest, odvojen account/credential, immutable/locked gde platforma podržava; backup bez verifikovanog restore-a nije prihvatljiv dokaz.
16. Kandidatski cilj pre pilota je RPO≤24h i RTO≤8h za kompletan servis; to nije dostignuta SLA tvrdnja. `RestoreRehearsal.rpo_observed_seconds/rto_observed_seconds` i svi integrity testovi moraju dokazati cilj na reprezentativnom obimu pre `GO`. Stroži budući SLA zahteva poseban kapacitet/ugovor. Restore rehearsal je obavezan najmanje pre pilota i kvartalno tokom pilota/produkcije.
17. Restore proverava DB+object storage konzistentnost, tenant izolaciju, auth revocation, ledger/document hashes, outbox/inbox dedupe i critical smoke; izolovano okruženje se uništava.
18. Migracije su forward-only default, transakcione/batched gde moguće, sa expand→backfill→verify→switch→contract za rizične promene. Nema table lock-a bez procene/downtime plana.
19. Rollback aplikacije ne sme koristiti nekompatibilnu staru šemu, oživeti revoked session/role ili izgubiti committed finance/audit. Tada se koristi forward recovery.
20. Deploy je immutable artifact istog SHA kroz okruženja; nema ručnog patch-a na serveru. DB migration head i app compatibility se proveravaju pre traffic-a.
21. Feature flag je typed, scoped, default, owner, expiry/review date i kill switch; nije authorization kontrola. mySOKOLA ostaje default OFF/pilot allowlist po M28.
22. Staging do pilot odobrenja koristi synthetic data. Production dump se ne kopira u dev/test.
23. Incident log/alert ne nosi PII. Correlation ID je random i ne kodira tenant/person.
24. Handover mora omogućiti drugoj stručnoj osobi da podigne lokalno/test okruženje, pokrene migracije/seed/test/build/deploy rehearsal i rollback bez privatnog razgovora ili ličnog imena.
25. Release PASS zahteva nula skipped critical testova, poznat commit/artifact/lock/migration head, SBOM/dependency/security scan, backup/restore dokaz i otvorene rizike eksplicitno klasifikovane.

### 4.1 Edge cases

| Scenario | Ishod |
|---|---|
| Commit uspe, broker nedostupan | Outbox ostaje PENDING; business write nije izgubljen/ponovljen. |
| Publisher pošalje pa padne pre ack-a | Ponovljena isporuka; inbox dedupe daje jedan efekat. |
| Lease istekne tokom dugog job-a | Stari fencing token ne commit-uje checkpoint/result. |
| Replay stare M12 poruke posle novije verzije | Consumer ignoriše/stale code; ne vraća ledger unazad. |
| Audit hash mismatch | Critical alert, read-only preservation i incident; nema auto-repair. |
| M18 dobije sequence N+2 pre N+1 | N+2 se deduplikuje i drži kao gap; contiguous barrier se ne pomera. |
| Dead-letter replay ponovo failuje | REPLAY_FAILED sa attempt/failure ref; nema auto-loop-a; nova dual approval generation ili discard. |
| Backup DB uspe, object manifest ne | Backup FAILED, nije restore kandidat. |
| Rollback app posle destructive schema | Zabranjen; forward recovery. |
| Telemetry provider outage | App radi; bounded local/server buffer bez PII, drop metric; nema business rollback-a. |

## 5. Tenant/security

Tenant-bound audit/outbox/inbox/job/dead-letter imaju `school_id`; composite ownership i query scope. Platform-null school je dozvoljen samo za registry-allow-listed platform događaje. Payload schema registry dozvoljava samo opaque IDs/status/version/reason/correlation; token, email, child name, message/document body, bank/payment reference i ciphertext key ref su zabranjeni.

Kanonski ključevi su: `platform.operations.view`, `platform.jobs.manage`, `platform.deadletters.replay`, `platform.audit.verify`, `platform.backup.manage`, `platform.restore.execute`, `platform.release.manage`, `school.audit.view`, `school.audit.export`. Tačni role binding-i su u M05 registru; skraćeni `.suffix` ili `view/export` nisu runtime ključevi. Restore/dead-letter zahtevaju step-up i dual control; release zahteva step-up i odvojenu CI/deployment evidence proveru. Support/break-glass ne briše audit, ne exportuje bulk tenant podatke i nema secret/backup pristup.

## 6. Lifecycle

| Entitet | Iz | Operacija/uslov | U |
|---|---|---|---|
| Outbox | PENDING | valid claim | CLAIMED |
| Outbox | CLAIMED | durable broker publish | PUBLISHED |
| Outbox | CLAIMED | retryable failure/lease expiry pre max | PENDING |
| Outbox | PENDING/CLAIMED | max/terminal schema failure | DEAD_LETTERED |
| Outbox | PENDING | owner-approved semantic cancellation | CANCELLED |
| Inbox | — | first delivery/claim | PROCESSING |
| Inbox | PROCESSING | commit consumer effect+receipt | SUCCEEDED |
| Inbox | PROCESSING | transient failure | FAILED_RETRYABLE |
| Inbox | FAILED_RETRYABLE | new fenced attempt | PROCESSING |
| Inbox | PROCESSING/FAILED_RETRYABLE | terminal/max | FAILED_TERMINAL |
| JobExecution | — | accepted/deduped trigger | QUEUED |
| JobExecution | QUEUED | prvi fenced attempt počinje | RUNNING |
| JobExecution | RUNNING | attempt uspe i result/checkpoint commit | SUCCEEDED |
| JobExecution | RUNNING | retryable attempt fail pre max | RUNNING; novi JobAttempt |
| JobExecution | RUNNING | terminal ili max attempts | FAILED_FINAL ili DEAD_LETTERED prema definition |
| JobExecution | QUEUED/RUNNING | authorized cancel request | CANCEL_REQUESTED |
| JobExecution | CANCEL_REQUESTED | nema aktivnog attempt-a/novog commita | CANCELLED |
| JobExecution | RUNNING | max runtime pre result commit-a | TIMED_OUT |
| JobAttempt | — | fenced claim | CLAIMED |
| JobAttempt | CLAIMED | worker start | RUNNING |
| JobAttempt | RUNNING | fenced result commit | SUCCEEDED |
| JobAttempt | RUNNING | transient allow-list failure | FAILED_RETRYABLE |
| JobAttempt | RUNNING | terminal failure | FAILED_TERMINAL |
| JobAttempt | CLAIMED/RUNNING | lease/fence izgubljen | LEASE_LOST |
| JobAttempt | RUNNING | runtime exceeded | TIMED_OUT |
| JobAttempt | CLAIMED/RUNNING | execution cancel pre commit-a | CANCELLED |
| DeadLetter | — | terminal source failure | OPEN |
| DeadLetter | OPEN | dual-control approval | REPLAY_APPROVED |
| DeadLetter | REPLAY_APPROVED | new replay attempt created | REPLAYING |
| DeadLetter | REPLAYING | replay terminal success | RESOLVED |
| DeadLetter | REPLAYING | replay failure | REPLAY_FAILED |
| DeadLetter | REPLAY_FAILED | nova dual-control approval generation | REPLAY_APPROVED |
| DeadLetter | OPEN/REPLAY_APPROVED/REPLAY_FAILED | justified non-replay resolution | DISCARDED |
| AuditSegmentSeal | — | zatvoren period + recompute + sign | immutable SEALED red |
| AuditSegmentVerification | —/VERIFIED/CORRUPT | nova nezavisna provera seal-a | novi VERIFIED ili CORRUPT red |
| AuditArchiveEvidence | — | enkriptovana arhiva + manifest/byte verify | nova immutable archive generacija |
| Backup | — | start | STARTED |
| Backup | STARTED | DB+object+encryption verification | VERIFIED |
| Backup | STARTED | any required component fails | FAILED |
| Backup | VERIFIED | retention expiry | EXPIRED |
| Restore | — | approved plan | PLANNED |
| Restore | PLANNED | isolated execution starts | RUNNING |
| Restore | RUNNING | all integrity/isolation/smoke checks pass | VERIFIED |
| Restore | RUNNING | any required check fails | FAILED |
| Restore | VERIFIED/FAILED | isolated target securely destroyed | DESTROYED |
| ReleaseEvidence | — | assemble | ASSEMBLING |
| ReleaseEvidence | ASSEMBLING | all required evidence valid | VALIDATED |
| ReleaseEvidence | ASSEMBLING | missing/failed evidence | REJECTED |
| ReleaseEvidence | VALIDATED | dokaz opozvan/nevažeći pre deploy-a | REJECTED uz očuvan validation par |
| ReleaseEvidence | VALIDATED | immutable artifact deployed | DEPLOYED |
| ReleaseEvidence | DEPLOYED | compatible rollback completed | ROLLED_BACK |
| ReleaseEvidence | ASSEMBLING/VALIDATED/DEPLOYED | newer candidate replaces | SUPERSEDED |

PUBLISHED/CANCELLED/DEAD_LETTERED outbox, SUCCEEDED/FAILED_TERMINAL inbox, SUCCEEDED/FAILED_FINAL/CANCELLED/TIMED_OUT/DEAD_LETTERED JobExecution, svaki završeni JobAttempt, RESOLVED/DISCARDED dead letter, svaki AuditSegmentSeal/Verification/ArchiveEvidence red, FAILED/EXPIRED backup, DESTROYED restore i REJECTED/ROLLED_BACK/SUPERSEDED release su terminalni redovi. Najnovija verification generacija može prijaviti CORRUPT posle ranijeg VERIFIED rezultata, ali oba append-only reda i originalni seal ostaju nepromenjeni. `REPLAY_FAILED` nije terminalan, ali nema automatski izlaz bez nove approval generation. Retry/replay/novi release pravi novu povezanu attempt/candidate generaciju; ne oživljava terminalni red. PUBLISHED outbox i SUCCEEDED inbox se nikada ne vraćaju unazad.

## 7. Error catalog i API

| Code | HTTP | Značenje |
|---|---:|---|
| `OPS_UNAUTHENTICATED` | 401 | Sesija nevažeća. |
| `OPS_FORBIDDEN` | 403 | Nema platform/school permission. |
| `OPS_NOT_FOUND_SAFE` | 404 | Skriven/cross-tenant zapis. |
| `OPS_IDEMPOTENCY_CONFLICT` | 409 | Isti key, drugi request. |
| `OPS_VERSION_CONFLICT` | 409 | CAS/fencing konflikt. |
| `OPS_LEASE_LOST` | 409 | Worker više nije owner. |
| `OPS_SCHEMA_UNSUPPORTED` | 422 | Event/job/config schema nije podržana. |
| `OPS_JOB_DEFINITION_UNKNOWN` | 422 | Job key/version nije published u aktivnom katalogu. |
| `OPS_STREAM_SEQUENCE_GAP` | 409 | Consumer nema kontinuiranu producer barijeru. |
| `OPS_AUDIT_SEAL_INVALID` | 409 | Segment seal/signature/hash ne prolazi proveru. |
| `OPS_AUDIT_ARCHIVE_INVALID` | 409 | Arhiva, manifest, byte hash ili veza ka seal-u nije dokaziva. |
| `OPS_PAYLOAD_FORBIDDEN_FIELD` | 422 | PII/secret/unknown field. |
| `OPS_REPLAY_NOT_SAFE` | 409 | Replay bi prekršio verziju/invarijantu. |
| `OPS_REPLAY_APPROVAL_REQUIRED` | 409 | Nema važeće approval generation za pokušaj. |
| `OPS_RESTORE_NOT_VERIFIED` | 409 | Restore nije prošao integritet/smoke. |
| `OPS_ROLLBACK_INCOMPATIBLE` | 409 | Stara aplikacija ne podržava šemu. |
| `OPS_RELEASE_EVIDENCE_INCOMPLETE` | 409 | Nedostaje obavezni dokaz. |
| `OPS_RATE_LIMITED` | 429 | Operativni limit. |
| `OPS_DEPENDENCY_UNAVAILABLE` | 503 | Broker/storage/provider nedostupan. |
| `OPS_INTERNAL_SAFE` | 500 | Bez PII/stack leak-a. |

Queries `ListAuditEvents`, `GetAuditSegmentEvidence` (seal, verifications i archive generations), `ListJobExecutions`, `GetJobExecutionAttempts`, `ListDeadLetters`, `PreviewDeadLetterReplay`, `ListBackups`, `GetRestoreRehearsal`, `GetReleaseCandidateEvidence` koriste cursor pagination default 25/max100 i tenant/scope guard pre count-a. Commands su tačno: `ApproveDeadLetterReplay`, `ExecuteDeadLetterReplay`, `ApproveNewDeadLetterReplay`, `DiscardDeadLetter`, `RequestJobCancellation`, `TriggerPublishedOwnerJob`, `SealAuditSegment`, `VerifyAuditSegment`, `CreateAndVerifyAuditArchiveEvidence`, `CreateBackup`, `VerifyBackup`, `PlanRestore`, `ExecuteRestore`, `VerifyRestore`, `DestroyRestoreEnvironment`, `AssembleReleaseEvidence`, `ValidateReleaseEvidence`, `DeployReleaseCandidate`, `RollbackReleaseCandidate`. `CreateAndVerifyAuditArchiveEvidence` zahteva `platform.audit.verify`, step-up, validan seal/latest VERIFIED chain, M17 task/policy scope i private storage; tek posle object upload-a i ponovnog manifest/byte read-a commit-uje evidence. Privremeni objekat pre tog commit-a nosi non-downloadable `PENDING_EVIDENCE` storage tag sa infrastrukturnim lifecycle brisanjem najkasnije za 24h; neuspeh ne stvara evidence red. Svaki write ima idempotency, expected version, correlation i obavezni zatvoreni reason code gde menja/prekida operativno stanje; privileged commands koriste step-up i propisani dual control.

## 8. Observability, QA i handover acceptance

SLI: API latency/error, auth deny, queue age/depth, oldest outbox, retries/deadletters, job duration/timeout, projection lag, backup age, restore result, storage/db saturation, notification provider outcome. Alerti imaju severity/owner/runbook/dedupe/cooldown; nema alert storm-a. SLO se definiše i meri po okruženju; dokumentacija ne tvrdi dostignuće bez RUM/monitoring dokaza.

Obavezni artefakti: README/setup, env/config schema bez secret vrednosti, architecture/module map, DB migration/runbook, seed synthetic accounts/two tenants, test commands, CI pipeline, artifact/SBOM, deploy/rollback/forward recovery, backup/restore, incident/support runbook, known risks, data retention/deletion, dependency licenses, changed-file/migration/test report generisan iz stvarnog izvršenja.

Acceptance uključuje transaction failure injection, duplicate/out-of-order, lease/fencing, dead-letter/replay, tenant-negative audit/jobs, immutable seal + append-only verification, PII payload schema fuzzing, telemetry redaction/cardinality, config fail-closed, migraciju reprezentativne kopije, concurrent deploy/job, backup corruption/missing object, full restore rehearsal, rollback incompatibility, synthetic staging, secrets scan, SAST/dependency scan i kompletan M00–M21+M28 QA manifest sa 0 skipped kritičnih scenarija. M21 ostaje `SPEC_CANDIDATE` dok repo dokaz ne postoji.
