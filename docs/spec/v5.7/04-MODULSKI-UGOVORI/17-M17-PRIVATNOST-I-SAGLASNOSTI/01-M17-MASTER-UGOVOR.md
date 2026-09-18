---
tip: modulni-implementacioni-ugovor
modul-id: M17
naziv: Privatnost, pravni osnovi, saglasnosti i prava lica
status: SPEC_CANDIDATE
revizija: "1.9"
datum: 2026-09-15
schema-zavisnosti: [M04, M06, M15]
read-portovi: [M01, M03, M05, M06, M07, M15]
application-orchestration: [consent-evidence-coordinator-M17-plus-M15, privacy-task-coordinator-M17-plus-owner-ports]
izlazni-portovi-za: [M13, M14, M16, M18, M19, M20, M21, M28]
offline-policy: DENY
---

# M17 — Privatnost, pravni osnovi, saglasnosti i prava lica

## 1. Cilj i granice

M17 je jedini vlasnik registra svrha obrade, pravnih osnova, verzija obaveštenja o privatnosti, opcionih saglasnosti, odluka/povlačenja saglasnosti, rokova čuvanja, legal hold-a i zahteva lica na koja se podaci odnose. Garantuje da se svaka obrada ličnih podataka može povezati sa školom, svrhom, pravnim osnovom, kategorijama podataka/lica, owner modulom, primaocima, rokom i važećom verzijom politike.

M17 ne poseduje `Person`/membership (M06), guardian/payer odnos (M07), dokument/binarni sadržaj/hash i dokaz klika (M15), autentifikaciju (M01), RBAC/support (M05), poslovne zapise vlasničkih modula, audit infrastrukturu (M21), niti pravni savet. M17 policy određuje da li owner modul sme da čuva/izveze/obriše/pseudonimizuje podatak; owner modul izvršava promenu kroz verzionisan port. M17 ne radi direktan update tuđih tabela.

H0 obuhvata privacy notice acknowledgement, granularne foto/video saglasnosti, withdrawal, subject request workflow, retention registry, legal hold i dokazivu orkestraciju izvoza/ispravke/brisanja. Biometrija, medicinska dokumentacija, kvalifikovani elektronski potpis, automatsko profilisanje sa pravnim dejstvom, prodaja podataka i marketing prema deci nisu H0.

## 2. Entiteti, polja i relacije

Svi ID-jevi su UUID. Svi `*_at` su UTC `TIMESTAMPTZ`; poslovni datum koristi School IANA zonu. `version` je `BIGINT >=1`. Kodovi su English `snake_case`/UPPER enum; opisni UI tekst je i18n. Polje je obavezno osim kada piše nullable. Aggregate/command red sa surrogate `id` koristi tenant-prefiksirani PK/UNIQUE; keyed projection/receipt bez `id` ima eksplicitni kompozitni PK/UNIQUE koji počinje sa `school_id` i nijedan tenant-less lookup.

### 2.1 `ProcessingPurposeVersion`

Immutable po objavi: `id`, `school_id`, `purpose_key varchar(80)`, `version_no int`, `name_i18n_key varchar(160)`, `description_i18n_key varchar(160)`, `controller_role enum(SCHOOL_CONTROLLER,SOKOLA_PROCESSOR,SOKOLA_INDEPENDENT_CONTROLLER)`, `legal_basis enum(CONTRACT,LEGAL_OBLIGATION,LEGITIMATE_INTEREST,VITAL_INTEREST,PUBLIC_TASK,CONSENT)`, `data_subject_categories text[]`, `data_categories text[]`, `owner_modules text[]`, `recipient_categories text[]`, `international_transfer_mode enum(NONE,ADEQUACY,SCC,OTHER_SAFEGUARD)`, `safeguard_reference nullable`, `automated_decision enum(NONE,ASSISTIVE,LEGAL_OR_SIMILAR_EFFECT)`, `necessity enum(REQUIRED_FOR_SERVICE,OPTIONAL)`, `retention_policy_version_id`, `effective_from`, `effective_until nullable`, `status enum(DRAFT,PUBLISHED,RETIRED)`, `content_hash char(64)`, `published_at nullable`, `published_by_account_id nullable`, `retired_at nullable`, `retired_by_account_id nullable`, `version`, `created_at`, `updated_at`. Unique `(school_id,purpose_key,version_no)`; objavljeni efektivni intervali istog ključa se ne preklapaju.

`CONSENT` zahteva `necessity=OPTIONAL` u H0. `LEGAL_OR_SIMILAR_EFFECT` je zabranjen. `OTHER_SAFEGUARD` bez odobrenog reference registry-ja failuje.

### 2.2 `PrivacyNoticeVersion`

`id`, `school_id`, `notice_key varchar(80)`, `version_no`, `document_version_id` (M15), `document_sha256`, `language_code`, `audience enum(ADULT_ACCOUNT,GUARDIAN,PARTICIPANT_WITH_CAPACITY,STAFF)`, `effective_from`, `effective_until nullable`, `status DRAFT|PUBLISHED|RETIRED`, `material_change boolean`, `change_summary_i18n_key`, `published_at nullable`, `published_by_account_id nullable`, `retired_at nullable`, `retired_by_account_id nullable`, `version`, `created_at`, `updated_at`. Immutable posle PUBLISHED osim lifecycle/effectivity polja. Unique key/version i non-overlap published interval.

### 2.3 `ConsentDefinitionVersion`

`id`, `school_id`, `consent_key varchar(80)`, `version_no`, `purpose_version_id` čiji je basis CONSENT, `decision_subject enum(ADULT_SELF,CHILD)`, `guardian_decision_rule enum(ANY_DECLINE_BLOCKS,SOLE_AUTHORITY_ONLY) nullable`, `media_scope enum(NONE,PHOTO,VIDEO)`, `channel_scope enum(INTERNAL_OPERATIONS,PRIVATE_GUARDIAN_CHANNEL,PUBLIC_WEBSITE,PUBLIC_SOCIAL_MEDIA,PRINTED_PROMOTION,EVENT_LIVESTREAM)`, `document_version_id` M15, `document_sha256`, `evidence_requirement_id` M15 `OPTIONAL_DECISION`, `title_i18n_key`, `plain_summary_i18n_key`, `effective_from`, `effective_until nullable`, `status DRAFT|PUBLISHED|RETIRED`, `material_change boolean`, `published_at nullable`, `published_by_account_id nullable`, `retired_at nullable`, `retired_by_account_id nullable`, `version`, `created_at`, `updated_at`. Evidence requirement mora ciljati isti document version/hash, isti subject tip i `mandatory_for_service=false`. `guardian_decision_rule` je obavezan samo za CHILD i mora biti null za ADULT_SELF. Jedna definicija pokriva tačno jednu svrhu i jedan scope; PHOTO i VIDEO nikad nisu isti consent key. Objavljena definicija je immutable osim lifecycle/effectivity polja.

### 2.4 `ConsentDecision`

