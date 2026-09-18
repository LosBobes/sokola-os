---
modul-id: M21
tip: qa-traceability
status: SPEC_CANDIDATE
revizija: "2.2"
datum: 2026-09-16
obavezni-scenariji: 151
---

# M21 — QA i operativni acceptance

Seed: dva tenant-a, platform event, svih 40 published job definitions iz kataloga v1 (39 H0 + M28 expiry default-disabled pre feature aktivacije), duplicate/out-of-order/poison events, producer stream sa sekvencama 1..5, lease races, PII fuzz payload, broker/storage/telemetry outage, audit month boundary/seal, corrupted backup, incompatible migration/app rollback i isolated restore environment. Clock/broker su deterministički.

| ID | Scenario | Očekivanje |
|---|---|---|
| M21-QA-001 | Business commit sa audit/outbox, uključujući canonical `event_hash` i outbox `payload_hash`. | Business, audit i immutable-hashovan outbox commit-uju svi ili svi rollback-uju; broker nije deo DB transakcije. |
| M21-QA-002 | DB failure pre outbox. | Nema business write-a. |
| M21-QA-003 | Broker outage posle commit-a. | Outbox PENDING; business ostaje jednom. |
| M21-QA-004 | Publish pa crash pre ack-a. | Redelivery; consumer effect jednom. |
| M21-QA-005 | Isti message ID/drugi payload hash. | Terminal security incident. |
| M21-QA-006 | Duplicate event 10x. | Jedan inbox effect. |
| M21-QA-007 | Aggregate v3 pa v2. | v2 stale/ignored po consumer ugovoru. |
| M21-QA-008 | Unsupported event version. | Dead-letter/alert, bez guess parse-a. |
| M21-QA-009 | Outbox payload s emailom. | Schema odbija business commit. |
| M21-QA-010 | Outbox payload s token/cipher key. | Schema odbija. |
| M21-QA-011 | Publisher lease race. | Jedan valid fencing publisher. |
| M21-QA-012 | Late publisher ack. | Ne menja noviju state generaciju. |
| M21-QA-013 | Retryable 503. | Backoff+jitter do max. |
| M21-QA-014 | Validation 422. | Terminalno, nema besmislenog retry-a. |
| M21-QA-015 | Max attempts. | DEAD_LETTERED + alert. |
| M21-QA-016 | Cancel already published. | Odbijeno; ne briše događaj. |
| M21-QA-017 | `CanonicalJsonV1/HashV1` kontrolni vektor i AuditEvent append. | Kontrolni vektor daje tačno `a86c94641070bd858e558d02644c8f398c3169541d8cb423278060b8dd302da2`; sequence/previous/event hash chain se reprodukuje byte-identično u svim runtime-ovima. |
| M21-QA-018 | Audit update/delete regular API. | Nema operacije/DB odbija. |
| M21-QA-019 | Izmena jednog istorijskog allow-listed byte-a, prethodnog hash-a ili canonical serializer pravila. | Ponovni `HashV1` ne odgovara; verify dodaje CORRUPT/critical incident, ništa istorijsko ne prepisuje. |
| M21-QA-020 | Audit metadata free-text/PII. | Allow-list odbija/rediguje pre commit-a. |
| M21-QA-021 | School A audit query s B ID-em. | Safe 404/nema count/cursor. |
| M21-QA-022 | Support audit. | Samo dozvoljeni sopstveni/support review projection. |
| M21-QA-023 | Break-glass audit delete/export. | Zabranjeno. |
| M21-QA-024 | Audit export. | Reauth, encrypted, expiring, tenant-only. |
| M21-QA-025 | Platform-null school business event. | Schema odbija ako nije registry allow-list. |
| M21-QA-026 | Telemetry event s child ID. | Odbijen/redacted. |
| M21-QA-027 | Telemetry s search text/amount. | Odbijen. |
| M21-QA-028 | URL query/path params u telemetry. | Nisu poslati. |
| M21-QA-029 | Daily pseudonym sutradan. | Ne može se povezati istim ključem. |
| M21-QA-030 | High-cardinality raw error. | Bounded error code samo. |
| M21-QA-031 | Telemetry provider outage. | Business radi; bounded buffer/drop metric. |
| M21-QA-032 | Telemetry sample 0%. | Audit/security decision nepromenjen. |
| M21-QA-033 | Public health. | Samo generic status. |
| M21-QA-034 | Detailed health bez permission. | 403. |
| M21-QA-035 | Alert storm 1k identičnih. | Dedupe/cooldown; incident count. |
| M21-QA-036 | Alert payload. | Nema tenant name/PII/secret. |
| M21-QA-037 | Published job registry. | Tačno 40 definicija i svaki key/trigger/limit odgovara katalogu v1; 39 su H0, a M28 expiry je default-disabled dok M28 feature nije efektivan. |
| M21-QA-038 | Unknown job u production. | Ne startuje. |
| M21-QA-039 | FORBID_OVERLAP parallel trigger. | Jedan run, drugi coalesced/rejected. |
| M21-QA-040 | ALLOW_BOUNDED preko limita. | Nema dodatnog claim-a. |
| M21-QA-041 | JobAttempt heartbeat stane. | Attempt LEASE_LOST; novi attempt_no i fencing token u istom logičkom JobExecution-u. |
| M21-QA-042 | Late old job checkpoint. | Odbijen. |
| M21-QA-043 | Job attempt/runtime timeout. | Attempt TIMED_OUT; execution prelazi u sledeći attempt ili terminal po tačnoj katalog politici. |
| M21-QA-044 | Job manual trigger bez permission/reason. | 403/422. |
| M21-QA-045 | DST nonexistent time. | Owner policy; scheduler ne nagađa. |
| M21-QA-046 | DST duplicate time. | Semantic idempotency jedan run. |
| M21-QA-047 | A poison workload/B normal. | Tenant fairness; B napreduje. |
| M21-QA-048 | Job checkpoint s PII. | Schema odbija/šifruje samo dozvoljeni opaque. |
| M21-QA-049 | Dead letter OPEN. | Nije automatski replay. |
| M21-QA-050 | Replay bez approval. | 403/409. |
| M21-QA-051 | Replay s promenjenim tenant/payload. | Zabranjeno. |
| M21-QA-052 | Replay stare verzije posle novije. | NOT_SAFE; nema rollback state-a. |
| M21-QA-053 | Bezbedan replay. | Novi replay attempt, original semantic dedupe; izvorni terminalni zapis se ne oživljava. |
| M21-QA-054 | Dva replay approval-a. | Expected version; jedan pobednik. |
| M21-QA-055 | Discard bez reason. | 422. |
| M21-QA-056 | Deadletter payload s raw exception. | Redacted/sanitized ref only. |
| M21-QA-057 | Startup missing required config. | Fail pre traffic-a. |
| M21-QA-058 | Unknown config key. | Fail/warning po schema; unsafe nije ignored. |
| M21-QA-059 | Secret u repo/config outputu. | Secret scan/release fail. |
| M21-QA-060 | Secret rotation. | Nova verzija bez plaintext loga/downtime tvrdnje. |
| M21-QA-061 | Feature flag OFF. | Capability unavailable; server guard i dalje važi. |
| M21-QA-062 | Flag korišćen kao auth. | Security test pada. |
| M21-QA-063 | mySOKOLA bez allowlist. | Default OFF. |
| M21-QA-064 | Kill switch. | Nova operacija blokirana, data ostaje konzistentna. |
| M21-QA-065 | DB backup uspe, objects ne. | Backup FAILED. |
| M21-QA-066 | Backup encryption/key metadata. | VERIFIED samo uz oba. |
| M21-QA-067 | Corrupted backup. | Verification/restore fail, ne kandidat. |
| M21-QA-068 | Restore direktno u production. | Zabranjeno. |
| M21-QA-069 | Isolated restore DB+objects. | Hash/references konzistentni. |
| M21-QA-070 | Restore tenant-negative suite. | Nema A/B leak-a. |
| M21-QA-071 | Restore revoked session. | Ostaje revoked. |
| M21-QA-072 | Restore finance/document hashes. | Exact/integritet prolazi. |
| M21-QA-073 | Restore outbox duplicate. | Consumer effect jednom. |
| M21-QA-074 | Restore environment cleanup. | DESTROYED + dokaz. |
| M21-QA-075 | RPO/RTO rehearsal. | Izmerene vrednosti ≤24h/≤8h i integrity suite daju dokaz, ili je pilot NO_GO; sama specifikacija nije SLA dokaz. |
| M21-QA-076 | Backup stariji od policy-ja. | Alert/pilot blocker. |
| M21-QA-077 | Additive expand migration. | Old/new app kompatibilni tokom prelaza. |
| M21-QA-078 | Backfill retry. | Idempotent, checkpoint, bez duplikata. |
| M21-QA-079 | Contract column pre reader switch-a. | Migration guard blokira. |
| M21-QA-080 | Long table lock procena prekoračena. | Deploy blokiran/downtime plan. |
| M21-QA-081 | Ambiguous legacy tenant. | Exception report; nema guess mapping-a. |
| M21-QA-082 | Migration failure. | Transaction rollback/forward recovery; dokaz. |
| M21-QA-083 | App rollback kompatibilna schema. | Dozvoljen immutable prior artifact. |
| M21-QA-084 | App rollback destructive-incompatible. | 409; forward recovery. |
| M21-QA-085 | Rollback oživljava revoked rights. | Security test blokira. |
| M21-QA-086 | Artifact različit između staging/prod. | Release rejected. |
| M21-QA-087 | Missing commit/lock/build hash. | Evidence incomplete. |
| M21-QA-088 | SBOM/dependency scan missing. | Release rejected. |
| M21-QA-089 | Critical vulnerability unresolved. | Release/pilot blocked. |
| M21-QA-090 | Test manifest ima skipped critical. | Release rejected. |
| M21-QA-091 | Staging ima realan child PII pre approval. | Security incident/blocker. |
| M21-QA-092 | Synthetic two-tenant seed. | Determinističan i idempotent. |
| M21-QA-093 | Fresh setup po README. | Druga osoba podiže build/test bez usmenog znanja. |
| M21-QA-094 | Missing env variable documentation. | Handover fail bez secret value objave. |
| M21-QA-095 | Deploy rehearsal. | Health/smoke/migration checks dokazani. |
| M21-QA-096 | Rollback/forward recovery rehearsal. | Izvršiv, očuva kritične invarijante. |
| M21-QA-097 | Incident runbook broker/db/storage. | Tačan owner/detection/containment/recovery. |
| M21-QA-098 | Audit/telemetry retention. | M17 policy + legal hold; nema proizvoljnog delete-a. |
| M21-QA-099 | Kompletan M00–M21 QA manifest. | Brojevi/mapiranja/test commands stvarni, 0 critical skipped. |
| M21-QA-100 | Full pilot-readiness rehearsal. | Restore, tenant, auth, privacy, kill switch, alert, rollback; PASS ili eksplicitni NO_GO. |
| M21-QA-101 | Dva paralelna business commita u istom producer stream-u. | Stream head daje jedinstvene uzastopne sequence brojeve bez commitovane rupe. |
| M21-QA-102 | Transakcija alocira sequence pa rollback. | Head increment i message oba rollback; sledeći commit dobija isti sledeći broj. |
| M21-QA-103 | Consumer primi sequence 1,3,2. | Posle 3 barrier ostaje 1; posle 2 atomarno napreduje na 3. |
| M21-QA-104 | Sequence 2 je DEAD_LETTERED. | Barrier ne preskače 2 dok owner-approved terminal disposition nije evidentiran; tada može napredovati. |
| M21-QA-105 | M18 snapshot traži source barrier 5, obrađeno 1..4. | Snapshot finance/report je UNAVAILABLE; nema lažne svežine. |
| M21-QA-106 | Dva identična scheduled trigger-a. | Jedan JobExecution po semantic scope-u; ne postoje dupli logical run-ovi. |
| M21-QA-107 | Retryable attempt fail pa uspeh. | Jedan execution, dva immutable JobAttempt reda, execution SUCCEEDED. |
| M21-QA-108 | Isti JobExecution trigger sa drugim payload/semantic hash-om pod istim idempotency key-em. | 409; prvi execution ostaje autoritet. |
| M21-QA-109 | Cancel se trka sa result commit-om. | Fencing/CAS daje ili SUCCEEDED ili CANCELLED; nikad oba ni partial checkpoint. |
| M21-QA-110 | Unknown family alias `JOB-11` pokušava start. | 422; samo stabilan katalog `job_key` i published version rade. |
| M21-QA-111 | Svaka od 40 definicija contract test. | Trigger, semantic key, scope, concurrency, runtime, lease, heartbeat, attempts i retry allow-list tačno odgovaraju katalogu; M12 event-cancellation i M20 issue-report job deduplikuju originalnim message ID-em, a schema/aggregate/source version koriste samo kao compatibility/stale guard. M04 effective-transition je jedan PLATFORM agreement-shard coordinator, ne PER_SCHOOL parent transition. |
| M21-QA-112 | Replay attempt ponovo failuje. | DeadLetter REPLAY_FAILED sa sanitized code/ref; nema automatskog trećeg pokušaja. |
| M21-QA-113 | Novi replay iz REPLAY_FAILED bez nove approval generation. | 409; source/payload nepromenjeni. |
| M21-QA-114 | Nova dual approval generation pa replay success. | REPLAY_APPROVED→REPLAYING→RESOLVED; oba pokušaja ostaju u istoriji. |
| M21-QA-115 | Audit partition shard fixture sa separatorima, Unicode vrednošću i zamenjenim redosledom JSON ključeva. | Domain+CanonicalJsonV1 algoritam daje isti shard u svim podržanim runtime-ovima; dve različite `(resource_type,resource_id)` vrednosti se ne spajaju zbog ambigviteta konkatenacije. |
| M21-QA-116 | Month seal dok period još traje. | Odbijeno; OPEN ostaje. |
| M21-QA-117 | Seal closed segment pa verify u drugom runtime-u. | `segment_digest`, `seal_hash` i ED25519 potpis reprodukuju se po tačnim domenima; immutable seal nastaje jednom, a zatim zaseban append-only VERIFIED rezultat sa count/first/last/previous-seal proverom. |
| M21-QA-118 | Istorijski audit byte ili signature promenjen posle verify. | Sledeća provera dodaje CORRUPT verification i critical incident; seal i raniji VERIFIED red se ne menjaju. |
| M21-QA-119 | Audit retention istekao ali nema seal/archive ili postoji legal hold. | Row disposition blokiran; read permission se ne širi. |
| M21-QA-120 | Audit retention je istekao, legal hold ne postoji, segment ima validan seal i politika zahteva potvrđen enkriptovan archive; prvi archive pokušaj padne posle temp upload-a, drugi uspe. | Prvi pokušaj nema evidence i `PENDING_EVIDENCE` object nestaje infrastrukturnim lifecycle-om ≤24h. Tek posle zasebnog immutable `AuditArchiveEvidence` reda sa ponovo izračunatim manifest/byte hash-em disposition uklanja/pseudonimizuje dozvoljene row podatke i dodaje disposition audit; seal ostaje byte-identičan i API više ne tvrdi da je row-level istorija dostupna. |
| M21-QA-121 | SCHOOL/PLATFORM AuditEvent i USER/SYSTEM/SUPPORT actor kombinacije. | DB prihvata samo tačan school/account/support conditional skup; hidden tenant nije otkriven. |
| M21-QA-122 | Prvi i naredni audit event hash link unutar mesečnog partition-a. | Samo sequence 1 ima null previous hash; `event_hash` pokriva ceo allow-listed red bez sopstvenog hash-a, a svaka sledeća `previous_hash` vrednost odgovara neposredno prethodnom događaju. |
| M21-QA-123 | Dva seal worker-a za isti partition. | Unique/CAS daje jedan immutable seal; drugi vraća isti dokaz ili 409, bez drugog potpisa. |
| M21-QA-124 | VERIFIED pa kasnija CORRUPT provera. | Dva append-only verification reda; latest health CORRUPT, originalni seal/verification nepromenjeni. |
| M21-QA-125 | Outbox PENDING/CLAIMED/PUBLISHED/DEAD_LETTERED/CANCELLED conditional polja i mutacija immutable envelope-a posle insert-a. | Lease/publish/error/cancel polja odgovaraju statusu; envelope/payload hash se reprodukuje pre publish-a, immutable field update je odbijen i plaintext token se ne čuva. |
| M21-QA-126 | Inbox PROCESSING/SUCCEEDED/FAILED conditional polja; broker envelope ima promenjen school/schema/payload uz isti message/hash. | Lease/processed/result/error matrica je DB-proverljiva; consumer ponovo računa ceo envelope hash i mismatch je incident bez business efekta. |
| M21-QA-127 | JobDefinition DRAFT/PUBLISHED/RETIRED i lease math. | Publish samo uz tačan katalog red, publish/retire par i heartbeat≤lease/3<runtime. |
| M21-QA-128 | JobExecution QUEUED/RUNNING/terminalna polja. | Attempt/start/finish/error kombinacija tačno odgovara statusu; CANCEL_REQUESTED ne prima novi attempt. |
| M21-QA-129 | JobAttempt sa raw lease tokenom ili kontradiktornim vremenima. | Schema/log scan odbija raw credential; DB odbija lifecycle kombinaciju. |
| M21-QA-130 | DeadLetter approval/replay/resolution conditional polja. | Nema REPLAYING bez approval generacije; failure i resolution dokazi nisu izmišljeni. |
| M21-QA-131 | Telemetry događaj sa raw ID/amount/search tekstom ili bez delete_after. | Schema odbija i broji privacy incident; business tok nije rollback-ovan. |
| M21-QA-132 | Backup STARTED/VERIFIED/FAILED/EXPIRED polja. | Samo VERIFIED `FULL_SERVICE` artifact je restore kandidat; manifest/hash/complete/expiry matrica prolazi DB CHECK. |
| M21-QA-133 | Restore PLANNED/RUNNING/VERIFIED/FAILED/DESTROYED polja, isti planner/approver i direktan production target. | Dva različita aktuelna aktera, approval time/reason i isolated target obavezni su pre rada; rezultati postoje samo posle izvršenja; DESTROYED čuva `pre_destroy_outcome`, pripadajući dokaz i vreme uništenja. |
| M21-QA-134 | ReleaseEvidence lifecycle polja, uključujući naknadno nevažeći dokaz posle VALIDATED a pre deploy-a. | VALIDATED→REJECTED je jedini post-validation reject i čuva validation par; validacija/deploy/rollback/supersede imaju tačne reference i vremena; ASSEMBLING ne glumi rezultat. |
| M21-QA-135 | M17 AVAILABLE export pređe TTL. | `privacy.export_expiry_cleanup` atomarno EXPIRED, objekti imaju deletion receipt, ticket/session ne vraćaju byte. |
| M21-QA-136 | Katalog se poredi sa tačnim allow-list skupom 40 v1 ključeva; nedostaje jedan od M02 delivery, M05 temporal, M13 delivery, M18 export-generate, M19 expiry ili M20 issue-report ključeva, odnosno pojavljuje se stari `people.relation_retention_review`, `structure.occupancy_claim_expiry`, `groups.enrollment_effective_transition`, `communication.scheduled_publish` ili `pwa.private_artifact_cleanup`. | Contract test pada na missing/unexpected ključu; prolaz zahteva tačno 40 jedinstvenih allow-list redova, bez aliasa i sa jednim redom po ključu/verziji. |
| M21-QA-137 | PLATFORM operational red nosi school_id, SCHOOL red nema school_id, ili AuditSegmentSeal/Verification/ArchiveEvidence koristi scope/school različit od parent događaja/seal-a. | DB CHECK i composite FK odbijaju pre seal/verification/archive commit-a; cross-tenant seal ID ne daje oracle niti zapis. |
| M21-QA-138 | Fuzz raw auth/lease/download/provider/replay credential kroz sve M21 tabele i događaje. | Nula prihvaćenih vrednosti i nula log/dead-letter curenja. |
| M21-QA-139 | Terminalni status bez required timestamp/reason/hash-a. | DB constraint odbija za outbox/inbox/job/dead-letter/backup/restore/release. |
| M21-QA-140 | `finance.event_cancellation_materialize` primi isti `EventCancelledV1` deset puta i worker padne posle srednje stranice. | Jedan logical `JobExecution`/inbox efekat; retry nastavlja od trajnog checkpoint-a, svaki assessment dobija deterministički `message_id:assessment_id` command i nema duplog storna, kredita ili druge novčane promene. |
| M21-QA-141 | Dva PLATFORM trigger-a istog job-a/semantic scope-a imaju null school. | Nenull `execution_scope_key=PLATFORM` i unique daju tačno jedan JobExecution; drugi dobija isti execution. |
| M21-QA-142 | SCHOOL execution nosi pogrešan izvedeni scope ključ ili PLATFORM nosi school_id. | DB CHECK odbija. |
| M21-QA-143 | Isti audit chain ima događaje u januaru, nema ih u februaru i ima ih u martu. | Januar i mart su odvojeni partition-i sa sequence od 1; martovski seal pokazuje na januarski seal kao prethodni neprazan segment istog stabilnog `audit_chain_key`. |
| M21-QA-144 | Dva producer stream-a koriste isti aggregate ID/version/event type; zatim isti stream pokuša dupli semantic sequence i vrednost 65536. | Različiti stream-ovi su dozvoljeni i izolovani; duplikat u istom stream-u je odbijen, a vrednost van UInt16 opsega ne ulazi u outbox. |
| M21-QA-145 | Isti inbox message ID stigne sa drugim `schema_version`, pa stigne nepoznata schema verzija pod novim ID-em. | Prvi slučaj je security incident bez efekta; drugi je deterministički unsupported-schema failure/dead-letter, bez tolerantnog parsiranja. |
| M21-QA-146 | Dead-letter recovery telo sadrži zabranjeno polje, ima pogrešan domain-separated canonical hash/encryption key ili mu istekne `payload_delete_after`. | Allow-list odbija zabranjeno; HashV1/key mismatch blokira replay i podiže incident; expiry briše byte uz receipt i svaki kasniji replay vraća `OPS_REPLAY_NOT_SAFE`. |
| M21-QA-147 | Svaka ReleaseCandidateEvidence statusna kombinacija, paralelni deploy i supersede ciklus. | DB prihvata samo tačnu lifecycle matricu; CAS daje jedan deploy ishod; self/cyclic supersede je odbijen i istorijski dokaz nije prepisan. |
| M21-QA-148 | DB-only ili tenant-only backup pokušava status VERIFIED. | Odbijeno; H0 restore kandidat mora biti `scope=FULL_SERVICE` sa DB+object+schema/config evidence celinom. |
| M21-QA-149 | M01 account ili M05 support grant se deaktivira posle već commitovanog audit/release reda. | Istorijski opaque actor ref ostaje; nema reverse FK cascade/update, ali svaki novi privileged write ponovo validira aktuelni port/version i failuje zatvoreno. |
| M21-QA-150 | Telemetry `delete_after` je null, lokalni datum bez zone ili vreme pre `recorded_at`. | Schema/DB odbija; prihvaća samo UTC `TIMESTAMPTZ` budući rok iz objavljene retention politike. |
| M21-QA-151 | Jedan globalni account pripada školama A/B; M01 PLATFORM invalidation stigne 10 puta i worker padne posle A. | Jedan logical platform JobExecution/inbox efekat; retry nastavlja idempotentno i invalidira A/B projekcije bez school/child PII u eventu. Stari authorization version je odbijen u obe škole i pre završetka fan-out-a. Kompletan acceptance zahteva 151/151 stvarno izvršenih testova, 0 failed/skipped/flaky i svih 40 job ugovora. |

Suite: transaction/outbox/inbox, producer-stream barrier, audit integrity/seal/retention, jobs/fencing/fairness, deadletter, telemetry/privacy, config/secrets, backup/restore/DR, migration/deploy/rollback, security scans, handover/pilot. QA 001–016, 101–105 i 144–145 pokriva outbox/inbox; 017–025, 115–124 i 143 audit; 037–048, 106–111, 140–142 i 151 jobs; 049–056, 112–114 i 146 replay; 057–100 ostale operativne/handover ugovore; 121–139 i 147–150 conditional schema/credential/backup/release/retention ugovore. Nema flaky/wall-clock/network zavisnosti bez kontrolisanog fake-a.