Append-only: `id`, `school_id`, `consent_definition_version_id`, `giver_person_id`, `giver_account_id` nullable, `subject_person_id`, `participant_profile_id nullable`, `guardian_relation_id nullable`, `decision_generation BIGINT >=1`, `decision enum(GRANTED,DECLINED,WITHDRAWN)`, `effective_at`, `recorded_at`, `channel enum(AUTHENTICATED_WEB_PWA,STAFF_ASSISTED,API_MIGRATION)`, `actor_type enum(SUBJECT,AUTHORIZED_STAFF,TRUSTED_MIGRATION)`, `recorded_by_account_id` nullable, `recorded_by_system_identity` nullable `varchar(128)`, `source_system_code` nullable `varchar(96)`, `source_evidence_hash` nullable lowercase `CHAR(64)`, `evidence_id` M15, `authority_set_hash_at_decision char(64)`, `authorization_basis_type`, `authorization_basis_id`, `supersedes_decision_id nullable`, `reason_code nullable`, `correlation_id`, `idempotency_key_hash`, `decision_hash`, `created_at`. Nema update/delete. Unique `(school_id,consent_definition_version_id,subject_person_id,giver_person_id,decision_generation)`; jedan giver head po istoj semantic key grupi kroz serializovan command/head projekciju. Agregirani subject state računa se iz svih važećih giver head-ova. M15 evidence mora koristiti isti giver/subject/basis, isti requirement/document/hash, actor/channel/recorder/source proof i mapiranje `GRANTED→CONSENT_GRANTED`, `DECLINED→CONSENT_DECLINED`, `WITHDRAWN→CONSENT_WITHDRAWN`.

Za `decision_subject=ADULT_SELF` važi `subject_person_id=giver_person_id`, a participant/guardian polja su null. Za CHILD su participant i aktuelni guardian relation obavezni. `WITHDRAWN` zahteva `supersedes_decision_id` ka aktuelnom GRANTED head-u istog davaoca/definition/subjecta; novi GRANTED ili DECLINED posle prethodne odluke referencira neposredni prethodni head. Dozvoljene actor/channel kombinacije i njihove nullability garancije identične su M15: browser SUBJECT zahteva isti giver/recorder account; STAFF_ASSISTED zahteva stvarni recorder account, step-up, posebnu permission, prisutnog davaoca i reason, dok giver account sme biti null; API_MIGRATION zahteva TRUSTED_MIGRATION, null recorder account, allow-listed system identity, source system/hash i reason, dok giver account sme biti null. Druge kombinacije su DB-invalidne. Migracija prenosi samo dokazivu postojeću odluku, nikad pretpostavljeni opt-in; bulk grant je zabranjen.

### 2.5 `ConsentGiverState`

Projekcija odluke jednog davaoca: `school_id`, `consent_key`, `subject_person_id`, `giver_person_id`, `current_definition_version_id`, `head_decision_id nullable`, `authority_set_hash_at_decision nullable`, `state enum(NOT_ASKED,GRANTED,DECLINED,WITHDRAWN,RECONSENT_REQUIRED)`, `effective_at nullable`, `state_changed_at`, `version`, `updated_at`. Unique `(school_id,consent_key,subject_person_id,giver_person_id)`. `NOT_ASKED` zahteva null head/authority/effective polja; GRANTED/DECLINED/WITHDRAWN zahtevaju sva tri non-null; `RECONSENT_REQUIRED` zahteva null `effective_at`, a sme zadržati prethodni head/authority samo kao istorijsku referencu koja ne daje aktivni consent. `state_changed_at` je uvek non-null DB-clock vreme poslednje promene izvedenog stanja. Projekcija se menja samo CAS-om nad `version`; nije dokaz, jer je dokaz append-only `ConsentDecision` i M15 evidence. Jedan staratelj ne može izmeniti ili povući odluku drugog staratelja.

### 2.6 `ConsentEffectiveState`

Agregirana projekcija za dete/subjekta: `school_id`, `consent_key`, `subject_person_id`, `current_definition_version_id`, `state enum(NOT_ASKED,GRANTED,DECLINED,WITHDRAWN,RECONSENT_REQUIRED)`, `state_reason_code nullable`, `current_authority_set_hash char(64)`, `decision_set_hash char(64)`, `effective_at` nullable, `state_changed_at`, `authorization_version`, `version`, `updated_at`. Unique `(school_id,consent_key,subject_person_id)`. `decision_set_hash` je SHA-256 kanonski sortiranog skupa važećih giver-head ID-jeva i verzija; prazan skup ima kanonski hash. GRANTED/DECLINED/WITHDRAWN zahtevaju non-null `effective_at` i null reason; NOT_ASKED zahteva null effective/reason; RECONSENT_REQUIRED zahteva null effective i non-null reason. `state_changed_at` je uvek non-null DB-clock vreme poslednje promene. Projekcija i authorization-version promena koriste isti CAS/DB commit; projekcija nije dokaz.

`ConsentDefinitionVersion.guardian_decision_rule` je obavezan za `decision_subject=CHILD`: `ANY_DECLINE_BLOCKS | SOLE_AUTHORITY_ONLY`. H0 default je `ANY_DECLINE_BLOCKS`. Za aktuelnu definiciju i nepromenjen M07 authority set važi potpuni prioritet: najmanje jedan `DECLINED` head daje `DECLINED`; inače najmanje jedan `WITHDRAWN` daje `WITHDRAWN`; inače najmanje jedan `GRANTED` daje `GRANTED`; bez odluka je `NOT_ASKED`. Neodgovaranje drugog aktivnog guardian-a nije grant niti automatski veto. Material change dokumenta/purpose-a ili promena skupa/vrste ovlašćenih guardian-a daje `RECONSENT_REQUIRED` sa razlogom `DEFINITION_CHANGED` ili `GUARDIAN_AUTHORITY_CHANGED`, pre ponovnog računanja. Prethodni decision-i ostaju istorijski dokaz, ali ne mogu sami ponovo aktivirati consent nakon authority promene. `SOLE_AUTHORITY_ONLY` je dozvoljen samo kada M07 resolver potvrdi dokumentovanu isključivu nadležnost tačno jednog aktivnog staratelja. Škola i support nikada ne mogu dati saglasnost umesto ovlašćenog lica niti preglasati njegovu odluku.

### 2.7 `RetentionPolicyVersion`

`id`, `school_id nullable` (`null` samo platform default), `policy_scope_key varchar(80)`, `policy_key`, `version_no`, `owner_module`, `record_category`, `trigger enum(RECORD_CREATED,RELATION_ENDED,CONTRACT_ENDED,ACCOUNT_CLOSED,LEGAL_EVENT)`, `retention_period_iso8601`, `disposition enum(DELETE,PSEUDONYMIZE,ANONYMIZE,REVIEW_REQUIRED)`, `grace_period_days`, `legal_hold_eligible`, `higher_authority_reference nullable`, `status DRAFT|PUBLISHED|RETIRED`, `effective_from`, `effective_until nullable`, `content_hash`, `published_at nullable`, `published_by_account_id nullable`, `retired_at nullable`, `retired_by_account_id nullable`, `version`, `created_at`, `updated_at`. Platform default zahteva `school_id=NULL` i literal `policy_scope_key=PLATFORM`; school override zahteva non-null school i `policy_scope_key=SCHOOL:<lower-uuid>`. Unique `(policy_scope_key,policy_key,version_no)` i exclusion/partial constraint sprečavaju preklapajuće PUBLISHED intervale istog scope/key-a bez SQL NULL rupe. Platform publish koristi platform permission bez aktivnog school context-a; school override koristi tačan M03 context. Published je immutable osim lifecycle/effectivity polja; tenant override ne sme produžiti ili skratiti rok protiv obavezujuće platform/legal policy bez eksplicitnog `higher_authority_reference`.

### 2.8 `LegalHold`

`id`, `school_id`, `scope_type enum(PERSON,FAMILY,DOCUMENT,CASE,RECORD_CATEGORY)`, `scope_id_or_hmac`, `record_categories`, `reason_code`, `legal_reference_ciphertext`, `status DRAFT|ACTIVE|RELEASED|EXPIRED`, `requested_by_account_id`, `starts_at nullable`, `expires_at nullable`, `activated_at nullable`, `activated_by_account_id nullable`, `released_at nullable`, `released_by_account_id nullable`, `release_reason_code nullable`, `expired_at nullable`, `version`, `created_at`, `updated_at`. Hold ne daje read pristup i ne kopira sadržaj. Aktivacija/release zahtevaju `privacy.legal_hold.manage`, step-up i dual control (requester != approver).

### 2.9 `DataSubjectRequest`

`id`, `school_id`, `request_type enum(ACCESS,RECTIFICATION,ERASURE,RESTRICTION,OBJECTION,PORTABILITY,CONSENT_STATUS)`, `subject_mode enum(SELF,CHILD_BY_GUARDIAN)`, `requester_person_id nullable`, `subject_person_id nullable`, `guardian_relation_id nullable`, `subject_basis_hash nullable CHAR(64)`, `submitted_by_account_id nullable`, `intake_document_version_id nullable` M15, `requested_scope_codes text[]`, `received_channel enum(AUTHENTICATED_WEB_PWA,STAFF_ASSISTED,EMAIL_INTAKE)`, `identity_assurance enum(UNVERIFIED,SESSION_VERIFIED,STEP_UP_VERIFIED,MANUAL_VERIFIED)`, `identity_verification_method_code nullable enum(AUTHENTICATED_SESSION,FRESH_STEP_UP,IN_PERSON_OFFICIAL_DOCUMENT_INSPECTED_NO_COPY)`, `identity_verified_at nullable`, `identity_verified_by_account_id nullable`, `initial_identity_pending boolean`, `identity_verification_deadline_at nullable`, `status enum(RECEIVED,IDENTITY_PENDING,VALIDATING,IN_PROGRESS,WAITING_FOR_SUBJECT,CANCEL_REQUESTED,COMPLETED,PARTIALLY_COMPLETED,REJECTED,CANCELLED,EXPIRED)`, `received_at`, `statutory_due_at`, `paused_at nullable`, `pause_reason_code nullable`, `cancellation_requested_at nullable`, `cancellation_requested_by_person_id nullable`, `cancellation_reason_code nullable`, `decision_reason_code nullable`, `completed_at nullable`, `response_document_version_id nullable` M15, `version`, `created_at`, `updated_at`. EMAIL_INTAKE uvek nastaje kao IDENTITY_PENDING sa `identity_assurance=UNVERIFIED`, null requester/subject/guardian/basis i non-null restricted M15 intake document; tenant se izvodi iz server-controlled školskog intake kanala, ne iz email teksta ili request body-ja. Email/ime se nikad ne koriste za automatsko Person povezivanje. Tek zasebna `VerifyIdentity` komanda može vezati requester, subject i aktuelni subject basis. AUTHENTICATED_WEB_PWA zahteva `submitted_by_account_id` koji se mapira na isti requester Person; može nastati kao RECEIVED samo kada aktuelna sesija zadovolji propisani assurance i subject basis, inače je IDENTITY_PENDING. Nevažeći ili tuđi child/guardian target je safe 404, ne IDENTITY_PENDING oracle. STAFF_ASSISTED zahteva stvarni staff submitter, M15 intake document, permission, razlog i zasebnu manual identity verifikaciju. Svaki zahtev koji počne kao IDENTITY_PENDING ima immutable `initial_identity_pending=true` i `identity_verification_deadline_at=min(received_at+168h,statutory_due_at)` po DB clock-u; zahtev koji počne RECEIVED ima false/null par. Scope je zatvorena allow-list bez slobodnog PII teksta; svi raw intake podaci/prilozi su M15 restricted documents. Cancellation reason je zatvoren kod bez slobodnog teksta; povlačenje mora dokazati isti vezani requester identitet ili aktuelno ovlašćenje staratelja sa assurance nivoom koji nije slabiji od nivoa prihvaćenog pri podnošenju.

H0 mapiranje assurance/metoda je zatvoreno: `SESSION_VERIFIED↔AUTHENTICATED_SESSION`, `STEP_UP_VERIFIED↔FRESH_STEP_UP`, `MANUAL_VERIFIED↔IN_PERSON_OFFICIAL_DOCUMENT_INSPECTED_NO_COPY`; `UNVERIFIED` zahteva sva tri verification polja null. Manual verification beleži ovlašćeni school privacy staff account, vreme i metod, ali ne čuva fotografiju/kopiju identifikacionog dokumenta, njegov broj ili slobodnu belešku. Session/step-up verification actor je isti account čija je proverena sesija. Od RECEIVED nadalje verification metod/actor/time su immutable dokaz prijema identitetske provere; kasnija deaktivacija account-a ne prepisuje istoriju, ali svaki novi pristup ponovo prolazi aktuelnu autorizaciju.

### 2.10 `PrivacyTask`

`id`, `school_id`, `request_id nullable`, `policy_version_id nullable`, `legal_hold_id nullable`, `owner_module`, `task_type enum(EXPORT,RECTIFY,DELETE,PSEUDONYMIZE,RESTRICT,UNRESTRICT,REVIEW)`, `target_type`, `target_id_hmac`, `status PENDING|LEASED|SUCCEEDED|FAILED_RETRYABLE|FAILED_FINAL|BLOCKED_BY_HOLD|CANCELLED`, `attempt_count`, `next_attempt_at nullable`, `lease_token_hash nullable`, `lease_until nullable`, `fencing_token UInt64`, `result_code nullable`, `result_receipt_hash nullable`, `last_error_code nullable`, `version`, `created_at`, `updated_at`, `finished_at nullable`. Payload sa identifikatorima je encrypted/minimal; nema PII u queue/logu.

### 2.11 `PrivacyExportArtifact`, segmenti i download autorizacija

`PrivacyExportArtifact`: `id`, `school_id`, `request_id`, `requested_by_account_id`, `delivery_mode enum(REQUESTER_ACCOUNT_DOWNLOAD,CONTROLLED_STAFF_HANDOFF)`, `requester_account_id nullable`, `authorization_version_at_request`, `status QUEUED|BUILDING|AVAILABLE|FAILED|EXPIRED|REVOKED`, `manifest_hash nullable`, `segment_count UInt32`, `total_size_bytes UInt64`, `failure_code nullable`, `available_at nullable`, `expires_at nullable`, `revoked_at nullable`, `revocation_reason_code nullable`, `version`, `created_at`, `updated_at`. `requested_by_account_id` je autentifikovani actor koji je pokrenuo artifact, ne dokaz identiteta lica. REQUESTER_ACCOUNT_DOWNLOAD zahteva non-null requester account koji se autoritativno mapira na već verifikovani `DataSubjectRequest.requester_person_id`; CONTROLLED_STAFF_HANDOFF zahteva null requester account i ovlašćenog privacy staff actor-a. AVAILABLE zahteva manifest, najmanje jedan segment, `available_at` i `expires_at<=available_at+24h`; ostala stanja nemaju downloadable rezultat. FAILED zahteva safe failure code; EXPIRED/REVOKED zahtevaju odgovarajući terminalni timestamp/reason. Jedan artifact je za jedan request, jednu školu i jedan authorization presek.

`PrivacyExportSegment`: immutable `id`, `school_id`, `artifact_id`, `sequence_no UInt32`, `storage_object_key`, `encryption_key_ref`, `content_sha256`, `size_bytes UInt64`, `row_count UInt64`, `created_at`; unique `(school_id,artifact_id,sequence_no)`. Objekat je private, tenant-keyed i nikad nema javni URL. Manifest pokriva uređeni skup segment hash-eva, kategorije, redakcije i schema verzije, ali ne sadrži same podatke.

`PrivacyExportDownloadTicket`: `ticket_digest`, `school_id`, `artifact_id`, `account_id`, `handoff_authorization_id nullable`, `authorization_version`, `subject_basis_hash`, `issued_at`, `expires_at` najviše 60s, `used_at nullable`, `status ACTIVE|USED|EXPIRED|REVOKED`; raw ticket se vraća jednom i ne loguje. `PrivacyExportDownloadSession`: `session_digest`, `school_id`, `artifact_id`, `account_id`, `handoff_authorization_id nullable`, `authorization_version`, `subject_basis_hash`, `status ACTIVE|COMPLETED|EXPIRED|REVOKED`, `issued_at`, `expires_at` najviše 10min bez produženja, `last_range_at nullable`, `completed_at nullable`, `version`. REQUESTER_ACCOUNT_DOWNLOAD zahteva null handoff authorization i isti aktuelni requester account; CONTROLLED_STAFF_HANDOFF zahteva isti non-null APPROVED handoff authorization i tačno njegovog ovlašćenog staff account-a. Atomski consume pravi najviše jednu sesiju; svaki manifest/segment/range zahtev ponovo proverava M01/M03/M05, `privacy.exports.download`, subject/request scope, authorization version, mode-specifičan actor i artifact/handoff TTL.

`PrivacyExportHandoffAuthorization`: `id`, `school_id`, `artifact_id`, `requester_person_id`, `handoff_method enum(IN_PERSON_ENCRYPTED_DIGITAL,IN_PERSON_PRINTED)`, `authorized_staff_account_id`, `requested_by_account_id`, `approved_by_account_id nullable`, `status DRAFT|APPROVED|CONSUMED|REVOKED|EXPIRED`, `requested_at`, `approved_at nullable`, `expires_at`, `consumed_at nullable`, `recipient_identity_reverification_method_code nullable enum(IN_PERSON_OFFICIAL_DOCUMENT_INSPECTED_NO_COPY)`, `recipient_identity_reverified_at nullable`, `package_manifest_hash nullable`, `revoked_at nullable`, `revocation_reason_code nullable`, `version`; unique `(school_id,artifact_id)`. DRAFT nema approval/terminal polja. APPROVED zahteva approver različit od requester-a i authorized staff-a, fresh step-up, `expires_at<=min(approved_at+2h,artifact.expires_at)` i nema terminalna polja. CONSUMED zahteva tačan in-person identity re-verification metod, consume/reverify vreme i package manifest hash; REVOKED/EXPIRED zahtevaju samo pripadajući terminalni dokaz. Zapis nikada ne čuva email/adresu, broj/kopiju dokumenta, lozinku, sadržaj ili slobodnu belešku.

`PrivacyCommandReceipt`: `id`, `school_id`, `actor_account_id nullable`, `actor_type USER|SYSTEM`, `actor_scope_key Code128`, `command_name`, `idempotency_key_hash`, `request_hash`, `outcome SUCCEEDED|REJECTED`, `result_ref nullable`, `response_hash`, `created_at`, `expires_at`; unique `(school_id,actor_scope_key,command_name,idempotency_key_hash)`. USER zahteva non-null account i `actor_scope_key='ACCOUNT:'+lower(uuid)`; SYSTEM zahteva null account, `actor_scope_key='SYSTEM:'+job_key` i registry-allow-listed job/command. Nenull scope ključ sprečava da SQL nullable-UNIQUE semantika propusti dva system receipt-a. Čuva se najmanje 30 dana i duže kada odgovarajući evidence/retention ugovor to zahteva.

### 2.12 Relacije, conditional-null i integritet

- Svaki tenant entitet ima kompozitni FK `(school_id,id)` ka tenant owner-u.
- Consent definition referencira PUBLISHED processing purpose i tačan M15 document version/hash.
- Consent decision school/subject/giver/guardian/evidence moraju pripadati istom tenant kontekstu; globalni Person ne daje cross-school pravo.
- M17 ima fizičke tenant-safe reference ka M15 document/evidence zapisima. Obrnute M15 legal-policy vrednosti su samo immutable logical snapshot/ref + content hash bez fizičkog FK-a ili schema importa, pa dependency ostaje jednosmeran M17→M15.
- DataSubjectRequest može objediniti više PrivacyTask zapisa; completion se izvodi samo iz terminalnih task receipt-a. Neutralni application coordinator čita/zaključava M17 task kroz M17 API, poziva tačno jedan verzionisani owner port i zatim M17-u predaje durable owner receipt; M17 ne importuje owner schema, ne čita owner tabelu i ne poziva owner modul direktno.
- LegalHold se proverava pre planiranja i neposredno pre disposition commit-a.
- `RecordConsentDecision` orkestracija zaključava consent subject/head, aktuelni M07 authority snapshot i M15 requirement red deterministički; M17 decision, M15 evidence, oba owner audit/outbox zapisa i receipt commit-uju ili svi rollback-uju.
- `ConsentDecision` i M15 evidence moraju se poklopiti po giver/subject/participant, odluci, actor/channel/recorder identitetu, source proof-u, authorization basis-u, document/requirement verziji i korelaciji; nijedna vrednost se ne izvodi nagađanjem iz email-a ili UI label-a.
- Svaka versioned definicija u DRAFT ima publish/retire actor-vremena null. PUBLISHED zahteva publish actor/vreme i null retire actor/vreme; RETIRED zahteva oba para. `effective_until`, kada postoji, mora biti strogo posle `effective_from`.
- LegalHold DRAFT ima activation/release/expiry polja null; ACTIVE zahteva `starts_at`, activation actor/vreme i null release/expiry; RELEASED zahteva release actor/vreme/reason; EXPIRED zahteva `expired_at`, `expires_at<=expired_at` i nema lažnog release actor-a.
- DataSubjectRequest u IDENTITY_PENDING sme imati nullable identitetske/subject reference, ali intake ostaje dokaziv: EMAIL_INTAKE ima null submitter i obavezan M15 intake document; STAFF_ASSISTED ima submitter+intake document; AUTHENTICATED_WEB_PWA ima submitter i requester koji se poklapaju preko M01/M06 mapiranja. Dok je status IDENTITY_PENDING, identitetske reference/basis i sva verification polja su null, assurance je UNVERIFIED. Od RECEIVED nadalje `requester_person_id`, `subject_person_id`, non-UNVERIFIED assurance, `subject_basis_hash` i tačno usklađen method/actor/time trio su obavezni. SELF zahteva requester=subject i null guardian relation; CHILD_BY_GUARDIAN zahteva različit requester/subject i aktuelni M07 guardian relation istog school-a. Nijedan intake document/claim sam po sebi nije subject basis.
- DataSubjectRequest pause polja su oba non-null samo u WAITING_FOR_SUBJECT, a inače oba null. Tri `cancellation_*` polja su ili sva null ili sva non-null; non-null su dozvoljena samo u CANCEL_REQUESTED i terminalnom rezultatu requester withdrawal-a. CANCEL_REQUESTED nema `completed_at`, `decision_reason_code` ni response document. `completed_at` je non-null samo za terminalne statuse. COMPLETED zahteva M15 response document i null decision reason; PARTIALLY_COMPLETED zahteva M15 response document i zatvoren decision reason; REJECTED zahteva zatvoren decision reason i M15 response document koji objašnjava odbijanje i pravni/escalation kanal bez internog security detalja. CANCELLED zahteva cancellation trojku i `decision_reason_code=REQUEST_WITHDRAWN_NO_COMMITTED_EFFECT`, bez response document-a. EXPIRED je dozvoljen samo iz IDENTITY_PENDING na/posle immutable deadline-a, zahteva `decision_reason_code=IDENTITY_VERIFICATION_WINDOW_EXPIRED` i nema response document. PARTIALLY_COMPLETED nastao povlačenjem zahteva zahteva `decision_reason_code=REQUEST_WITHDRAWN_AFTER_COMMITTED_EFFECT` i M15 response document koji navodi kategorije već izvršenih efekata bez nepotrebnog PII-a.
- PrivacyTask LEASED jedini ima lease hash/until; PENDING/FAILED_RETRYABLE imaju `next_attempt_at`; SUCCEEDED zahteva result code+receipt+finished_at; FAILED_FINAL zahteva last error+finished_at; BLOCKED_BY_HOLD zahteva legal_hold_id i nema lease; CANCELLED zahteva result code+finished_at. Stale fencing token ne sme promeniti red.
- Download ticket `used_at` je non-null iff USED; session `completed_at` je non-null iff COMPLETED. EXPIRED/REVOKED autorizacija nikad ne vraća segment byte.
- Handoff authorization postoji samo za CONTROLLED_STAFF_HANDOFF artifact. Njegov requester/school/artifact composite mora odgovarati verifikovanom request-u. DRAFT/APPROVED ne dokazuju isporuku; samo CONSUMED uz identity re-verification i package hash. Završetak handoff-a u istom commit-u postavlja authorization CONSUMED, artifact REVOKED sa reason `CONTROLLED_HANDOFF_COMPLETED`, opoziva ticket/session i kreira durable segment deletion receipt.

## 3. Poslovna pravila, invarijante i edge cases

1. Svaka obrada mora imati aktivan `purpose_key`; „GDPR consent” nije univerzalni osnov.
2. Obavezna usluga ne sme koristiti CONSENT kao prikriven uslov. Odbijena opcionalna foto/video saglasnost ne blokira raspored, prisustvo, finansije, dokumenta potrebna za uslugu ili komunikaciju.
3. PHOTO i VIDEO, kao i svaki public channel scope, imaju posebne odluke. Nema bundled checkbox-a ni unapred čekiranog polja.
4. Povlačenje važi od committed `effective_at`; ne poništava zakonitu raniju obradu, ali blokira nove owner-module radnje zasnovane samo na toj saglasnosti.
5. Materijalno nova consent verzija postavlja `RECONSENT_REQUIRED`; stari grant se ne prenosi. Nematerijalna copy izmena bez promene svrhe/scope-a može zadržati state samo uz `material_change=false` i isti semantički hash registry.
6. Privacy notice zahteva acknowledgement evidence, ali acknowledgement nije consent i njegovo odbijanje/izostanak ne menja pravni osnov već samo onboarding status prema policy-ju.
7. Guardian može odlučivati za dete samo uz aktivan M07 relation i odgovarajući decision scope; pravo se proverava i pri prikazu i neposredno pre commit-a.
8. Dete bez utvrđenog capacity pravila nema self-consent u H0. Punoletna/osposobljena osoba odlučuje za sebe.
9. Owner modul pre opcionog korišćenja poziva `AuthorizeProcessing`; rezultat sadrži purpose/version, basis, consent head/security version i TTL≤60s. Visokorizičan/public-media write ponavlja proveru pre commit-a.
10. Consent cache nije autoritet ako freshness nije dokazana. Withdrawal bumpuje privacy authorization version u istom commit-u; naredni zahtev fail-closed čita authoritative state.
11. `GuardianLinkActivated`, `GuardianLinkRevoked` ili promena authority scope-a pokreću idempotentnu re-evaluaciju. Ako se `current_authority_set_hash` razlikuje od hash-a poslednjeg decision skupa, stanje je `RECONSENT_REQUIRED`; nikad se ne dobija skriveni GRANTED samo uklanjanjem davaoca koji je DECLINED/WITHDRAWN.
12. DSAR pristup izvozi samo podatke konkretnog subjekta i dozvoljeni kontekst; prava drugih lica se maskiraju/rediguju. Nema tenant-wide export-a kroz subject request.
13. Rectification ne prepisuje append-only finansijske/audit/evidence činjenice; owner modul dodaje korektivni zapis ili menja mutable profil prema svom ugovoru.
14. Erasure nije automatsko fizičko brisanje svega: legal obligation, legal claim, finansijska istorija, audit integritet i aktivan hold daju granularni `PARTIALLY_COMPLETED/REJECTED` rezultat sa reason code-om.
15. Legal hold zaustavlja samo obuhvaćene kategorije. Ne sme beskonačno blokirati nepovezane podatke niti dati korisniku podatke koje ranije nije smeo da vidi.
16. Retention task je idempotentan i tenant-fair. Uspeh se potvrđuje owner-module receipt-om; M17 ne proglašava brisanje na osnovu poslatog događaja.
17. Izvoz je šifrovan, vremenski ograničen, download reautorizovan, sa manifestom kategorija i redakcija. Link/token se ne šalje u push payload-u.
18. IP adresa se ne prikuplja po default-u. Ako aktivna policy verzija dokaže neophodnost, čuva se encrypted, odvojeno i sa kraćim rokom.
19. Nema PII, raw tokena, request teksta ili dokument sadržaja u logu, metric label-u, trace-u, outbox-u ili error detail-u.
20. Requester može povući neterminalni DSAR. Pre početka rada zahtev ide direktno u CANCELLED. Kada je rad počeo, zahtev ide u CANCEL_REQUESTED: PENDING/FAILED_RETRYABLE/BLOCKED_BY_HOLD taskovi se atomarno otkazuju, a LEASED task mora pre owner poziva ponovo proveriti request version/status. Durable owner receipt nastao pre te provere ili u već započetom owner commit-u ne sme se izgubiti. Reconciliation zaključava request i sve njegove taskove: nula SUCCEEDED taskova daje CANCELLED, a najmanje jedan SUCCEEDED task daje PARTIALLY_COMPLETED sa M15 odgovorom. Retention/policy task bez `request_id` nikada se ne otkazuje povlačenjem DSAR-a.
21. Unverified intake je evidencija prijema, ne potvrda identiteta ili prava. `VerifyIdentity` je idempotentna, expected-version komanda koja zaključava request, uzima svež autoritativni DB instant, proverava M01/M06/M07 i vezuje sve identitetske reference plus tačan verification method/actor/time u jednom commit-u sa status tranzicijom, auditom i receipt-om. Ako je `database_now >= identity_verification_deadline_at`, ista transakcija materijalizuje EXPIRED i ne prihvata dokaz, bez obzira da li expiry job već radi. Dva pokušaja koji claim-uju različitog requester-a/subjecta ne koriste last-write-wins: jedan može uspeti, drugi dobija version conflict i zahteva novu ljudsku proveru.
22. `privacy.dsar_orchestration` koristi database clock i materijalizuje IDENTITY_PENDING u EXPIRED na verification deadline-u; request-time `VerifyIdentity` sprovodi isti cutoff, pa petnaestominutni raspored job-a nije grace period. Idempotentni retry vraća isti EXPIRED receipt; kasni identity proof ne oživljava red, već zahteva novi povezani request. Expiry ne briše M15 intake dokument mimo njegove M17 retention/legal-hold politike i ne predstavlja odluku o meritumu zahteva. IDENTITY_PENDING se ne može povući kao verifikovan requester zahtev: actor prvo mora uspešno dokazati identitet, a zatim iz VALIDATING stanja poslati cancellation, ili intake bez verifikacije deterministički ističe.
23. Verifikovani requester bez aktivnog M01 naloga ne dobija lažni self-service ticket niti mora da otvori nalog. Koristi se CONTROLLED_STAFF_HANDOFF sa dual control-om, fresh step-up proverom staff actor-a i ponovnom in-person proverom identiteta primaoca bez čuvanja dokumenta/broja. Export byte, javni/signed URL, ticket, password ili prilog nikada se ne šalju emailom, push-om ili porukom. Digitalni paket se predaje lično, re-enkriptovan za jednokratni recipient secret koji SOKOLA ne čuva i koji se ne prenosi istim kanalom; štampani paket se predaje lično. Neuspešan/napušten handoff ne sme biti označen kao delivered. Request-time guard odbija DRAFT/APPROVED handoff čim `database_now>=expires_at`; M21 `privacy.export_expiry_cleanup` samo materijalizuje EXPIRED i opoziva povezani ticket/session, bez grace perioda.

### 3.1 Granični slučajevi

| # | Scenario | Determinističko ponašanje |
|---:|---|---|
| 1 | Dva guardian-a istovremeno daju suprotne odluke | Zaključavaju se oba giver head-a i agregat po determinističnom redosledu; `ANY_DECLINE_BLOCKS` proizvodi konzervativni efektivni rezultat bez last-write-wins. Škola ne sme preglasati odluku. |
| 2 | Guardian relation opozvan posle prikaza forme | Precommit M07 recheck; 403/404, nema decision/evidence uspeha. |
| 3 | Withdrawal i public-photo publish u trci | Privacy version/consent head zaključavanje; withdrawal commit sprečava kasniji publish; in-flight publish ponavlja guard. |
| 4 | Nova consent verzija objavljena tokom klika | Expected definition version/hash mismatch 409; korisniku se prikazuje nova verzija. |
| 5 | Dupli klik Grant istim ključem | Jedan decision/evidence; isti receipt. Isti ključ/drugi payload 409. |
| 6 | Legal hold aktiviran dok delete task čeka | Precommit hold recheck; task BLOCKED_BY_HOLD, ništa obrisano. |
| 7 | Owner modul privremeno nedostupan | Task FAILED_RETRYABLE uz backoff; zahtev ostaje IN_PROGRESS, nema lažnog completion-a. |
| 8 | ACCESS export sadrži drugog roditelja | Redaction policy uklanja kontakt/privatne podatke drugog lica; manifest beleži kategoriju redakcije, ne njen sadržaj. |
| 9 | Zahtev stigao pred rok, identitet nije potvrđen | IDENTITY_PENDING; due clock/pauza samo po eksplicitnom policy/legal rule-u, nikad proizvoljno. |
| 10 | Škola deaktivirana | Novi consent/DSAR intake ostaje dostupan kroz minimalan compliance kanal; redovne poslovne obrade su blokirane prema M04. |
| 11 | Consent dokument uklonjen iz M15 | Objavljena definition ostaje vezana za immutable historical version; novi grant nije moguć ako version nije dostupna za prikaz. |
| 12 | Cross-tenant isti Person ID | School+subject basis obavezan; druga škola dobija safe 404 i nema indikator postojanja odluke. |
| 13 | Guardian A grant, guardian B decline, zatim se B veza opozove | Stanje postaje `RECONSENT_REQUIRED/GUARDIAN_AUTHORITY_CHANGED`, ne GRANTED; istorija obe odluke ostaje. |
| 14 | M15 evidence upis padne posle pripreme M17 decision-a | Cela coordinator transakcija rollback-uje; nema ConsentDecision bez odgovarajućeg evidence-a. |
| 15 | Requester povuče zahtev dok worker drži LEASED task | CANCEL_REQUESTED i fencing sprečavaju novi owner poziv; ako je owner receipt već durable, on se priznaje i ishod je PARTIALLY_COMPLETED, inače task postaje CANCELLED i zahtev završava CANCELLED. |
| 16 | Email intake sadrži adresu/ime postojeće osobe ili tvrdi dete druge škole | Kreira se samo IDENTITY_PENDING sa restricted M15 intake dokumentom i null Person/subject vezama; nema email auto-linka, target lookup odgovora ili cross-tenant indikatora. Ako se identitet kasnije ručno potvrdi bez naloga, odgovor ide samo controlled in-person handoff-om. |

## 4. Tenant & Security Guard

Svaka komanda/query prolazi: M01 session → M03 tenant context → M04 School status/compliance allowance → M05 permission → M17 resource guard → M07 subject/guardian guard → M15 exact document/evidence guard gde je potreban. Organizacija, email, globalni Person ili UI workspace ne daju pristup.

Kanonski permission ključevi su pojedinačno registrovani u M05 `03-M05-PERMISSION-REGISTRY-M17-M21-M28.md`: `privacy.purposes.view`, `privacy.purposes.manage`, `privacy.purposes.publish`, `privacy.notices.view`, `privacy.notices.manage`, `privacy.notices.publish`, `privacy.consents.view`, `privacy.consents.manage`, `privacy.consents.publish`, `privacy.consents.decide_self`, `privacy.consents.decide_child`, `privacy.consents.assist`, `privacy.requests.create_self`, `privacy.requests.create_child`, `privacy.requests.view`, `privacy.requests.manage`, `privacy.requests.decide`, `privacy.retention.view`, `privacy.retention.manage`, `privacy.retention.publish`, `privacy.legal_hold.view`, `privacy.legal_hold.manage`, `privacy.legal_hold.approve`, `privacy.exports.download`, `privacy.audit.view`. Slash-skraćenica nije runtime ključ. OWNER/MANAGER nemaju implicitni pristup sadržaju svih DSAR priloga; potreban je purpose/assignment. Support standardno dobija samo maskirane agregate; break-glass ne može grantovati consent niti obrisati/izvesti child podatke bez zasebnog scope-a i školskog naknadnog pregleda.

Cross-tenant/skriven target je safe 404. Poznat vidljiv resurs bez akcije je 403. List/count/search primenjuju tenant+subject filter pre agregacije, sortiranja i paginacije. Storage je private; export/download koristi M15-equivalent single-use ticket i ponovnu autorizaciju. Enkripcioni ključevi/kontekst su tenant-bound; backup/restore zadržava izolaciju.

## 5. Lifecycle i dozvoljene tranzicije

### 5.1 Verzije politike/notice/consent/retention

| Stanje | Komanda | Novo stanje | Uslov |
|---|---|---|---|
| — | CreateDraft | DRAFT | Validan tenant i permission. |
| DRAFT | UpdateDraft | DRAFT | Expected version; nema istorijskog overwrite-a objavljenog zapisa. |
| DRAFT | Publish | PUBLISHED | Potpun schema/hash/document/retention guard; non-overlap. |
| PUBLISHED | Retire | RETIRED | Reason; nova obrada ne bira retired verziju. |
| PUBLISHED | CreateNewVersion | DRAFT | Novi red; stari immutable. |

### 5.2 Consent effective state

| Pre | Akcija | Posle |
|---|---|---|
| NOT_ASKED | Grant | GRANTED |
| NOT_ASKED | Decline | DECLINED |
| GRANTED | Withdraw | WITHDRAWN |
| DECLINED/WITHDRAWN | Grant na istoj važećoj verziji | GRANTED, novi decision |
| bilo koje | Objavljena material-change verzija | RECONSENT_REQUIRED |
| RECONSENT_REQUIRED | Grant/Decline nove verzije | GRANTED/DECLINED |

Promena M07 authority set-a iz bilo kog consent stanja vodi u `RECONSENT_REQUIRED`. Novo odlučivanje zapisuje aktuelni `authority_set_hash_at_decision`; agregat se ne vraća u GRANTED dok najmanje jedna važeća odluka pod aktuelnim authority set-om ne prođe definisani prioritet.

Nema `WITHDRAWN→GRANTED` update-a starog reda; svaki korak je novi append-only decision. Retired consent ne prima novu odluku.

### 5.3 DataSubjectRequest

| Pre | Akcija | Posle |
|---|---|---|
| — | Submit | RECEIVED ili IDENTITY_PENDING |
| RECEIVED | StartValidation | VALIDATING |
| IDENTITY_PENDING | VerifyIdentity | VALIDATING |
| IDENTITY_PENDING | verification deadline job | EXPIRED |
| VALIDATING | AcceptForWork | IN_PROGRESS |
| VALIDATING | Reject | REJECTED |
| IN_PROGRESS | AskSubject | WAITING_FOR_SUBJECT |
| WAITING_FOR_SUBJECT | ReceiveSubjectInput | IN_PROGRESS |
| IN_PROGRESS | CompleteAll | COMPLETED |
| IN_PROGRESS | CompleteWithExceptions | PARTIALLY_COMPLETED |
| RECEIVED/VALIDATING | CancelByRequester | CANCELLED |
| IN_PROGRESS/WAITING_FOR_SUBJECT | CancelByRequester | CANCEL_REQUESTED |
| CANCEL_REQUESTED | ReconcileCancellation; nema SUCCEEDED taska | CANCELLED |
| CANCEL_REQUESTED | ReconcileCancellation; postoji najmanje jedan SUCCEEDED task | PARTIALLY_COMPLETED |

COMPLETED/PARTIALLY_COMPLETED/REJECTED/CANCELLED/EXPIRED su terminalni; korekcija otvara novi povezani request. `CancelByRequester` i `ReconcileCancellation` zaključavaju request red uz expected version. Ako completion commit pobedi pre cancellation lock-a, zahtev je već terminalan i cancel dobija 409 bez promene; ako cancellation pobedi, nijedan kasniji completion ne može preskočiti CANCEL_REQUESTED reconciliation.

### 5.4 LegalHold i PrivacyTask

| Entitet | Pre | Akcija | Posle | Obavezna garancija |
|---|---|---|---|---|
| LegalHold | — | Request | DRAFT | requester, scope i razlog; nema aktivnog efekta |
| LegalHold | DRAFT | ApproveAndActivate | ACTIVE | drugi actor, step-up, `starts_at`, audit |
| LegalHold | ACTIVE | Release | RELEASED | drugi ovlašćeni actor, reason, audit |
| LegalHold | ACTIVE | expiry job na `expires_at` | EXPIRED | DB clock, deterministički receipt |
| PrivacyTask | — | Plan | PENDING | request ili retention policy source |
| PrivacyTask | PENDING/FAILED_RETRYABLE | fenced claim | LEASED | važeći lease/fencing; attempts++ |
| PrivacyTask | LEASED | owner receipt durable | SUCCEEDED | result code/hash/finished time |
| PrivacyTask | LEASED | transient allow-list failure | FAILED_RETRYABLE | safe error + `next_attempt_at` |
| PrivacyTask | LEASED | terminal/max failure | FAILED_FINAL | safe error + finished time |
| PrivacyTask | PENDING/LEASED | matching hold | BLOCKED_BY_HOLD | lease više ne daje commit pravo |
| PrivacyTask | BLOCKED_BY_HOLD | hold više nije efektivan | PENDING | ponovna policy/owner provera |
| PrivacyTask | PENDING/FAILED_RETRYABLE/BLOCKED_BY_HOLD | request je CANCEL_REQUESTED | CANCELLED | zatvoren result code; nema owner write-a |
| PrivacyTask | LEASED | cancellation recheck pre owner poziva | CANCELLED | važeći fencing token; owner nije pozvan |
| PrivacyTask | LEASED | durable owner receipt postoji uprkos cancellation race-u | SUCCEEDED | receipt se ne odbacuje; request reconciliation određuje PARTIALLY_COMPLETED |

RELEASED/EXPIRED hold i SUCCEEDED/FAILED_FINAL/CANCELLED task su terminalni. Lease fencing sprečava stale worker commit.

### 5.5 Privacy export i download

`PrivacyExportArtifact`: `—→QUEUED→BUILDING→AVAILABLE`; QUEUED/BUILDING mogu preći u FAILED ili REVOKED; AVAILABLE prelazi u EXPIRED na TTL ili REVOKED na authorization/request opoziv odnosno završeni controlled handoff. FAILED/EXPIRED/REVOKED su terminalni i nikada se ne oživljavaju; retry pravi novi artifact vezan za isti request i nov idempotency key. Ticket: `—→ACTIVE→USED|EXPIRED|REVOKED`. Session: `—→ACTIVE→COMPLETED|EXPIRED|REVOKED`. Handoff: `—→DRAFT→APPROVED→CONSUMED`, a DRAFT/APPROVED mogu u REVOKED/EXPIRED; terminalna stanja se ne oživljavaju. Dva paralelna consume-a istog ticket-a daju tačno jednu sesiju; dva completion pokušaja istog handoff-a daju jedan CONSUMED receipt i jedno brisanje artifact-a.

## 6. Error catalog

| Kod | HTTP | Značenje |
|---|---:|---|
| `M17_NOT_FOUND` | 404 | Target ne postoji ili je skriven/cross-tenant. |
| `M17_FORBIDDEN` | 403 | Vidljiv resurs, nedostaje akcijska dozvola. |
| `M17_INVALID_INPUT` | 422 | Nevalidan enum/polje/interval/hash. |
| `M17_PURPOSE_NOT_ACTIVE` | 409 | Nema aktivne svrhe/verzije. |
| `M17_CONSENT_NOT_VALID_BASIS` | 422 | CONSENT se koristi za obaveznu H0 obradu. |
| `M17_BUNDLED_CONSENT_FORBIDDEN` | 422 | Više scope-ova u jednoj odluci. |
| `M17_GUARDIAN_BASIS_INVALID` | 403 | Nema aktuelnog M07 ovlašćenja. |
| `M17_DEFINITION_STALE` | 409 | Verzija/hash promenjen. |
| `M17_DECISION_CONFLICT` | 409 | Paralelna ili authority-mode kontradikcija. |
| `M17_IDEMPOTENCY_KEY_REUSED` | 409 | Isti ključ, drugi payload. |
| `M17_VERSION_CONFLICT` | 409 | Expected version nije aktuelan. |
| `M17_DOCUMENT_UNAVAILABLE` | 409 | Tačna M15 verzija nije prikaziva. |
| `M17_REQUEST_IDENTITY_REQUIRED` | 403 | Nedovoljan assurance za zahtev. |
| `M17_REQUEST_INTAKE_INVALID` | 422 | Intake channel, submitter, M15 dokument ili nullable identity skup nisu konzistentni. |
| `M17_REQUEST_TRANSITION_INVALID` | 409 | Nedozvoljena state tranzicija. |
| `M17_LEGAL_HOLD_ACTIVE` | 409 | Disposition blokiran aktivnim hold-om. |
| `M17_RETENTION_NOT_DUE` | 409 | Rok nije nastupio. |
| `M17_OWNER_MODULE_UNAVAILABLE` | 503 | Owner port failuje; nema lažnog uspeha. |
| `M17_EXPORT_NOT_READY` | 409 | Export nije kompletan/verifikovan. |
| `M17_DOWNLOAD_TICKET_INVALID` | 404 | Nepostojeći/istekao/iskorišćen ticket. |
| `M17_EXPORT_EXPIRED` | 410 | Artifact/session je istekao; byte se ne vraća. |
| `M17_EXPORT_REVOKED` | 410 | Request, subject basis ili authorization je opozvan. |
| `M17_EXPORT_LIMIT_EXCEEDED` | 413 | Segment ili kompletan export prelazi propisanu granicu. |
| `M17_HANDOFF_INVALID` | 409 | Mode, dual-control, staff actor, TTL ili identity re-verification handoff-a nije validan. |
| `M17_RATE_LIMITED` | 429 | Tenant/actor limit. |
| `M17_STEP_UP_REQUIRED` | 401 | Potrebna sveža step-up autentifikacija. |

Error body sadrži samo `code`, generičku i18n poruku, `correlation_id` i bezbedne retry podatke. Nema stack trace-a, PII-a, cross-tenant indikatora ili policy tajne.

`M17_ALREADY_EQUIVALENT` nije greška: identična semantička/idempotentna komanda vraća HTTP 200, originalni receipt i `result_code=M17_ALREADY_EQUIVALENT`, bez novog decision/evidence/audit/outbox efekta.

## 7. API, idempotency, concurrency, audit i NFR

Komande: `Create/Update/Publish/RetireProcessingPurpose`, `Create/Publish/RetirePrivacyNotice`, `Create/Publish/RetireConsentDefinition`, `RecordConsentDecision` (neutralni M17+M15 coordinator), `ReevaluateConsentAuthoritySet`, `Create/Publish/RetireRetentionPolicy`, `Request/ApproveAndActivate/ReleaseLegalHold`, `Submit/Verify/Validate/Decide/Complete/CancelDataSubjectRequest`, `Plan/Lease/CompletePrivacyTask`, `Request/RevokePrivacyExport`, `Request/Approve/RevokeControlledPrivacyExportHandoff`, `Issue/ConsumePrivacyExportDownloadTicket`, `CompletePrivacyExportDownloadSession`, `CompleteControlledPrivacyExportHandoff`. Query-ji: `GetEffectiveProcessingAuthorization`, `GetConsentState`, `ListPrivacyNotices`, `GetDataSubjectRequest`, `ListPrivacyTasks`, `GetPrivacyExport`, `GetControlledPrivacyExportHandoff`, `StreamPrivacyExportSegmentRange`. Svaki write ima `Idempotency-Key`, `correlation_id`, canonical payload hash; mutacije imaju expected version. Receipt traje najmanje do kraja odgovarajućeg retention/audit roka, nikad kraće od 30 dana.

Lock order: School privacy-version head → policy/consent head → subject → giver head-ovi sortirani po `giver_person_id` → aggregate consent head → request → task/artifact; legal hold pre owner target. Dva različita payload-a sa istim key-em su 409. Worker koristi samo digestovan lease token+fencing i `SKIP LOCKED`; retry je exponential+jitter sa tenant fairness, max pokušaji po published policy-ju, zatim manual review. Za owner-module privacy task nema distributed transaction-a: neutralni application coordinator zavisi od M17 task API-ja i verzionisanog owner porta, dok ni M17 ni owner modul ne zavise jedan od drugog za orchestration. Owner port vraća durable receipt/event; coordinator njime završava M17 task, M17 saga napreduje tek nakon tog dokaza, a request completion čeka sve terminalne taskove. Consent decision, M15 evidence, giver/effective projekcije, audit, outbox i receipt koriste zajedničku lokalnu transakciju modularnog monolita; nijedan GRANTED/DECLINED/WITHDRAWN state nije vidljiv ako odgovarajući immutable M15 evidence nije durable.

Audit događaji: `privacy_purpose_published`, `privacy_notice_published`, `consent_definition_published`, `consent_decision_recorded`, `consent_withdrawn`, `privacy_request_received/status_changed/completed`, `retention_task_completed`, `legal_hold_requested/activated/released`, `privacy_export_requested/available/downloaded/revoked/expired`. Outbox nosi school, opaque IDs, type/status/version/effective_at; nema imena, emaila, razloga u slobodnom tekstu, IP-a ili sadržaja.

List API cursor default 25/max100; date range 366 dana, šire kroz async export. Jedan segment je najviše 100.000 redova i 2 GiB; jedan artifact najviše 20 segmenata/2.000.000 redova/20 GiB, a veći zahtev se deli na zasebne odobrene artifact-e ili odbija 413 bez silent truncation-a. Generisanje i streaming su bounded-memory. Artifact download TTL je najviše 24h; ticket ≤60s; sesija ≤10min. p95 consent state≤250ms, decision≤600ms, request read≤350ms bez eksternog worker vremena. Rate limits: decision 30/min/account; DSAR submit 5/24h/subject/type uz accessibility override; export download 10/h/account. Observability koristi module/operation/result/latency/tenant_hash, nikad raw school/person/request ID.

Minimalni indeksi: purpose `(school_id,purpose_key,status,effective_from)`; consent definition `(school_id,consent_key,status,effective_from)`; decision `(school_id,subject_person_id,consent_definition_version_id,effective_at,id)`; effective unique; request `(school_id,subject_person_id,status,statutory_due_at,id)`; hold scope/status; task `(school_id,status,next_attempt_at,id)` i lease expiry; artifact `(school_id,request_id,status,created_at)`; segment unique `(school_id,artifact_id,sequence_no)`; ticket/session digest unique. Partial UNIQUE/constraint sprečava preklapajuće published intervale i dva aktivna head-a.

## 8. Acceptance kriterijumi, migracija i seed

M17 je prihvatljiv tek kada `02-M17-QA-I-TRACEABILITY.md` prođe bez preskočenih kritičnih testova. Migracija prvo inventariše svaki postojeći consent/privacy/marketing flag; mapira samo uz dokaz `source→definition version→subject→giver→timestamp→document/hash`. Nedokazani boolean postaje `NOT_ASKED`, nikad GRANTED. Legacy bundled photo/video se ne deli u dva granta; oba postaju RECONSENT_REQUIRED. Backfill je tenant-batched, idempotentan, resumable i ne loguje PII. Dual-read je dozvoljen samo privremeno; cutover/rollback zadržava stari izvor read-only do reconciliation-a.

Obavezni sintetički seed: dve škole; isti globalni adult Person sa različitim membership/guardian scope-om; po dvoje dece; dva guardian-a sa konfliktom; PHOTO i VIDEO definicije po private/public kanalu; notice material/non-material verzije; grant/decline/withdraw/reconsent; ACCESS/ERASURE request; jedan granularni legal hold; retry/final task; export sa redakcijom. Svi emailovi koriste `example.invalid`; nema realnih podataka.
